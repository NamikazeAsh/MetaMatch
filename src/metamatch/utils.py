import requests
import re
import json
import os
import time
from . import config

CACHE_FILE = config.JSON_DIR / "api_cache.json"
CACHE_MAX_ENTRIES = 2000
CACHE_EVICT_COUNT = 200
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days


def _entry_ts(entry) -> float:
    """Return timestamp of a cache entry, or 0 for legacy flat entries."""
    if isinstance(entry, dict) and "ts" in entry:
        return entry["ts"]
    return 0.0


def _entry_data(entry):
    """Unwrap a cache entry, handling both new {data, ts} and legacy flat formats."""
    if isinstance(entry, dict) and "ts" in entry and "data" in entry:
        return entry["data"]
    return entry  # legacy flat entry


def _wrap(data) -> dict:
    return {"data": data, "ts": time.time()}


def load_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                raw = json.load(f)
            # Evict stale entries (TTL check) on load
            now = time.time()
            return {
                k: v for k, v in raw.items()
                if now - _entry_ts(v) < CACHE_TTL_SECONDS or _entry_ts(v) == 0.0
            }
        except:
            return {}
    return {}


def save_cache(cache):
    # Size cap: if over limit, drop the oldest entries
    if len(cache) > CACHE_MAX_ENTRIES:
        sorted_keys = sorted(cache, key=lambda k: _entry_ts(cache[k]))
        for k in sorted_keys[:CACHE_EVICT_COUNT]:
            del cache[k]

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


# Global in-memory cache to reduce reads
API_CACHE = load_cache()

def pokeSlugify(name):
    """
    Normalize Pokemon names for API/Smogon usage.
    Handles tricky forms like Ogerpon, Urshifu, and Paradox mons.
    """
    name = name.lower().strip()
    # Remove gender
    name = re.sub(r'\s*\([mf]\)$', '', name)
    name = name.replace(" ", "-")
    name = name.replace(".", "")
    name = name.replace("'", "")
    name = name.replace("%", "")
    
    # Explicit Mappings for PokeAPI quirks
    special_cases = {
        # Ogerpon
        "ogerpon-wellspring": "ogerpon-wellspring-mask",
        "ogerpon-hearthflame": "ogerpon-hearthflame-mask",
        "ogerpon-cornerstone": "ogerpon-cornerstone-mask",
        "ogerpon-teal": "ogerpon",
        
        # Urshifu
        "urshifu-rapid-strike": "urshifu-rapid-strike",
        "urshifu": "urshifu-single-strike", # Default if unspecified
        
        # Paldean Tauros
        "tauros-paldea-water": "tauros-paldea-aqua-breed",
        "tauros-paldea-fire": "tauros-paldea-blaze-breed",
        "tauros-paldea-combat": "tauros-paldea-combat-breed",
        
        # Enamorus / Basculegion
        "enamorus": "enamorus-incarnate",
        "enamorus-therian": "enamorus-therian",
        "basculegion": "basculegion-male",
        "basculegion-f": "basculegion-female",
        
        # Paradox / Others
        "iron-valiant": "iron-valiant", # Already correct but good to be explicit
        "roaring-moon": "roaring-moon",
        "great-tusk": "great-tusk",
        "scream-tail": "scream-tail",
        "flutter-mane": "flutter-mane",
        "slither-wing": "slither-wing",
        "sandy-shocks": "sandy-shocks",
        "iron-treads": "iron-treads",
        "iron-bundle": "iron-bundle",
        "iron-hands": "iron-hands",
        "iron-jugulis": "iron-jugulis",
        "iron-moth": "iron-moth",
        "iron-thorns": "iron-thorns",
        "wo-chien": "wo-chien",
        "chien-pao": "chien-pao",
        "ting-lu": "ting-lu",
        "chi-yu": "chi-yu",
        
        # Megas / Forms (if you ever add Gen 6/7)
        "mimikyu": "mimikyu-disguised",
        "aegislash": "aegislash-shield",
        "giratina": "giratina-altered",
        "shaymin": "shaymin-land",
        "keldeo": "keldeo-ordinary",
    }
    
    if name in special_cases:
        return special_cases[name]
        
    return name

def fetch_pokemon_data(name):
    """
    Fetches full Pokemon data (types, stats, sprites) with caching.
    """
    slug = pokeSlugify(name)

    # Check cache — support both new {data, ts} and legacy flat entries
    if slug in API_CACHE:
        cached = _entry_data(API_CACHE[slug])
        if isinstance(cached, dict) and 'stats' in cached:
            return cached

    url = f"https://pokeapi.co/api/v2/pokemon/{slug}"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()

            processed_data = {
                'types': [t["type"]["name"].capitalize() for t in data["types"]],
                'stats': {s["stat"]["name"]: s["base_stat"] for s in data["stats"]},
                'sprite': data['sprites']['front_default'],
                'abilities': [a['ability']['name'] for a in data['abilities']]
            }

            API_CACHE[slug] = _wrap(processed_data)
            save_cache(API_CACHE)
            return processed_data
    except Exception as e:
        print(f"Error fetching {name}: {e}")

    return None

