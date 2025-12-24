import requests
import json
from bs4 import BeautifulSoup
import sys
from pathlib import Path

# Add 'src' directory to path so "import metamatch" works
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(SRC_DIR))

from metamatch.utils import fetch_pokemon_data

SMOGON_API_URL = "https://pkmn.github.io/smogon/data/analyses/gen9ou.json"

def clean_html(html_text):
    """
    Removes HTML tags from the text.
    """
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, 'html.parser')
    return soup.get_text(separator=" ").strip()

def get_pokemon_context(name):
    """
    Fetches Type and Ability data to enrich the chunk.
    """
    data = fetch_pokemon_data(name)
    if not data:
        return ""
    
    types = "/".join(data.get('types', []))
    abilities = ", ".join(data.get('abilities', []))
    
    # This header acts as a strong "anchor" for the semantic search
    return f"Pokemon: {name}. Type: {types}. Abilities: {abilities}."

def fetch_smogon_strategies():
    """
    Fetches Gen 9 OU analyses and parses them into chunks.
    """
    print(f"Fetching strategies from {SMOGON_API_URL}...")
    try:
        res = requests.get(SMOGON_API_URL, timeout=10)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"Error fetching Smogon data: {e}")
        return []

    chunks = []
    
    # Process each Pokemon
    total = len(data)
    print(f"Processing {total} Pokemon...")
    
    for i, (pokemon, analysis) in enumerate(data.items()):
        if i % 10 == 0:
            print(f"  Enriching {i}/{total}...", end="\r")
            
        # 1. Fetch Enrichment Data (Types, Abilities)
        context_header = get_pokemon_context(pokemon)
        
        # 2. Parse Overview
        if 'overview' in analysis and analysis['overview']:
            text = clean_html(analysis['overview'])
            # Combine Header + Specific Content
            full_text = f"{context_header} Overview: {text}"
            
            chunks.append({
                "pokemon": pokemon,
                "category": "Overview",
                "text": full_text,
                "metadata": {"pokemon": pokemon, "type": "overview"}
            })

        # 3. Parse Sets
        if 'sets' in analysis:
            for set_name, set_data in analysis['sets'].items():
                description = clean_html(set_data.get('description', ''))
                
                moves = ", ".join(set_data.get('moves', []))
                item = set_data.get('item', 'None')
                ability = set_data.get('ability', 'None')
                nature = set_data.get('nature', 'None')
                
                set_block = (
                    f"{context_header} Set '{set_name}': "
                    f"Item: {item} | Ability: {ability} | Nature: {nature} | "
                    f"Moves: {moves}. "
                    f"Strategy: {description}"
                )
                
                chunks.append({
                    "pokemon": pokemon,
                    "category": "Set",
                    "text": set_block,
                    "metadata": {"pokemon": pokemon, "type": "set", "set_name": set_name}
                })

        # 4. Parse Comments
        if 'comments' in analysis and analysis['comments']:
             text = clean_html(analysis['comments'])
             full_text = f"{context_header} Strategy Comments: {text}"
             
             chunks.append({
                "pokemon": pokemon,
                "category": "Comments",
                "text": full_text,
                "metadata": {"pokemon": pokemon, "type": "comments"}
            })

    print(f"\nParsed and enriched {len(chunks)} strategy chunks.")
    return chunks

if __name__ == "__main__":
    # Test run
    strategies = fetch_smogon_strategies()
    if strategies:
        print("\n--- Sample Enriched Chunk ---")
        print(strategies[0]['text'])