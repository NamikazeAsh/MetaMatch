"""Spread Lab: the smallest EV (or Champions stat point) spread that hits the benchmarks you pick."""
from html import escape

import streamlit as st

from metamatch import config
from metamatch.auditor import load_chaos_data
from metamatch.engine.dex import dex_for_format
from metamatch.engine.sets import likely_set
from metamatch.engine.spread_lab import (LABELS, STATS, Benchmark, Lab, _budget, check_spread, ladder_spreads,
                                         showdown_block, spread_text)
from metamatch.sprites import get_sprite
from metamatch.ui import section_header

KINDS = {"Outspeed": "outspeed", "Knock out": "ko", "Survive a hit": "survive"}
KIND_TAG = {"outspeed": ("SPEED", "#22d3ee"), "ko": ("KNOCKOUT", "#34d399"), "survive": ("SURVIVE", "#fbbf24")}
MAX_ROWS = 6
STYLE = """
<style>
.sl-mon { display: grid; grid-template-columns: 84px 1fr; gap: 16px; align-items: center; padding: 14px 18px; border-radius: 14px;
  background: linear-gradient(135deg, rgba(34,211,238,.08), rgba(255,255,255,.02)); border: 1px solid rgba(34,211,238,.25); }
.sl-mon img { width: 84px; height: 84px; object-fit: contain; filter: drop-shadow(0 0 8px rgba(34,211,238,.3)); }
.sl-mon .nm { font-size: 1.35rem; font-weight: 800; }
.sl-mon .meta { color: #9fb0cc; font-size: .9rem; margin-top: 2px; }
.sl-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.sl-chip { font-size: .76rem; padding: 2px 10px; border-radius: 999px; background: rgba(255,255,255,.06); color: #c6d1e3; }
.sl-tag { display: inline-block; font: 800 .68rem system-ui, sans-serif; letter-spacing: .12em; padding: 3px 9px; border-radius: 999px; }
.sl-sentence { color: #9fb0cc; font-size: .86rem; margin-top: -4px; }
.sl-result { background: rgba(34,211,238,.06); border: 1px solid rgba(34,211,238,.35); border-radius: 14px; padding: 18px 20px; }
.sl-result.fail { background: rgba(248,113,113,.06); border-color: rgba(248,113,113,.35); }
.sl-result .eyebrow { font: 700 .7rem system-ui, sans-serif; letter-spacing: .14em; color: #22d3ee; text-transform: uppercase; }
.sl-result.fail .eyebrow { color: #f87171; }
.sl-result .big { font: 700 1.4rem/1.3 'JetBrains Mono', monospace; color: #e6edf7; margin-top: 4px; }
.sl-budget { margin-top: 12px; }
.sl-budget .row { display: flex; justify-content: space-between; font-size: .84rem; color: #9fb0cc; }
.sl-track { height: 8px; border-radius: 4px; background: rgba(255,255,255,.08); overflow: hidden; margin-top: 4px; }
.sl-track i { display: block; height: 100%; border-radius: 4px; background: linear-gradient(90deg, #22d3ee, #34d399); }
.sl-stats { display: grid; gap: 6px; margin-top: 14px; }
.sl-stat { display: grid; grid-template-columns: 36px 1fr 38px; gap: 10px; align-items: center; font-size: .82rem; }
.sl-stat span:first-child { color: #9fb0cc; font-weight: 600; }
.sl-stat .bar { height: 10px; border-radius: 5px; background: rgba(255,255,255,.06); overflow: hidden; }
.sl-stat .bar i { display: block; height: 100%; border-radius: 5px; background: #22d3ee; }
.sl-stat b { text-align: right; font-variant-numeric: tabular-nums; }
.sl-stat.zero { opacity: .4; }
.sl-check { display: grid; grid-template-columns: 22px 1fr auto; gap: 10px; align-items: center; padding: 9px 12px; margin-top: 6px;
  border-radius: 10px; background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.07); }
.sl-check .mark { font-weight: 800; }
.sl-check.ok .mark { color: #34d399; } .sl-check.bad .mark { color: #f87171; }
.sl-check .detail { color: #9fb0cc; font-family: 'JetBrains Mono', monospace; font-size: .8rem; }
.sl-ladder { width: 100%; border-collapse: separate !important; border-spacing: 0 6px; border: none !important; }
.sl-ladder th, .sl-ladder td { border: none !important; padding: 8px 10px; font-size: .86rem; }
.sl-ladder th { color: #9fb0cc; font-weight: 600; text-align: left; font-size: .76rem; }
.sl-ladder td { background: rgba(255,255,255,.03); }
.sl-ladder td:first-child { border-radius: 10px 0 0 10px; font-family: 'JetBrains Mono', monospace; font-size: .8rem; }
.sl-ladder td:last-child { border-radius: 0 10px 10px 0; text-align: right; }
.sl-hit { font: 700 .74rem system-ui, sans-serif; padding: 2px 9px; border-radius: 999px; }
.sl-hit.all { background: rgba(52,211,153,.15); color: #34d399; }
.sl-hit.some { background: rgba(251,191,36,.15); color: #fbbf24; }
.sl-hit.none { background: rgba(248,113,113,.15); color: #f87171; }
[class*="st-key-slrow_"] { border-left: 3px solid #22d3ee !important; }
[class*="st-key-slrow_"][class*="_ko"] { border-left-color: #34d399 !important; }
[class*="st-key-slrow_"][class*="_survive"] { border-left-color: #fbbf24 !important; }
</style>
"""


