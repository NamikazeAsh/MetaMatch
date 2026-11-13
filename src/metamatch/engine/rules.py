"""
Rules answers from Pokemon Showdown's own text (data/json/rules_text.json, built by scripts/build_rules_text.py):
what an ability, item, move or weather does, which team members it applies to, and exact yes or no answers for the
rules that come down to a flag or a fixed multiplier ("does Mold Breaker ignore Levitate", "does Magic Bounce
reflect Stealth Rock", "does Sharpness boost Razor Shell", "does sun boost Flamethrower").
"""
import json
import re
from functools import lru_cache

from metamatch import config

PATH = config.JSON_DIR / "rules_text.json"
TYPES = ["Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground", "Flying", "Psychic",
         "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"]

# Weather words and the move whose text states that weather's rules
FIELD_WORDS = {"sun": "Sunny Day", "sunny": "Sunny Day", "sunlight": "Sunny Day", "rain": "Rain Dance",
               "sand": "Sandstorm", "sandstorm": "Sandstorm", "snow": "Snowscape", "hail": "Snowscape"}
WEATHER_SCALES = {"Sunny Day": {"Fire": 1.5, "Water": 0.5}, "Rain Dance": {"Water": 1.5, "Fire": 0.5}}
WEATHER_NAMES = {"Sunny Day": "sun", "Rain Dance": "rain", "Sandstorm": "sand", "Snowscape": "snow"}
MOLD_BREAKERS = {"Mold Breaker", "Teravolt", "Turboblaze"}
# Abilities keyed on a move flag: (flag, what the ability does to such moves, multiplier or None)
FLAG_ABILITIES = {
    "Sharpness": ("slicing", "boosts", 1.5), "Iron Fist": ("punch", "boosts", 1.2), "Strong Jaw": ("bite", "boosts", 1.5),
    "Mega Launcher": ("pulse", "boosts", 1.5), "Tough Claws": ("contact", "boosts", 1.3), "Punk Rock": ("sound", "boosts", 1.3),
    "Soundproof": ("sound", "blocks", None), "Bulletproof": ("bullet", "blocks", None), "Overcoat": ("powder", "blocks", None),
    "Wind Rider": ("wind", "blocks", None), "Magic Bounce": ("reflectable", "reflects", None),
}
FLAG_NAMES = {"slicing": "a slicing move", "punch": "a punching move", "bite": "a biting move", "pulse": "a pulse move",
              "contact": "a contact move", "sound": "a sound move", "bullet": "a ball or bomb move",
              "powder": "a powder move", "wind": "a wind move", "reflectable": "a move that can be bounced back"}
# Single word names that are also ordinary English: only matched when written with a capital letter
COMMON_WORDS = {"pressure", "substitute", "strength", "transform", "conversion", "frustration", "punishment", "retaliate",
                "magnitude", "safeguard", "captivate", "stockpile", "imprison", "teleport", "attract", "present", "judgment",
                "gravity", "illusion", "protect", "recover", "counter", "struggle", "endure", "memento", "defiant", "comeuppance",
                "instruct", "obstruct", "trick", "growth", "return", "bounce", "charm", "rest", "surf", "sturdy", "guts"}
YES_NO = re.compile(r"^\s*(?:does|do|is|are|can|will|would|won't|doesn't|isn't)\b", re.I)
BOOST_CUE = re.compile(r"\b(?:boosts?|stronger|strengthen\w*|power(?:ed)?|more damage|increase\w*|raise\w*|halve\w*|weaker|"
                       r"weaken\w*|less damage|reduce\w*|lower\w*|affect\w*|damage)\b", re.I)
# The question asks whether damage goes down, so "yes" means weakened
ASKS_DOWN = re.compile(r"\b(?:weaker|weaken\w*|halve\w*|reduce\w*|lower\w*|less)\b", re.I)
# Moves whose behaviour changes with the weather: {move: {weather move: what happens}}
WEATHER_MOVES = {
    "Weather Ball": {"Sunny Day": "becomes a Fire type move with 100 power", "Rain Dance": "becomes a Water type move with 100 power",
                     "Sandstorm": "becomes a Rock type move with 100 power", "Snowscape": "becomes an Ice type move with 100 power"},
    "Solar Beam": {"Sunny Day": "fires in one turn with no charging turn", "Rain Dance": "has its power halved",
                   "Sandstorm": "has its power halved", "Snowscape": "has its power halved"},
    "Solar Blade": {"Sunny Day": "fires in one turn with no charging turn", "Rain Dance": "has its power halved",
                    "Sandstorm": "has its power halved", "Snowscape": "has its power halved"},
    "Thunder": {"Rain Dance": "never misses", "Sunny Day": "has 50% accuracy"},
    "Hurricane": {"Rain Dance": "never misses", "Sunny Day": "has 50% accuracy"},
    "Blizzard": {"Snowscape": "never misses"},
    "Electro Shot": {"Rain Dance": "fires in one turn with no charging turn"},
    "Hydro Steam": {"Sunny Day": "does 1.5x damage instead of being weakened"},
}


