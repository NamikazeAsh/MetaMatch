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
SETUP_ALIASES = {"dd": "Dragon Dance", "sd": "Swords Dance", "np": "Nasty Plot", "cm": "Calm Mind", "qd": "Quiver Dance"}
WEATHER = {"rain": "Rain", "sun": "Sun", "sunlight": "Sun", "sand": "Sand", "sandstorm": "Sand",
           "snow": "Snow", "hail": "Snow"}
SCREENS = {"reflect": "isReflect", "light screen": "isLightScreen", "aurora veil": "isAuroraVeil", "veil": "isAuroraVeil"}

GLUE_RE = re.compile(r"^[\s/+,()]*(?:(?:my|your|the|a|an|their|opposing|enemy)\s+)?[\s/+,()]*$", re.I)
NO_RE = r"(?:no|without|not holding|minus)\s+(?:an?\s+|any\s+|its\s+|the\s+)?"
NO_BOOSTS_RE = re.compile(r"\b(?:no|without|ignor\w*)\s+(?:any\s+|stat\s+)?boosts?\b", re.I)
# "Ignore items", "not counting items", "no items or abilities": bare stats for both sides
RAW_RE = re.compile(r"\b(?:ignor\w*|without|disregard\w*|not\s+counting|not\s+including|excluding|leaving\s+out)\s+"
                    r"(?:all\s+|any\s+|held\s+|the\s+)?(?:items?|abilities)\b|"
                    r"\bno\s+(?:held\s+)?items\b", re.I)


@dataclass
class Constraints:
    user: dict = field(default_factory=dict)       # set details for the player's Pokemon
    opponent: dict = field(default_factory=dict)   # set details for the opponent
    conditions: dict = field(default_factory=dict)  # calc Field: weather, terrain
    screens: dict = field(default_factory=dict)    # "user" | "opponent" | "defender" -> set of calc Side flags
    raw_stats: bool = False                        # compare bare stats: no items or abilities
    no_boosts: bool = False                        # "assume no boosts": no stat stages, Protosynthesis or Quark Drive
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
    for m in re.finditer(r"\b(?:no|without|not|never|doesn'?t|does not|won'?t|will not|didn'?t|isn'?t)\s+"
                         r"(?:going to\s+|gonna\s+)?(?:use\s+)?tera\w*\b", query, re.I):
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
    for a, b, moves in _move_runs(query, dex):
        add(a, b, "moves", moves, "suffix")
    for m in re.finditer(r"\bability\s*:\s*([A-Za-z][\w' -]*?)(?=[,);.\n]|$)", query, re.I):
        name = dex.ability_name(m.group(1)) if dex else None
        if name:
            add(m.start(), m.end(), "ability", name, "suffix")
    for rx in (r"\btera(?:stalli[sz]\w*|s\b|'?d\b)?(?:\s+type)?\s*(?::|into|to|as)?\s*(\w+)\b", r"\b(\w+)\s+tera\b"):
        for m in re.finditer(rx, query, re.I):
            if m.group(1).capitalize() in TYPES:
                add(m.start(), m.end(), "tera", m.group(1).capitalize())
    setup = {**{m.lower(): m for m in SETUP_MOVES}, **SETUP_ALIASES}
    names = "|".join(re.escape(k) for k in sorted(setup, key=len, reverse=True))
    for m in re.finditer(rf"\b(?:after|following)\s+(?:an?\s+|one\s+|a single\s+)?({names})\b", query, re.I):
        if free(m.start(), m.end()):
            boost = SETUP_MOVES[setup[m.group(1).lower()]]
            hits.extend((m.start(), m.end(), "boost", (stat, n), "subject") for stat, n in boost.items())
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
        style = "subject" if re.search(r"\bat\s*$", query[:m.start()], re.I) else "prefix"
        add(m.start(), m.end(), "boost", (stat, int(m.group(1))), style)
    # Full names before casual ones, so "Choice Scarf" is one detail and not "Choice" plus "scarf"
    for rx, item in _items(dex):
        for m in rx.finditer(query):
            add(m.start(), m.end(), "item", item)
    for alias, item in ITEM_ALIASES.items():
        for m in re.finditer(rf"\b{alias}\b", query, re.I):
            add(m.start(), m.end(), "item", item)
    # "both uninvested", "both Jolly": the detail describes both sides
    hits[:] = [(a, b, k, v, "both" if re.search(r"\bboth\s+(?:are\s+|run\s+|running\s+|have\s+)?$", query[:a], re.I) else st)
               for a, b, k, v, st in hits]
    if dex:
        for name in dex.ability_names:
            if len(name) > 3:
                for m in re.finditer(rf"\b{re.escape(name)}\b", query):
                    add(m.start(), m.end(), "ability_loose", name)
    return hits


