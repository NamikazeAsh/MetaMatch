"""
Builds the local RAG index from every source:
  * Smogon analyses for each SV format (rag/scraper.py)
  * concept notes, one file per game (data/knowledge/concepts_<general|sv|champions>.md)
  * Champions usage cards from the downloaded chaos stats (rag/usage_cards.py)
  * reworded Pokechamp community guides from the local cache (rag/pokechamp.py)
Run: python src/metamatch/rag/build_index.py  (or scripts/update_meta.py --rebuild-index)
"""
import re
import sys
from pathlib import Path

# Add 'src' directory to path so "import metamatch" works
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(SRC_DIR))

from metamatch import config  # noqa: E402
from metamatch.rag import pokechamp, scraper, store, usage_cards  # noqa: E402
from metamatch.rag.chunking import header  # noqa: E402

KNOWLEDGE_DIR = config.DATA_DIR / "knowledge"
# File -> (game tag, source label). "any" concepts reach every game's prompts, so they must hold everywhere
CONCEPT_FILES = {"concepts_general.md": ("any", "General singles concept"),
                 "concepts_sv.md": ("sv", "SV singles concept"),
                 "concepts_champions.md": ("champions", "Champions singles concept")}


def load_concepts():
    """One chunk per '## Title' section of each concept file (text before the first title is a preamble)."""
    chunks = []
    for name, (game, source) in CONCEPT_FILES.items():
        path = KNOWLEDGE_DIR / name
        if not path.exists():
            print(f"Warning: {path} not found")
            continue
        sections = re.split(r"^## (.+)$", path.read_text(encoding="utf-8"), flags=re.M)
        for title, body in zip(sections[1::2], sections[2::2]):
            body = body.strip()
            if body:
                chunks.append({
                    "pokemon": "Concept",
                    "text": header("General concept", title.strip(), source) + body,
                    "metadata": {"pokemon": "Concept", "type": "concept", "title": title.strip(), "section": title.strip(),
                                 "source": "concepts", "game": game, "play": "singles", "format": "any"},
                })
    print(f"Loaded {len(chunks)} concept chunks.")
    return chunks


def main():
    print("Starting Knowledge Base construction...")
    chunks = scraper.fetch_smogon_strategies()
    chunks.extend(load_concepts())
    chunks.extend(usage_cards.build_chunks())
    # Run `python -m metamatch.rag.pokechamp` first to fill the guide cache
    guide_chunks = pokechamp.build_chunks()
    print(f"Loaded {len(guide_chunks)} community guide chunks.")
    chunks.extend(guide_chunks)
    if not chunks:
        print("No data fetched. Aborting.")
        return
    store.rebuild_index(chunks)
    print("Done! Knowledge Base is ready.")


if __name__ == "__main__":
    main()
