"""
The chat's voice, on top of the answer packet (engine/packet.py).

The engine's answer sentence is shown as written. The model writes two labelled lines in one call:
  OPENER: a short line in the persona's voice that makes no claim at all (the only place personality lives)
  WHY:    one plain sentence explaining the answer from the facts the engine picked
Each line is checked on its own and replaced on its own when it fails: a stock opener from the persona's bank, and the
first picked fact's own text for the why. So an answer is never worse than the engine's, and with Ollama offline the
same packet renders without the model.

Plain labelled lines, not JSON: small models follow "OPENER: ... / WHY: ..." reliably, and strict format decoding has
been measured to cost small models accuracy.
"""
import re

from . import claims
from .client import chat, ollama_available
from metamatch.engine.names import find_pokemon

PERSONAS = {
    "strategy": {
        "name": "Professor Oak",
        "voice": "Professor Oak, a warm, experienced Pokemon researcher who loves the big picture",
        "moods": ["curious", "nostalgic", "encouraging", "thoughtful", "delighted", "reflective"],
        "bank": ["Ah, good question.", "Now this takes me back.", "Let's look at the big picture.",
                 "An excellent thing to wonder about!", "Ah, a question I hear often.",
                 "Ah, I've studied this for years.", "Let's think this through together.", "A fine question, my friend.",
                 "Research has the answer here.", "Splendid, let's dig in.", "This one is worth a closer look.",
                 "Ah, now we're getting somewhere."],
    },
    "mechanics": {
        "name": "Clemont",
        "voice": "Clemont, an upbeat young inventor who loves explaining exactly how things work",
        "moods": ["excited", "precise", "inventive", "proud", "eager", "focused"],
        "bank": ["Science has the answer!", "The future is now, thanks to science!", "Let me run the numbers!",
                 "Ooh, a perfect question for my calculations!", "Time to check the data!", "My gadgets are ready!",
                 "This one comes down to the math!", "Let's measure it properly!", "Calculations complete!",
                 "Oh, I love this kind of question!", "Precision is everything here!", "Allow me to explain!"],
    },
    "builder": {
        "name": "Brock",
        "voice": "Brock, a calm, friendly breeder who knows what ladder players really run",
        "moods": ["calm", "friendly", "practical", "steady", "warm", "confident"],
        "bank": ["Let's see what the ladder says.", "Good thing to check before battling.", "Here's what I've seen.",
                 "Solid question, let's take a look.", "Details matter when building.", "Let me check my notes.",
                 "Good builders ask exactly this.", "Alright, let's figure it out.",
                 "That's a smart thing to ask.", "Let's keep it practical.", "I've raised plenty of these, so here goes.",
                 "Okay, here's the deal."],
    },
}

MAX_OPENER_WORDS = 12
PROBLEM_WORDS = re.compile(r"\b(?:problem\w*|challeng\w*|trick(?:y|ier)|troubl\w*|dilemma|predicament|pickle|tough|"
                           r"difficult\w*|situation|conundrum|uh oh|oh no)\b", re.I)
# At least this share of the why sentence's content words must come from the facts it explains
MIN_CLOSENESS = 0.7
# Battle words and judgements: an opener mentioning them is making a claim, not setting a tone
BATTLE_WORDS = re.compile(r"\b(?:use|uses|using|switch\w*|lead\w*|beat\w*|win\w*|lose\w*|losing|weak\w*|resist\w*|immun\w*|"
                          r"fast\w*|slow\w*|speed|ko\w*|knock\w*|hits?|damage|tera\w*|items?|moves?|sets?|teams?|threats?|"
                          r"checks|counters?|answers|safe|rain|sun|sand|snow|hazards?|rocks|spikes|outspeed\w*|"
                          r"survive\w*|super|effective|stab|boost\w*|sweep\w*|wall\w*)\b", re.I)