_MOVE_RX = {}


def _move_regex(dex):
    if id(dex) not in _MOVE_RX:
        names = sorted((n for n in dex.move_data if len(n) > 2), key=len, reverse=True)
        _MOVE_RX[id(dex)] = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in names) + r")(?![\w-])", re.I)
    return _MOVE_RX[id(dex)]


def _move_runs(query, dex, least=3):
    """(start, end, moves) for runs of `least` or more move names separated only by list punctuation."""
    if not dex:
        return []
    found = [(m.start(), m.end(), dex.move_name(m.group(1))) for m in _move_regex(dex).finditer(query)]
    runs, cur = [], []
    for hit in found:
        if cur and not re.fullmatch(r"[\s,/|;-]*(?:and\s+|or\s+)?[\s-]*", query[cur[-1][1]:hit[0]], re.I):
            runs.append(cur)
            cur = []
        cur.append(hit)
    runs.append(cur)
    return [(r[0][0], r[-1][1], list(dict.fromkeys(x[2] for x in r))) for r in runs if len(r) >= least]


def _sentence_start(query, pos):
    return max(query.rfind(c, 0, pos) for c in ".?!;\n") + 1


def _owner(spans, a, b, style, blanked, query, subject="user", survive=False):
    """Side of the mention a detail belongs to: a glued next mention, else the closest mention before it.
    'subject' details (setup moves, "at +2") go to whoever acts unless a mention sits right before them
    ("mine at +1"). Details before any mention ("Assuming 252 HP / 4 Def, does X OHKO Y") describe the
    defender: the subject of a survive question, else the side opposite the subject."""
    if style == "prefix":
        nxt = next((s for s in spans if s[0] >= b), None)
        if nxt and GLUE_RE.match(blanked[b:nxt[0]]):
            return nxt[3]
    prev = next((s for s in reversed(spans) if s[1] <= a), None)
    if style == "subject":
        if prev and re.fullmatch(r"[\s,']*(?:s\s+)?(?:is\s+)?(?:at\s+)?", blanked[prev[1]:a], re.I):
            return prev[3]
        # Boosts belong to whoever attacks: the subject, or its opponent in a survive question
        return ("opponent" if subject == "user" else "user") if survive else subject
    if prev:
        return prev[3]
    if survive:
        return subject
    return "opponent" if subject == "user" else "user"


def _field(query, out):
    for m in re.finditer(r"\b(?:in|under|with|during|while)\s+(?:the\s+|harsh\s+|heavy\s+)?(rain|sun|sunlight|sandstorm|sand|snow|hail)\b|"
                         r"\b(rain|sun|sandstorm|sand|snow)\s+(?:is\s+)?(?:up|active|on the field)\b", query, re.I):
        out.conditions["weather"] = WEATHER[(m.group(1) or m.group(2)).lower()]
        out.consumed.append(m.span())
    for m in re.finditer(r"(?:^|[.?!;]\s*)(rain|sun|sand|sandstorm|snow)\s*[:,]", query, re.I):
        out.conditions["weather"] = WEATHER[m.group(1).lower()]
        out.consumed.append(m.span(1))
    for m in re.finditer(r"\b(Electric|Grassy|Psychic|Misty)\s+Terrain\b", query, re.I):
        out.conditions["terrain"] = m.group(1).capitalize()
        out.consumed.append(m.span())
    screen = r"(reflect|light screen|aurora veil|veil)"
    for m in re.finditer(rf"\b(?:behind|under|through|with|into)\s+(?:an?\s+|the\s+)?{screen}\b[^.?;,]*|"
                         rf"\b{screen}\s+(?:is\s+|being\s+)?(?:up|active|set|on)\b[^.?;,]*", query, re.I):
        name = (m.group(1) or m.group(2)).lower()
        tail = m.group(0).lower()
        side = ("opponent" if re.search(r"\b(opposing|their|enemy|opponent'?s?|other|foe'?s?)\s+side\b", tail) else
                "user" if re.search(r"\b(my|our)\s+side\b", tail) else "defender")
        out.screens.setdefault(side, set()).add(SCREENS[name])
        out.consumed.append(m.span())


# Words that stand for one side in a mirror match: "mine at +1, theirs is Adamant"
SIDE_WORDS = [(r"\b(?:mine|my one|my side)\b", "user"),
              (r"\b(?:theirs|their one|the other one|the opposing one|their side|the opponent'?s?)\b", "opponent")]


