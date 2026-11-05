"""
Deterministic query planner: works out what a chat question is asking (intent) and about
what (team member, opponent, move, type, stat, explicit opponent set), so questions the
engine can answer never depend on the LLM reading facts correctly.
"""
import re
from dataclasses import dataclass, field

from metamatch import config
from metamatch.engine.dex import dex_for_format, to_id
from metamatch.engine.sets import likely_set
from metamatch.engine.names import find_pokemon, find_pokemon_spans

TYPES = ["Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground",
         "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"]
NATURES = ["Hardy", "Lonely", "Brave", "Adamant", "Naughty", "Bold", "Docile", "Relaxed", "Impish", "Lax",
           "Timid", "Hasty", "Serious", "Jolly", "Naive", "Modest", "Mild", "Quiet", "Bashful", "Rash",
           "Calm", "Gentle", "Sassy", "Careful", "Quirky"]
STAT_WORDS = {"hp": "hp", "attack": "atk", "atk": "atk", "defense": "def", "def": "def",
              "special attack": "spa", "spa": "spa", "special defense": "spd", "spd": "spd",
              "speed": "spe", "spe": "spe"}
EV_LABELS = {"hp": "hp", "atk": "atk", "def": "def", "spa": "spa", "spd": "spd", "spe": "spe"}

USAGE_RE = re.compile(r"\b(most common|most used|usage|popular|standard (?:set|item|spread)|what (?:item|ability|tera|nature|spread)|which (?:item|ability|tera))\b", re.I)
KO_RE = re.compile(r"\b(ohko|2hko|3hko|ohkos|2hkos|one ?shot|survive|survives|kill|kills|ko|kos)\b", re.I)
DAMAGE_RE = re.compile(r"(\bdamage\b|\bpercent(?:age)?\b|%|\bhow much\b)", re.I)
SPEED_RE = re.compile(r"\b(outspeed|outspeeds|faster|slower|speed tie|out speed|outpace)\b", re.I)
TYPE_ASK_RE = re.compile(r"\b(immune|immunity|weak|weakness|resist|resists|resistant|neutral|super effective|not very effective)\b", re.I)
STAT_RE = re.compile(r"\bstat\b", re.I)
# "how much Speed does my X have", "what Speed does my X hit": a stat question when no opponent is named
STAT_ASK_RE = re.compile(r"\b(how much|what)\s+(speed|attack|defense|special attack|special defense|hp)\b", re.I)


@dataclass
class Plan:
    intent: str = "open"            # speed, ko, damage, type, stat, usage, clarify, open
    format_id: str = config.DEFAULT_FORMAT
    user: dict | None = None        # team member entry from readTeam
    user_named: bool = False        # False when `user` is just the only member of a one Pokemon team
    opponents: list = field(default_factory=list)   # Pokemon names not on the team
    move: str | None = None
    attacker: str = "user"          # who uses `move`: "user" or "opponent"
    subject: str = "user"           # whose side the question is asked from: "user" or "opponent"
    speed_ask: str = "faster"       # "slower" when the question asks if the subject is slower
    ko_hits: int = 1                # 1 for OHKO, 2 for 2HKO...
    survive: bool = False           # "can X survive ..." flips the yes/no
    atk_type: str | None = None
    stat: str | None = None
    usage_field: str | None = None  # item, ability, move, tera, spread
    opp_overrides: dict = field(default_factory=dict)  # explicit set details from the question
    raw_stats: bool = False         # "ignore items/abilities": compare bare stats, no Scarf or field

    @property
    def opponent(self):
        return self.opponents[0] if self.opponents else None


def _team_member(name, team, dex):
    """The team entry a query name refers to, matching base species or Mega forme."""
    target = to_id(name)
    species = dex.species(name) if dex else None
    base = to_id(species.get("baseSpecies", "")) if species else ""
    for p in team.values():
        ids = {to_id(p.get("Pokemon")), to_id(p.get("Forme"))}
        # A bare base name ("Ogerpon") also means a team member of that species ("Ogerpon-Wellspring")
        member = dex.species(p.get("Pokemon")) if dex else None
        member_base = to_id(member.get("baseSpecies", "")) if member else ""
        if target in ids or (base and base in ids) or (member_base and target == member_base):
            return p
    return None


def _blank(text, phrase):
    """Blank out a matched phrase (case insensitive) so later scans don't see it."""
    return re.sub(re.escape(phrase), " " * len(phrase), text, flags=re.I)


def _find_move(query, candidates, dex):
    """Longest move named in the query: known movesets match in any case, other dex moves only in Title Case."""
    lowered = query.lower()
    hits = [m for m in candidates if m and m.lower() in lowered]
    if not hits and dex:
        hits = [m for m in dex.move_data if len(m) > 3 and re.search(rf"(?<![\w]){re.escape(m)}(?![\w])", query)]
    # "Psychic type attacks" names a type, not the move Psychic
    hits = [m for m in hits if not re.search(rf"\b{re.escape(m)}[\s-]*type", query, re.I)]
    return max(hits, key=len) if hits else None


