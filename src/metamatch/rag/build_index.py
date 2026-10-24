import sys
from pathlib import Path
import re

# Add 'src' directory to path so "import metamatch" works
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(SRC_DIR))

from metamatch.rag import scraper, store, usage_cards, pokechamp

def load_concepts():
    """
    Loads manual concept guides from data/knowledge/concepts.md
    """
    concept_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "knowledge" / "concepts.md"
    if not concept_path.exists():
        print(f"Warning: Concepts file not found at {concept_path}")
        return []

    with open(concept_path, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = []
    # Split by markdown headers (## Title)
    sections = re.split(r'(^## .+$)', text, flags=re.MULTILINE)
    
    current_title = "General"
    
    for i in range(len(sections)):
        section = sections[i].strip()
        if not section: continue
        
        if section.startswith("##"):
            current_title = section.replace("##", "").strip()
        else:
            # This is the content for the previous title
            chunks.append({
                "pokemon": "General Concept", # Generic placeholder
                "category": "Guide",
                "text": f"GUIDE: {current_title}\n{section}",
                "metadata": {"pokemon": "Concept", "type": "concept", "title": current_title}
            })
            
    print(f"Loaded {len(chunks)} concept chunks.")
    return chunks

def main():
    print("Starting Knowledge Base construction...")
    
    # 1. Scrape Strategies (Smogon SV OU analyses)
    chunks = scraper.fetch_smogon_strategies()
    for c in chunks:
        c["metadata"].update({"game": "sv", "play": "singles"})
    
    # 2. Load Manual Concepts (general singles knowledge, valid for every game)
    concept_chunks = load_concepts()
    for c in concept_chunks:
        c["metadata"].update({"game": "any", "play": "singles"})
    chunks.extend(concept_chunks)

    # 3. Champions usage cards from Smogon chaos data
    chunks.extend(usage_cards.build_chunks())

    # 4. Reworded Pokechamp community guides (run `python -m metamatch.rag.pokechamp` first to fill the cache)
    guide_chunks = pokechamp.build_chunks()
    print(f"Loaded {len(guide_chunks)} community guide chunks.")
    chunks.extend(guide_chunks)

    if not chunks:
        print("No data fetched. Aborting.")
        return

    # 5. Index
    store.rebuild_index(chunks)
    
    print("Done! Knowledge Base is ready.")

if __name__ == "__main__":
    main()