def extract(query, spans, dex, user_item=None, subject="user", survive=False):
    """Constraints for `query`. spans: (start, end, name, side) Pokemon mentions in order, side 'user' | 'opponent'.
    user_item: the player's held item, so "no booster" is credited to the side that actually holds one.
    subject: side of the question's subject; survive: a survive question (see _owner)."""
    out = Constraints()
    out.raw_stats = bool(RAW_RE.search(query))
    out.no_boosts = bool(NO_BOOSTS_RE.search(query))
    out.strongest = bool(re.search(r"\b(strongest|best|most damaging|hardest hitting)\s+(?:listed\s+)?(?:attack|move)", query, re.I))
    _field(query, out)
    # Nothing inside a field phrase or a Pokemon name is a set detail
    hits = [h for h in _hits(query, dex)
            if not any(a <= h[0] and h[1] <= b for a, b in out.consumed)
            and not any(h[0] < s[1] and s[0] < h[1] for s in spans)]
    blanked = query
    for a, b, *_ in hits:
        blanked = blanked[:a] + " " * (b - a) + blanked[b:]
    marks = sorted(spans + [(m.start(), m.end(), "", side) for rx, side in SIDE_WORDS for m in re.finditer(rx, query, re.I)])
    loose = {}
    for a, b, key, value, style in sorted(hits, key=lambda h: h[0]):
        side = getattr(out, _owner(marks, a, b, style, blanked, query, subject, survive))
        # "...? no booster": a negated item with no mention earlier in its sentence goes to whoever holds it
        alone = not any(_sentence_start(query, a) <= s[0] < a for s in marks)
        if key == "no_item" and alone and user_item and value.lower() == user_item.lower():
            side = out.user
        if key == "ability_loose":
            # A bare ability name ("thanks to Levitate") only counts beside other set details or glued to a name
            nxt = next((s for s in marks if s[0] >= b), None)
            if nxt and GLUE_RE.match(blanked[b:nxt[0]]):
                side.setdefault("ability", value)
                out.consumed.append((a, b))
            else:
                loose.setdefault(id(side), (side, value))
            continue
        out.consumed.append((a, b))
        for side in ((out.user, out.opponent) if style == "both" else (side,)):
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


# Battle conditions players state. Each one found is credited to a side and counted by the questions it
# changes (Tailwind in a speed question, a crit in a KO question); the rest are reported in the answer as
# not counted, never silently dropped
UNHANDLED_RE = re.compile(
    r"\b(tailwind|trick room|sticky web|stealth rock|spikes|burn(?:ed|t)?|paraly[sz]ed|poisoned|frostbit\w*|"
    r"critical hits?|crits?|helping hand|friend guard|protosynthesis active|quark drive active|"
    r"(?:after|with)\s+(?:a\s+|one\s+)?(?:stealth rock|spikes)\s+(?:chip|damage))\b|"
    r"\b(?:at|from)\s+(?!100\b)\d{1,2}\s*%\s*(?:hp|health)?", re.I)
NEGATED_RE = re.compile(r"\b(?:no|not|without|ignor\w*|assume no|assuming no)\b[^.?;]*$", re.I)


@dataclass
class Condition:
    text: str                 # as the question says it: "Tailwind", "burned", "50% HP"
    kind: str | None          # tailwind, trick_room, status, hp, stealth_rock, spikes, crit, qp; None if not modelled
    value: object = None      # status code ("brn"), HP percent, Spikes layers
    side: str | None = None   # "user", "opponent", "both", or None when the question doesn't say
    span: tuple = (0, 0)


# Which question types each condition changes. Status is keyed by code: burn and poison change damage
# and KO counts, paralysis changes Speed.
COUNTS_FOR = {"tailwind": {"speed"}, "trick_room": {"speed"}, "brn": {"ko", "damage"}, "psn": {"ko", "damage"},
              "par": {"speed"}, "hp": {"ko", "damage"}, "stealth_rock": {"ko", "damage"}, "spikes": {"ko", "damage"},
              "crit": {"ko", "damage"}, "qp": {"speed", "ko", "damage"}}
LAYER_WORDS = {"1": 1, "2": 2, "3": 3, "one": 1, "two": 2, "three": 3, "single": 1, "double": 2, "triple": 3}
MY_RE = re.compile(r"\b(?:my|our)\s+(?:own\s+)?$", re.I)
THEIR_RE = re.compile(r"\b(?:their|opposing|enemy|the opponent'?s?|the foe'?s?)\s+$", re.I)
SIDE_TAIL_RE = re.compile(r"^\s+(?:up\s+)?(?:on|for)\s+(my|our|their|the opposing|the enemy|the opponent'?s?)\s+side\b", re.I)
# "Dragapult has Tailwind", "Dragapult's Tailwind": the side of the mention right before
SETTER_RE = re.compile(r"^(?:'s|\s+(?:has|have|had|gets|got|sets?|set up|uses?|used)(?:\s+up)?)\s+(?:a\s+|the\s+)?$", re.I)


