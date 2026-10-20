import re
import requests
import json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from .utils import pokeSlugify, fetch_pokemon_data, calculate_speed
from . import config

def get_latest_stats_url():
    """
    Calculates the URL for the previous month's Smogon stats directory.
    """
    today = datetime.today()
    first_day_of_current_month = today.replace(day=1)
    last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
    year = last_day_of_previous_month.year
    month = last_day_of_previous_month.month
    return f"https://www.smogon.com/stats/{year:04d}-{month:02d}/"

def download_stat_file(stats_url, target_filename):
    """
    Downloads a specific stat file from the Smogon stats index page.
    Saves it to the 'stats/' directory and returns the local path.
    """
    try:
        response = requests.get(stats_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        link = soup.find('a', href=target_filename)
        if not link:
            print(f"Warning: Could not find '{target_filename}' at {stats_url}")
            return None
            
        file_url = stats_url + target_filename
        file_response = requests.get(file_url)
        file_response.raise_for_status()
        
        local_path = config.STATS_DIR / target_filename
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

def generate_speed_tiers(pokemon_names, game="sv"):
    """
    Generates speed benchmarks for the top meta Pokemon.
    Returns a sorted list of tiers.
    """
    print(f"Generating Speed Tiers ({game})...")
    tiers = []
    
    if game == "champions":
        # Level 50, max investment is 32 stat points
        max_invest, min_speed = config.CHAMPIONS_SP_MAX, 100
    else:
        max_invest, min_speed = 252, 200
        # Common fixed benchmarks
        tiers.append({'label': 'Choice Scarf Gholdengo', 'speed': 447, 'owner': 'Gholdengo'})
        tiers.append({'label': 'Max Speed Dragapult', 'speed': 421, 'owner': 'Dragapult'})
    
    seen_speeds = set()
    
    for name in pokemon_names[:30]: # Limit to top 30 to save time/clutter
        data = fetch_pokemon_data(name)
        if not data: continue
        
        base_spe = data['stats']['speed']
        
        # 1. Max Speed (+Nature, full investment)
        max_spe = calculate_speed(base_spe, ev=max_invest, nature_mod=1.1, game=game)
        if max_spe > min_speed and max_spe not in seen_speeds:
            tiers.append({'label': f"Max {name}", 'speed': max_spe, 'owner': name})
            seen_speeds.add(max_spe)
            
        # 2. Scarf User (if base speed is decent > 80). Megas hold their stone, so never Scarf
        if base_spe >= 80 and "-Mega" not in name:
            scarf_spe = int(max_spe * 1.5)
            if scarf_spe not in seen_speeds:
                tiers.append({'label': f"Scarf {name}", 'speed': scarf_spe, 'owner': name})
                seen_speeds.add(scarf_spe)

    # Sort by speed descending
    return sorted(tiers, key=lambda x: x['speed'], reverse=True)

def speed_tiers_path(game):
    """Speed tiers are stored per game since SV (Lv100) and Champions (Lv50) numbers don't mix."""
    return config.JSON_DIR / ("meta_speeds_champions.json" if game == "champions" else "meta_speeds.json")

def main():
    """
    Main function to automate downloading and processing of Smogon stats.
    """
    print("Starting Smogon stats update...")
    stats_base_url = get_latest_stats_url()
    chaos_url_base = stats_base_url + "chaos/"
    
    # --- Download files (usage .txt and chaos .json for every registered format) ---
    names_by_game = {}
    for fmt_id, fmt in config.FORMATS.items():
        print(f"\nProcessing {fmt['label']}...")
        
        # Text file (Usage)
        txt_path = download_stat_file(stats_base_url, fmt["stats"] + ".txt")
            
        # JSON file (Chaos/Partners)
        print(f"Downloading Chaos data for {fmt['label']}...")
        download_stat_file(chaos_url_base, fmt["stats"] + ".json")

        if txt_path:
            # Get top 1000 from each format to populate the search bar
            names = parse_smogon_usage(txt_path, top_n=1000)
            if not names:
                continue
            ordered = names_by_game.setdefault(fmt["game"], [])
            ordered.extend(n for n in names if n not in ordered)

    if not names_by_game:
        print("No usage stats were downloaded or parsed. Aborting update.")
        return

    sorted_names = list({n for names in names_by_game.values() for n in names})

    # --- Fetch types and save final JSON ---
    print(f"Found {len(sorted_names)} unique Pokémon across all formats. Fetching data...")
    top_poke_data = {}
    for name in sorted_names:
        data = fetch_pokemon_data(name)
        if data:
            top_poke_data[name] = data['types']
    
    with open(config.JSON_DIR / "topPoke.json", "w") as f:
        json.dump(top_poke_data, f, indent=2)
        
    # --- Generate Speed Tiers (one file per game, from that game's usage order) ---
    for game, names in names_by_game.items():
        speed_tiers = generate_speed_tiers(names, game)
        with open(speed_tiers_path(game), "w") as f:
            json.dump(speed_tiers, f, indent=2)

    print(f"\nSuccessfully updated meta data and speed tiers.")
