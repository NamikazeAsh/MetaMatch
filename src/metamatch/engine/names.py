"""
Finds the Pokemon a chat message refers to, the way players actually type them:
exact names ("Rotom-Wash", "great tusk"), community nicknames ("Lando", "Pex"),
"Mega Garchomp Z" style Mega names, and small typos ("excadril").
"""
import difflib
import json
import re
from functools import lru_cache

from metamatch import config

# Widely used community nicknames. Only unambiguous ones: words that are also ordinary
# English ("hands", "ape") are left out on purpose.
NICKNAMES = {
    "lando": "Landorus-Therian", "lando t": "Landorus-Therian", "landot": "Landorus-Therian",
    "lando i": "Landorus", "tusk": "Great Tusk", "pult": "Dragapult", "dpult": "Dragapult",
    "gambit": "Kingambit", "pex": "Toxapex", "corv": "Corviknight", "corvi": "Corviknight",
    "clef": "Clefable", "cress": "Cresselia", "rilla": "Rillaboom", "skarm": "Skarmory",
    "nite": "Dragonite", "dnite": "Dragonite", "ferro": "Ferrothorn", "zama": "Zamazenta",
    "glisc": "Gliscor", "hippo": "Hippowdon", "chomp": "Garchomp", "garch": "Garchomp",
    "tran": "Heatran", "tink": "Tinkaton", "gking": "Slowking-Galar", "g king": "Slowking-Galar",
    "valiant": "Iron Valiant", "treads": "Iron Treads", "moth": "Iron Moth", "crown": "Iron Crown",
    "ghold": "Gholdengo", "gholdy": "Gholdengo", "excad": "Excadrill", "drill": "Excadrill",
    "bax": "Baxcalibur", "pecha": "Pecharunt", "torn t": "Tornadus-Therian", "tornt": "Tornadus-Therian",
    "volc": "Volcarona", "ttar": "Tyranitar", "zap": "Zapdos", "gzap": "Zapdos-Galar",
    "wellspring": "Ogerpon-Wellspring", "hearthflame": "Ogerpon-Hearthflame",
    "cornerstone": "Ogerpon-Cornerstone", "ogre": "Ogerpon", "meow": "Meowscarada",
    "sam h": "Samurott-Hisui", "hisuian samurott": "Samurott-Hisui", "urshi": "Urshifu-Rapid-Strike",
    "rs urshifu": "Urshifu-Rapid-Strike", "kyurem": "Kyurem", "darmanitan": "Darmanitan",
    "lucario": "Lucario", "zard": "Charizard", "gross": "Metagross", "scizor": "Scizor",
    "pawm": "Pawmot", "sneas": "Sneasler", "annihil": "Annihilape", "prim": "Primarina",
    "hatt": "Hatterene", "ceru": "Ceruledge", "staraptor": "Staraptor",
}

# Nicknames that are also ordinary English: they only count in a Pokemon slot (see _nickname_ok)
AMBIGUOUS_NICKNAMES = {"gross", "moth", "crown", "drill", "valiant", "treads", "zap", "hippo", "meow",
                       "prim", "ogre", "cornerstone"}
# Words right before a Pokemon slot: "my moth", "vs gross", "ohko crown"
SLOT_WORDS = {"my", "your", "their", "opposing", "opp", "enemy", "vs", "versus", "against", "than",
              "does", "can", "outspeed", "outspeeds", "ohko", "ohkos", "2hko", "ko", "kos", "kill", "beat", "check"}
# Regional forme suffix -> the adjective players use ("Ninetales-Alola" -> "Alolan Ninetales")
REGION_ADJ = {"Alola": "alolan", "Galar": "galarian", "Hisui": "hisuian", "Paldea": "paldean"}
# Base formes the dex has no name for, so "Single Strike Urshifu" still resolves
BASE_FORMES = {"Urshifu": "Single Strike", "Landorus": "Incarnate", "Tornadus": "Incarnate",
               "Thundurus": "Incarnate", "Enamorus": "Incarnate", "Ogerpon": "Teal"}

