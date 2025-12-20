import re
import requests
import json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from helper import pokeSlugify

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
        
        local_path = f"stats/{target_filename}"
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
    pat = re.compile(r'^\s*\|\s*\d+\s*\|\s*([^|]+?)\s*\|')
    names = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                m = pat.match(line)
                if not m:
                    continue
                names.append(m.group(1).strip())
        return names[:top_n] if top_n else names
    except FileNotFoundError:
        print(f"Error: Could not find file {path} to parse.")
        return []

from helper import pokeSlugify, fetch_pokemon_data, calculate_speed

def generate_speed_tiers(pokemon_names):
    """
    Generates speed benchmarks for the top meta Pokemon.
    Returns a sorted list of tiers.
    """
    print("Generating Speed Tiers...")
    tiers = []
    
    # Common fixed benchmarks
    tiers.append({'label': 'Choice Scarf Gholdengo', 'speed': 447, 'owner': 'Gholdengo'})
    tiers.append({'label': 'Max Speed Dragapult', 'speed': 421, 'owner': 'Dragapult'})
    
    seen_speeds = set()
    
    for name in pokemon_names[:30]: # Limit to top 30 to save time/clutter
        data = fetch_pokemon_data(name)
        if not data: continue
        
        base_spe = data['stats']['speed']
        
        # 1. Max Speed (+Nature, 252 EVs)
        max_spe = calculate_speed(base_spe, ev=252, nature_mod=1.1)
        if max_spe > 200 and max_spe not in seen_speeds:
            tiers.append({'label': f"Max {name}", 'speed': max_spe, 'owner': name})
            seen_speeds.add(max_spe)
            
        # 2. Scarf User (if base speed is decent > 80)
        if base_spe >= 80:
            scarf_spe = int(max_spe * 1.5)
            if scarf_spe not in seen_speeds:
                tiers.append({'label': f"Scarf {name}", 'speed': scarf_spe, 'owner': name})
                seen_speeds.add(scarf_spe)

    # Sort by speed descending
    return sorted(tiers, key=lambda x: x['speed'], reverse=True)

def main():
    """
    Main function to automate downloading and processing of Smogon stats.
    """
    print("Starting Smogon stats update...")
    stats_base_url = get_latest_stats_url()
    
    # --- Define target files ---
    target_files = ["gen9ou-1825.txt", "gen9ou-1695.txt"] 
    
    # --- Download files ---
    downloaded_paths = []
    for filename in target_files:
        path = download_stat_file(stats_base_url, filename)
        if path:
            downloaded_paths.append(path)
            
    if not downloaded_paths:
        print("No stats files were downloaded. Aborting update.")
        return

    # --- Parse files and combine lists ---
    print("\nParsing downloaded files...")
    combined_names = set()
    for path in downloaded_paths:
        names = parse_smogon_usage(path, top_n=60)
        combined_names.update(names)
    
    sorted_names = list(combined_names)

    # --- Fetch types and save final JSON ---
    print(f"Found {len(sorted_names)} unique Pokémon. Fetching data...")
    top_poke_data = {}
    for name in sorted_names:
        data = fetch_pokemon_data(name)
        if data:
            top_poke_data[name] = data['types']
    
    output_path = "jsons/topPoke.json"
    with open(output_path, "w") as f:
        json.dump(top_poke_data, f, indent=2)
        
    # --- Generate Speed Tiers ---
    speed_tiers = generate_speed_tiers(sorted_names)
    with open("jsons/meta_speeds.json", "w") as f:
        json.dump(speed_tiers, f, indent=2)

    print(f"\nSuccessfully updated meta data and speed tiers.")

if __name__ == "__main__":
    main()