def _pokemon_options(format_id, team):
    data = load_chaos_data(format_id) or {}
    ranked = [n for n, e in sorted(data.items(), key=lambda kv: kv[1].get("usage", 0), reverse=True) if e.get("usage", 0) > 0.002]
    mine = [p["Pokemon"] for p in (team or {}).values()]
    return list(dict.fromkeys(mine + ranked)), set(mine)


def _base(name, format_id, team):
    """(calc base spec, moves, where the set came from) for the Pokemon being tuned."""
    for p in (team or {}).values():
        if p["Pokemon"] == name:
            return ({"name": p.get("Forme") or name, "item": p.get("Item") or None,
                     "ability": p.get("Mega Ability") or p.get("Ability") or None},
                    [m["name"] for m in p.get("Moves", [])], "your team")
    s = likely_set(name, format_id)
    if not s:
        return None, [], ""
    return {"name": s["name"], "item": s.get("item"), "ability": s.get("ability")}, [m for m, _ in s["moves"]], "its most common set"


def _attacks(moves, dex):
    return [m for m in moves if (dex.move(m) or {}).get("category") in ("Physical", "Special")]


def _their_attacks(target, format_id, dex):
    s = likely_set(target, format_id)
    return _attacks([m for m, _ in (s or {}).get("moves", [])], dex)


def _rows():
    if "sl_rows" not in st.session_state:
        st.session_state.sl_rows = [0]
        st.session_state.sl_next = 1
    return st.session_state.sl_rows


def _reachable_ko(base, format_id, targets, attacks):
    """(target, move, hits) for a knockout among the top threats that a spread can guarantee but that needs some
    investment, so the example shows the search at work. Falls back to any reachable one."""
    fallback = None
    for target in targets[1:10]:
        for move in attacks:
            for hits in (1, 2):
                r = Lab(base, [Benchmark("ko", target, move, hits)], format_id).run()
                if r.ok and r.used > 0:
                    return target, move, hits
                if r.ok and not fallback:
                    fallback = (target, move, hits)
    return fallback


def _load_example(format_id, name, targets, attacks, base):
    """Three benchmarks to show how it works: outspeed, a 2HKO and a hit to survive. Runs as a button callback."""
    dex = dex_for_format(format_id)
    st.session_state.sl_rows = [0, 1, 2]
    st.session_state.sl_next = 3
    st.session_state["sl_kind_0"], st.session_state[f"sl_target_0_{format_id}"] = "Outspeed", targets[0]
    st.session_state["sl_reach_0"], st.session_state["sl_scarf_0"] = "Its usual spread", False
    ko = _reachable_ko(base, format_id, targets, attacks) if attacks else None
    if ko:
        st.session_state["sl_kind_1"], st.session_state[f"sl_target_1_{format_id}"] = "Knock out", ko[0]
        st.session_state[f"sl_move_1_{name}"], st.session_state["sl_hits_1"] = ko[1], "One hit" if ko[2] == 1 else "Two hits"
    else:
        st.session_state["sl_kind_1"], st.session_state[f"sl_target_1_{format_id}"] = "Outspeed", targets[1]
    survive_target = next((t for t in targets[2:12] if _their_attacks(t, format_id, dex)), targets[2])
    st.session_state["sl_kind_2"], st.session_state[f"sl_target_2_{format_id}"] = "Survive a hit", survive_target
    their = _their_attacks(survive_target, format_id, dex)
    if their:
        st.session_state[f"sl_their_2_{survive_target}"] = their[0]
    st.session_state.pop("sl_result", None)


