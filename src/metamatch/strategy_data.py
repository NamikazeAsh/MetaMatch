import requests
import json
import os
from pathlib import Path
from . import config
from .utils import pokeSlugify

# Define sources for the Master Strategy Database
# We switch to the 'sets' endpoint for structured data
STRATEGY_SOURCES = {
    "OU": "https://pkmn.github.io/smogon/data/sets/gen9ou.json",
    "UU": "https://pkmn.github.io/smogon/data/sets/gen9uu.json",
    "NatDex": "https://pkmn.github.io/smogon/data/sets/gen9nationaldex.json"
}

LOCAL_STRATEGY_FILE = config.JSON_DIR / "strategies_combined.json"

def ensure_strategy_data():
    """
    Checks if the combined strategy data exists locally.
    If not, downloads and merges data from all sources.
    """
    if not LOCAL_STRATEGY_FILE.exists():
        return update_strategy_cache()
    
    return load_strategy_data()

def update_strategy_cache():
    """
    Downloads raw JSONs from Smogon for multiple formats,
    merges them into a single dictionary, and saves it.
    """
    print("Building Master Strategy Database...")
    master_data = {}

    for format_name, url in STRATEGY_SOURCES.items():
        print(f"Fetching {format_name} strategies...")
        try:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            data = res.json()
            
            # Merge logic
            for pokemon, sets_dict in data.items():
                if pokemon not in master_data:
                    master_data[pokemon] = {
                        'sets': {},
                        'formats': []
                    }
                
                # Update Formats List
                if format_name not in master_data[pokemon]['formats']:
                    master_data[pokemon]['formats'].append(format_name)
                
                # Merge Sets
                for set_name, set_data in sets_dict.items():
                    unique_set_name = f"{set_name} ({format_name})"
                    
                    # Normalize Moves: 'moves' is a list of lists/strings in the raw data
                    # e.g. [['Dragon Darts', 'Draco Meteor'], 'Hex', ...]
                    # We need to flatten it for searching
                    flat_moves = []
                    raw_moves = set_data.get('moves', [])
                    for slot in raw_moves:
                        if isinstance(slot, list):
                            flat_moves.extend(slot)
                        else:
                            flat_moves.append(slot)
                    
                    # Store cleaned data
                    master_data[pokemon]['sets'][unique_set_name] = {
                        'moves': flat_moves,
                        'item': set_data.get('item', 'None'),
                        'ability': set_data.get('ability', 'None'),
                        'nature': set_data.get('nature', 'None')
                    }

        except Exception as e:
            print(f"Error fetching {format_name}: {e}")

    # Save combined file
    try:
        with open(LOCAL_STRATEGY_FILE, "w", encoding='utf-8') as f:
            json.dump(master_data, f, indent=2)
        print(f"Successfully cached strategies for {len(master_data)} Pokemon.")
    except Exception as e:
        print(f"Error saving strategy cache: {e}")
        
    return master_data

