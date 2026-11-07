"""Spread Lab: the smallest EV (or Champions stat point) spread that hits the benchmarks you pick."""
from html import escape

import streamlit as st

from metamatch import config
from metamatch.auditor import load_chaos_data
from metamatch.engine.dex import dex_for_format
from metamatch.engine.sets import likely_set
from metamatch.engine.spread_lab import Benchmark, Lab, check_spread, ladder_spreads, showdown_block, spread_text

KINDS = {"Outspeed": "outspeed", "Knock out": "ko", "Survive a hit": "survive"}
MAX_ROWS = 6
STYLE = """
<style>
.sl-result { background: rgba(34,211,238,.06); border: 1px solid rgba(34,211,238,.35); border-radius: 14px; padding: 16px 18px; }
.sl-result .big { font: 700 1.35rem/1.3 'JetBrains Mono', monospace; color: #e6edf7; }
.sl-result .sub { color: #9fb0cc; font-size: .9rem; margin-top: 4px; }
.sl-check { display: grid; grid-template-columns: 22px 1fr auto; gap: 10px; align-items: center; padding: 8px 12px; margin-top: 6px;
  border-radius: 10px; background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.07); }
.sl-check .mark { font-weight: 800; }
.sl-check.ok .mark { color: #34d399; } .sl-check.bad .mark { color: #f87171; }
.sl-check .detail { color: #9fb0cc; font-family: 'JetBrains Mono', monospace; font-size: .82rem; }
</style>
"""


def _pokemon_options(format_id, team):
    data = load_chaos_data(format_id) or {}
    ranked = [n for n, e in sorted(data.items(), key=lambda kv: kv[1].get("usage", 0), reverse=True) if e.get("usage", 0) > 0.002]
    mine = [p["Pokemon"] for p in (team or {}).values()]
    return list(dict.fromkeys(mine + ranked)), set(mine)


def _base(name, format_id, team):
    """(calc base spec, moves, label of where the set came from) for the Pokemon being tuned."""
    for p in (team or {}).values():
        if p["Pokemon"] == name:
            return ({"name": p.get("Forme") or name, "item": p.get("Item") or None,
                     "ability": p.get("Mega Ability") or p.get("Ability") or None},
                    [m["name"] for m in p.get("Moves", [])], "your team")
    s = likely_set(name, format_id)
    if not s:
        return None, [], ""
    return {"name": s["name"], "item": s.get("item"), "ability": s.get("ability")}, [m for m, _ in s["moves"]], "its most common set"


def _rows():
    if "sl_rows" not in st.session_state:
        st.session_state.sl_rows = [0]
        st.session_state.sl_next = 1
    return st.session_state.sl_rows


def _check_html(label, ok, detail):
    cls, mark = ("ok", "✓") if ok else ("bad", "✗")
    return (f'<div class="sl-check {cls}"><span class="mark">{mark}</span><span>{escape(label)}</span>'
            f'<span class="detail">{escape(detail)}</span></div>')


