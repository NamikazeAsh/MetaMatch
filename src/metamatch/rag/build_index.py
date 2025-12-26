import sys
from pathlib import Path
import re

# Add 'src' directory to path so "import metamatch" works
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(SRC_DIR))

from metamatch.rag import scraper, store

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
    
    # 1. Scrape Strategies
    chunks = scraper.fetch_smogon_strategies()
    
    # 2. Load Manual Concepts
    concept_chunks = load_concepts()
    chunks.extend(concept_chunks)

    if not chunks:
        print("No data fetched. Aborting.")
        return

    # 3. Index
    store.rebuild_index(chunks)
    
    print("Done! Knowledge Base is ready.")

if __name__ == "__main__":
    main()
