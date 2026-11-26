"""
Smogon strategy analyses as RAG chunks, for every format with analyses: SV OU, UU and National Dex, and Champions OU.
The text comes from the same cache the Coach Guide's cards use (rag/cards._load: pkmn.github.io mirror, gitignored,
never republished), refreshed at build time. Each analysis section (overview, every set description, other options)
is split into 300 to 900 character chunks under a 'Pokemon | Section | Format' header. Empty sections produce no
chunks. A Mega's set is filed under the Mega (Charizard-Mega-Y, with "species": Charizard), so a question that
names the Mega finds it, while one that names the base species still does through "species".
"""
import re

from metamatch import config
from metamatch.rag.chunking import header, html_paragraphs, join_dangling, split_paragraphs

# Formats with their own analyses, by the mirror's file name (rag/cards.FORMAT_SOURCE); Champions UU reads OU's
INDEXED = {"gen9ou": "gen9ou", "gen9uu": "gen9uu", "gen9natdex": "gen9nationaldex", "gen9championsou": "championsou"}


def fetch_analyses(key, refresh=True):
    """{pokemon: analysis} for one mirror file, refreshed from the mirror when `refresh` (else the cache)."""
    from metamatch.rag import cards
    if refresh:
        cards.refresh(key)
    return cards._load(key)


def _mega(pokemon, set_name, html, format_id, items, dex):
    """The Mega forme a set is about, or None: its Mega Stone (from the Strategy Dex set data, SV) or, with no
    item data (Champions), the set's own text naming 'Mega Charizard Y'."""
    if not dex:
        return None
    item = items.get(set_name)
    if item:
        forme = dex.mega_forme(pokemon, item)
        if forme:
            return forme
    text = re.sub(r"<[^>]+>", " ", html or "")
    m = re.search(rf"\bMega {re.escape(pokemon)}(?: ([XYZ])\b)?", text)
    if not m:
        return None
    forme = f"{pokemon}-Mega" + (f"-{m.group(1)}" if m.group(1) else "")
    return forme if dex.species(forme) else None


def analysis_chunks(data, format_id, strat_data=None):
    """Chunks for one format's analyses JSON ({pokemon: {overview, sets: {name: {description}}, comments}})."""
    from metamatch.engine.dex import dex_for_format
    game = config.format_game(format_id)
    label = f"{'Champions' if game == 'champions' else 'SV'} {config.format_info(format_id)['label'].replace('Champions ', '')} analysis"
    dex = dex_for_format(format_id) if config.has_megas(format_id) else None
    suffix = f" ({config.format_info(format_id)['label']})"
    chunks = []
    for pokemon, analysis in data.items():
        items = {}
        for name, s in ((strat_data or {}).get(pokemon, {}).get("sets") or {}).items():
            if name.endswith(suffix):
                item = s.get("item")
                items[name[:-len(suffix)]] = item[0] if isinstance(item, list) and item else item
        sections = [("Overview", analysis.get("overview"), {"type": "overview"}, pokemon)]
        for name, s in (analysis.get("sets") or {}).items():
            html = (s or {}).get("description")
            forme = _mega(pokemon, name, html, format_id, items, dex) if dex else None
            sections.append((f"Set {name}", html, {"type": "set", "set_name": name}, forme or pokemon))
        sections += [("Other options", analysis.get("comments"), {"type": "comments"}, pokemon)]
        for section, html, extra, who in sections:
            for part, text in enumerate(join_dangling(split_paragraphs(html_paragraphs(html)))):
                chunks.append({
                    "pokemon": who,
                    "text": header(who, section, label) + text,
                    "metadata": {"pokemon": who, "species": pokemon, "section": section, "part": part,
                                 "source": "smogon_analysis", "game": game, "play": "singles", "format": format_id,
                                 **extra},
                })
    return chunks


def fetch_smogon_strategies(refresh=True):
    """Analysis chunks for every format that has Smogon analyses."""
    from metamatch import strategy_data
    strat = strategy_data.ensure_strategy_data()
    chunks = []
    for format_id, key in INDEXED.items():
        data = fetch_analyses(key, refresh)
        found = analysis_chunks(data, format_id, strat)
        print(f"{config.format_info(format_id)['label']}: {len(data)} analyses, {len(found)} chunks")
        chunks.extend(found)
    return chunks


if __name__ == "__main__":
    out = fetch_smogon_strategies(refresh=False)
    if out:
        print(out[0]["text"])