@lru_cache(maxsize=1)
def table():
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"abilities": {}, "items": {}, "moves": {}}


@lru_cache(maxsize=1)
def _patterns():
    """[(regex, kind, name)], longest names first so 'Rain Dance' wins over 'Rain'."""
    out = []
    for kind, key in (("ability", "abilities"), ("item", "items"), ("move", "moves")):
        for name in table()[key]:
            if len(name) < 4:
                continue
            flags = 0 if (" " not in name and (name.lower() in COMMON_WORDS or len(name) < 8)) else re.I
            out.append((re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])", flags), kind, name))
    for word, move in FIELD_WORDS.items():
        out.append((re.compile(rf"\b{word}\b", re.I), "field", move))
    out.sort(key=lambda p: len(p[0].pattern), reverse=True)
    return out


def find_named(text, blocked=()):
    """[(kind, name)] for every ability, item, move and weather named in `text`, in order. `blocked` is a list of
    (start, end) spans to ignore, such as Pokemon names."""
    taken = list(blocked)
    found = []
    for pattern, kind, name in _patterns():
        for m in pattern.finditer(text):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            # "Psychic type" is a type, not the move
            if name in TYPES and re.match(r"[\s-]*(?:types?|moves?|attacks?)\b", text[m.end():], re.I):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), kind, name))
    seen, out = set(), []
    for _, kind, name in sorted(found):
        if (kind, name) not in seen:
            seen.add((kind, name))
            out.append((kind, name))
    return out


def entry(kind, name):
    key = {"ability": "abilities", "item": "items", "move": "moves", "field": "moves"}[kind]
    return table()[key].get(name) or {}


def text_line(kind, name, full=False):
    e = entry(kind, name)
    text = (e.get("desc") if full else None) or e.get("short", "")
    label = WEATHER_NAMES.get(name, name).capitalize() if kind == "field" else name
    return f"{label}: {text}" if text else ""


def _type_in(text):
    for t in TYPES:
        if re.search(rf"\b{t}\b", text, re.I):
            return t
    return None


def yes_no(query, named, scales, immunities):
    """(answer, reason) when the question is a yes or no about a rule the data settles exactly, else None."""
    if not YES_NO.search(query):
        return None
    abilities = [n for k, n in named if k == "ability"]
    moves = [n for k, n in named if k == "move"]
    fields = [n for k, n in named if k == "field"]
    other_abilities = [a for a in abilities if a not in MOLD_BREAKERS]
    breakers = [a for a in abilities if a in MOLD_BREAKERS]
    if breakers and other_abilities and re.search(r"\b(?:ignore|bypass|go(?:es)? through|work|affect|hit)\w*", query, re.I):
        target = other_abilities[0]
        if entry("ability", target).get("breakable"):
            return "yes", f"{breakers[0]} ignores {target}, which is one of the Abilities it bypasses."
        return "no", f"{breakers[0]} does not ignore {target}, which is not one of the Abilities it bypasses."
    for ability in abilities:
        if ability in FLAG_ABILITIES and moves:
            flag, effect, mult = FLAG_ABILITIES[ability]
            move = moves[0]
            has = flag in entry("move", move).get("flags", [])
            what = FLAG_NAMES[flag]
            if has:
                how = f" ({mult:g}x power)" if mult else ""
                return "yes", f"{ability} {effect} {move}{how}, because {move} is {what}."
            return "no", f"{ability} does not affect {move}, because {move} is not {what}."
        if ability == "Technician" and moves:
            bp = entry("move", moves[0]).get("basePower", 0)
            if bp:
                return (("yes", f"Technician boosts {moves[0]} (1.5x power), because its base power is {bp}, at most 60.") if bp <= 60 else
                        ("no", f"Technician does not boost {moves[0]}, because its base power is {bp}, above 60."))
        low = ability.lower()
        t = _type_in(query)
        if t and low in immunities and BOOST_CUE.search(query) is None:
            if immunities[low] == t.lower():
                return "yes", f"{ability} makes its holder immune to {t} attacks."
        if t and low in scales:
            factor = scales[low].get(t.lower())
            if factor:
                verb = "halves" if factor == 0.5 else f"multiplies by {factor:g}"
                return "yes", f"{ability} {verb} the damage its holder takes from {t} attacks."
            if low not in immunities:
                return "no", f"{ability} does not change the damage its holder takes from {t} attacks."
    for weather in fields:
        if weather in WEATHER_SCALES and BOOST_CUE.search(query):
            t = (entry("move", moves[0]).get("type") if moves else None) or _type_in(query)
            if not t:
                continue
            factor = WEATHER_SCALES[weather].get(t)
            name = WEATHER_NAMES[weather]
            subject = f"{moves[0]} ({t})" if moves else f"{t} attacks"
            down = bool(ASKS_DOWN.search(query))
            if moves and moves[0] == "Hydro Steam" and weather == "Sunny Day":
                factor = 1.5
            does, it = ("does", "it is") if moves else ("do", "they are")
            if factor and factor > 1:
                return ("no" if down else "yes"), f"In {name}, {subject} {does} {factor:g}x damage, so {it} boosted."
            if factor:
                return ("yes" if down else "no"), f"In {name}, {subject} {does} only {factor:g}x damage, so {it} weakened."
            return "no", f"{name.capitalize()} does not change the damage of {t} attacks."
    return None


