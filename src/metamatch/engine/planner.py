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
from metamatch.logic_engine import find_pokemon_in_query

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


@dataclass
class Plan:
    intent: str = "open"            # speed, ko, damage, type, stat, usage, clarify, open
    format_id: str = config.DEFAULT_FORMAT
    user: dict | None = None        # team member entry from readTeam
    user_named: bool = False        # False when `user` is just the only member of a one Pokemon team
    opponents: list = field(default_factory=list)   # Pokemon names not on the team
    move: str | None = None
    attacker: str = "user"          # who uses `move`: "user" or "opponent"
    ko_hits: int = 1                # 1 for OHKO, 2 for 2HKO...
    survive: bool = False           # "can X survive ..." flips the yes/no
    atk_type: str | None = None
    stat: str | None = None
    usage_field: str | None = None  # item, ability, move, tera, spread
    opp_overrides: dict = field(default_factory=dict)  # explicit set details from the question

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
        if target in ids or (base and base in ids):
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


def _parse_set(query, dex):
    """Explicit opponent set details: '@ Item', a nature, an ability and '252 HP / 4 Def' style spreads."""
    overrides = {}
    item = re.search(r"@\s*([A-Za-z][\w' .-]*?)\s*(?:,|\?|$)", query)
    if item and dex and dex.item_name(item.group(1)):
        overrides["item"] = dex.item_name(item.group(1))
    for nature in NATURES:
        if re.search(rf"\b{nature}\b", query):
            overrides["nature"] = nature
            break
    evs = re.findall(r"(\d+)\s*(HP|Atk|Def|SpA|SpD|Spe)\b", query)
    if evs:
        overrides["evs"] = {EV_LABELS[s.lower()]: int(v) for v, s in evs}
    if dex and overrides:
        for name in dex.ability_names:
            if len(name) > 3 and re.search(rf"\b{re.escape(name)}\b", query):
                overrides["ability"] = name
                break
    return overrides


def _usage_field(query):
    q = query.lower()
    for word, fld in (("tera", "tera"), ("ability", "ability"), ("item", "item"), ("spread", "spread"),
                      ("nature", "spread"), ("move", "move"), ("set", "item")):
        if word in q:
            return fld
    return "item"


def plan_query(query, team):
    """Builds a Plan for a chat question about `team` (readTeam output)."""
    team = team or {}
    format_id = config.team_format(team)
    dex = dex_for_format(format_id)
    plan = Plan(format_id=format_id)

    names = find_pokemon_in_query(query)
    for name in names:
        member = _team_member(name, team, dex)
        if member is not None:
            plan.user = plan.user or member
            plan.user_named = True
        elif name not in plan.opponents:
            plan.opponents.append(name)
    if plan.user is None and len(team) == 1:
        plan.user = next(iter(team.values()))

    # Text with Pokemon names removed, for move, type and keyword scans
    scrubbed = query
    for name in names:
        scrubbed = _blank(scrubbed, name)

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

    plan.opp_overrides = _parse_set(query, dex) if plan.opponent else {}
    if dex:
        for ability in dex.ability_names:
            if len(ability) > 3:
                scrubbed = _blank(scrubbed, ability)

    # Who attacks: possessive "X's Move" wins, then "survive", then whose moveset has the move
    if plan.move:
        lowered = query.lower()
        opp_poss = plan.opponent and f"{plan.opponent.lower()}'s {plan.move.lower()}" in lowered
        if opp_poss or (re.search(r"\bsurvive", lowered) and plan.move not in user_moves):
            plan.attacker = "opponent"
        elif plan.move not in user_moves and plan.move in opp_moves:
            plan.attacker = "opponent"

    # Usage goes last: speed and KO questions also say "most common spread"
    q = query
    if STAT_RE.search(q) and plan.user and not SPEED_RE.search(q):
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
    elif (SPEED_RE.search(q) or KO_RE.search(q) or DAMAGE_RE.search(q)) and not plan.opponents:
        # A matchup question with no recognisable opponent: ask, never answer a different question
        plan.intent = "clarify"
    elif USAGE_RE.search(q) and (plan.opponent or plan.user):
        plan.intent = "usage"
        plan.usage_field = _usage_field(q)
    return plan
