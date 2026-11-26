"""
Strategy Search: the Coach Chat tab's place on the web deploy, where no local model runs. Ask a strategy question
and get the closest passages from Smogon's analyses (and MetaMatch's concept notes and ladder cards), quoted as
written, with the writers credited and a link to the full analysis. Retrieval is rag/lite: the same hybrid
ranking as the local chat, on static embeddings that need no GPU or torch.
"""
import re
from html import escape

import streamlit as st

from metamatch import config
from metamatch.sprites import get_sprite
from metamatch.ui import section_header

SHOW = 4
EXAMPLES = {"sv": ("How do I beat Kingambit?", "What does Gholdengo do on hyper offense?", "When should I Terastallize?"),
            "champions": ("How do I use Mega Charizard Y?", "What partners does Garchomp want?", "How is Champions different?")}
STYLE = """
<style>
.ss-hit { border-radius:14px; padding:14px 16px; margin:10px 0; background:linear-gradient(160deg, var(--tc1a), rgba(255,255,255,.015) 60%);
  border:1px solid var(--tc44); border-left:3px solid var(--tc); }
.ss-top { display:flex; align-items:center; gap:12px; }
.ss-top img { width:48px; height:48px; object-fit:contain; flex-shrink:0; }
.ss-k { font-size:.66rem; font-weight:800; letter-spacing:1.6px; text-transform:uppercase; color:#8a93a6; }
.ss-t { font-weight:800; color:#fff; font-size:1rem; }
.ss-body { font-size:.9rem; color:#d6dbe6; line-height:1.55; margin-top:10px; }
.ss-src { font-size:.76rem; color:#8a93a6; margin-top:10px; }
.ss-src a { color:#7fe6ff; text-decoration:none; } .ss-src a:hover { text-decoration:underline; }
.ss-oak { font-size:1rem; font-weight:700; color:#e6edf7; margin:6px 2px 4px; }
[class*="st-key-ss_ex_"] button { padding:4px 14px !important; border-radius:999px !important; }
</style>
"""


@st.cache_resource(show_spinner=False)
def _ready():
    """Loads the model and builds the index once per server process (shared by every visitor)."""
    from metamatch.rag import lite
    lite.index()
    return True


def _writers(species, format_id):
    from metamatch.rag import cards
    key = cards.FORMAT_SOURCE.get(format_id)
    entry = (cards._load(key) or {}).get(species, {}) if key else {}
    names = [w.get("username") for w in ((entry.get("credits") or {}).get("writtenBy") or []) if w.get("username")]
    return ", ".join(names[:3]) + (" and others" if len(names) > 3 else "")


def _source(meta, format_id):
    """The credit line for a passage: who wrote it and where to read the rest."""
    src = meta.get("source")
    if src == "smogon_analysis":
        species = meta.get("species") or meta.get("pokemon")
        fmt = meta.get("format") or format_id
        from metamatch.rag.cards import analysis_url
        url = analysis_url(meta.get("pokemon") or species, fmt) or analysis_url(meta.get("pokemon") or species, "gen9ou")
        writers = _writers(species, fmt)
        by = f" by {escape(writers)}" if writers else ""
        return f'From Smogon&#39;s analysis{by}. <a href="{url}" target="_blank" rel="noopener">Read the full analysis on Smogon</a>'
    if src == "smogon_guide":
        url = meta.get("url")
        link = f' <a href="{escape(url)}" target="_blank" rel="noopener">Read the guide</a>' if url else ""
        return f"From a Smogon guide ({escape(str(meta.get('year') or ''))}).{link}"
    if src == "smogon_stats":
        return "From this month&#39;s Smogon ladder usage stats."
    if src == "pokechamp":
        return "From a Pokéchamp community guide, reworded."
    return "A MetaMatch concept note."


def _hit(h, format_id, type_map, question=""):
    from metamatch.engine.dex import dex_for_format
    from metamatch.rag.chunking import body
    meta = h["metadata"]
    who = meta.get("pokemon") or ""
    dex = dex_for_format(format_id)
    species = dex.species(who) if dex and who not in ("Concept", "Guide") else None
    color = type_map.get(((species or {}).get("types") or ["Normal"])[0], {}).get("color", "#00d4ff") if species else "#00d4ff"
    sprite = get_sprite(who) if species else None
    img = f'<img src="{escape(sprite)}" alt="">' if sprite else ""
    title = meta.get("title") if who in ("Concept", "Guide") else who
    kicker = meta.get("section") or ""
    return (f'<div class="ss-hit" style="--tc:{color};--tc1a:{color}1a;--tc44:{color}44"><div class="ss-top">{img}<div>'
            f'<div class="ss-k">{escape(kicker)}</div><div class="ss-t">{escape(title or kicker)}</div></div></div>'
            f'<div class="ss-body">{escape(_excerpt(body(h["text"]), meta, question))}</div><div class="ss-src">{_source(meta, format_id)}</div></div>')


def _excerpt(text, meta, question=""):
    """Smogon's and Pokechamp's writing shows as the two sentences that best answer the question (agents/retell
    picks them), pointing to the full piece, so the search sends readers to the source rather than republishing
    it. MetaMatch's own notes and ladder cards show in full."""
    if meta.get("source") not in ("smogon_analysis", "smogon_guide", "pokechamp"):
        return text
    from metamatch.agents.retell import best_sentences
    short = " ".join(best_sentences(question, text, k=2))
    if len(short) > 420:
        short = short[:417].rsplit(" ", 1)[0] + "..."
    return short + (" ..." if short != text.strip() and not short.endswith("...") else "")


def _ask(question):
    st.session_state["strategy_search_q"] = question


def render(type_map=None):
    type_map = type_map or {}
    format_id = st.session_state.get("format_id") or config.DEFAULT_FORMAT
    label = config.format_info(format_id)["label"]
    section_header("Ask the analyses", "Strategy Search")
    st.caption(f"Search Smogon's {label} analyses with a strategy question. Each result is a short excerpt with a link "
               "to the full analysis. The Coach Chat runs when MetaMatch is on your own computer.")
    question = st.text_input("Question", key="strategy_search_q", label_visibility="collapsed",
                             placeholder="For example: how do I beat Kingambit?")
    if not question:
        st.html(STYLE)
        with st.container(horizontal=True):
            for ex in EXAMPLES["champions" if config.format_game(format_id) == "champions" else "sv"]:
                st.button(ex, key=f"ss_ex_{ex}", type="tertiary", on_click=_ask, args=(ex,))
        return
    try:
        with st.spinner("Loading the analyses (only the first search takes a moment)..."):
            _ready()
        from metamatch.rag import lite
        hits = lite.query_strategies(question, n_results=SHOW, format_id=format_id)
    except Exception:   # offline or the model couldn't be fetched: say so, never an error page
        st.info("Strategy Search couldn't load the analyses right now. Try again in a moment.")
        return
    if not hits:
        st.caption(f"Nothing in the {label} analyses matches that yet.")
        return
    # Oak's line over the results: a template by what the top passage is, never by what it says (agents/retell)
    from metamatch.agents.retell import template
    oak = f'<div class="ss-oak">{escape(template(hits[0]["metadata"]))}</div>'
    st.html(STYLE + oak + "".join(_hit(h, format_id, type_map, question) for h in hits))
