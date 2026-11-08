"""Coach Guide tab: a pilot guide written by the engine from the Threat Board, Speed and type data."""
import json
from html import escape

import streamlit as st

from metamatch import config
from metamatch.engine import guide as engine_guide
from metamatch.sprites import get_sprite
from metamatch.ui import section_header

STYLE = """
<style>
.cg-win { display: grid; grid-template-columns: 120px 1fr; gap: 18px; align-items: center; padding: 18px 20px; border-radius: 14px;
  background: linear-gradient(135deg, rgba(0,212,255,.08), rgba(255,255,255,.02)); border: 1px solid rgba(0,212,255,.28); margin-bottom: 14px; }
.cg-win img { width: 120px; height: 120px; object-fit: contain; filter: drop-shadow(0 6px 14px rgba(0,0,0,.45)); }
.cg-eyebrow { font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; color: #00d4ff; font-weight: 700; }
.cg-win .nm { font-size: 1.7rem; font-weight: 800; color: #fff; line-height: 1.2; margin: 2px 0 8px; }
.cg-points { display: flex; flex-direction: column; gap: 5px; }
.cg-point { display: grid; grid-template-columns: 18px 1fr; gap: 6px; font-size: .92rem; color: #d6deeb; }
.cg-point b { color: #34d399; }
.cg-keep { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 10px; font-size: .85rem; color: #9fb0cc; }
.cg-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px 2px 2px; border-radius: 999px; font-size: .8rem;
  background: rgba(248,113,113,.10); border: 1px solid rgba(248,113,113,.28); color: #fecaca; }
.cg-chip img { width: 26px; height: 26px; object-fit: contain; }
.cg-head { font-weight: 700; font-size: 1.05rem; margin: 12px 0 8px; color: #e6edf7; }
.cg-cards { display: grid; gap: 10px; }
.cg-card { display: grid; grid-template-columns: 56px 1fr; gap: 12px; align-items: start; padding: 12px 14px; border-radius: 12px;
  background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.07); }
.cg-card img { width: 56px; height: 56px; object-fit: contain; }
.cg-card .nm { font-weight: 700; margin-bottom: 4px; }
.cg-card .cg-point { font-size: .86rem; }
.cg-best { display: inline-block; margin-left: 8px; font-size: .7rem; font-weight: 700; padding: 1px 8px; border-radius: 999px;
  background: rgba(52,211,153,.14); color: #34d399; vertical-align: middle; }
.cg-type { display: inline-block; font-size: .72rem; font-weight: 700; padding: 1px 8px; border-radius: 6px; color: #fff; margin: 0 3px 3px 0; }
.cg-row { display: grid; grid-template-columns: 78px 1fr; gap: 8px; font-size: .84rem; align-items: baseline; margin-top: 4px; }
.cg-row .k { white-space: nowrap; color: #8fa1bf; font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; }
.cg-gone { text-decoration: line-through; opacity: .55; }
.cg-note { font-size: .84rem; color: #9fb0cc; margin-top: 6px; }
.cg-combos { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.cg-combo { padding: 12px 14px; border-radius: 12px; background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.07); min-width: 0; }
.cg-duo { display: flex; align-items: center; gap: 2px; margin-bottom: 4px; }
.cg-duo img { width: 48px; height: 48px; object-fit: contain; }
.cg-duo .plus { color: #8fa1bf; font-weight: 700; margin: 0 4px; }
.cg-combo .nm { font-weight: 700; margin-bottom: 6px; }
.cg-watch { display: grid; gap: 10px; }
.cg-threat { display: grid; grid-template-columns: 48px 1fr; gap: 10px; align-items: center; padding: 10px 12px; border-radius: 12px;
  background: rgba(248,113,113,.05); border: 1px solid rgba(248,113,113,.25); }
.cg-threat img { width: 48px; height: 48px; object-fit: contain; }
.cg-threat .nm { font-weight: 700; }
.cg-threat small { color: #fca5a5; font-size: .82rem; }
@media (max-width: 900px) { .cg-combos, .cg-watch { grid-template-columns: 1fr; } .cg-win { grid-template-columns: 80px 1fr; }
  .cg-win img { width: 80px; height: 80px; } }
</style>
"""


@st.cache_data(show_spinner=False, max_entries=16)
def _guide(team_json, format_id, stats_month):
    from metamatch.tabs.tab_threats import _board
    team = json.loads(team_json)
    return engine_guide.team_guide(team, format_id, _board(team_json, format_id, stats_month))


def _img(name):
    return f'<img src="{escape(get_sprite(name) or "")}" alt="">'


def _points(points, mark="✓"):
    return '<div class="cg-points">' + "".join(
        f'<div class="cg-point"><b>{mark}</b><span>{escape(p)}</span></div>' for p in points) + "</div>"


