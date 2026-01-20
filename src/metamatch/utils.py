import requests
import re
import json
import os
from . import config

CACHE_FILE = config.JSON_DIR / "api_cache.json"

def load_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(cache):
    # Ensure directory exists
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
    }
    
    if name in special_cases:
        return special_cases[name]
        
    return name

def fetch_pokemon_data(name):
    """
    Fetches full Pokemon data (types, stats, sprites) with caching.
    """
    slug = pokeSlugify(name)
    
    # Check Cache
    if slug in API_CACHE and 'stats' in API_CACHE[slug]:
        return API_CACHE[slug]
    
    url = f"https://pokeapi.co/api/v2/pokemon/{slug}"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            
            # Extract only what we need to save space
            processed_data = {
                'types': [t["type"]["name"].capitalize() for t in data["types"]],
                'stats': {s["stat"]["name"]: s["base_stat"] for s in data["stats"]},
                'sprite': data['sprites']['front_default'],
                'abilities': [a['ability']['name'] for a in data['abilities']]
            }
            
            # Update Cache
            API_CACHE[slug] = processed_data
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