def load_strategy_data():
    """
    Loads the local strategy JSON.
    """
    if LOCAL_STRATEGY_FILE.exists():
        try:
            with open(LOCAL_STRATEGY_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def load_usage_stats():
    """
    Loads all available usage stats from the stats directory.
    Returns a dict: {'gen9ou': data_dict, ...}
    """
    stats = {}
    for f in config.STATS_DIR.glob("*.json"):
        if "chaos" in f.name or "1825" in f.name or "1760" in f.name:
            try:
                with open(f, "r", encoding='utf-8') as file:
                    content = json.load(file)
                    stats[f.stem] = content.get('data', {})
            except:
                continue
    return stats

def find_usage_matches(target_moves, usage_data=None, threshold=1.0):
    """
    Finds Pokemon that have >threshold% usage for ALL target moves in the stats.
    
    Args:
        target_moves (list): List of move strings.
        usage_data (dict): Pre-loaded usage stats.
        threshold (float): Minimum usage percentage to be considered a match.
        
    Returns:
        list: List of dicts {pokemon, format, moves: {move: usage_pct}}
    """
    if usage_data is None:
        usage_data = load_usage_stats()
        
    results = []
    targets_norm = [m.lower().replace("-", "").replace(" ", "") for m in target_moves]
    
    for fmt, p_data in usage_data.items():
        # Clean format name
        fmt_lower = fmt.lower()
        if "nationaldex" in fmt_lower or "natdex" in fmt_lower: 
            fmt_label = "NatDex"
        elif "gen9ou" in fmt_lower: 
            fmt_label = "OU"
        elif "gen9uu" in fmt_lower: 
            fmt_label = "UU"
        else: 
            # Fallback: remove version numbers and weights
            fmt_label = fmt.split("-")[0].replace("gen9", "").upper()
            if not fmt_label: fmt_label = fmt

        for pokemon, stats in p_data.items():
            moves_stats = stats.get('Moves', {})
            total_usage = sum(stats.get('Abilities', {}).values()) # Proxy for total count
            if total_usage == 0: total_usage = 1 # Avoid div/0
            
            match = True
            found_moves = {}
            
            for t in targets_norm:
                # Find the key in moves_stats (normalization required)
                found = False
                for m_key, m_val in moves_stats.items():
                    if m_key.lower().replace("-", "").replace(" ", "") == t:
                        usage_pct = (m_val / total_usage) * 100
                        # Check strict threshold
                        if usage_pct >= threshold:
                            found = True
                            found_moves[m_key] = usage_pct
                        break
                if not found:
                    match = False
                    break
            
            if match:
                results.append({
                    "pokemon": pokemon,
                    "format": fmt_label,
                    "source": "usage",
                    "moves": found_moves # {MoveName: Usage%}
                })
                
    return results

def get_all_known_moves(data=None, usage_data=None):
    """
    Scans both strategy dex AND usage stats to find all unique moves.
    Prioritizes formatted names (e.g. "Thunder Wave") over slugs (e.g. "thunderwave").
    """
    unique_moves = set()
    norm_map = {} # "thunderwave" -> "Thunder Wave"
    
    # 1. Strategy Dex (Source of Truth for formatting)
    if data is None:
        data = ensure_strategy_data()
    
    for pokemon, analysis in data.items():
        if 'sets' in analysis:
            for set_data in analysis['sets'].values():
                for move in set_data.get('moves', []):
                    unique_moves.add(move)
                    # Normalize for deduplication lookup
                    norm = move.lower().replace("-", "").replace(" ", "")
                    norm_map[norm] = move

    # 2. Usage Stats
    if usage_data is None:
        usage_data = load_usage_stats()
        
    for fmt_data in usage_data.values():
        for p_stats in fmt_data.values():
            for m in p_stats.get('Moves', {}).keys():
                if not m: continue
                
                # Check if we already have a formatted version of this move
                m_norm = m.lower().replace("-", "").replace(" ", "")
                
                if m_norm in norm_map:
                    # We already have "Thunder Wave", so ignore "thunderwave"
                    continue
                else:
                    # It's a new move (niche), likely a slug like "hiddenpowerfire"
                    # Add it, but maybe try to title case it for slightly better UI
                    # Or just add as is if we can't pretty it up safely
                    unique_moves.add(m)
                    
    return sorted(list(unique_moves), key=lambda x: x.lower())

def find_sets_with_moves(target_moves, data=None):
    """
    Finds all sets that contain ALL of the target moves.
    
    Args:
        target_moves (list): List of move strings (e.g. ["Scald", "Thunder Wave"])
        data (dict, optional): Pre-loaded strategy data.
        
    Returns:
        list: List of dicts with details.
    """
    if data is None:
        data = ensure_strategy_data()
        
    results = []
    
    # Normalize targets for comparison
    targets_norm = [m.lower().replace("-", "").replace(" ", "") for m in target_moves]
    
    for pokemon, analysis in data.items():
        if 'sets' not in analysis:
            continue
            
        for set_name, set_data in analysis['sets'].items():
            set_moves = set_data.get('moves', [])
            
            # Check if this set has ALL target moves
            # We use loose matching (ignoring case/spaces)
            set_moves_norm = [m.lower().replace("-", "").replace(" ", "") for m in set_moves]
            
            match = True
            for t in targets_norm:
                if t not in set_moves_norm:
                    match = False
                    break
            
            if match:
                results.append({
                    "pokemon": pokemon,
                    "set_name": set_name,
                    "item": set_data.get("item", "None"),
                    "ability": set_data.get("ability", "None"),
                    "nature": set_data.get("nature", "None"),
                    "moves": set_moves,
                    "formats": analysis.get('formats', [])
                })
                
    return results
