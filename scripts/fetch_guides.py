"""
Caches the short list of Smogon technique and archetype guides in data/knowledge/guides/ (gitignored), one request
every few seconds with an honest User-Agent; pages already cached are skipped. Rebuild the index afterwards:
  python scripts/fetch_guides.py
  python src/metamatch/rag/build_index.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from metamatch.rag import guides  # noqa: E402

if __name__ == "__main__":
    print(f"{guides.fetch_all(force='--force' in sys.argv)} pages fetched")
