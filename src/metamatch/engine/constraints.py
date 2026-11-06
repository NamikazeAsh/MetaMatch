"""
Constraints a question states, so the solvers answer the question that was asked instead of
the ladder's most common set: per side set details (nature, EVs, item or explicitly no item,
ability, Tera, moves, boosts) and the field (screens, weather, terrain).

Every value is checked against a closed vocabulary (dex names, natures, types), so nothing
the question doesn't say can appear. Each detail is credited to a Pokemon mention: a run of
details glued to the next mention ("a Timid Specs Iron Bundle") belongs to it, anything else
to the closest mention before it ("Tornadus-Therian runs Timid with 252 Spe"), and details
before any mention to the opponent. `consumed` lists the character spans used, so the
planner's move and type scans skip them ("moves: Knock Off, Ice Shard" names no asked move).
"""
import re
from dataclasses import dataclass, field

TYPES = ["Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground",
         "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy", "Stellar"]
NATURES = ["Hardy", "Lonely", "Brave", "Adamant", "Naughty", "Bold", "Docile", "Relaxed", "Impish", "Lax",
           "Timid", "Hasty", "Serious", "Jolly", "Naive", "Modest", "Mild", "Quiet", "Bashful", "Rash",
           "Calm", "Gentle", "Sassy", "Careful", "Quirky"]
STATS = ("hp", "atk", "def", "spa", "spd", "spe")
STAT_ALIASES = {"hp": "hp", "atk": "atk", "attack": "atk", "def": "def", "defense": "def", "defence": "def",
                "spa": "spa", "special attack": "spa", "spatk": "spa", "spd": "spd", "special defense": "spd",
                "spdef": "spd", "spe": "spe", "speed": "spe"}
STAT_WORD = r"(special attack|special defen[cs]e|attack|defen[cs]e|speed|spatk|spdef|hp|atk|def|spa|spd|spe)"
# Natures raising (or lowering) a stat, physical then special flavour
PLUS_NATURES = {"spe": ("Jolly", "Timid"), "atk": ("Adamant", "Adamant"), "spa": ("Modest", "Modest"),
                "def": ("Impish", "Bold"), "spd": ("Careful", "Calm"), "hp": ("Serious", "Serious")}
MINUS_NATURES = {"spe": ("Brave", "Quiet")}
# Natures that are not everyday English, so lowercase "jolly" still counts
CASUAL_NATURES = {"Jolly", "Timid", "Adamant", "Modest", "Impish", "Sassy", "Naughty", "Docile", "Bashful", "Quirky"}
# Casual item names players type ("specs", "boots"); full dex names are matched separately
ITEM_ALIASES = {
    "specs": "Choice Specs", "scarf": "Choice Scarf", "band": "Choice Band", "scarfed": "Choice Scarf",
    "banded": "Choice Band", "boots": "Heavy-Duty Boots", "hdb": "Heavy-Duty Boots", "lefties": "Leftovers",
    "lefty": "Leftovers", "booster": "Booster Energy", "sash": "Focus Sash", "lorb": "Life Orb",
    "helmet": "Rocky Helmet", "vest": "Assault Vest", "eviolite": "Eviolite", "belt": "Expert Belt",
    "leftovers": "Leftovers", "life orb": "Life Orb",
}
SETUP_MOVES = {"Swords Dance": {"atk": 2}, "Nasty Plot": {"spa": 2}, "Dragon Dance": {"atk": 1, "spe": 1},
               "Calm Mind": {"spa": 1, "spd": 1}, "Quiver Dance": {"spa": 1, "spd": 1, "spe": 1},
               "Bulk Up": {"atk": 1, "def": 1}, "Shell Smash": {"atk": 2, "spa": 2, "spe": 2},
               "Agility": {"spe": 2}, "Iron Defense": {"def": 2}, "Belly Drum": {"atk": 6},
               "Tidy Up": {"atk": 1, "spe": 1}, "Victory Dance": {"atk": 1, "def": 1, "spe": 1}}
WEATHER = {"rain": "Rain", "sun": "Sun", "sunlight": "Sun", "sand": "Sand", "sandstorm": "Sand",
           "snow": "Snow", "hail": "Snow"}