JUDGEMENT = re.compile(r"\b(?:great news|good news|bad news|unfortunately|luckily|sadly|thankfully|easy|easily|tough|"
                       r"trouble|danger\w*|perfect\w* (?:answer|counter)|best|worst)\b", re.I)
META = re.compile(r"\b(?:engine|facts?|result|data says|according to)\b", re.I)
FLOURISH = re.compile(r"\b(?:incredible|amazing|perfect|flawless|unstoppable|crushes|obliterates|demolish\w*|"
                      r"with ease|effortlessly|my dear trainer|young trainer)\b", re.I)
NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _norm(text):
    return (text or "").lower().replace("é", "e")


def _stem(word):
    return word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word


def _words(text):
    return {_stem(w) for w in re.findall(r"[a-z']+", _norm(text))}


def repair_why(text, cited, team_names=()):
    """Fixes the model's harmless slips before checking: a leading fact label ('F1: ...'), and a team species written
    without its owner word when the facts only ever call it 'your X' or 'the opposing X'."""
    text = re.sub(r"^\s*F\d+\s*[:.)-]\s*", "", (text or "").strip())
    source = " ".join(f.text for f in cited).lower()
    for name in team_names:
        mine, theirs = f"your {name}".lower() in source, f"opposing {name}".lower() in source
        if mine == theirs:
            continue
        owner = "your " if mine else "the opposing "
        # Case blind, so a sentence opening "Your Kingambit" doesn't become "Your your Kingambit"
        text = re.sub(rf"(?<!your )(?<!opposing )\b{re.escape(name)}\b", owner + name, text, flags=re.I)
    return text[:1].upper() + text[1:] if text else text


def check_opener(text, recent=()):
    """Why the opener can't be shown, or None. It may set a tone and nothing else."""
    from .grounded import _claims_something
    text = (text or "").strip()
    if not text:
        return "empty"
    if len(text.split()) > MAX_OPENER_WORDS or len(re.findall(r"[.!?]", text)) > 2:
        return "too long"
    if _claims_something(text) or BATTLE_WORDS.search(text) or JUDGEMENT.search(text) or META.search(text):
        return "makes a claim"
    # "That's quite a challenge!" over "Your team runs no weather" frames every question as trouble
    if PROBLEM_WORDS.search(text):
        return "calls it a problem"
    w = _words(text)
    for prev in recent or ():
        p = _words(prev)
        if w and p and len(w & p) / len(w | p) >= 0.6:
            return "repeats a recent opener"
    return None


def _numbers(text):
    return {n.rstrip("0").rstrip(".") if "." in n else n for n in NUMBER.findall(text or "")}


def check_why(text, cited, packet, verdict=None, team_names=()):
    """Why the why sentence can't be shown, or None. It may only use what the cited facts say: their numbers, their
    Pokemon (with the same owner words when a species is on both sides), their moves, items and abilities, and no
    speed, knockout, type or who beats whom claim that disagrees with the engine's verdict."""
    from metamatch.engine import rules
    text = (text or "").strip()
    if not text:
        return "empty"
    if len(re.findall(r"[.!?](?:\s|$)", text)) > 1 or len(text.split()) > 40:
        return "more than one sentence"
    # The answer sentence is shown right before the why, so what it names may be named again
    source = " ".join(f.text for f in cited) + " " + (packet.answer if packet else "")
    low_source = _norm(source)
    unknown = _numbers(text) - _numbers(source) - {"1"}
    if unknown:
        return f"numbers not in the facts: {', '.join(sorted(unknown))}"
    invented = [n for n in find_pokemon(text) if n.lower() not in low_source]
    if invented:
        return f"Pokemon not in the facts: {', '.join(invented)}"
    named = [n for kind, n in rules.find_named(text) if kind in ("move", "item", "ability") and n.lower() not in low_source]
    if named:
        return f"moves, items or abilities not in the facts: {', '.join(named)}"
    # A species on both sides (a mirror) needs its owner word every time
    for name in team_names:
        if f"your {name}".lower() in low_source and f"opposing {name}".lower() in low_source:
            for m in re.finditer(rf"\b{re.escape(name)}\b", text, re.I):
                if not re.search(r"(?:your|opposing)\s+$", text[max(0, m.start() - 12):m.start()], re.I):
                    return f"{name} without 'your' or 'opposing'"
    if FLOURISH.search(text) or META.search(text):
        return "flourish or talk about the engine"
    if re.search(r"\bF\d+\b", text):
        return "a fact label instead of the fact"
    if _closeness(text, cited) < MIN_CLOSENESS:
        return "says things the facts don't"
    if verdict is not None:
        from .grounded import CLAIM_CHECKS
        check = CLAIM_CHECKS.get(verdict.intent)
        clash = check(text, verdict) if check else None
        if clash:
            return clash
    return None