def _find_type(text):
    """Attack type named in the question, preferring 'X type' / 'X attacks' phrasing."""
    for t in TYPES:
        if re.search(rf"\b{t}[\s-]*(type|attacks?|moves?)\b", text, re.I):
            return t
    for t in TYPES:
        if re.search(rf"\b{t}\b", text, re.I):
            return t
    return None


def _find_stat(query):
    lowered = query.lower()
    for word in sorted(STAT_WORDS, key=len, reverse=True):
        if re.search(rf"\b{word}\b", lowered):
            return STAT_WORDS[word]
    return None


# Text allowed between a set detail and the Pokemon it describes: "my Jolly 252 Atk Great Tusk"
GLUE_RE = re.compile(r"^[\s/+,()]*(?:(?:my|your|the|a|an)\s+)?[\s/+,()]*$", re.I)


def _owner(spans, start, end, style, text):
    """'user' when a set detail is glued to a team member's mention, else 'opponent' (old behaviour)."""
    if style == "prefix":
        nxt = next((s for s in spans if s[0] >= end), None)
        if nxt and nxt[3] == "user" and GLUE_RE.match(text[end:nxt[0]]):
            return "user"
    else:
        prev = next((s for s in reversed(spans) if s[1] <= start), None)
        if prev and prev[3] == "user" and GLUE_RE.match(text[prev[1]:start]):
            return "user"
    return "opponent"


def _parse_set(query, dex, spans=()):
    """Explicit opponent set details: '@ Item', a nature, an ability and '252 HP / 4 Def' style spreads.
    `spans` are (start, end, name, side) mentions; details glued to a team member's mention are skipped."""
    hits = []  # (start, end, key, value, style)
    for m in re.finditer(r"@\s*((?:[A-Za-z][\w'.-]*\s*){1,4})", query):
        words = m.group(1).split()
        for k in range(len(words), 0, -1):
            if dex and dex.item_name(" ".join(words[:k])):
                hits.append((m.start(), m.end(), "item", dex.item_name(" ".join(words[:k])), "suffix"))
                break
    for nature in NATURES:
        for m in re.finditer(rf"\b{nature}\b", query):
            hits.append((m.start(), m.end(), "nature", nature, "prefix"))
    for m in re.finditer(r"(\d+)\s*(HP|Atk|Def|SpA|SpD|Spe)\b", query):
        hits.append((m.start(), m.end(), "evs", (EV_LABELS[m.group(2).lower()], int(m.group(1))), "prefix"))
    if dex:
        for name in dex.ability_names:
            if len(name) > 3:
                for m in re.finditer(rf"\b{re.escape(name)}\b", query):
                    hits.append((m.start(), m.end(), "ability", name, "prefix"))
    # Blank every detail so a run of them ("Jolly 252 Atk") still counts as glued to the name
    text = query
    for a, b, *_ in hits:
        text = text[:a] + " " * (b - a) + text[b:]
    overrides = {}
    for a, b, key, value, style in sorted(hits, key=lambda h: h[0]):
        if _owner(spans, a, b, style, text) != "opponent":
            continue
        if key == "evs":
            overrides.setdefault("evs", {})[value[0]] = value[1]
        elif key == "ability":
            overrides.setdefault("_ability", value)
        else:
            overrides.setdefault(key, value)
    ability = overrides.pop("_ability", None)
    if ability and overrides:
        overrides["ability"] = ability
    return overrides


def _usage_field(query):
    """Which usage field is asked for; whole words only, so 'Terapagos' is not 'tera'."""
    for pattern, fld in ((r"tera", "tera"), (r"abilit(?:y|ies)", "ability"), (r"items?", "item"),
                         (r"spreads?", "spread"), (r"natures?", "spread"), (r"move(?:s|set)?", "move"), (r"sets?", "item")):
        if re.search(rf"\b{pattern}\b", query, re.I):
            return fld
    return "item"


PRONOUN_RE = re.compile(r"\b(i|we|it|you|he|she|they)\b", re.I)
TARGET_RE = re.compile(r"\b(to|against|into|on|vs)\b", re.I)


def _subject(query, spans):
    """Side of the question's grammatical subject: the last mention before the question verb
    ("outspeed", "OHKO", "survive", or "to" in damage questions) in the same sentence. A lead in
    sentence ("Raging Bolt is on its usual set, does my Skarmory outspeed it?") is skipped."""
    anchor = SPEED_RE.search(query) or KO_RE.search(query) or TARGET_RE.search(query)
    if not anchor:
        return "user"
    begin = max(query.rfind(c, 0, anchor.start()) for c in ".?!;") + 1
    before = [(b, side) for a, b, _, side in spans if begin <= a < anchor.start()]
    if not before:
        return "user"
    # "my Skarmory vs a Raging Bolt, do I outspeed it?": a pronoun after the last name is the real subject
    if PRONOUN_RE.search(query[before[-1][0]:anchor.start()]):
        return "user"
    return before[-1][1]