SCREENS = {"reflect": "isReflect", "light screen": "isLightScreen", "aurora veil": "isAuroraVeil"}

GLUE_RE = re.compile(r"^[\s/+,()]*(?:(?:my|your|the|a|an|their|opposing|enemy)\s+)?[\s/+,()]*$", re.I)
NO_RE = r"(?:no|without|not holding|minus)\s+(?:an?\s+|any\s+|its\s+|the\s+)?"
# "Ignore items", "no items or abilities": bare stats for both sides
RAW_RE = re.compile(r"\b(?:ignor\w*|without|disregard\w*)\s+(?:all\s+|any\s+|held\s+)?(?:items?|abilities)\b|"
                    r"\bno\s+(?:held\s+)?items\b", re.I)


@dataclass
class Constraints:
    user: dict = field(default_factory=dict)       # set details for the player's Pokemon
    opponent: dict = field(default_factory=dict)   # set details for the opponent
    conditions: dict = field(default_factory=dict)  # calc Field: weather, terrain
    screens: dict = field(default_factory=dict)    # "user" | "opponent" | "defender" -> set of calc Side flags
    raw_stats: bool = False                        # compare bare stats: no items or abilities
    strongest: bool = False                        # "uses its strongest (listed) move"
    consumed: list = field(default_factory=list)   # (start, end) spans the constraints came from


def _item_patterns(dex):
    """(compiled regex, item) for full item names: multiword in any case, one word names only in Title Case."""
    out = []
    for name in (dex.item_data if dex else ()):
        if len(name) < 5 or (name.endswith(" Ball") and name not in ("Iron Ball", "Light Ball")):
            continue
        flags = re.I if " " in name or "-" in name else 0
        out.append((re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])", flags), name))
    return out


_ITEM_CACHE = {}


def _items(dex):
    key = id(dex)
    if key not in _ITEM_CACHE:
        _ITEM_CACHE[key] = _item_patterns(dex)
    return _ITEM_CACHE[key]