def _pick_mood(persona, recent_moods):
    moods = PERSONAS[persona]["moods"]
    fresh = [m for m in moods if m not in (recent_moods or ())]
    return (fresh or moods)[0]


def stock_opener(persona, recent=()):
    """The least recently used opener from the persona's bank."""
    bank = PERSONAS.get(persona, PERSONAS["strategy"])["bank"]
    for line in bank:
        if line not in (recent or ()) and check_opener(line, recent) is None:
            return line
    return bank[0]


def _prompt(packet, persona, mood):
    who = PERSONAS[persona]["voice"]
    why_facts = [packet.fact(fid) for fid in packet.why]
    system = (
        f"You are {who}. You are talking with a trainer about their Pokemon team.\n"
        "A battle engine has already answered their question, and the answer is shown to them exactly as written.\n"
        "Reply with exactly these two lines and nothing else:\n"
        "OPENER: <a short reaction in your own voice>\n"
        "WHY: <one sentence>\n\n"
        f"OPENER is {MAX_OPENER_WORDS} words at most, in a {mood} mood. It is only a greeting or reaction: no Pokemon, "
        "type, move, item, ability, number, result or advice.\n"
        "WHY restates one of the WHY FACTS in simpler words. Keep every Pokemon with its 'your' or 'the opposing', and "
        "every number, exactly as written. Do not add reasons, stats or anything the fact does not say."
    )
    user = (f"QUESTION: {packet.question}\n"
            f"ANSWER (already shown, do not repeat it): {packet.answer}\n"
            "WHY FACTS:\n" + "\n".join(f"{f.id}. {f.text}" for f in why_facts))
    return system, user, why_facts


LINE = re.compile(r"^\s*\**\s*(OPENER|WHY)\s*\**\s*:\s*(.+?)\s*$", re.I | re.M)


def parse(reply):
    """{'opener': ..., 'why': ...} from the model's labelled lines. A 3B model often drops the labels and writes the
    two lines bare, so two unlabelled lines are read in order."""
    out = {}
    for label, text in LINE.findall(reply or ""):
        out.setdefault(label.lower(), text.strip().strip('"'))
    if not out:
        lines = [l.strip().strip('"') for l in (reply or "").splitlines() if l.strip()]
        if len(lines) >= 2:
            out = {"opener": lines[0], "why": lines[1]}
        elif len(lines) == 1:
            out = {"why": lines[0]}
    return out


STOP = set("""a an the of to in on at for and or but is are was were be been it its it's this that these those with by from
as your opposing their them they so which who what when than then into out up down over can will would could should
has have had does do did not no yes one two three four hit hits deal deals dealt damage take takes taking much
just also only very because since team pokemon""".split())


def _closeness(text, cited):
    """Share of the why sentence's content words that appear in the cited facts: a restatement scores high, an
    invented reason ('because it has a higher base speed', 'impressive stats') scores low."""
    source = _words(" ".join(f.text for f in cited))
    words = [_stem(w) for w in re.findall(r"[a-z']+", _norm(text)) if w not in STOP and len(w) > 2]
    return sum(w in source for w in words) / len(words) if words else 1.0