# Tokens that look like names to a fuzzy matcher but are normal question words
COMMON_WORDS = {
    "outspeed", "outspeeds", "faster", "slower", "survive", "survives", "damage", "percent", "percentage",
    "attack", "attacks", "special", "defense", "immune", "resist", "resists", "neutral", "effective",
    "common", "spread", "ladder", "ability", "abilities", "health", "boosts", "effects", "evolving",
    "evolves", "running", "assume", "ignore", "item", "items", "stat", "stats", "speed", "level",
    "champions", "against", "should", "would", "could", "which", "where", "there", "their", "about",
    "after", "before", "usage", "smogon", "standard", "pokemon", "team", "teams", "matchup", "switch",
}


def norm(text):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def _mega_aliases(name):
    """'Garchomp-Mega-Z' -> ['mega garchomp z', 'mega garchomp-z'...] so players can say it either way."""
    parts = name.split("-Mega")
    if len(parts) != 2:
        return []
    base, suffix = norm(parts[0]), norm(parts[1])
    return [f"mega {base} {suffix}".strip(), f"{base} mega {suffix}".strip()]


def _norm_map(text):
    """norm(text) padded with spaces, plus the raw index of each normalised character."""
    out, idx = [" "], [0]
    for i, ch in enumerate(text or ""):
        c = ch.lower()
        if len(c) == 1 and ("a" <= c <= "z" or "0" <= c <= "9"):
            out.append(c)
            idx.append(i)
        elif out[-1] != " ":
            out.append(" ")
            idx.append(i)
    if out[-1] != " ":
        out.append(" ")
        idx.append(len(text or ""))
    return "".join(out), idx


def _nickname_ok(query, start, end):
    """An English word nickname ('moth', 'gross') counts only where a Pokemon fits."""
    raw = query[start:end]
    before = query[:start].rstrip()
    if raw[:1].isupper() and before and before[-1] not in ".?!:":
        return True
    if re.match(r"['\u2019]s\b", query[end:]):
        return True
    prev = re.findall(r"[a-z0-9]+", before.lower())
    return bool(prev) and prev[-1] in SLOT_WORDS


@lru_cache(maxsize=1)
def _forme_aliases():
    """Aliases built from dex forme data: 'alolan ninetales', 'wash rotom', 'rotom w', 'black kyurem'."""
    from metamatch.engine.dex import get_dex
    bases = {}
    for game in ("sv", "champions"):
        dex = get_dex(game)
        for name, data in (dex.species_data.items() if dex else []):
            base = data.get("baseSpecies")
            if base and name.startswith(base + "-"):
                forme = name[len(base) + 1:]
                if not re.search(r"Mega|Gmax|Totem|Tera$", forme):
                    bases.setdefault(base, {})[name] = forme
    pairs = {}
    for base, formes in bases.items():
        b = norm(base)
        initials = [f[0].lower() for f in formes.values()]
        for name, forme in formes.items():
            f = norm(forme)
            pairs.setdefault(f"{f} {b}", name)
            region, _, rest = forme.partition("-")
            if region in REGION_ADJ:
                adj, rest = REGION_ADJ[region], norm(rest)
                pairs.setdefault(f"{adj} {b} {rest}".strip(), name)
                if rest:
                    pairs.setdefault(f"{adj} {rest} {b}", name)
            # One letter short forms ("Rotom W") only when unambiguous and not an English word ("Ninetales a")
            letter = forme[0].lower()
            if "-" not in forme and initials.count(letter) == 1 and letter not in "ai":
                pairs.setdefault(f"{b} {letter}", name)
    for base, forme in BASE_FORMES.items():
        pairs.setdefault(f"{norm(forme)} {norm(base)}", base)
        pairs.setdefault(f"{norm(base)} {norm(forme)}", base)
    return pairs


