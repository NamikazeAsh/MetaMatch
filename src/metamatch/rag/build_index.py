import sys
from pathlib import Path

# Add 'src' directory to path so "import metamatch" works
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(SRC_DIR))

from metamatch.rag import scraper, store

def main():
    print("Starting Knowledge Base construction...")
    
    # 1. Scrape
    chunks = scraper.fetch_smogon_strategies()
    if not chunks:
        print("No data fetched. Aborting.")
        return

    # 2. Index
    store.rebuild_index(chunks)
    
    print("Done! Knowledge Base is ready.")

if __name__ == "__main__":
    main()
