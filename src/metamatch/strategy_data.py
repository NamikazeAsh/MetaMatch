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
                        'nature': set_data.get('nature', 'None')
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

def load_usage_stats():
    """Every chaos file in the stats folder: {file stem: {pokemon: chaos entry}}."""
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
    Pokemon whose ladder sets run every target move on at least `threshold` percent of sets, in any loaded
    format: [{pokemon, format, source: 'usage', moves: {move: usage %}}]. usage_data defaults to load_usage_stats().
    """
    if usage_data is None:
        usage_data = load_usage_stats()
        
    results = []
    targets_norm = [m.lower().replace("-", "").replace(" ", "") for m in target_moves]
    
    for fmt, p_data in usage_data.items():
        # Display label for the stats file
        fmt_id = config.format_from_stats_stem(fmt)
        if fmt_id:
            fmt_label = config.FORMATS[fmt_id]["label"]
        else: 
            # A file for an unregistered format: its name without the rating suffix
            fmt_label = fmt.split("-")[0].replace("gen9", "").upper()
            if not fmt_label: fmt_label = fmt

        for pokemon, stats in p_data.items():
            moves_stats = stats.get('Moves', {})
            # Abilities sum to the Pokemon's total weight, so a move's share is its weight over that
            total_usage = sum(stats.get('Abilities', {}).values())
            if total_usage == 0: total_usage = 1
            
            match = True
            found_moves = {}
            
            for t in targets_norm:
                # Chaos move keys are ids; compare without case, spaces or hyphens
                found = False
                for m_key, m_val in moves_stats.items():
                    if m_key.lower().replace("-", "").replace(" ", "") == t:
                        usage_pct = (m_val / total_usage) * 100
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
                    "moves": found_moves
                })
                
    return results

def get_all_known_moves(data=None, usage_data=None):
    """
    Every move in the Strategy Dex and the usage stats, sorted. Strategy Dex names ('Thunder Wave') win over
    the usage files' ids ('thunderwave'); an id only appears when no set spells it out.
    """
    unique_moves = set()
    norm_map = {}   # "thunderwave" -> "Thunder Wave"

    if data is None:
        data = ensure_strategy_data()
    
    for pokemon, analysis in data.items():
        if 'sets' in analysis:
            for set_data in analysis['sets'].values():
                for move in set_data.get('moves', []):
                    unique_moves.add(move)
                    norm = move.lower().replace("-", "").replace(" ", "")
                    norm_map[norm] = move

    # Usage stats add the moves no Strategy Dex set runs
    if usage_data is None:
        usage_data = load_usage_stats()
        
    for fmt_data in usage_data.values():
        for p_stats in fmt_data.values():
            for m in p_stats.get('Moves', {}).keys():
                if not m: continue
                
                m_norm = m.lower().replace("-", "").replace(" ", "")
                
                if m_norm in norm_map:
                    continue
                else:
                    unique_moves.add(m)
                    
    return sorted(list(unique_moves), key=lambda x: x.lower())

def find_sets_with_moves(target_moves, data=None):
    """
    Strategy Dex sets that run every target move (names compared without case, spaces or hyphens):
    [{pokemon, set_name, item, ability, nature, moves, formats}]. data defaults to the combined sets.
    """
    if data is None:
        data = ensure_strategy_data()
        
    results = []
    
    targets_norm = [m.lower().replace("-", "").replace(" ", "") for m in target_moves]
    
    for pokemon, analysis in data.items():
        if 'sets' not in analysis:
            continue
            
        for set_name, set_data in analysis['sets'].items():
            set_moves = set_data.get('moves', [])
            
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
