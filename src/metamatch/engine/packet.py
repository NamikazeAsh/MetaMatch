"""
The answer packet: one shape for everything the chat model reads.

The engine writes the answer sentence and a list of facts. Each fact is one plain claim in which every Pokemon is
"your X" or "the opposing X", numbers carry their unit ("% of its HP", "Speed", "% of sets"), and engine jargon (OHKO,
EV lines, calc descriptions) is kept apart in `detail` for the Engine facts dropdown. The model never sees the jargon
and never has to work out whose Pokemon a name is. Design and evidence: docs/research/chat_packet_design_2026_11_15.md.
"""
import re
from dataclasses import dataclass, field

MAX_FACT_WORDS = 32
JARGON = re.compile(r"\b(?:OHKO|\dHKO|HKO|BP|SpA|SpD|Atk|Def|Spe|STAB|calc)\b|\d+\+")
PRONOUN_FOR_MON = re.compile(r"^(?:it|its|they|their)\b|\b(?:it|its|they|them|their)\s+(?:beats|loses|outspeeds|is|does|takes|knocks)\b",
                             re.I)


@dataclass
class Fact:
    kind: str                   # speed, damage, ko, matchup, type, usage, rule, set, role, engine, stated, score, concept
    text: str                   # one plain claim, owner word on every Pokemon, no jargon
    data: dict = field(default_factory=dict)   # machine fields, with units
    role: str = "context"       # answer, why, context
    detail: str = ""            # exact engine wording, shown only in the dropdown
    id: str = ""                # F1, F2... assigned by the packet


@dataclass
class Packet:
    question: str
    intent: str
    category: str = ""
    persona: str = ""
    answer: str = ""            # the engine's answer sentence(s); empty when the question is open
    facts: list = field(default_factory=list)
    why: list = field(default_factory=list)      # ids of facts the model may explain (at most two)
    caveats: list = field(default_factory=list)  # what the answer does not count
    cards: list = field(default_factory=list)    # (label, text) shown to the user verbatim, never to the model
    link: str = ""                               # dashboard tab the answer comes from

    def add(self, fact, why=False):
        fact.id = f"F{len(self.facts) + 1}"
        self.facts.append(fact)
        if why and len(self.why) < 2:
            self.why.append(fact.id)
        return fact

    def fact(self, fid):
        return next((f for f in self.facts if f.id == fid), None)


# Plain language helpers ----------------------------------------------------------------------------------------

def mon(name, mine):
    """'your Gholdengo' or 'the opposing Gholdengo'."""
    return f"your {name}" if mine else f"the opposing {name}"


def cap(text):
    return text[:1].upper() + text[1:] if text else text


def pct(lo, hi):
    """'95 to 114%' (whole numbers; the dropdown keeps the decimals)."""
    lo, hi = round(lo), round(hi)
    return f"{lo}%" if lo == hi else f"{lo} to {hi}%"


def hits(worst, best=None):
    """'in one hit', 'in 2 hits', 'in 2 or 3 hits', or None when it can't knock out."""
    if not worst:
        return None
    best = best or worst
    if best == worst:
        return "in one hit" if worst == 1 else f"in {worst} hits"
    if best == 1:
        return f"in one hit on a high roll, {worst} at worst" if worst > 2 else "in one or two hits"
    return f"in {best} or {worst} hits" if worst - best == 1 else f"in {best} to {worst} hits"


STAT_WORDS = {"hp": "HP", "atk": "Attack", "def": "Defense", "spa": "Special Attack", "spd": "Special Defense",
              "spe": "Speed"}


def spread_words(nature, evs, unit="EVs"):
    """('Timid', {'spa': 252, 'spe': 252, 'spd': 4}) -> 'Timid nature with 252 Special Attack, 252 Speed and 4 Special
    Defense EVs', with no stat shorthand."""
    parts = [f"{v} {STAT_WORDS[k]}" for k, v in sorted((evs or {}).items(), key=lambda kv: -kv[1]) if v]
    return f"{nature} nature with {join(parts)} {unit}" if parts else f"{nature} nature with no investment"


def share(x):
    """0.4 -> '40%' (shares of sets or teams)."""
    return f"{round(x * 100)}%"


def join(items):
    items = list(items)
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


HKO_WORDS = {"O": "knock out in one hit", "2": "knock out in two hits", "3": "knock out in three hits",
             "4": "knock out in four hits"}


def plainify(text):
    """Engine shorthand in plain words: '2HKO 6 of the 12' -> 'knock out in two hits 6 of the 12', 'Pokémon' -> 'Pokemon',
    'goes from 1.5x to 2x STAB' -> 'gets a stronger same type bonus (2 times instead of 1.5)'."""
    text = re.sub(r"\b(O|\d)HKOs?\b", lambda m: HKO_WORDS.get(m.group(1), f"knock out in {m.group(1)} hits"), text)
    text = re.sub(r"\b(goes|go) from 1\.5x to 2x STAB\b", lambda m: ("gets" if m.group(1) == "goes" else "get")
                  + " a stronger same type bonus (2 times instead of 1.5)", text)
    text = re.sub(r"\b(gains|gain) STAB\b", lambda m: m.group(1) + " the same type bonus (1.5 times)", text)
    text = re.sub(r"\bSTAB\b", "same type bonus", text)
    return text.replace("Pokémon", "Pokemon")


def first_sentences(text, max_words=MAX_FACT_WORDS):
    """The leading sentences of a long text that fit in `max_words` (at least the first one)."""
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        if out and len(" ".join(out + [sentence]).split()) > max_words:
            break
        out.append(sentence)
    return " ".join(out)


# Checks ------------------------------------------------------------------------------------------------------------

def lint(fact, team_names=()):
    """Problems with a fact's text: jargon, too long, a bare team species with no owner word, a pronoun standing for
    a Pokemon. Empty when the fact is fit for the model."""
    problems = []
    text = fact.text
    if JARGON.search(text):
        problems.append(f"jargon: {JARGON.search(text).group(0)}")
    if len(text.split()) > MAX_FACT_WORDS:
        problems.append(f"{len(text.split())} words")
    # Rule text is Showdown's own wording ("This Pokemon..."), and usage facts are about the species on the ladder,
    # where a team species named without "your" is the ladder's, not the trainer's
    if fact.kind in ("rule", "usage"):
        return problems
    if PRONOUN_FOR_MON.search(text):
        problems.append("pronoun for a Pokemon")
    for name in team_names:
        for m in re.finditer(rf"\b{re.escape(name)}\b", text):
            before = text[max(0, m.start() - 14):m.start()].lower()
            if not re.search(r"(?:your|opposing|ladder)\s+$", before):
                problems.append(f"no owner word before {name}")
                break
    return problems