def _hits(query, dex):
    """Every detail in the query: (start, end, key, value, style). 'prefix' details can glue to the next mention."""
    hits = []
    for m in re.finditer(r"@\s*((?:[A-Za-z][\w'.-]*\s*){1,4})", query):
        words = list(re.finditer(r"[A-Za-z][\w'.-]*", m.group(1)))
        for k in range(len(words), 0, -1):
            name = dex.item_name(" ".join(w.group() for w in words[:k])) if dex else None
            if name:
                hits.append((m.start(), m.start(1) + words[k - 1].end(), "item", name, "suffix"))
                break
    taken = [(a, b) for a, b, *_ in hits]

    def free(a, b):
        return not any(a < y and x < b for x, y in taken)

    def add(a, b, key, value, style="prefix"):
        if free(a, b):
            hits.append((a, b, key, value, style))
            taken.append((a, b))

    # Negations first, so "no Choice Scarf" never reads as holding one
    for m in re.finditer(rf"\b{NO_RE}speed\s+(?:items?|boosting\s+items?)\b", query, re.I):
        add(m.start(), m.end(), "no_speed_item", True, "suffix")
    for m in re.finditer(rf"\b{NO_RE}(?:held\s+)?item\b|\bitemless\b", query, re.I):
        add(m.start(), m.end(), "item", "", "suffix")
    for m in re.finditer(rf"\b{NO_RE}(?:tera(?:stalli[sz]\w*)?)\b", query, re.I):
        add(m.start(), m.end(), "tera", "", "suffix")
    for alias, item in ITEM_ALIASES.items():
        for m in re.finditer(rf"\b{NO_RE}{alias}\b", query, re.I):
            add(m.start(), m.end(), "no_item", item, "suffix")
    for rx, item in _items(dex):
        for m in re.finditer(rf"\b{NO_RE}{rx.pattern}", query, rx.flags):
            add(m.start(), m.end(), "no_item", item, "suffix")

    for m in re.finditer(r"\bmoves?\s*:\s*([^)\n;.?]+)", query, re.I):
        moves = [dex.move_name(x.strip()) for x in re.split(r"[,/]|\band\b", m.group(1))] if dex else []
        moves = [x for x in moves if x]
        if moves:
            add(m.start(), m.end(), "moves", moves, "suffix")
    for m in re.finditer(r"\bability\s*:\s*([A-Za-z][\w' -]*?)(?=[,);.\n]|$)", query, re.I):
        name = dex.ability_name(m.group(1)) if dex else None
        if name:
            add(m.start(), m.end(), "ability", name, "suffix")
    for m in re.finditer(r"\btera(?:stalli[sz]\w*)?(?:\s+type)?\s*(?::|into|to|as)?\s*(\w+)\b|\b(\w+)\s+tera\b", query, re.I):
        t = (m.group(1) or m.group(2) or "").capitalize()
        if t in TYPES:
            add(m.start(), m.end(), "tera", t)
    for move, boost in SETUP_MOVES.items():
        for m in re.finditer(rf"\b(?:after|following)\s+(?:an?\s+|one\s+|a single\s+)?{move}\b", query, re.I):
            if free(m.start(), m.end()):
                hits.extend((m.start(), m.end(), "boost", (stat, n), "suffix") for stat, n in boost.items())
                taken.append(m.span())
    for nature in NATURES:
        # English words ("calm", "bold", "careful") only count capitalised; never inside "Calm Mind" or "Brave Bird"
        flags = re.I if nature in CASUAL_NATURES else 0
        for m in re.finditer(rf"\b{nature}\b(?!\s+(?:Mind|Bird))(?:\s+nature)?", query, flags):
            add(m.start(), m.end(), "nature", nature)
    for m in re.finditer(rf"(?<![\w.%])(\d{{1,3}})\+?\s*{STAT_WORD}\b(?:\s+(?:evs?|sp|stat points))?", query, re.I):
        # Over 252 is a stat, not an investment ("my 300 Speed Tusk")
        if int(m.group(1)) <= 252:
            stat = STAT_ALIASES[m.group(2).lower().replace("defence", "defense")]
            add(m.start(), m.end(), "evs", (stat, int(m.group(1))))
    for m in re.finditer(rf"\b(max(?:imum)?|min(?:imum)?)\s+{STAT_WORD}\b(?:\s+(?:evs?|investment))?", query, re.I):
        stat = STAT_ALIASES.get(m.group(2).lower())
        if stat:
            add(m.start(), m.end(), "max" if m.group(1).lower().startswith("max") else "min", stat)
    for m in re.finditer(r"\b(?:uninvested|no investment|0 investment)\b", query, re.I):
        add(m.start(), m.end(), "uninvested", True)
    for m in re.finditer(rf"(?<![\w])([+-][1-6])\s*{STAT_WORD}?\b", query, re.I):
        stat = STAT_ALIASES.get((m.group(2) or "").lower(), "_atk")
        add(m.start(), m.end(), "boost", (stat, int(m.group(1))))
    for alias, item in ITEM_ALIASES.items():
        for m in re.finditer(rf"\b{alias}\b", query, re.I):
            add(m.start(), m.end(), "item", item)
    for rx, item in _items(dex):
        for m in rx.finditer(query):
            add(m.start(), m.end(), "item", item)
    if dex:
        for name in dex.ability_names:
            if len(name) > 3:
                for m in re.finditer(rf"\b{re.escape(name)}\b", query):
                    add(m.start(), m.end(), "ability_loose", name)
    return hits


def _sentence_start(query, pos):
    return max(query.rfind(c, 0, pos) for c in ".?!;\n") + 1


def _owner(spans, a, b, style, blanked, query):
    """Side of the mention a detail belongs to: glued next mention, else closest mention before, else opponent."""
    if style == "prefix":
        nxt = next((s for s in spans if s[0] >= b), None)
        if nxt and GLUE_RE.match(blanked[b:nxt[0]]):
            return nxt[3]
    prev = next((s for s in reversed(spans) if s[1] <= a), None)
    if prev:
        return prev[3]
    # Details before any name in a later clause ("Assuming 252 HP / 4 Def, does X OHKO Y") describe the opponent
    return "opponent"