MAX_PICKS = 3
FACTS_LINE = re.compile(r"^\s*\**\s*FACTS?\s*\**\s*:\s*(.+?)\s*$", re.I | re.M)


def pick(packet, recent_openers=(), recent_moods=()):
    """(opener, fact ids, report) for an open question: the model only chooses which numbered facts answer it best
    (and writes the opener); the app shows the chosen facts word for word. Falls back to the packet's first facts."""
    persona = packet.persona if packet.persona in PERSONAS else "strategy"
    mood = _pick_mood(persona, recent_moods)
    default = (packet.why or [f.id for f in packet.facts])[:2]
    report = {"opener": "stock", "facts": "default", "mood": mood}
    if not packet.facts or not ollama_available():
        return stock_opener(persona, recent_openers), default, report
    system = (
        f"You are {PERSONAS[persona]['voice']}. A trainer asked a question about their Pokemon team, and a battle "
        "engine computed the numbered facts below.\n"
        "Reply with exactly these two lines and nothing else:\n"
        "OPENER: <a short reaction in your own voice>\n"
        f"FACTS: <the numbers of the 1 to {MAX_PICKS} facts that answer the question best, most useful first>\n\n"
        f"OPENER is {MAX_OPENER_WORDS} words at most, in a {mood} mood: only a greeting or reaction, with no Pokemon, "
        "type, move, item, ability, number, result or advice."
    )
    numbered = {str(i + 1): f for i, f in enumerate(packet.facts)}
    user = f"QUESTION: {packet.question}\nFACTS:\n" + "\n".join(f"{n}. {f.text}" for n, f in numbered.items())
    try:
        reply = chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                     temperature=0.3, max_tokens=60)
    except Exception as e:
        print(f"Picker failed: {e}")
        return stock_opener(persona, recent_openers), default, report
    got = parse(reply)
    line = (FACTS_LINE.search(reply or "") or None)
    numbers = re.findall(r"\d+", line.group(1) if line else (reply or "").splitlines()[-1] if reply else "")
    ids = list(dict.fromkeys(numbered[n].id for n in numbers if n in numbered))[:MAX_PICKS]
    if ids:
        report["facts"] = "model"
    else:
        ids = default
    opener = got.get("opener", "")
    if check_opener(opener, recent_openers) is None:
        report["opener"] = "model"
    else:
        opener = stock_opener(persona, recent_openers)
    return opener, ids, report


def speak(packet, verdict=None, team_names=(), recent_openers=(), recent_moods=()):
    """(opener, why, report): the checked opener and why sentence for a packet, each falling back on its own.
    report says which slots came from the model, for tracing."""
    persona = packet.persona if packet.persona in PERSONAS else "strategy"
    mood = _pick_mood(persona, recent_moods)
    system, user, cited = _prompt(packet, persona, mood)
    fallback_why = cited[0].text if cited else ""
    report = {"opener": "stock", "why": "fact", "mood": mood}
    if not ollama_available() or not cited:
        return stock_opener(persona, recent_openers), fallback_why, report
    try:
        got = parse(chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                         temperature=0.3, max_tokens=90))
    except Exception as e:  # model call failed: the packet still renders on its own
        print(f"Voice failed: {e}")
        return stock_opener(persona, recent_openers), fallback_why, report
    opener, why = got.get("opener", ""), got.get("why", "")
    if check_opener(opener, recent_openers) is None:
        report["opener"] = "model"
    else:
        report["opener_rejected"] = check_opener(opener, recent_openers)
        opener = stock_opener(persona, recent_openers)
    why = repair_why(why, cited, team_names)
    reason = check_why(why, cited, packet, verdict, team_names)
    # A why that only says the answer again adds nothing: show a fact instead
    if reason is None and _closeness(why, [type("A", (), {"text": packet.answer})()]) >= 0.9:
        reason = "repeats the answer"
    if reason is None:
        report["why"] = "model"
    else:
        report["why_rejected"] = reason
        why = fallback_why
    return opener, why, report
