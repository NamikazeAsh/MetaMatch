"""
Oak voices a retrieved passage without restating it: the strategy questions no engine function answers get the
closest Smogon analysis, concept note or guide passage (rag/store via coach.references), framed by one line in Oak's
voice and followed by the passage's own sentences that best answer the question, quoted as written with the source.

Why not let the model retell the passage: measured on the blind questions (bench/rag/retell.py, 2026 11 26), the 3B
model's free retellings moved claims onto the wrong Pokemon or drifted off the question in about 1 in 3 answers even
behind name, number and pairing checks ("Hippowdon removes items with Knock Off" from a passage where Tornadus-T
does). The model writes only the framing line, which may name nothing but the Pokemon the passage is about, so it
can't misstate the advice; the advice itself is always Smogon's (or the concept note's) own words.
"""
import re
from functools import lru_cache

from metamatch.engine.names import find_pokemon
from metamatch.rag.chunking import body

STOP = set("the a an of to in on is do does i my how what for with and or vs it be should can are as good best set "
           "use run its this that which when why who you your me".split())
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower().replace("-", "")) if w not in STOP and len(w) > 2}


def best_sentences(query, passage, k=3):
    """The k sentences of `passage` that share the most words with the question, in the passage's own order (the
    first sentences when none do). Quoted as written, so whatever they say is the source's claim, not ours."""
    sentences = [s.strip() for s in SENTENCE.split(passage.strip()) if s.strip()]
    if len(sentences) <= k:
        return sentences
    asked = _words(query)
    scored = [(len(asked & _words(s)), -i, i) for i, s in enumerate(sentences)]
    if not any(score for score, _, _ in scored):
        return sentences[:k]
    keep = sorted(i for _, _, i in sorted(scored, reverse=True)[:k])
    return [sentences[i] for i in keep]


def _subject(meta):
    who = meta.get("pokemon") or ""
    return None if who in ("Concept", "Guide", "") else who


def template(meta, recent=()):
    """Oak's framing line without the model: by what the passage is, never what it says."""
    who, section = _subject(meta), meta.get("section") or ""
    if meta.get("source") == "smogon_analysis" and who:
        if section.startswith("Set "):
            options = (f"Ah, {who}! Here's how players run its {section[4:]} set:",
                       f"For {who}, here's what the {section[4:]} set is about:")
        elif section == "Overview":
            options = (f"Here's the big picture on {who}:", f"Ah, {who}! Here's what it brings to a team:")
        else:
            options = (f"A few other options people weigh up for {who}:",)
    elif meta.get("type") == "concept":
        title = meta.get("title") or section
        options = (f"Good question. Here's the gist of {title.lower()}:", f"Let me explain {title.lower()}:")
    elif meta.get("source") == "smogon_guide":
        options = ("There's a fine old guide on just this. In short:", "An older guide put it well:")
    elif meta.get("source") == "smogon_stats":
        options = (f"Here's what the ladder shows for {who}:",) if who else ("Here's what the ladder shows:",)
    else:
        options = ("Here's how it has been explained before:",)
    return next((o for o in options if o not in (recent or ())), options[0])


@lru_cache(maxsize=1)
def _names_pattern():
    """One regex for every move, item and ability name in Showdown's data, longest first. Case sensitive, so
    "protect your partner" isn't read as the move."""
    from metamatch.engine import rules
    table = rules.table()
    names = sorted({n for key in ("moves", "items", "abilities") for n in (table.get(key) or {}) if len(n) > 3},
                   key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b")


def check_frame(line, meta):
    """Why a model written framing line can't be used, or None: one short sentence that names no Pokemon but the
    passage's own, no numbers, no moves, items or abilities (the facts come from the quote, never from the frame)."""
    if not line or len(line.split()) > 16 or len(SENTENCE.split(line.strip())) > 2:
        return "not one short line"
    if re.search(r"\d", line):
        return "a number"
    who = (_subject(meta) or "").lower()
    others = [n for n in find_pokemon(line) if n.lower() != who and n.split("-")[0].lower() != who.split("-")[0]]
    if others:
        return f"another Pokemon ({', '.join(others)})"
    named = _names_pattern().search(line)
    if named and named.group(1).lower() != who:
        return f"a move, item or ability ({named.group(1)})"
    return None


FRAME_SYSTEM = """You are Professor Oak, a warm Pokemon researcher. A trainer asked the QUESTION; you are about to read
them a short passage on SUBJECT. Reply with ONE sentence of at most 12 words that names SUBJECT and ends with a colon,
like "Ah, Kingambit! Here's how the experts run it:" or "Good question! Here's how hazards work:".
Never state a fact, move, item, number or any other Pokemon."""


def frame(query, meta, recent=(), model=None, use_model=None):
    """(Oak's line before the quote, who wrote it). A template line by default: on the blind questions (2026 11 26)
    the local models' own lines passed check_frame but still slipped in wrong claims ("Raging Bolt is a powerful
    move", Llama's "Landorus-Therian's role in the ecosystem"), while the templates are always right and read as
    warmly. METAMATCH_FRAME=model (or use_model=True) lets the model write it, still behind check_frame."""
    import os
    from metamatch.agents.client import chat, ollama_available
    if use_model is None:
        use_model = os.getenv("METAMATCH_FRAME") == "model"
    if use_model and ollama_available():
        subject = _subject(meta) or meta.get("title") or meta.get("section") or "this"
        try:
            line = chat([{"role": "system", "content": FRAME_SYSTEM},
                         {"role": "user", "content": f"QUESTION: {query}\nSUBJECT: {subject}"}],
                        temperature=0.6, max_tokens=40, model=model).strip().strip('"')
        except Exception:   # the model went away: the template line
            line = ""
        if line and not check_frame(line, meta):
            return (line if line.endswith(":") else line.rstrip(".!") + ":"), "model"
    return template(meta, recent), "template"


def quoted(query, hit, k=3):
    """The passage sentences that answer the question, as one quote."""
    return " ".join(best_sentences(query, body(hit["text"]), k))