def _types(types, type_map, gone=()):
    if not types:
        return '<span style="color:#34d399">none</span>'
    return "".join(f'<span class="cg-type{" cg-gone" if t in gone else ""}" '
                   f'style="background:{type_map.get(t, {}).get("color", "#555")}">{escape(t)}</span>' for t in types)


def _win(w):
    keep = ""
    if w["threats"]:
        chips = "".join(f'<span class="cg-chip">{_img(t)}{escape(t)}</span>' for t in w["threats"])
        keep = f'<div class="cg-keep">Keep it healthy until these are worn down: {chips}</div>'
    else:
        keep = f'<div class="cg-keep">{escape(w["keep"])}</div>'
    return (f'<div class="cg-win">{_img(w["name"])}<div><div class="cg-eyebrow">Win condition</div>'
            f'<div class="nm">{escape(w["name"])}</div>{_points(w["points"])}{keep}</div></div>')


def _leads(leads):
    return '<div class="cg-head">Leads</div><div class="cg-cards">' + "".join(
        f'<div class="cg-card">{_img(x["name"])}<div><div class="nm">{escape(x["name"])}</div>{_points(x["points"])}</div></div>'
        for x in leads) + "</div>"


def _tera(tera, type_map):
    if not tera:
        return '<div class="cg-head">Tera plan</div><div class="cg-note">No Tera Types listed on this team.</div>'
    cards = ""
    for x in tera[:3]:
        best = '<span class="cg-best">Best Tera</span>' if x["best"] else ""
        cards += (f'<div class="cg-card">{_img(x["name"])}<div><div class="nm">{escape(x["name"])} to '
                  f'{_types([x["tera"]], type_map)}{best}</div>'
                  f'<div class="cg-row"><span class="k">Weak to</span><span>{_types(x["before"], type_map, gone=x["removed"])}</span></div>'
                  f'<div class="cg-row"><span class="k">After Tera</span><span>{_types(x["after"], type_map)}</span></div>'
                  f'<div class="cg-note">{escape(x["note"])}.</div></div></div>')
    return '<div class="cg-head">Tera plan</div><div class="cg-cards">' + cards + "</div>"


def _mega(mega):
    if not mega:
        return '<div class="cg-head">Mega Evolution</div><div class="cg-note">No Mega Stone on this team.</div>'
    return '<div class="cg-head">Mega Evolution</div><div class="cg-cards">' + "".join(
        f'<div class="cg-card">{_img(x["forme"])}<div><div class="nm">{escape(x["name"])}</div>{_points(x["points"])}</div></div>'
        for x in mega) + "</div>"


def _combos(combos):
    if not combos:
        return ""
    cards = "".join(
        f'<div class="cg-combo"><div class="cg-duo">{_img(a)}<span class="plus">+</span>{_img(b)}</div>'
        f'<div class="nm">{escape(a)} and {escape(b)}</div>{_points(c["points"], "•")}</div>'
        for c in combos for a, b in [c["pair"]])
    return f'<div class="cg-head">Pairs that cover each other</div><div class="cg-combos">{cards}</div>'


def _watch(watch):
    if not watch:
        return ""
    cards = "".join(
        f'<div class="cg-threat">{_img(w["name"])}<div><div class="nm">{escape(w["name"])}</div>'
        f'<small>{escape(w["text"])} · on {w["usage"]:g}% of teams</small></div></div>' for w in watch)
    return f'<div class="cg-head">Watch out for</div><div class="cg-watch">{cards}</div>'


def render(type_map=None):
    from metamatch.tabs.tab_threats import _stats_month
    type_map = type_map or {}
    team = st.session_state.analysis["team"]
    format_id = config.team_format(team)
    section_header("Game plan", "Team Pilot Guide")
    label = config.FORMATS.get(format_id, {}).get("label", format_id)
    st.caption(f"Built from your Threat Board, Speed and type matchups against the most used Pokémon in {label}. "
               "Every line is calculated, not generated, so it only names moves your team actually runs.")
    with st.spinner("Writing your guide..."):
        g = _guide(json.dumps(team, sort_keys=True, default=str), format_id, _stats_month())
    if not g.win:
        st.info("The guide needs the damage calc and this format's usage data.")
        return
    st.markdown(STYLE + _win(g.win), unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        st.markdown(STYLE + _leads(g.leads) + _watch(g.watch), unsafe_allow_html=True)
    with right:
        st.markdown(STYLE + (_mega(g.mega) if config.format_game(format_id) == "champions" else _tera(g.tera, type_map)),
                    unsafe_allow_html=True)
    st.markdown(STYLE + _combos(g.combos), unsafe_allow_html=True)
    st.caption(f"Matchups are one on one against each threat's most common set (top {g.n_threats} by usage); "
               "switching, hazards and setup turns aren't simulated.")