def weather_effect(named):
    """'In sun, Weather Ball becomes a Fire type move with 100 power.' for a weather dependent move and a weather."""
    moves = [n for k, n in named if k == "move" and n in WEATHER_MOVES]
    fields = [n for k, n in named if k == "field"]
    for move in moves:
        for weather in fields:
            effect = WEATHER_MOVES[move].get(weather)
            if effect:
                return f"In {WEATHER_NAMES[weather]}, {move} {effect}."
    return None


def team_lines(named, team):
    """What the named rules mean for this team: who carries them, and for flag abilities which of the holder's moves
    they apply to. An item whose text names an Ability brings in that Ability's text for the holder."""
    lines = []
    for kind, name in named:
        for p in (team or {}).values():
            who = p.get("Forme") or p["Pokemon"]
            moves = [m["name"] for m in p.get("Moves", [])]
            ability = p.get("Mega Ability") or p.get("Ability")
            if kind == "ability" and ability == name:
                if name in FLAG_ABILITIES and FLAG_ABILITIES[name][1] == "boosts":
                    flag = FLAG_ABILITIES[name][0]
                    yes = [m for m in moves if flag in entry("move", m).get("flags", [])]
                    no = [m for m in moves if m not in yes]
                    kind_of = FLAG_NAMES[flag].removeprefix("a ")
                    line = f"Your {who} has {name}"
                    if yes:
                        line += f"; it boosts {_join(yes)} ({kind_of}{'s' if len(yes) > 1 else ''})"
                    if no:
                        line += f"; not {_join(no)}"
                    lines.append(line + ".")
                else:
                    lines.append(f"Your {who} has {name}.")
            elif kind == "item" and p.get("Item") == name:
                lines.append(f"Your {who} holds {name}.")
                if ability and ability in entry("item", name).get("short", "") + entry("item", name).get("desc", ""):
                    lines.append(f"{who}'s {text_line('ability', ability)}")
            elif kind == "move" and name in moves:
                lines.append(f"Your {who} runs {name}.")
    return list(dict.fromkeys(lines))


def _join(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def team_rules(team, query=""):
    """Rule text for every ability and item on the team plus anything the question names, for agent prompts."""
    lines = []
    for p in (team or {}).values():
        who = p.get("Forme") or p["Pokemon"]
        ability = p.get("Mega Ability") or p.get("Ability")
        if ability and entry("ability", ability):
            lines.append(f"{who}'s ability {text_line('ability', ability)}")
        if p.get("Item") and entry("item", p["Item"]):
            lines.append(f"{who}'s item {text_line('item', p['Item'])}")
    for kind, name in find_named(query):
        line = text_line(kind, name)
        if line and not any(line in existing for existing in lines):
            lines.append(line)
    return lines
