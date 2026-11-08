"""Move Search: sets that run every chosen move, from the Strategy Dex (verified) and ladder usage (loose matches)."""
from html import escape

import streamlit as st

from metamatch import config, strategy_data
from metamatch.sprites import get_sprite

STYLE = """
<style>
.ms-sum { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin:6px 0 4px; }
.ms-sum b { font-size:1.15rem; color:#fff; font-weight:800; }
.ms-pill { font-size:0.74rem; font-weight:700; padding:3px 10px; border-radius:999px; border:1px solid; }
.ms-pill.ok { color:#7fe6ff; background:rgba(0,212,255,0.10); border-color:rgba(0,212,255,0.28); }
.ms-pill.loose { color:#ffd866; background:rgba(255,204,51,0.10); border-color:rgba(255,204,51,0.28); }
.ms-sec { margin:22px 2px 10px; }
.ms-sec-k { font-size:0.66rem; font-weight:800; letter-spacing:2px; text-transform:uppercase; color:#00d4ff; }
.ms-sec-k.loose { color:#ffd866; }
.ms-sec-t { font-weight:900; font-size:1.25rem; color:#fff; margin-top:2px; }
.ms-sec-c { font-size:0.82rem; color:#8a93a6; margin-top:2px; }
.ms-grid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:12px; }
.ms-card { position:relative; border-radius:14px; padding:14px 16px; min-width:0;
  background:linear-gradient(160deg, var(--tc1a), rgba(255,255,255,0.015) 55%); border:1px solid var(--tc44);
  box-shadow:0 0 18px -12px var(--tc); transition:transform .15s ease, box-shadow .15s ease; }
.ms-card:hover { transform:translateY(-3px); box-shadow:0 0 24px -8px var(--tc); }
.ms-top { display:flex; gap:12px; align-items:center; }
.ms-top img { width:64px; height:64px; object-fit:contain; flex-shrink:0; filter:drop-shadow(0 0 10px var(--tc88)); }
.ms-name { font-weight:800; font-size:1.05rem; color:#fff; }
.ms-set { font-size:0.82rem; color:#aab3c5; margin-top:1px; }
.ms-fmt { display:inline-block; font-size:0.62rem; font-weight:800; letter-spacing:0.8px; text-transform:uppercase; padding:2px 8px;
  border-radius:999px; color:#7fe6ff; background:rgba(0,212,255,0.12); border:1px solid rgba(0,212,255,0.28); }
.ms-fmt.loose { color:#ffd866; background:rgba(255,204,51,0.12); border-color:rgba(255,204,51,0.28); }
.ms-meta { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
.ms-meta span { font-size:0.74rem; color:#d6dbe6; padding:3px 9px; border-radius:8px; background:rgba(0,0,0,0.25);
  border:1px solid rgba(255,255,255,0.07); }
.ms-meta span i { font-style:normal; color:#8a93a6; margin-right:5px; }
.ms-moves { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:6px; margin-top:10px; }
.ms-move { font-size:0.8rem; padding:5px 9px; border-radius:8px; background:rgba(255,255,255,0.05);
  border:1px solid rgba(255,255,255,0.07); color:#aab3c5; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ms-move.hit { color:#5fd38d; background:rgba(95,211,141,0.12); border-color:rgba(95,211,141,0.35); font-weight:700; }
.ms-bars { display:flex; flex-direction:column; gap:7px; margin-top:12px; }
.ms-bar-row { display:flex; justify-content:space-between; font-size:0.8rem; color:#d6dbe6; }
.ms-bar-row b { color:#fff; font-variant-numeric:tabular-nums; }
.ms-bar { height:5px; border-radius:4px; background:rgba(255,255,255,0.07); overflow:hidden; margin-top:3px; }
.ms-bar i { display:block; height:100%; background:var(--tc); box-shadow:0 0 8px -2px var(--tc); }
.ms-empty { border:1px dashed rgba(255,255,255,0.12); border-radius:14px; padding:22px; text-align:center; color:#8a93a6; font-size:0.9rem; }
@media (max-width: 900px) { .ms-grid { grid-template-columns:minmax(0, 1fr); } }
@media (prefers-reduced-motion: reduce) { .ms-card { transition:none; } .ms-card:hover { transform:none; } }
</style>
"""


def _options(value):
    """Strategy Dex fields can be one value or a list of alternatives: 'Sitrus Berry / Heavy-Duty Boots'."""
    if isinstance(value, (list, tuple)):
        return escape(" / ".join(str(v) for v in value))
    return escape(str(value).strip("[]").replace("'", "").replace(", ", " / "))


def _norm(m):
    return m.lower().replace("-", "").replace(" ", "")


def _vars(name, dex, type_map):
    species = dex.species(name) if dex else None
    color = type_map.get(((species or {}).get("types") or ["Normal"])[0], {}).get("color", "#00d4ff")
    return f"--tc:{color}; --tc1a:{color}1a; --tc44:{color}44; --tc88:{color}88;"