def _select(label, options, key, default_index=0, **kw):
    """A selectbox that only sets a default when Session State doesn't already hold one (no Streamlit warning)."""
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]
    if key in st.session_state:
        return st.selectbox(label, options, key=key, **kw)
    return st.selectbox(label, options, index=min(default_index, len(options) - 1), key=key, **kw)


def _mon_card(name, base, moves, source, dex):
    species = dex.species(base["name"]) or dex.species(name) or {}
    types = " / ".join(species.get("types", []))
    sprite = escape(get_sprite(name) or "")
    meta = " · ".join(x for x in (types, base.get("item") or "No item", base.get("ability") or "") if x)
    chips = "".join(f'<span class="sl-chip">{escape(m)}</span>' for m in moves)
    return (f'<div class="sl-mon"><img src="{sprite}" alt=""><div><div class="nm">{escape(name)}</div>'
            f'<div class="meta">{escape(meta)}</div><div class="sl-chips">{chips}</div>'
            f'<div class="meta" style="margin-top:6px">Set from {escape(source)}</div></div></div>')


def _result_card(result, game):
    unit = "stat points" if game == "champions" else "EVs"
    if not result.ok:
        return (f'<div class="sl-result fail"><div class="eyebrow">No spread does all of it</div>'
                f'<div class="big">{escape(result.problem)}</div></div>')
    budget, cap = _budget(game)
    used = result.used
    stats = "".join(
        f'<div class="sl-stat{" zero" if not result.evs.get(k) else ""}"><span>{LABELS[k]}</span>'
        f'<div class="bar"><i style="width:{result.evs.get(k, 0) / cap * 100:.0f}%"></i></div><b>{result.evs.get(k, 0)}</b></div>'
        for k in STATS)
    headline = (spread_text(result.nature, result.evs, game).replace(" (stat points)", "") if used
                else "No investment needed")
    note = "" if used else (f'<div class="row" style="margin-top:6px"><span>Its base stats and item already hit every '
                            f'benchmark, so the whole budget is free.</span><span></span></div>')
    return (f'<div class="sl-result"><div class="eyebrow">Smallest spread that does it</div>'
            f'<div class="big">{escape(headline)}</div>{note}'
            f'<div class="sl-budget"><div class="row"><span>Investment used</span><span>{used} of {budget} {unit}</span></div>'
            f'<div class="sl-track"><i style="width:{used / budget * 100:.0f}%"></i></div>'
            f'<div class="row" style="margin-top:4px"><span>{budget - used} {unit} left to put wherever you like</span><span></span></div></div>'
            f'<div class="sl-stats">{stats}</div></div>')


def _check_html(label, ok, detail):
    cls, mark = ("ok", "✓") if ok else ("bad", "✗")
    return (f'<div class="sl-check {cls}"><span class="mark">{mark}</span><span>{escape(label)}</span>'
            f'<span class="detail">{escape(detail)}</span></div>')


def _ladder_table(rows):
    body = []
    for r in rows:
        cls = "all" if r["hit"] == r["n"] and r["n"] else "none" if r["hit"] == 0 else "some"
        body.append(f'<tr><td>{escape(r["spread"])}</td><td>{r["share"]}</td>'
                    f'<td><span class="sl-hit {cls}">{r["hit"]} of {r["n"]}</span></td></tr>')
    return ('<table class="sl-ladder"><tr><th>Spread</th><th>Share</th><th style="text-align:right">Benchmarks hit</th></tr>'
            + "".join(body) + "</table>")


