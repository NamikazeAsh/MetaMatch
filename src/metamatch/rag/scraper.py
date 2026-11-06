"""
Smogon strategy analyses (pkmn.github.io mirror) as RAG chunks, one set per supported SV format.
Each analysis section (overview, every set description, other options) is split into 300 to 900
character chunks under a 'Pokemon | Section | Format' header. Empty sections produce no chunks.
"""
import requests

from metamatch import config
from metamatch.rag.chunking import header, html_paragraphs, split_paragraphs

ANALYSES_URL = "https://pkmn.github.io/smogon/data/analyses/{}.json"


def fetch_analyses(sets_id):
    try:
        res = requests.get(ANALYSES_URL.format(sets_id), timeout=20)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"Could not fetch {sets_id} analyses: {e}")
        return {}


def analysis_chunks(data, format_id):
    """Chunks for one format's analyses JSON ({pokemon: {overview, sets: {name: {description}}, comments}})."""
    label = f"SV {config.format_info(format_id)['label']} analysis"
    chunks = []
    for pokemon, analysis in data.items():
        sections = [("Overview", analysis.get("overview"), {"type": "overview"})]
        sections += [(f"Set {name}", s.get("description"), {"type": "set", "set_name": name})
                     for name, s in (analysis.get("sets") or {}).items()]
        sections += [("Other options", analysis.get("comments"), {"type": "comments"})]
        for section, html, extra in sections:
            for part, text in enumerate(split_paragraphs(html_paragraphs(html))):
                chunks.append({
                    "pokemon": pokemon,
                    "text": header(pokemon, section, label) + text,
                    "metadata": {"pokemon": pokemon, "section": section, "part": part, "source": "smogon_analysis",
                                 "game": "sv", "play": "singles", "format": format_id, **extra},
                })
    return chunks


def fetch_smogon_strategies():
    """Analysis chunks for every SV format that has Smogon analyses."""
    chunks = []
    for format_id, fmt in config.FORMATS.items():
        if fmt["game"] != "sv" or not fmt.get("sets"):
            continue
        print(f"Fetching {fmt['label']} analyses...")
        data = fetch_analyses(fmt["sets"])
        found = analysis_chunks(data, format_id)
        print(f"  {len(data)} analyses, {len(found)} chunks")
        chunks.extend(found)
    return chunks


if __name__ == "__main__":
    out = fetch_smogon_strategies()
    if out:
        print(out[0]["text"])
