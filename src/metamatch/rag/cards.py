"""
Smogon analysis cards: a Pokemon's strategy text shown verbatim under a chat answer, with where it comes from.
The text is never given to the model and never treated as a fact; it is a cited reference for the trainer.

Which text is shown (the user's rule, 2026 11 15): the current format's overview; else the best overview from another
tier of the same game; else an older game's overview, labelled as how the Pokemon was played then and flagged when it
mentions mechanics the current game lacks; else the current format's set descriptions. For the top 40 Gen 9 OU
Pokemon, 28 lack an SV OU overview and this chain finds text for 27 of them.
Cache: data/knowledge/smogon/<source>.json, filled by scripts/fetch_smogon_analyses.py (gitignored).
"""
import json
import re
from functools import lru_cache

from bs4 import BeautifulSoup

from metamatch import config
from metamatch.engine.dex import to_id

CACHE_DIR = config.DATA_DIR / "knowledge" / "smogon"
# Source key -> (game label, tier label, is the current game)
SOURCES = {
    "gen9ou": ("SV", "OU", True), "gen9uu": ("SV", "UU", True), "gen9ru": ("SV", "RU", True), "gen9nu": ("SV", "NU", True),
    "gen9ubers": ("SV", "Ubers", True), "gen9nationaldex": ("SV", "National Dex", True),
    "championsou": ("Champions", "OU", True),
    "gen8ou": ("Gen 8", "OU", False), "gen8uu": ("Gen 8", "UU", False), "gen8ubers": ("Gen 8", "Ubers", False),
    "gen7ou": ("Gen 7", "OU", False), "gen6ou": ("Gen 6", "OU", False),
}
# The current format's own analyses, then the rest of its game, then older games
FORMAT_SOURCE = {"gen9ou": "gen9ou", "gen9uu": "gen9uu", "gen9nationaldex": "gen9nationaldex",
                 "gen9championsou": "championsou", "gen9championsuu": "championsou"}
OLD_MECHANICS = re.compile(r"\b(?:Dynamax\w*|Max (?:Airstream|Quake|Knuckle|Steelspike|Overgrowth|Flare|Geyser)|"
                           r"Z-?Moves?|Z-Crystal|\w+ium Z|Mega Evolution|Mega Evolve\w*)\b", re.I)
MAX_CHARS = 900


@lru_cache(maxsize=None)
def _load(key):
    try:
        return json.loads((CACHE_DIR / f"{key}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _text(html):
    return re.sub(r"\s+", " ", BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)).strip()


def _entry(data, name):
    if name in data:
        return data[name]
    target = to_id(name)
    return next((v for k, v in data.items() if to_id(k) == target), None)


def _trim(text, limit=MAX_CHARS):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    return cut[:end + 1] if end > limit // 2 else cut + "..."


def _order(format_id):
    """Source keys in the order the chain tries them for this format."""
    own = FORMAT_SOURCE.get(format_id, "gen9ou")
    game_sv = config.format_game(format_id) == "sv"
    same_game = [k for k, (_, _, current) in SOURCES.items() if current and k != own
                 and (k != "championsou" if game_sv else k == "championsou")]
    older = [k for k, (_, _, current) in SOURCES.items() if not current]
    return [own] + same_game + older


def card(pokemon, format_id):
    """(label, text, note) for the best Smogon analysis text about `pokemon`, or None. `note` warns when an older
    game's text mentions mechanics the current game doesn't have."""
    order = _order(format_id)
    # Champions is new enough that almost nothing has an overview yet: its own current set text beats an old game's
    if config.format_game(format_id) == "champions":
        e = _entry(_load(order[0]), pokemon)
        for name, s in ((e or {}).get("sets") or {}).items():
            if s.get("description"):
                return f"{_label(order[0])}, {name} set", _trim(_text(s["description"])), ""
    # Overviews first, anywhere in the chain
    for key in order:
        e = _entry(_load(key), pokemon)
        if e and e.get("overview"):
            return _label(key), _trim(_text(e["overview"])), _note(key, e["overview"], format_id)
    # Then the first set description, preferring the current format
    for key in order:
        e = _entry(_load(key), pokemon)
        for name, s in ((e or {}).get("sets") or {}).items():
            if s.get("description"):
                return f"{_label(key)}, {name} set", _trim(_text(s["description"])), _note(key, s["description"], format_id)
    return None


def _label(key):
    game, tier, current = SOURCES[key]
    return f"From the {game} {tier} analysis" + ("" if current else " (how it was played then)")


def _note(key, html, format_id):
    if SOURCES[key][2]:
        return ""
    champions = config.format_game(format_id) == "champions"
    hit = OLD_MECHANICS.search(_text(html))
    if hit and not (champions and "mega" in hit.group(0).lower()):
        return f"Mentions {hit.group(0)}, which this game doesn't have."
    return ""


def cards_for(names, format_id, limit=2):
    """Cards for up to `limit` Pokemon, in order, skipping ones with no text."""
    out = []
    for name in names:
        c = card(name, format_id)
        if c:
            out.append(c)
        if len(out) == limit:
            break
    return out
