import requests
import json
from . import config

# Smogon Strategy Dex sets per format (pkmn.github.io's structured sets files). Champions has none published yet.
STRATEGY_SOURCES = {
    f["label"]: f"https://pkmn.github.io/smogon/data/sets/{f['sets']}.json"
    for f in config.FORMATS.values() if f["sets"]
}

LOCAL_STRATEGY_FILE = config.JSON_DIR / "strategies_combined.json"

def ensure_strategy_data():
    """The combined Strategy Dex sets, downloaded and merged on first use."""
    if not LOCAL_STRATEGY_FILE.exists():
        return update_strategy_cache()
    
    return load_strategy_data()

def update_strategy_cache():
    """
    Downloads every format's sets file and merges them into one {pokemon: {sets, formats}} file. A format that
    fails to download is skipped, not fatal.
    """
    print("Building Master Strategy Database...")
    master_data = {}

    for format_name, url in STRATEGY_SOURCES.items():
        print(f"Fetching {format_name} strategies...")
        try:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            data = res.json()
            
            for pokemon, sets_dict in data.items():
                if pokemon not in master_data:
                    master_data[pokemon] = {
                        'sets': {},
                        'formats': []
                    }
                
                if format_name not in master_data[pokemon]['formats']:
                    master_data[pokemon]['formats'].append(format_name)
                
                # Set names get the format appended, so the same set name in two formats stays two sets
                for set_name, set_data in sets_dict.items():
                    unique_set_name = f"{set_name} ({format_name})"
                    
                    # A move slot is a name or a list of alternatives ([['Dragon Darts', 'Draco Meteor'], 'Hex']),
                    # flattened so a search matches any of them
                    flat_moves = []
                    raw_moves = set_data.get('moves', [])
                    for slot in raw_moves:
                        if isinstance(slot, list):
                            flat_moves.extend(slot)
                        else:
                            flat_moves.append(slot)
                    
                    master_data[pokemon]['sets'][unique_set_name] = {
                        'moves': flat_moves,
                        'item': set_data.get('item', 'None'),
                        'ability': set_data.get('ability', 'None'),
                        'nature': set_data.get('nature', 'None'),
                        # Smogon's recommended Tera types for the set (Scarlet and Violet formats only)
                        'teratypes': [t for t in ([set_data['teratypes']] if isinstance(set_data.get('teratypes'), str)
                                                  else set_data.get('teratypes') or [])]
                    }

        except Exception as e:
            print(f"Error fetching {format_name}: {e}")

    try:
        with open(LOCAL_STRATEGY_FILE, "w", encoding='utf-8') as f:
            json.dump(master_data, f, indent=2)
        print(f"Successfully cached strategies for {len(master_data)} Pokemon.")
    except Exception as e:
        print(f"Error saving strategy cache: {e}")
        
    return master_data

def load_strategy_data():
    """The combined Strategy Dex sets on disk, or {} when missing or unreadable."""
    if LOCAL_STRATEGY_FILE.exists():
        try:
            with open(LOCAL_STRATEGY_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}
