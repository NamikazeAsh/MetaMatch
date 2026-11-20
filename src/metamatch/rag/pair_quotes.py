"""
What Smogon's analyses say about two Pokemon facing each other, quoted verbatim under the engine's one on one verdict.

The engine gives the answer ("your Corviknight loses to Kingambit one on one"); this only finds the best sentence in
the format's own Smogon analyses that is about that pair, and says whose analysis it is from. It never asserts which
way the sentence points: in the RAG 2.0 test (docs/research/rag_2_0_checks_test.md) a rule based reading of "who checks
whom" was wrong 26% of the time, while 82% of these sentences were about the two Pokemon facing each other. When the
text and the calc disagree, the player sees both side by side.

No vector search: sentences are indexed by the Pokemon pair they name (the analysis's own Pokemon counts as named,
since "it" means it), so this runs on the web version too, from the analyses rag/cards.py fetches on first use.
"""
import re
from functools import lru_cache

from metamatch.rag.cards import FORMAT_SOURCE, SOURCES, _load, _text

# A sentence about a matchup: checking, walling, threatening, knocking out, switching in, struggling against
MATCHUP = re.compile(r"\b(?:check\w*|counter\w*|wall(?!break)\w*|handl\w*|switch(?:es|ing)? (?:in|into)|tak(?:e|es|ing) on|"
                     r"stand(?:s|ing)? up to|fares? well|threat\w*|O?HKO\w*|2HKO\w*|KO\w*|beat\w*|struggl\w*|trouble|"
                     r"answer\w*|revenge kill\w*|outsp\w+|stop\w*|blank\w*|immun\w*|resist\w*|vulnerable|weak to)\b",
                     re.I)
# Strong words lift a sentence above one that only mentions a resistance or a KO in passing
STRONG = re.compile(r"\b(?:check\w*|counter\w*|wall(?!break)\w*|handl\w*|switch(?:es|ing)? into|tak(?:e|es|ing) on|"
                    r"struggl\w*|answer\w*|beat\w*|trouble|vulnerable|weak to)\b", re.I)
NEAR = 90   # characters before a Pokemon's name a matchup word may sit and still be about it
# Teammate talk and Speed benchmarks name two Pokemon without being about them facing each other
NOT_A_MATCHUP = re.compile(r"\b(?:teammates?|partners?|pairs? (?:well |nicely )?with|pair [\w-]+ with|appreciat\w*|"
                           r"in return|helps?|accompan\w+|alongside|best friend|utility for|on (?:more )?\w+ teams|"
                           r"\d+ Speed EVs?|Speed EVs|nature)\b", re.I)


# How Smogon writes formes: "Landorus-T", "Ogerpon-W", "Hisuian Samurott", "Bloodmoon Ursaluna"
SUFFIX = {"Therian": "T", "Wellspring": "W", "Cornerstone": "C", "Hearthflame": "H", "Speed": "S", "Attack": "A",
          "Defense": "D", "Incarnate": "I"}
REGION = {"Galar": "Galarian", "Hisui": "Hisuian", "Alola": "Alolan", "Paldea": "Paldean"}
# "them" and "they" in a sentence that doesn't name the analysis's Pokemon usually mean its teammates or foes
OTHERS = re.compile(r"\b(?:they|them|their)\b", re.I)


@lru_cache(maxsize=4)
def _names(key):
    """(pattern, alias -> name) for every Pokemon in the dex and the source's analyses, Smogon's shorthands included.
    One exact pattern is about a hundred times faster than fuzzy name matching over thousands of sentences."""
    from metamatch.engine.dex import get_dex
    names = set(_load(key) or {})
    for game in ("sv", "champions"):
        dex = get_dex(game)
        if dex:
            names |= set(dex.species_data)
    alias = {}
    for n in names:
        alias[n] = n
        if "-" in n:
            base, form = n.split("-", 1)
            if form in SUFFIX:
                alias[f"{base}-{SUFFIX[form]}"] = n
            if form in REGION:
                alias[f"{REGION[form]} {base}"] = n
            if form == "Bloodmoon":
                alias[f"Bloodmoon {base}"] = n
    ordered = sorted(alias, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(a) for a in ordered) + r")(?![\w-])"), alias


def _sentences(html):
    text = _text(html)
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s]


def _parts(entry):
    """(label, html) for the parts of one analysis: its overview, each set, and its other options."""
    if entry.get("overview"):
        yield "overview", entry["overview"]
    for name, s in (entry.get("sets") or {}).items():
        if s.get("description"):
            yield f"{name} set", s["description"]
    if entry.get("comments"):
        yield "other options", entry["comments"]


