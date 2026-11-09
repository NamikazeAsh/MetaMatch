import re
import requests
import json
from bs4 import BeautifulSoup
from .utils import fetch_pokemon_data, calculate_speed
from . import config
from .engine.dex import get_dex

TIMEOUT = 60  # seconds; chaos files are several MB


def download_stat_file(stats_url, target_filename, local_name=None, dest_dir=None):
    """
    Downloads a specific stat file from the Smogon stats index page.
    Saves it to dest_dir (default the 'stats/' directory) as local_name if given, and returns the local path.
    """
    try:
        response = requests.get(stats_url, timeout=TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        link = soup.find('a', href=target_filename)
        if not link:
            print(f"Warning: Could not find '{target_filename}' at {stats_url}")
            return None
            
        file_url = stats_url + target_filename
        file_response = requests.get(file_url, timeout=TIMEOUT)
        file_response.raise_for_status()
        
        local_path = (dest_dir or config.STATS_DIR) / (local_name or target_filename)
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(file_response.text)
            
        print(f"Successfully downloaded and saved '{target_filename}' to '{local_path}'")
        return local_path
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading stats: {e}")
        return None

def parse_smogon_usage(path, top_n=100):
    """
    Parses a smogon usage stats file and returns a list of top Pokémon names.
    """
    if not path:
        return []
    # Matches the Pokémon name column in Smogon's table format: | Rank | Name | ...
    pat = re.compile(r'^\s*\| \d+\s+\| ([^|]+?) \|')
    names = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                m = pat.search(line)
                if not m:
                    continue
                names.append(m.group(1).strip())
        return names[:top_n] if top_n else names
    except FileNotFoundError:
        print(f"Error: Could not find file {path} to parse.")
        return []

def species_info(name, game="sv"):
    """(types, base Speed) from the bundled dex, falling back to PokeAPI, or None."""
    dex = get_dex(game) or get_dex("sv")
    species = dex.species(name) if dex else None
    if species:
        return species["types"], species["baseStats"]["spe"]
    data = fetch_pokemon_data(name)
    return (data["types"], data["stats"]["speed"]) if data else None


def generate_speed_tiers(pokemon_names, game="sv"):
    """
    Speed benchmarks for the format's top 30: each one's max Speed, and its Choice Scarf Speed when its base
    Speed is 80 or more. Returns [{label, speed, owner}], fastest first.
    """
    print(f"Generating Speed Tiers ({game})...")
    tiers = []
    
    if game == "champions":
        # Level 50, max investment is 32 stat points
        max_invest, min_speed = config.CHAMPIONS_SP_MAX, 100
    else:
        max_invest, min_speed = 252, 200
        # Two benchmarks players quote by name
        tiers.append({'label': 'Choice Scarf Gholdengo', 'speed': 447, 'owner': 'Gholdengo'})
        tiers.append({'label': 'Max Speed Dragapult', 'speed': 421, 'owner': 'Dragapult'})
    
    seen_speeds = set()
    
    for name in pokemon_names[:30]:
        info = species_info(name, game)
        if not info: continue
        
        base_spe = info[1]
        
        # Max Speed: full investment and a Speed nature
        max_spe = calculate_speed(base_spe, ev=max_invest, nature_mod=1.1, game=game)
        if max_spe > min_speed and max_spe not in seen_speeds:
            tiers.append({'label': f"Max {name}", 'speed': max_spe, 'owner': name})
            seen_speeds.add(max_spe)
            
        # Choice Scarf only for base 80 or faster; a Mega holds its stone, so it never has one
        if base_spe >= 80 and "-Mega" not in name:
            scarf_spe = int(max_spe * 1.5)
            if scarf_spe not in seen_speeds:
                tiers.append({'label': f"Scarf {name}", 'speed': scarf_spe, 'owner': name})
                seen_speeds.add(scarf_spe)

    return sorted(tiers, key=lambda x: x['speed'], reverse=True)

def speed_tiers_path(game):
    """Speed tiers are stored per game since SV (Lv100) and Champions (Lv50) numbers don't mix."""
    return config.JSON_DIR / ("meta_speeds_champions.json" if game == "champions" else "meta_speeds.json")

def refresh_derived():
    """
    Rebuilds topPoke.json and the speed tier files from the usage stats already in data/stats.
    Returns the number of Pokemon written to topPoke.json.
    """
    names_by_game = {}
    for fmt in config.FORMATS.values():
        names = parse_smogon_usage(config.STATS_DIR / (fmt["stats"] + ".txt"), top_n=1000)
        ordered = names_by_game.setdefault(fmt["game"], [])
        ordered.extend(n for n in names if n not in ordered)

    if not any(names_by_game.values()):
        print("No usage stats found in data/stats. Nothing to refresh.")
        return 0

    top_poke_data = {}
    for game, names in names_by_game.items():
        for name in names:
            info = None if name in top_poke_data else species_info(name, game)
            if info:
                top_poke_data[name] = info[0]

    with open(config.JSON_DIR / "topPoke.json", "w") as f:
        json.dump(top_poke_data, f, indent=2)

    # One speed tier file per game, from that game's usage order
    for game, names in names_by_game.items():
        if names:
            with open(speed_tiers_path(game), "w") as f:
                json.dump(generate_speed_tiers(names, game), f, indent=2)

    print(f"Refreshed topPoke.json ({len(top_poke_data)} Pokemon) and speed tiers.")
    return len(top_poke_data)