def _possessor(query, move, plan):
    """'user' or 'opponent' when the move is written as 'X's Move' (X may be a nickname), else None."""
    m = re.search(rf"['’]s\s+{re.escape(move)}", query, re.I)
    if not m:
        return None
    owners = find_pokemon(query[:m.start()])
    if not owners:
        return None
    if owners[-1] in plan.opponents:
        return "opponent"
    return "user" if plan.user is not None else None


def plan_query(query, team):
    """Builds a Plan for a chat question about `team` (readTeam output)."""
    team = team or {}
    format_id = config.team_format(team)
    dex = dex_for_format(format_id)
    plan = Plan(format_id=format_id)

    raw_spans = find_pokemon_spans(query)
    names = list(dict.fromkeys(d for _, _, d in raw_spans))
    for name in names:
        member = _team_member(name, team, dex)
        if member is not None:
            plan.user = plan.user or member
            plan.user_named = True
        elif name not in plan.opponents:
            plan.opponents.append(name)
    if plan.user is None and len(team) == 1:
        plan.user = next(iter(team.values()))
    spans = [(a, b, d, "opponent" if d in plan.opponents else "user") for a, b, d in raw_spans]
    plan.subject = _subject(query, spans)

    # Text with Pokemon names removed, for move, type and keyword scans
    scrubbed = query
    for name in names:
        scrubbed = _blank(scrubbed, name)
    # Nicknames too ("gambit"), which the canonical name blanking above misses
    for a, b, _ in raw_spans:
        scrubbed = scrubbed[:a] + " " * (b - a) + scrubbed[b:]
    names_only = scrubbed

    members = [plan.user] if plan.user else list(team.values())
    user_moves = [m["name"] for p in members for m in p.get("Moves", [])]
    opp_set = likely_set(plan.opponent, format_id) if plan.opponent else None
    opp_moves = [m for m, _ in opp_set["moves"]] if opp_set else []
    plan.move = _find_move(scrubbed, user_moves + opp_moves, dex)
    if plan.move:
        scrubbed = _blank(scrubbed, plan.move)
        # "How much does Knock Off do to X?" is about whichever team member runs Knock Off
        if plan.user is None:
            plan.user = next((p for p in members if plan.move in [m["name"] for m in p.get("Moves", [])]), None)
            plan.user_named = plan.user is not None
            user_moves = [m["name"] for m in (plan.user or {}).get("Moves", [])]

    plan.opp_overrides = _parse_set(query, dex, spans) if plan.opponent else {}
    if dex:
        for ability in dex.ability_names:
            if len(ability) > 3:
                scrubbed = _blank(scrubbed, ability)

    # Who attacks: possessive "X's Move" wins, then a move only one side runs, then grammar:
    # the subject attacks, unless it is the one trying to survive
    survive = bool(re.search(r"\bsurvive", query, re.I))
    other = "opponent" if plan.subject == "user" else "user"
    possessor = _possessor(query, plan.move, plan) if plan.move else None
    if possessor:
        plan.attacker = possessor
    elif plan.move and plan.move in user_moves and plan.move not in opp_moves:
        plan.attacker = "user"
    elif plan.move and plan.move in opp_moves and plan.move not in user_moves:
        plan.attacker = "opponent"
    else:
        plan.attacker = other if survive else plan.subject
    if re.search(r"\b(slower|outsped)\b", query, re.I):
        plan.speed_ask = "slower"

    # Usage goes last: speed and KO questions also say "most common spread"
    q = query
    if plan.user and not SPEED_RE.search(q) and (STAT_RE.search(q) or (STAT_ASK_RE.search(q) and not plan.opponents)):
        plan.intent = "stat"
        plan.stat = _find_stat(scrubbed) or "spe"
    elif KO_RE.search(q) and plan.opponent and (plan.user or plan.move):
        plan.intent = "ko"
        hits = re.search(r"\b(o|\d)hko", q, re.I)
        plan.ko_hits = 1 if not hits or hits.group(1).lower() == "o" else int(hits.group(1))
        plan.survive = bool(re.search(r"\bsurvive", q, re.I))
    elif TYPE_ASK_RE.search(q) and _find_type(scrubbed) and (plan.user or plan.opponent):
        plan.intent = "type"
        plan.atk_type = _find_type(scrubbed)
    elif DAMAGE_RE.search(q) and plan.opponent and (plan.user or plan.move):
        plan.intent = "damage"
    elif SPEED_RE.search(q) and plan.opponent and plan.user:
        plan.intent = "speed"
        plan.raw_stats = bool(re.search(r"\b(ignor\w*|without|no)\b[^.?]*\b(items?|scarf)\b", q, re.I))
    elif (SPEED_RE.search(q) or KO_RE.search(q) or DAMAGE_RE.search(q)) and not plan.opponents:
        # A matchup question with no recognisable opponent: ask, never answer a different question
        plan.intent = "clarify"
    elif USAGE_RE.search(q) and (plan.opponent or plan.user):
        plan.intent = "usage"
        plan.usage_field = _usage_field(names_only)
    return plan