def calculate_speed(base_speed, ev=0, iv=31, nature_mod=1.0, item=""):
    """
    Calculates the actual Speed stat at Level 100.
    """
    # Stat Formula: floor(((2 * Base + IV + (EV/4)) * Level / 100) + 5) * Nature
    level = 100
    stat = int(((2 * base_speed + iv + (ev / 4)) * level / 100) + 5)
    stat = int(stat * nature_mod)
    
    # Apply Items
    if item.lower() == "choice scarf":
        stat = int(stat * 1.5)
    elif item.lower() == "iron ball":
        stat = int(stat * 0.5)
        
    return stat


def fetch_ability_data(ability_name: str) -> str:
    """
    Fetches the short effect description of an ability from PokeAPI.
    Returns a plain-English string like 'Doubles Speed in harsh sunlight.'
    Returns empty string on failure.
    """
    slug = ability_name.lower().strip().replace(" ", "-").replace("'", "")
    cache_key = f"ability::{slug}"

    if cache_key in API_CACHE:
        cached = _entry_data(API_CACHE[cache_key])
        if isinstance(cached, str):
            return cached

    url = f"https://pokeapi.co/api/v2/ability/{slug}"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            # Prefer English short_effect; fall back to effect
            for entry in data.get("effect_entries", []):
                if entry.get("language", {}).get("name") == "en":
                    desc = entry.get("short_effect", entry.get("effect", "")).strip()
                    API_CACHE[cache_key] = _wrap(desc)
                    save_cache(API_CACHE)
                    return desc
    except Exception as e:
        print(f"Error fetching ability {ability_name}: {e}")

    return ""


def fetch_move_data(move_name):
    """
    Fetches move metadata from PokeAPI.
    """
    slug = move_name.lower().replace(" ", "-").replace("'", "")
    cache_key = f"move::{slug}"
    default = {'type': None, 'power': None, 'accuracy': None, 'category': None}

    if cache_key in API_CACHE:
        cached = _entry_data(API_CACHE[cache_key])
        if isinstance(cached, dict) and 'type' in cached:
            return cached

    url = f"https://pokeapi.co/api/v2/move/{slug}"
    try:
        res = requests.get(url, timeout=3)
        if res.status_code != 200:
            return default

        data = res.json()
        processed = {
            'type': data['type']['name'].capitalize(),
            'power': data['power'],
            'accuracy': data['accuracy'],
            'category': data['damage_class']['name'].capitalize()
        }
        API_CACHE[cache_key] = _wrap(processed)
        save_cache(API_CACHE)
        return processed
    except Exception:
        return default


# --- Pokepaste Integration ---
POKEPASTE_PATTERN = re.compile(r'pokepast\.es/([a-zA-Z0-9]+)')

def is_pokepaste_url(text: str) -> bool:
    """Check if text contains a pokepast.es URL."""
    return bool(POKEPASTE_PATTERN.search(text.strip()))

def fetch_pokepaste(url_or_id: str) -> str | None:
    """
    Fetch raw team export from pokepast.es.
    Accepts full URL or just the paste ID.
    Returns the raw Showdown export text, or None on failure.
    """
    text = url_or_id.strip()
    
    # Extract ID from URL if needed
    match = POKEPASTE_PATTERN.search(text)
    if match:
        paste_id = match.group(1)
    else:
        paste_id = text  # Assume it's just the ID
    
    try:
        raw_url = f"https://pokepast.es/{paste_id}/raw"
        resp = requests.get(raw_url, timeout=5)
        if resp.status_code == 200:
            # Normalize line endings (pokepaste returns \r\n)
            return resp.text.replace('\r\n', '\n').strip()
        return None
    except Exception:
        return None

def is_showdown_export(text: str) -> bool:
    """
    Detect if text looks like a Showdown team export.
    Checks for common patterns like '@' (item), 'Ability:', 'EVs:', 'Nature'.
    """
    text = text.strip()
    if not text:
        return False
    # Must have at least one Pokemon with item OR ability line
    has_item = '@' in text
    has_ability = 'Ability:' in text
    has_nature = 'Nature' in text
    has_move = text.count('\n-') >= 1
    return (has_item or has_ability) and (has_nature or has_move)