def _field(query, out):
    for m in re.finditer(r"\b(?:in|under|with|during|while)\s+(?:the\s+|harsh\s+|heavy\s+)?(rain|sun|sunlight|sandstorm|sand|snow|hail)\b|"
                         r"\b(rain|sun|sandstorm|sand|snow)\s+(?:is\s+)?(?:up|active|on the field)\b", query, re.I):
        out.conditions["weather"] = WEATHER[(m.group(1) or m.group(2)).lower()]
        out.consumed.append(m.span())
    for m in re.finditer(r"\b(Electric|Grassy|Psychic|Misty)\s+Terrain\b", query, re.I):
        out.conditions["terrain"] = m.group(1).capitalize()
        out.consumed.append(m.span())
    screen = r"(reflect|light screen|aurora veil)"
    for m in re.finditer(rf"\b(?:behind|under|through|with|into)\s+(?:an?\s+|the\s+)?{screen}\b[^.?;,]*|"
                         rf"\b{screen}\s+(?:is\s+|being\s+)?(?:up|active|set|on)\b[^.?;,]*", query, re.I):
        name = (m.group(1) or m.group(2)).lower()
        tail = m.group(0).lower()
        side = ("opponent" if re.search(r"\b(opposing|their|enemy|opponent'?s?|other|foe'?s?)\s+side\b", tail) else
                "user" if re.search(r"\b(my|our)\s+side\b", tail) else "defender")
        out.screens.setdefault(side, set()).add(SCREENS[name])
        out.consumed.append(m.span())


def extract(query, spans, dex, user_item=None):
    """Constraints for `query`. spans: (start, end, name, side) Pokemon mentions in order, side 'user' | 'opponent'.
    user_item: the player's held item, so "no booster" is credited to the side that actually holds one."""
    out = Constraints()
    out.raw_stats = bool(RAW_RE.search(query))
    out.strongest = bool(re.search(r"\b(strongest|best|most damaging|hardest hitting)\s+(?:listed\s+)?(?:attack|move)", query, re.I))
    _field(query, out)
    # Nothing inside a field phrase or a Pokemon name is a set detail
    hits = [h for h in _hits(query, dex)
            if not any(a <= h[0] and h[1] <= b for a, b in out.consumed)
            and not any(h[0] < s[1] and s[0] < h[1] for s in spans)]
    blanked = query
    for a, b, *_ in hits:
        blanked = blanked[:a] + " " * (b - a) + blanked[b:]
    loose = {}
    for a, b, key, value, style in sorted(hits, key=lambda h: h[0]):
        side = getattr(out, _owner(spans, a, b, style, blanked, query))
        if key == "no_item" and user_item and value.lower() == user_item.lower():
            side = out.user
        if key == "ability_loose":
            # A bare ability name ("thanks to Levitate") only counts beside other set details
            loose.setdefault(id(side), (side, value))
            continue
        out.consumed.append((a, b))
        if key == "evs":
            side.setdefault("evs", {})[value[0]] = value[1]
        elif key == "boost":
            side.setdefault("boosts", {})[value[0]] = side.get("boosts", {}).get(value[0], 0) + value[1]
        elif key in ("max", "min"):
            side.setdefault(key, []).append(value)
        elif key == "no_item":
            if side.get("item") in (None, value):
                side["item"] = ""
        else:
            side.setdefault(key, value)
    for side, ability in loose.values():
        if side and "ability" not in side:
            side["ability"] = ability
    return out


# Conditions players state that the engine does not model yet: reported, never silently dropped
UNHANDLED_RE = re.compile(
    r"\b(tailwind|trick room|sticky web|stealth rock|spikes|burn(?:ed|t)?|paraly[sz]ed|poisoned|frostbit\w*|"
    r"critical hits?|crits?|helping hand|friend guard|protosynthesis active|quark drive active|"
    r"(?:after|with)\s+(?:a\s+|one\s+)?(?:stealth rock|spikes)\s+(?:chip|damage))\b|"
    r"\b(?:at|from)\s+(?!100\b)\d{1,2}\s*%\s*(?:hp|health)?", re.I)
NEGATED_RE = re.compile(r"\b(?:no|not|without|ignor\w*|assume no|assuming no)\b[^.?;]*$", re.I)