def _kind(text):
    t = text.lower()
    for word, kind in (("tailwind", "tailwind"), ("trick room", "trick_room"), ("stealth rock", "stealth_rock"),
                       ("spikes", "spikes"), ("crit", "crit"), ("active", "qp")):
        if word in t:
            return kind, None
    if t.startswith("burn"):
        return "status", "brn"
    if t.startswith("paraly"):
        return "status", "par"
    if t == "poisoned":
        return "status", "psn"
    m = re.search(r"(\d{1,2})\s*%", t)
    if m:
        return "hp", int(m.group(1))
    return None, None   # Sticky Web, frostbite, Helping Hand, Friend Guard


def _condition_side(query, a, b, kind, marks):
    """Side a condition belongs to, or None when the question leaves it to the solver's default."""
    lead = query[max(_sentence_start(query, a), a - 30):a]
    tail = SIDE_TAIL_RE.match(query[b:b + 40])
    if tail:
        return "user" if tail.group(1).lower() in ("my", "our") else "opponent"
    if MY_RE.search(lead):
        return "user"
    if THEIR_RE.search(lead):
        return "opponent"
    if kind in ("crit", "trick_room"):
        return None
    if kind == "tailwind" and re.search(r"\bboth\b[^.?;,]*$", lead, re.I):
        return "both"
    sentence = _sentence_start(query, a)
    prev = next((s for s in reversed(marks) if sentence <= s[0] and s[1] <= a), None)
    if kind in ("tailwind", "stealth_rock", "spikes"):
        return prev[3] if prev and SETTER_RE.match(query[prev[1]:a]) else None
    nxt = next((s for s in marks if s[0] >= b), None)
    glued = nxt and GLUE_RE.match(query[b:nxt[0]])
    if kind == "hp":
        return prev[3] if prev else (nxt[3] if glued else None)
    return nxt[3] if glued else (prev[3] if prev else None)


def conditions(query, consumed, spans):
    """Every battle condition the question states ("under Tailwind", "burned", "at 50% HP"), with its side.
    A negated mention ("no crits") is an assumption the engine already makes, so it is skipped."""
    marks = sorted(spans + [(m.start(), m.end(), "", side) for rx, side in SIDE_WORDS for m in re.finditer(rx, query, re.I)])
    out, seen = [], set()
    for m in UNHANDLED_RE.finditer(query):
        a, b = m.span()
        if any(x <= a and b <= y for x, y in consumed) or any(a < s[1] and s[0] < b for s in spans):
            continue
        lead = query[max(_sentence_start(query, a), a - 40):a]
        if NEGATED_RE.search(lead):
            continue
        text = re.sub(r"^(?:at|from)\s+", "", m.group(0).strip(), flags=re.I)
        if text.lower() in seen:
            continue
        seen.add(text.lower())
        kind, value = _kind(text)
        if kind == "spikes" and lead.lower().rstrip().endswith("toxic"):
            kind = None   # Toxic Spikes poison on entry; not modelled
        if kind == "spikes":
            layers = re.search(r"\b(\d|one|two|three|single|double|triple)\s+(?:layers?\s+(?:of\s+)?)?$", lead, re.I)
            value = LAYER_WORDS[layers.group(1).lower()] if layers else 1
        out.append(Condition(text, kind, value, _condition_side(query, a, b, kind, marks) if kind else None, (a, b)))
    return out


def counts_for(cond, intent):
    """True when the condition changes the answer to this kind of question."""
    key = cond.value if cond.kind == "status" else cond.kind
    return bool(cond.kind) and intent in COUNTS_FOR.get(key, ())


def unhandled(query, consumed, spans):
    """Stated conditions as plain phrases, for callers that only report them."""
    return [c.text for c in conditions(query, consumed, spans)]


def describe(cond, names):
    """'Tailwind on your side', 'a burned Great Tusk', 'Kingambit at 50% HP'. names: side -> Pokemon shown."""
    who = names.get(cond.side, "")
    if cond.kind == "tailwind":
        return {"user": "Tailwind on your side", "opponent": "Tailwind on their side"}.get(cond.side, "Tailwind on both sides")
    if cond.kind == "trick_room":
        return "Trick Room"
    if cond.kind == "crit":
        return "a critical hit"
    if cond.kind == "status":
        return f"a {({'brn': 'burned', 'par': 'paralyzed', 'psn': 'poisoned'})[cond.value]} {who}"
    if cond.kind == "hp":
        return f"{who} at {cond.value}% HP"
    if cond.kind == "stealth_rock":
        return f"Stealth Rock on {who}'s side"
    if cond.kind == "spikes":
        return f"{cond.value} {'layer' if cond.value == 1 else 'layers'} of Spikes on {who}'s side"
    if cond.kind == "qp":
        return f"{cond.text.lower().replace(' active', '').title()} active on {who}"
    return cond.text


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