@lru_cache(maxsize=1)
def _usage_names():
    """Species on this month's usage list (topPoke.json), which changes with every stats update."""
    try:
        with open(config.JSON_DIR / "topPoke.json", encoding="utf-8") as f:
            return tuple(json.load(f).keys())
    except (OSError, json.JSONDecodeError):
        return ()


@lru_cache(maxsize=1)
def _dex_names():
    """Every species in the bundled dexes, so a Pokemon that drops off the usage list is still recognised."""
    from metamatch.engine.dex import get_dex
    names = []
    for game in ("sv", "champions"):
        dex = get_dex(game)
        if dex:
            names.extend(dex.species_data)
    return tuple(dict.fromkeys(names))


@lru_cache(maxsize=1)
def _index():
    """(alias, display) pairs, longest alias first so 'Rotom-Wash' beats 'Rotom'."""
    names = list(dict.fromkeys(_usage_names() + _dex_names()))
    pairs = {norm(n): n for n in names}
    for n in names:
        for alias in _mega_aliases(n):
            pairs.setdefault(alias, n)
    known = set(names)
    for alias, target in _forme_aliases().items():
        if target in known:
            pairs.setdefault(alias, target)
    for alias, target in NICKNAMES.items():
        if target in known:
            pairs.setdefault(alias, target)
    return tuple(sorted(pairs.items(), key=lambda x: len(x[0]), reverse=True))


@lru_cache(maxsize=1)
def _game_words():
    """Words from move, item and ability names ('helmet', 'meteor'), which typo matching must skip."""
    from metamatch.engine.dex import get_dex
    words = set()
    for game in ("sv", "champions"):
        dex = get_dex(game)
        if dex:
            for name in list(dex.move_data) + list(dex.item_data) + dex.ability_names:
                words.update(norm(name).split())
    return words


@lru_cache(maxsize=1)
def _fuzzy_targets():
    """Single and two word names that typos are matched against."""
    # Usage list names only: typo matching against every dex entry (CAP, battle formes) misfires far more often
    usage = set(_usage_names())
    return {alias: display for alias, display in _index()
            if display in usage and len(alias) >= 5 and alias.count(" ") <= 1
            and alias not in AMBIGUOUS_NICKNAMES and len(alias.split()[-1]) > 1}


def find_pokemon_spans(query):
    """(start, end, display) for every Pokemon mention, as raw character offsets into `query`, in order."""
    text, idx = _norm_map(query)
    found = []
    for alias, display in _index():
        key = f" {alias} "
        pos = text.find(key)
        while pos >= 0:
            start, end = idx[pos + 1], idx[pos + len(alias)] + 1
            if alias in AMBIGUOUS_NICKNAMES and not _nickname_ok(query, start, end):
                pos = text.find(key, pos + 1)
                continue
            found.append((start, end, display))
            # Blank out the match (keeping the boundary spaces) so 'Rotom' doesn't also fire inside 'Rotom Wash'
            text = text[:pos + 1] + " " * len(alias) + text[pos + 1 + len(alias):]
            pos = text.find(key)

    # Typos: whatever words are left, matched closely against known names
    targets = _fuzzy_targets()
    words = [(m.start(), m.group()) for m in re.finditer(r"[a-z0-9]+", text)]
    for i, (pos, word) in enumerate(words):
        if len(word) < 5 or word in COMMON_WORDS or word in _game_words() or word.isdigit():
            continue
        candidates = [word]
        if i + 1 < len(words):
            candidates.insert(0, f"{word} {words[i + 1][1]}")
        for cand in candidates:
            match = difflib.get_close_matches(cand, targets, n=1, cutoff=0.85)
            if match and targets[match[0]] not in [d for _, _, d in found]:
                found.append((idx[pos], idx[pos + len(cand) - 1] + 1, targets[match[0]]))
                break
    return sorted(found)


def find_pokemon(query):
    """Pokemon named in the query, in the order they appear."""
    return list(dict.fromkeys(d for _, _, d in find_pokemon_spans(query)))
