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


@lru_cache(maxsize=1)
def _index():
    """(alias, display) pairs, longest alias first so 'Rotom-Wash' beats 'Rotom'."""
    try:
        with open(config.JSON_DIR / "topPoke.json", encoding="utf-8") as f:
            names = list(json.load(f).keys())
    except (OSError, json.JSONDecodeError):
        names = []
    pairs = {norm(n): n for n in names}
    for n in names:
        for alias in _mega_aliases(n):
            pairs.setdefault(alias, n)
    known = set(names)
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
    return {alias: display for alias, display in _index() if len(alias) >= 5 and alias.count(" ") <= 1}


def find_pokemon(query):
    """Pokemon named in the query, in the order they appear."""
    text = f" {norm(query)} "
    found = []
    for alias, display in _index():
        key = f" {alias} "
        pos = text.find(key)
        while pos >= 0:
            if display not in [d for _, d in found]:
                found.append((pos, display))
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
            if match and targets[match[0]] not in [d for _, d in found]:
                found.append((pos, targets[match[0]]))
                break
    return [display for _, display in sorted(found)]
