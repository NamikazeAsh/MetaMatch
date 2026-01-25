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

def split_into_paragraphs(html_text, min_length=50):
    """
    Splits HTML content into meaningful text chunks based on <p> tags.
    merges small paragraphs to avoid fragmentation.
    """
    if not html_text: 
        return []
    
    soup = BeautifulSoup(html_text, 'html.parser')
    chunks = []
    current_chunk = ""
    
    for element in soup.recursiveChildGenerator():
        if element.name in ['p', 'h3', 'h4', 'li']:
            text = element.get_text(strip=True)
            if not text: continue
            
            # If it's a header, start a new chunk immediately
            if element.name in ['h3', 'h4']:
                if current_chunk: chunks.append(current_chunk)
                current_chunk = f"[{text}] "
            else:
                if len(current_chunk) + len(text) > 1000: # Soft limit
                    chunks.append(current_chunk)
                    current_chunk = text
                else:
                    if current_chunk: current_chunk += " "
                    current_chunk += text
        elif element.name is None and not element.parent.name in ['p', 'h3', 'h4', 'li']:
            # Loose text not in tags
            text = element.strip()
            if len(text) > 20:
                if current_chunk: current_chunk += " "
                current_chunk += text

    if current_chunk:
        chunks.append(current_chunk)
        
    # Fallback if no tags found (just plain text or weird formatting)
    if not chunks:
        raw = soup.get_text(separator=" ").strip()
        if raw: chunks.append(raw)
        
    return chunks

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
        
        # 2. Parse Overview (Split by paragraph) with Heuristic Detection
        if 'overview' in analysis and analysis['overview']:
            paragraphs = split_into_paragraphs(analysis['overview'])
            for idx, p in enumerate(paragraphs):
                # Heuristic: Check for counter-play keywords
                category = "Overview"
                p_lower = p.lower()
                if any(kw in p_lower for kw in ["check", "counter", "weakness", "struggle", "revenge kill", "threat", "wall"]):
                    category = "Checks & Counters"
                    full_text = f"{context_header} **COUNTERPLAY / WEAKNESSES**: {p}"
                else:
                    full_text = f"{context_header} Overview Part {idx+1}: {p}"

                chunks.append({
                    "pokemon": pokemon,
                    "category": category,
                    "text": full_text,
                    "metadata": {"pokemon": pokemon, "type": category.lower(), "part": idx}
                })

        # 3. Parse Sets
        if 'sets' in analysis:
            for set_name, set_data in analysis['sets'].items():
                description_html = set_data.get('description', '')
                
                # Split set descriptions too, as they often contain "Usage Tips" and "Team Options"
                paragraphs = split_into_paragraphs(description_html)
                
                moves = ", ".join(set_data.get('moves', []))
                item = set_data.get('item', 'None')
                ability = set_data.get('ability', 'None')
                nature = set_data.get('nature', 'None')
                
                # Base set info header
                set_header = (
                    f"{context_header} Set '{set_name}': "
                    f"Item: {item} | Ability: {ability} | Nature: {nature} | "
                    f"Moves: {moves}. "
                )
                
                if not paragraphs:
                    # Fallback for empty description
                    chunks.append({
                        "pokemon": pokemon,
                        "category": "Set",
                        "text": set_header,
                        "metadata": {"pokemon": pokemon, "type": "set", "set_name": set_name, "part": 0}
                    })
                
                for idx, p in enumerate(paragraphs):
                    # Apply Heuristic Detection to Set Descriptions too
                    category = "Set"
                    p_lower = p.lower()
                    if any(kw in p_lower for kw in ["check", "counter", "weakness", "struggle", "revenge kill", "threat", "wall"]):
                        category = "Checks & Counters"
                        full_text = f"{set_header} **COUNTERPLAY / WEAKNESSES** (from Set): {p}"
                    else:
                        full_text = f"{set_header} Strategy Part {idx+1}: {p}"
                    
                    chunks.append({
                        "pokemon": pokemon,
                        "category": category,
                        "text": full_text,
                        "metadata": {"pokemon": pokemon, "type": category.lower(), "set_name": set_name, "part": idx}
                    })


        # 4. Parse Comments (Split by paragraph/headers)
        if 'comments' in analysis and analysis['comments']:
             paragraphs = split_into_paragraphs(analysis['comments'])
             for idx, p in enumerate(paragraphs):
                 full_text = f"{context_header} Strategy Comments {idx+1}: {p}"
                 chunks.append({
                    "pokemon": pokemon,
                    "category": "Comments",
                    "text": full_text,
                    "metadata": {"pokemon": pokemon, "type": "comments", "part": idx}
                })

        # 5. Parse Checks & Counters (New - Future Proofing)
        if 'checks' in analysis and analysis['checks']:
            for idx, check in enumerate(analysis['checks']):
                check_name = check.get('name', 'General Counters')
                check_desc = check.get('description', '')
                
                # Split description if it's long HTML
                paragraphs = split_into_paragraphs(check_desc)
                if not paragraphs and check_desc: paragraphs = [check_desc]
                
                for p_idx, p in enumerate(paragraphs):
                    full_text = f"{context_header} **MAJOR THREAT** ({check_name}): {p}"
                    chunks.append({
                        "pokemon": pokemon,
                        "category": "Checks & Counters",
                        "text": full_text,
                        "metadata": {"pokemon": pokemon, "type": "checks", "check_name": check_name, "part": p_idx}
                    })

    print(f"\nParsed and enriched {len(chunks)} strategy chunks.")
    return chunks

if __name__ == "__main__":
    # Test run
    strategies = fetch_smogon_strategies()
    if strategies:
        print("\n--- Sample Enriched Chunk ---")
        print(strategies[0]['text'])