"""
Caches Smogon's strategy analyses (the pkmn.github.io mirror of smogon.com/dex) in data/knowledge/smogon/, so the chat
can show a Pokemon's analysis as a cited card ("From the SV OU analysis") without fetching anything at answer time.

Current SV tiers and Champions OU come first; older generations are kept as a fallback for Pokemon whose current
analysis has no overview, shown labelled as how the Pokemon was played then.
  python scripts/fetch_smogon_analyses.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from metamatch.rag.cards import CACHE_DIR, SOURCES  # noqa: E402

URL = "https://pkmn.github.io/smogon/data/analyses/{}.json"


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for key in SOURCES:
        try:
            with urllib.request.urlopen(URL.format(key), timeout=60) as r:
                data = json.load(r)
        except Exception as e:
            print(f"{key}: failed ({e})")
            continue
        (CACHE_DIR / f"{key}.json").write_text(json.dumps(data), encoding="utf-8")
        print(f"{key}: {len(data)} analyses")
        time.sleep(1)


if __name__ == "__main__":
    main()