def render(team=None):
    format_id = st.session_state.get("format_id") or config.DEFAULT_FORMAT
    game = config.format_game(format_id)
    dex = dex_for_format(format_id)
    options, mine = _pokemon_options(format_id, team)
    if not options:
        st.info("No usage stats for this format yet. Run `python scripts/update_meta.py` to download them.")
        return
    st.markdown(STYLE, unsafe_allow_html=True)

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
    st.markdown(STYLE + _mon_card(name, base, moves, source, dex), unsafe_allow_html=True)

    section_header("Benchmarks", "What does it need to do?")
    targets = [n for n in options if n != name][:80]
    attacks = _attacks(moves, dex)
    benchmarks = []
    for row in list(_rows()):
        kind = KINDS[st.session_state.get(f"sl_kind_{row}", "Outspeed")]
        with st.container(border=True, key=f"slrow_{row}_{kind}"):
            cols = st.columns([1.2, 1.6, 1.6, 1.1, 0.4], vertical_alignment="bottom")
            kind = KINDS[cols[0].selectbox("Goal", list(KINDS), key=f"sl_kind_{row}")]
            with cols[1]:
                target = _select("Against", targets, f"sl_target_{row}_{format_id}", default_index=row)
            b = Benchmark(kind, target)
            if kind == "ko":
                b.move = (cols[2].selectbox("With", attacks, key=f"sl_move_{row}_{name}") if attacks else "")
                b.hits = 1 if cols[3].selectbox("In", ["One hit", "Two hits"], key=f"sl_hits_{row}") == "One hit" else 2
            elif kind == "survive":
                their = _their_attacks(target, format_id, dex)
                b.move = cols[2].selectbox("Its move", their, key=f"sl_their_{row}_{target}") if their else ""
            else:
                reach = cols[2].selectbox("Beat", ["Every common spread", "Its usual spread"], key=f"sl_reach_{row}")
                b.every_spread = reach == "Every common spread"
                b.scarf = cols[3].checkbox("If it has Scarf", key=f"sl_scarf_{row}")
            if cols[4].button("✕", key=f"sl_del_{row}", help="Remove this benchmark") and len(st.session_state.sl_rows) > 1:
                st.session_state.sl_rows.remove(row)
                st.session_state.pop("sl_result", None)
                st.rerun()
            usable = kind == "outspeed" or bool(b.move)
            tag, color = KIND_TAG[kind]
            st.markdown(f'<div class="sl-sentence"><span class="sl-tag" style="background:{color}22;color:{color}">{tag}</span> '
                        f'{escape(b.label() if usable else "No attacking move to use here")}</div>', unsafe_allow_html=True)
            if usable:
                benchmarks.append(b)

    a, b_, c_ = st.columns([1, 1, 2])
    if a.button("Add benchmark", disabled=len(_rows()) >= MAX_ROWS, width="stretch"):
        st.session_state.sl_rows.append(st.session_state.sl_next)
        st.session_state.sl_next += 1
        st.rerun()
    b_.button("Try an example", width="stretch", on_click=_load_example, args=(format_id, name, targets, attacks, base),
              help="Fills in three benchmarks to show how it works.")
    run = c_.button("Find the smallest spread", type="primary", width="stretch")

    if run and benchmarks:
        with st.spinner("Searching spreads with the damage calculator..."):
            st.session_state.sl_result = (name, format_id, Lab(base, benchmarks, format_id).run(), benchmarks, moves, base)
    saved = st.session_state.get("sl_result")
    if not saved or saved[0] != name or saved[1] != format_id:
        st.caption("Pick what this Pokémon needs to do, then find the smallest spread that does all of it. "
                   "Every result is rechecked with the damage calculator.")
        return
    _, _, result, benchmarks, moves, base = saved
    st.markdown("---")
    left, right = st.columns([1.05, 1], gap="large")
    with left:
        st.markdown(STYLE + _result_card(result, game) + "".join(_check_html(*c) for c in result.checks),
                    unsafe_allow_html=True)
        if result.ok:
            st.markdown("**Ready to paste**")
            st.code(showdown_block(name, base.get("item"), base.get("ability"), result.nature, result.evs, moves), language=None)
    with right:
        st.markdown("**How the ladder's spreads do**")
        rows = []
        for nature, evs, share in ladder_spreads(name, format_id, n=5):
            checks = check_spread(base, nature, evs, benchmarks, format_id) if benchmarks else []
            rows.append({"spread": spread_text(nature, evs, game).replace(" (stat points)", ""), "share": f"{share * 100:.0f}%",
                         "hit": sum(1 for _, ok, _ in checks if ok), "n": len(checks)})
        if rows:
            st.markdown(STYLE + _ladder_table(rows), unsafe_allow_html=True)
            st.caption(f"The five spreads players run most on {name}, on the same benchmarks.")