def unhandled(query, consumed, spans):
    """Phrases stating a condition the solvers can't apply ("under Tailwind", "burned", "at 50% HP").
    A negated mention ("no crits") is an assumption the engine already makes, so it is skipped."""
    out = []
    for m in UNHANDLED_RE.finditer(query):
        a, b = m.span()
        if any(x <= a and b <= y for x, y in consumed) or any(a < s[1] and s[0] < b for s in spans):
            continue
        lead = query[max(_sentence_start(query, a), a - 40):a]
        if NEGATED_RE.search(lead):
            continue
        out.append(m.group(0).strip())
    return list(dict.fromkeys(out))


def apply(spec, details, dex, game):
    """A calc spec with the stated details applied (a copy). Champions EVs over 32 are read as EVs and
    converted to stat points; 'max speed' means full investment plus a raising nature unless one is stated."""
    spec = dict(spec)
    if not details:
        return spec
    species = dex.species(spec["name"]) if dex else None
    base = (species or {}).get("baseStats", {})
    special = base.get("spa", 0) > base.get("atk", 0)
    cap = 32 if game == "champions" else 252
    if "item" in details:
        if details["item"]:
            spec["item"] = details["item"]
        else:
            spec.pop("item", None)
    if details.get("no_speed_item") and spec.get("item") in ("Choice Scarf", "Iron Ball", "Quick Powder"):
        spec.pop("item", None)
    if details.get("ability"):
        spec["ability"] = details["ability"]
    if details.get("tera"):
        spec["teraType"] = details["tera"]
    evs = None
    if details.get("evs") or details.get("max") or details.get("min") or details.get("uninvested"):
        evs = {k: 0 for k in STATS} if (details.get("evs") or details.get("uninvested")) else dict(spec.get("evs") or {})
        for k, v in (details.get("evs") or {}).items():
            evs[k] = min(32, (v + 4) // 8) if game == "champions" and v > 32 else v
        for k in details.get("max", []):
            evs[k] = cap
        for k in details.get("min", []):
            evs[k] = 0
            spec["ivs"] = {**spec.get("ivs", {}), k: 0}
        spec["evs"] = evs
    if details.get("nature"):
        spec["nature"] = details["nature"]
    elif details.get("max"):
        spec["nature"] = PLUS_NATURES[details["max"][0]][int(special)]
    elif details.get("min") and details["min"][0] in MINUS_NATURES:
        spec["nature"] = MINUS_NATURES[details["min"][0]][int(special)]
    elif details.get("uninvested"):
        spec["nature"] = "Serious"
    if details.get("boosts"):
        boosts = dict(details["boosts"])
        if "_atk" in boosts:  # "+2" with no stat: the attacking stat, whichever the move uses
            n = boosts.pop("_atk")
            boosts.setdefault("atk", n)
            boosts.setdefault("spa", n)
        spec["boosts"] = boosts
    return spec


LABELS = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}


def summary(details):
    """'Timid nature, 252 Spe, no speed item' for the facts list: what the answer took from the question."""
    parts = []
    if details.get("nature"):
        parts.append(f"{details['nature']} nature")
    parts += [f"{v} {LABELS[k]}" for k, v in (details.get("evs") or {}).items()]
    parts += [f"max {LABELS[k]}" for k in details.get("max", [])] + [f"min {LABELS[k]}" for k in details.get("min", [])]
    if details.get("uninvested"):
        parts.append("uninvested")
    if "item" in details:
        parts.append(details["item"] or "no item")
    if details.get("no_speed_item"):
        parts.append("no speed item")
    if details.get("ability"):
        parts.append(details["ability"])
    if details.get("tera"):
        parts.append(f"Tera {details['tera']}")
    elif details.get("tera") == "":
        parts.append("no Tera")
    parts += [f"{'+' if n > 0 else ''}{n} {LABELS.get(k, 'attacking stat')}" for k, n in (details.get("boosts") or {}).items()]
    if details.get("moves"):
        parts.append("moves " + ", ".join(details["moves"]))
    return ", ".join(parts)


def stated_spread(details):
    """True when the question gave this side's spread itself (nature or EVs)."""
    return bool(details) and any(details.get(k) for k in ("nature", "evs", "max", "min", "uninvested"))
