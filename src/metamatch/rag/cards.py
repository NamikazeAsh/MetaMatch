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
# Keyed by the app's format ids (config.FORMATS): National Dex is "gen9natdex", its Smogon source "gen9nationaldex"
FORMAT_SOURCE = {"gen9ou": "gen9ou", "gen9uu": "gen9uu", "gen9natdex": "gen9nationaldex",
                 "gen9championsou": "championsou", "gen9championsuu": "championsou"}
OLD_MECHANICS = re.compile(r"\b(?:Dynamax\w*|Max (?:Airstream|Quake|Knuckle|Steelspike|Overgrowth|Flare|Geyser)|"
                           r"Z-?Moves?|Z-Crystal|\w+ium Z|Mega Evolution|Mega Evolve\w*)\b", re.I)
MAX_CHARS = 900
MIRROR = "https://pkmn.github.io/smogon/data/analyses/{}.json"


def mega_analysis(base, forme, moves, format_id):
    """(label, preview, [the rest, by paragraph]) of the Smogon analysis set for a Mega on this team, or None. Smogon files a Mega's
    analysis under its base species, so the set is the one that talks about this Mega (by name: Mega Charizard Y, not
    X) and shares the most moves with the team's own. Only the format's own analysis counts: an older game's Mega
    played in a different metagame, so its text would mislead more than help."""
    key = FORMAT_SOURCE.get(format_id)
    if not key:
        return None
    entry = _entry(_load(key), base) or _entry(_load(key), forme) or {}
    head, _, rest = forme.partition("-Mega")
    called = f"Mega {head}" + (f" {rest.lstrip('-')}" if rest else "")
    mine = [m.lower() for m in moves]
    best, score = None, -1
    for set_name, s in (entry.get("sets") or {}).items():
        text = _text(s.get("description"))
        low = text.lower()
        # A set that only names other Megas ("hits Mega Dragalge") is about the base forme
        if f"mega {head.lower()}" not in low:
            continue
        points = (5 if called.lower() in low else 0) + sum(1 for m in mine if m in low)
        if points > score:
            best, score = (set_name, text), points
    if not best:
        return None
    set_name, _ = best
    html = (entry["sets"][set_name] or {}).get("description") or ""
    paragraphs = [re.sub(r"\s+", " ", p.get_text(" ", strip=True)) for p in BeautifulSoup(html, "html.parser").find_all("p")]
    paragraphs = [p for p in paragraphs if p] or [_text(html)]
    sentences = re.split(r"(?<=[.!?])\s+", paragraphs[0])
    preview, first_rest = " ".join(sentences[:2]), " ".join(sentences[2:])
    rest = ([first_rest] if first_rest else []) + paragraphs[1:]
    # Smogon is credited in the docs; the card just heads its quote
    return "The play", preview, rest


@lru_cache(maxsize=None)
def _load(key):
    """One source's analyses: the local cache, else fetched once from the pkmn.github.io mirror and kept. The cache is
    gitignored (Smogon's prose isn't republished in the repo), so a cloud deploy fills it on first use instead."""
    path = CACHE_DIR / f"{key}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if key not in SOURCES:
        return {}
    try:
        import requests
        resp = requests.get(MIRROR.format(key), timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:   # offline or the mirror moved: no card, never an error
        print(f"Smogon analyses for {key} unavailable: {e}")
        return {}
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass
    return data


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
