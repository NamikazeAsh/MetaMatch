"""
What the conversation is about, so a follow up is read as a full question before the planner, the router and retrieval
see it. "how do i beat lando" then "what if it's the scarf set" becomes "how do i beat a scarf Landorus-Therian";
"what about Gholdengo?" puts Gholdengo where the last question's opponent was; "why?" goes back to the last result.

Deterministic on purpose. In the 2026 11 14 baseline only 1 of 14 follow ups was answered right: the planner and
retrieval never saw earlier turns, and the models, which did, replayed earlier mistakes and copied their fact blocks.
The rewritten question is shown to the user ("Reading this as ..."), so a wrong reading is visible, not silent.
"""
import re
from dataclasses import dataclass, field

from metamatch.engine.names import find_pokemon_spans

# Words a short follow up is made of besides the Pokemon it names: "and what about Gholdengo then?"
FILLER = set("""and ok okay so but what about how vs versus against instead then too now same for with the a an if is it its
it's that this one ones mon guy thing their they them his her him opposing enemy opp my also or please hmm well say
suppose assume assuming on for in at""".split())
# Openers of a "same question, different details" follow up: "what if it's Scarf", "and with Specs?"
VARIANT_RE = re.compile(r"^\s*(?:(?:and|ok|okay|so|but|now)\s+)*(?:what if|what about|how about|if|with|assume|assuming|"
                        r"suppose|say|and if|but if|even if|without|no)\b", re.I)
# Words that make a short message a question of its own, not a follow up
ASKS_RE = re.compile(r"\b(?:outspeed\w*|faster|slower|ohko\w*|2hko\w*|ko|kos|survive\w*|damage|beat\w*|counter\w*|"
                     r"check\w*|resist\w*|weak\w*|immune|lead\w*|win\w*|replace\w*|teammates?|best|good|common|"
                     r"usage|play\w*|handle\w*|threat\w*)\b", re.I)
OWN_QUESTION_RE = re.compile(ASKS_RE.pattern + r"|\b(?:stat|stats|item|ability|moves?|tera|evs?|spread)\b", re.I)
WHY_RE = re.compile(r"^\s*(?:why|how come|how so|why is that|why not|why though|explain|explain (?:that|it|why)|"
                    r"can you explain|elaborate|really|are you sure|how)\W*$", re.I)
# Longest first, so "it's" is one pronoun and not "it" plus a stray "'s"
PRONOUN_RE = re.compile(r"\b(it['’]s|its|it|they['’]re|they|them|their|him|her|that thing|that mon|that one)\b", re.I)
# "is it worth", "it depends": an "it" that refers to nothing
EXPLETIVE_RE = re.compile(r"\bit(?:'s| is| was)?\s+(?:worth|possible|better|best|a good idea|okay|ok|fine|true|depends|"
                          r"likely|common|standard)\b|\bmake it\b", re.I)
REPLACE_RE = re.compile(r"\b(?:replace\w*|swap\w*|cut|drop)\b", re.I)
# Field conditions belong at the end of the question, not glued to a Pokemon
FIELD_RE = re.compile(r"\b(?:rain\w*|sun\w*|sand\w*|snow\w*|hail|trick room|tailwind|terrain|reflect|light screen|screens?|"
                      r"veil|stealth rock|rocks|spikes|burn\w*|paraly\w*|poison\w*|crit\w*|hp)\b", re.I)
DETAIL_FILLER_RE = re.compile(r"\b(?:what if|what about|how about|and if|but if|even if|if|and|but|so|now|ok|okay|with|"
                              r"assume|assuming|suppose|say|it'?s|it is|it has|it runs|it holds|they'?re|they have|"
                              r"they run|has|have|holds?|holding|runs?|running|is|on|the|a|an|set|one|instead|then|"
                              r"too|version|variant|uses?|using|clicks?|goes for|terastalli[sz]es)\b", re.I)
# Set up and boosts belong to whoever runs the move, so they go at the end of the question, not glued to a Pokemon
SETUP_RE = re.compile(r"\b(?:after|following)\b|[+]\d|\b(?:swords dance|nasty plot|dragon dance|calm mind|quiver dance|"
                      r"bulk up|shell smash|belly drum|tidy up|victory dance|shift gear|coil|growth|iron defense|"
                      r"agility|rock polish|curse|sd|dd|np|cm|qd)\b", re.I)
