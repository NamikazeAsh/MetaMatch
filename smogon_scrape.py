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

def get_pokemon_type(name):
    """
    Fetches Pokémon types from the PokeAPI.
    """
    url = f"https://pokeapi.co/api/v2/pokemon/{name.lower()}"
    try:
        res = requests.get(url)
        res.raise_for_status()
        data = res.json()
        return [t["type"]["name"].capitalize() for t in data["types"]]
    except requests.exceptions.RequestException:
        return [] # Return empty list if API call fails

def main():
    """
    Main function to automate downloading and processing of Smogon stats.
    """
    print("Starting Smogon stats update...")
    stats_base_url = get_latest_stats_url()
    
    # --- Define target files ---
    # Using 1695 as it's a common cutoff, fallback to 1630 if needed. Let's try 1695 first.
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
        names = parse_smogon_usage(path, top_n=100)
        combined_names.update(names)

    # --- Fetch types and save final JSON ---
    print(f"Found {len(combined_names)} unique Pokémon. Fetching types...")
    top_poke_data = {name: get_pokemon_type(pokeSlugify(name)) for name in combined_names}
    
    output_path = "jsons/topPoke.json"
    with open(output_path, "w") as f:
        json.dump(top_poke_data, f, indent=2)
        
    print(f"\nSuccessfully updated '{output_path}' with the latest meta data.")

if __name__ == "__main__":
    main()