IT = re.compile(r"\b(?:it|its|itself)\b", re.I)
CLAUSE_BREAK = re.compile(r"[;:]|, (?:while|but|whereas|and|which)\b| while | whereas ")


def _about_pair(s, subject, other, mentions):
    """True when a matchup word in `s` ties `other` to the analysis's own Pokemon, not to a third one.
    mentions: [(start, name)] for every Pokemon named, plus (start, subject) for each "it" / "its".
    Either the subject acts on the other ("it checks Kingambit", "Corviknight walls Kingambit" in Corviknight's
    analysis), or the other acts on the subject ("Kingambit threatens it"). "Corviknight checks Kingambit" in
    Dragapult's analysis names a third Pokemon as the one acting, so it isn't about Dragapult and Kingambit."""
    def doer_before(pos):
        """The last Pokemon named (or "it") before pos, within its clause."""
        start = max(0, pos - NEAR)
        brk = [m.end() for m in CLAUSE_BREAK.finditer(s, start, pos)]
        start = brk[-1] if brk else start
        before = [name for at, name in mentions if start <= at < pos]
        return before[-1] if before else None

    for at, name in mentions:
        if name != other:
            continue
        # The other as the target: the matchup word before it, and who does it
        words = [m for m in MATCHUP.finditer(s, max(0, at - NEAR), at)]
        if words:
            doer = doer_before(words[-1].start())
            if doer in (None, subject):
                return True
        # The other as the one acting: a matchup word just after it, aimed at the subject
        after = MATCHUP.search(s, at, min(len(s), at + 60))
        if after:
            aimed = [n for a, n in mentions if after.end() <= a < after.end() + 60]
            if aimed and aimed[0] == subject:
                return True
    return False


@lru_cache(maxsize=8)
def _index(key):
    """{frozenset({a, b}): [(score, analysis Pokemon, part label, sentence)]} for one source's analyses."""
    pattern, alias = _names(key)
    index = {}
    for subject, entry in (_load(key) or {}).items():
        for part, html in _parts(entry):
            for s in _sentences(html):
                if not MATCHUP.search(s) or NOT_A_MATCHUP.search(s):
                    continue
                named = {alias[m] for m in pattern.findall(s)}
                said = subject in named
                # The analysis's own Pokemon is the sentence's "it"; with "they" or "them" and no name, it may not be
                if not said and OTHERS.search(s):
                    continue
                named.add(subject)
                if len(named) < 2:
                    continue
                base = (0.5 if said else 0.0) - len(s) / 2000
                mentions = sorted([(m.start(), alias[m.group(1)]) for m in pattern.finditer(s)] +
                                  [(m.start(), subject) for m in IT.finditer(s)])
                for other in named - {subject}:
                    # The matchup word has to tie this Pokemon to the analysis's own, not to a third one
                    if not _about_pair(s, subject, other, mentions):
                        continue
                    windows = [s[max(0, at - NEAR):at + 30] for at, n in mentions if n == other]
                    score = base + (1.0 if any(STRONG.search(w) for w in windows) else 0.0)
                    index.setdefault(frozenset((subject, other)), []).append((score, subject, part, s))
                # Two other Pokemon named together ("Great Tusk and Kingambit both...") are not a pair the
                # sentence is about, so only pairs with the analysis's own Pokemon are kept
    for quotes in index.values():
        quotes.sort(key=lambda q: -q[0])
    return index


def quote(a, b, format_id, prefer=None):
    """(heading, sentence) for the best sentence about `a` and `b` in the format's own analyses, or None.
    prefer: whose analysis to favour when both have one (the player's own Pokemon)."""
    key = FORMAT_SOURCE.get(format_id)
    if not key or key not in SOURCES:
        return None
    quotes = _index(key).get(frozenset((a, b)))
    if not quotes:
        return None
    best = max(quotes, key=lambda q: q[0] + (0.5 if prefer and q[1] == prefer else 0.0))
    _, subject, part, sentence = best
    game, tier, _ = SOURCES[key]
    return f"Smogon on {a} and {b}, from {subject}'s {game} {tier} analysis ({part})", sentence


def quotes_for(members, other, format_id, limit=3):
    """Card tuples (heading, sentence, note) for up to `limit` of the members against `other`, in order."""
    out = []
    for m in members:
        q = quote(m, other, format_id, prefer=m)
        if q:
            out.append((q[0], q[1], ""))
        if len(out) == limit:
            break
    return out