# "why not booster energy?": the share of that option on the Pokemon the conversation is about
WHY_NOT_RE = re.compile(r"^\s*(?:but |and |so )?(?:why not|what about|how about) (.+?)(?: instead| then)?\W*$", re.I)


@dataclass
class DialogueState:
    query: str = ""                               # the last question, as resolved
    opponents: list = field(default_factory=list)  # Pokemon off the team it was about (canonical names)
    member: str | None = None                     # the team member it named
    intent: str = ""
    verdict: object = None                        # the engine result shown for it, if any
    clarify: bool = False                         # the last answer asked which Pokemon was meant
    recent_openers: list = field(default_factory=list)  # the persona openers already used, newest last
    recent_moods: list = field(default_factory=list)


@dataclass
class Reading:
    text: str                 # the question to answer
    kind: str = "new"         # new, swap, variant, pronoun, why, clarify, replace
    why_of: object = None     # for "why?": the earlier verdict to explain again


def _member_names(team):
    names = set()
    for p in (team or {}).values():
        names |= {p.get("Pokemon"), p.get("Forme")} - {None}
    return names


def _spans(text):
    return [(a, b, name) for a, b, name in find_pokemon_spans(text)]


def _words_left(text, spans):
    for a, b, _ in sorted(spans, reverse=True):
        text = text[:a] + " " + text[b:]
    return [w for w in re.findall(r"[a-z0-9+'%]+", text.lower()) if w not in FILLER]


def _put(prev, spans, side_names, new):
    """`prev` with the first mention of a name in `side_names` replaced by `new`, or None if there is none."""
    for a, b, name in spans:
        if name in side_names:
            return prev[:a] + new + prev[b:]
    return None


def _detail(text, spans):
    """The set details a variant follow up states: 'what if it's the scarf set' -> 'scarf'."""
    for a, b, _ in sorted(spans, reverse=True):
        text = text[:a] + " " + text[b:]
    text = PRONOUN_RE.sub(" ", text)
    text = DETAIL_FILLER_RE.sub(" ", text)
    text = re.sub(r"\bteras?\s+(\w+)", r"Tera \1", text, flags=re.I)
    # Move names would split the details from the Pokemon they describe ("Tera Normal Extreme Speed Dragonite" reads
    # the Tera as nobody's); its likely set already carries its usual moves
    from metamatch.engine import rules
    moves = [n for kind, n in rules.find_named(text) if kind == "move"]
    if len(moves) < len(rules.find_named(text)) or re.search(r"\bTera \w+", text):
        for move in moves:
            text = re.sub(re.escape(move), " ", text, flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"[?!.]", " ", text)).strip()


def _insert_before(prev, spans, target, detail):
    """'Does my Dragapult outspeed Iron Valiant?' + 'Choice Scarf' for Iron Valiant -> '... outspeed Choice Scarf Iron Valiant?'"""
    for a, _, name in spans:
        if name == target:
            return prev[:a] + detail + " " + prev[a:]
    return None


def _moves_of(name, team):
    for p in (team or {}).values():
        if name in (p.get("Pokemon"), p.get("Forme")):
            return {m["name"].lower() for m in p.get("Moves", [])}
    return set()


SETUP_PHRASE_RE = re.compile(r"\s*\b(?:after|following)\s+(?:a\s+|an\s+|one\s+|two\s+)?(?P<move>swords dance|nasty plot|dragon dance|"
                             r"calm mind|quiver dance|bulk up|shell smash|belly drum|tidy up|victory dance|shift gear|"
                             r"coil|growth|iron defense|agility|rock polish|curse)s?\b|\s*(?:at\s+)?[+]\d\b", re.I)


def _drop_setup_it_lacks(text, moves):
    """'can my Corviknight ohko Great Tusk after swords dance' -> without the Swords Dance Corviknight doesn't run:
    a boost stated for the last member doesn't carry over to a member swapped in."""
    def keep(m):
        move = (m.group("move") or "").lower()
        return m.group(0) if move and move in moves else ""
    return SETUP_PHRASE_RE.sub(keep, text)