def render(team=None):
    format_id = st.session_state.get("format_id") or config.DEFAULT_FORMAT
    game = config.format_game(format_id)
    dex = dex_for_format(format_id)
    options, mine = _pokemon_options(format_id, team)
    if not options:
        st.info("No usage stats for this format yet. Run `python scripts/update_meta.py` to download them.")
        return

    c1, c2 = st.columns([2, 1])
    with c1:
        name = st.selectbox("Pokémon to tune", options, key=f"sl_mon_{format_id}",
                            format_func=lambda n: f"{n} (your team)" if n in mine else n)
    base, moves, source = _base(name, format_id, team)
    if not base:
        st.warning("No usage data for that Pokémon in this format.")
        return
    with c2:
        item = st.text_input("Item", base.get("item") or "", key=f"sl_item_{name}",
                             help=f"Starts from {source}. Change it to test another item, for example Choice Scarf.")
    base = {**base, "item": dex.item_name(item) if item and dex.item_name(item) else None}

    st.markdown("**Benchmarks**")
    targets = [n for n in options if n != name][:80]
    benchmarks = []
    for row in list(_rows()):
        cols = st.columns([1.2, 1.6, 1.6, 1.1, 0.4], vertical_alignment="bottom")
        kind_label = cols[0].selectbox("Goal", list(KINDS), key=f"sl_kind_{row}")
        kind = KINDS[kind_label]
        target = cols[1].selectbox("Against", targets, index=row % len(targets), key=f"sl_target_{row}_{format_id}")
        b = Benchmark(kind, target)
        if kind == "ko":
            attacks = [m for m in moves if (dex.move(m) or {}).get("category") in ("Physical", "Special")]
            b.move = cols[2].selectbox("With", attacks or ["(no attacking moves)"], key=f"sl_move_{row}_{name}")
            b.hits = 1 if cols[3].selectbox("In", ["One hit", "Two hits"], key=f"sl_hits_{row}") == "One hit" else 2
        elif kind == "survive":
            s = likely_set(target, format_id)
            their = [m for m, _ in (s or {}).get("moves", []) if (dex.move(m) or {}).get("category") in ("Physical", "Special")]
            b.move = cols[2].selectbox("Its move", their or ["(no attacking moves)"], key=f"sl_their_{row}_{target}")
        else:
            reach = cols[2].selectbox("Beat", ["Every common spread", "Its usual spread"], key=f"sl_reach_{row}")
            b.every_spread = reach == "Every common spread"
            b.scarf = cols[3].checkbox("If it has Scarf", key=f"sl_scarf_{row}")
        if cols[4].button("✕", key=f"sl_del_{row}", help="Remove this benchmark") and len(st.session_state.sl_rows) > 1:
            st.session_state.sl_rows.remove(row)
            st.rerun()
        if not b.move.startswith("(") or kind == "outspeed":
            benchmarks.append(b)

    a, b_ = st.columns([1, 5])
    if a.button("Add benchmark", disabled=len(_rows()) >= MAX_ROWS):
        st.session_state.sl_rows.append(st.session_state.sl_next)
        st.session_state.sl_next += 1
        st.rerun()
    run = b_.button("Find the smallest spread", type="primary")

    if run:
        with st.spinner("Searching spreads with the damage calculator..."):
            st.session_state.sl_result = (name, format_id, item, Lab(base, benchmarks, format_id).run(), benchmarks, moves, base)
    saved = st.session_state.get("sl_result")
    if not saved or saved[0] != name or saved[1] != format_id:
        st.caption("Pick what this Pokémon needs to do, then find the smallest spread that does all of it. "
                   "Every result is rechecked with the damage calculator.")
        return
    _, _, item_used, result, benchmarks, moves, base = saved
    left, right = st.columns([1.1, 1])
    with left:
        if result.ok:
            spare = result.budget - result.used
            unit = "stat points" if game == "champions" else "EVs"
            st.markdown(STYLE + f'<div class="sl-result"><div class="big">{escape(spread_text(result.nature, result.evs, game))}</div>'
                        f'<div class="sub">Uses {result.used} of {result.budget} {unit}, {spare} left to put anywhere.</div></div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(STYLE + f'<div class="sl-result"><div class="big">No spread does all of it</div>'
                        f'<div class="sub">{escape(result.problem)}</div></div>', unsafe_allow_html=True)
        st.markdown(STYLE + "".join(_check_html(*c) for c in result.checks), unsafe_allow_html=True)
        if result.ok:
            st.code(showdown_block(name, base.get("item"), base.get("ability"), result.nature, result.evs, moves), language=None)
    with right:
        st.markdown("**What the ladder runs**")
        rows = []
        for nature, evs, share in ladder_spreads(name, format_id, n=5):
            checks = check_spread(base, nature, evs, benchmarks, format_id) if benchmarks else []
            hit = sum(1 for _, ok, _ in checks if ok)
            rows.append({"Spread": spread_text(nature, evs, game).replace(" (stat points)", ""), "Share": f"{share * 100:.0f}%",
                         "Hits": f"{hit} of {len(checks)}"})
        if rows:
            st.dataframe(rows, hide_index=True, width="stretch")
            st.caption("How the most common spreads for this Pokémon do on the same benchmarks.")