def _verified_card(res, picked, label, dex, type_map):
    name = res["pokemon"]
    moves = "".join(
        f'<span class="ms-move{" hit" if _norm(m) in picked else ""}">{"✓ " if _norm(m) in picked else ""}{escape(m)}</span>'
        for m in dict.fromkeys(res["moves"]))
    meta = "".join(f'<span><i>{k}</i>{_options(res[f])}</span>' for k, f in (("Item", "item"), ("Ability", "ability"), ("Nature", "nature"))
                   if res.get(f) and str(res[f]).strip() not in ("None", "[]", ""))
    return (f'<div class="ms-card" style="{_vars(name, dex, type_map)}"><div class="ms-top">'
            f'<img src="{escape(get_sprite(name) or "")}" alt=""><div style="min-width:0">'
            f'<span class="ms-fmt">{escape(label)}</span><div class="ms-name">{escape(name)}</div>'
            f'<div class="ms-set">{escape(res["set_name"].split("(")[0].strip())}</div></div></div>'
            f'<div class="ms-meta">{meta}</div><div class="ms-moves">{moves}</div></div>')


def _loose_card(res, label, dex, type_map):
    name = res["pokemon"]
    bars = "".join(
        f'<div><div class="ms-bar-row"><span>{escape(m)}</span><b>{u:.1f}%</b></div>'
        f'<div class="ms-bar"><i style="width:{min(u, 100):.0f}%"></i></div></div>'
        for m, u in res["moves"].items())
    return (f'<div class="ms-card" style="{_vars(name, dex, type_map)}"><div class="ms-top">'
            f'<img src="{escape(get_sprite(name) or "")}" alt=""><div style="min-width:0">'
            f'<span class="ms-fmt loose">{escape(label)} ladder</span><div class="ms-name">{escape(name)}</div>'
            f'<div class="ms-set">Share of its sets running each move</div></div></div><div class="ms-bars">{bars}</div></div>')


def _search(moves, include_loose, label, is_champions, master_strat_data, usage_data):
    verified = [r for r in strategy_data.find_sets_with_moves(moves, data=master_strat_data) if label in r.get("formats", [])]
    loose = []
    # Smogon has no Champions analyses yet, so ladder usage is the only source there
    if include_loose or is_champions:
        loose = [r for r in strategy_data.find_usage_matches(moves, usage_data=usage_data) if r["format"] == label]
    seen = {r["pokemon"] for r in verified}
    return verified, [r for r in loose if r["pokemon"] not in seen]


def render(get_strat_data_fn, get_usage_data_fn, type_map=None):
    from metamatch.engine.dex import dex_for_format
    type_map = type_map or {}
    format_id = st.session_state.get("format_id")
    label = config.format_info(format_id)["label"]
    is_champions = config.format_game(format_id) == "champions"
    master_strat_data = get_strat_data_fn()
    usage_data = get_usage_data_fn()
    if "all_moves" not in st.session_state:
        with st.spinner("Loading move list..."):
            st.session_state.all_moves = strategy_data.get_all_known_moves(master_strat_data, usage_data)

    move_selection = st.multiselect("Moves", options=st.session_state.all_moves, key="move_search_select",
                                    placeholder="Type moves to search, for example Scald or Thunder Wave",
                                    label_visibility="collapsed")
    with st.container(horizontal=True, vertical_alignment="center"):
        search_clicked = st.button("Find sets", icon=":material/search:", type="primary", key="find_sets_btn")
        include_loose = st.toggle("Include loose matches", value=False,
                                  help="Also search ladder usage for Pokémon that run all of these moves, not always on one set.")
        st.caption(f"Searching {label}. Pick one or more moves, then find every set that runs all of them.")

    if search_clicked:
        if not move_selection:
            st.warning("Pick at least one move first.")
            return
        st.session_state.move_search_results = (tuple(move_selection), include_loose, format_id,
                                                _search(move_selection, include_loose, label, is_champions,
                                                        master_strat_data, usage_data))
    saved = st.session_state.get("move_search_results")
    # Results stay on screen across reruns, but only for the format and search they were made for
    if not saved or saved[2] != format_id:
        st.html(STYLE + '<div class="ms-empty">Your matches show up here as cards, verified Smogon sets first.</div>')
        return
    moves, loose_on, _, (verified, loose) = saved
    dex = dex_for_format(format_id)
    picked = {_norm(m) for m in moves}
    total = len(verified) + len(loose)
    if not total:
        st.html(STYLE + f'<div class="ms-empty">No {escape(label)} sets run {escape(", ".join(moves))}. '
                        'Try turning on loose matches, or pick another format above.</div>')
        return
    pills = f'<span class="ms-pill ok">{len(verified)} verified</span>' + (
        f'<span class="ms-pill loose">{len(loose)} loose</span>' if loose else "")
    html = STYLE + f'<div class="ms-sum"><b>{total} {"match" if total == 1 else "matches"}</b>{pills}</div>'
    if verified:
        html += ('<div class="ms-sec"><div class="ms-sec-k">Strategy Dex</div><div class="ms-sec-t">Verified sets</div>'
                 '<div class="ms-sec-c">Smogon sets that run every move you picked, highlighted in green.</div></div>')
        html += '<div class="ms-grid">' + "".join(_verified_card(r, picked, label, dex, type_map) for r in verified) + "</div>"
    if loose:
        html += ('<div class="ms-sec"><div class="ms-sec-k loose">Ladder usage</div><div class="ms-sec-t">Loose matches</div>'
                 '<div class="ms-sec-c">These Pokémon run all of these moves on the ladder, but not always on the same set.</div></div>')
        html += '<div class="ms-grid">' + "".join(_loose_card(r, label, dex, type_map) for r in loose) + "</div>"
    st.html(html)