def resolve(query, state, team):
    """How to read `query` given the conversation so far: a Reading with the full question."""
    if not state or not state.query:
        return Reading(query)
    members = _member_names(team)
    spans = _spans(query)
    named = [n for _, _, n in spans]
    prev = state.query
    prev_spans = _spans(prev)
    words = query.split()

    # "why?" right after an answer: explain that answer again
    if WHY_RE.match(query):
        if state.verdict is not None:
            return Reading(f"Why? {prev}", "why", why_of=state.verdict)
        return Reading(f"{prev} Explain why.", "why")

    # A reply to "which Pokemon do you mean?"
    if state.clarify and named and len(words) <= 6:
        filled = PRONOUN_RE.sub(named[0], prev, count=1) if PRONOUN_RE.search(prev) else f"{prev.rstrip('?. ')} against {named[0]}?"
        return Reading(filled, "clarify")

    # "why not booster energy?": how often that option shows up on the Pokemon the conversation is about
    why_not = WHY_NOT_RE.match(query)
    if why_not and not named and not SETUP_RE.search(query):
        from metamatch.engine import rules
        # "why not X" can be any option; "what about X" only an item, since "what about Knock Off" is usually a calc
        kinds = ("item", "move", "ability") if query.lower().lstrip().startswith(("why", "but why", "and why", "so why")) else ("item",)
        option = [n for kind, n in rules.find_named(why_not.group(1)) if kind in kinds]
        target = state.member or (state.opponents[0] if state.opponents else None)
        if option and target:
            return Reading(f"Is {option[0]} common on {target}?", "variant")

    # "what about Gholdengo?": the last question with this Pokemon swapped in on the same side
    if named and len(words) <= 8 and not _words_left(query, spans) and not OWN_QUESTION_RE.search(query):
        new = named[0]
        prev_members = [n for _, _, n in prev_spans if n in members and n not in state.opponents]
        if new in members and prev_members:
            swapped = _put(prev, prev_spans, set(prev_members), new)
            if swapped:
                swapped = _drop_setup_it_lacks(swapped, _moves_of(new, team))
        else:
            swapped = _put(prev, prev_spans, set(state.opponents), ("opposing " if new in members else "") + new)
        if swapped:
            return Reading(swapped, "swap")

    # "what if it's the scarf set", "and with Specs?": the last question with the stated details added
    if VARIANT_RE.match(query) and len(words) <= 12 and not ASKS_RE.search(query):
        detail = _detail(query, spans)
        if detail:
            if (FIELD_RE.search(detail) or SETUP_RE.search(detail)) and not named:
                # "after a swords dance" stays a phrase of its own: the planner credits it to whoever runs the move
                tail = query.strip().rstrip("?.!") if SETUP_RE.search(detail) else detail
                tail = re.sub(r"^\s*(?:(?:and|ok|okay|so|but|now)\s+)*(?:what if|what about|how about|and if|but if|if)\s+",
                              "", tail, flags=re.I)
                return Reading(f"{prev.rstrip('?. ')} {tail}?", "variant")
            target = named[0] if named else (state.opponents[0] if state.opponents else state.member)
            if target:
                text = prev
                if named and target not in [n for _, _, n in prev_spans]:
                    side = set(state.opponents) if target not in members else {state.member}
                    text = _put(prev, prev_spans, side, target) or prev
                rebuilt = _insert_before(text, _spans(text), target, detail)
                if rebuilt:
                    return Reading(rebuilt, "variant")

    # "does it outspeed my Gholdengo?": the pronoun is the last opponent (or the member, when only one was named)
    off_team = [n for n in named if n not in members]
    if not off_team and PRONOUN_RE.search(query) and not EXPLETIVE_RE.search(query):
        who = state.opponents[0] if state.opponents else (f"my {state.member}" if state.member and not named else None)
        if who:
            def sub(m):
                word = m.group(1).lower()
                if word in ("its", "their"):
                    return f"{who}'s"
                return f"{who} is" if word in ("it's", "it’s", "they're", "they’re") else who
            return Reading(PRONOUN_RE.sub(sub, query, count=1), "pronoun")

    # "ok what should I replace then": the member the conversation was about
    if REPLACE_RE.search(query) and not named and state.member:
        return Reading(f"{query.rstrip('?. ')} (my {state.member})?", "replace")
    return Reading(query)


def update(state, reading, plan, verdict=None, clarified=False):
    """The state after answering `reading` with `plan` (and `verdict`, when the engine answered)."""
    state = state or DialogueState()
    if reading.kind == "why":
        return state
    state.query = reading.text
    state.intent = plan.intent if plan else ""
    state.clarify = clarified
    state.verdict = verdict
    if plan and plan.opponents:
        state.opponents = list(plan.opponents)
    if plan and plan.user is not None and plan.user_named:
        state.member = plan.user.get("Pokemon")
    return state
