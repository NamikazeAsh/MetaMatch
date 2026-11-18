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
.cg-mega { position: relative; padding: 16px 18px; border-radius: 16px; overflow: visible;
  background: radial-gradient(circle at 0% 0%, color-mix(in srgb, var(--c) 20%, transparent), transparent 50%), linear-gradient(145deg, #1c2232, #141924);
  border: 1px solid color-mix(in srgb, var(--c) 38%, transparent); box-shadow: 0 10px 24px rgba(0,0,0,.4), inset 1px 1px 0 rgba(255,255,255,.05); }
.cg-mega-head { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.cg-mega-evo { display: flex; align-items: center; gap: 4px; }
.cg-mega-evo img { width: 56px; height: 56px; object-fit: contain; opacity: .75; }
.cg-mega-to img { width: 80px; height: 80px; opacity: 1; filter: drop-shadow(0 0 14px color-mix(in srgb, var(--c) 70%, transparent)); }
.cg-mega-arrow { position: relative; display: grid; place-items: center; width: 46px; height: 20px; }
.cg-mega-arrow::before { content: ""; position: absolute; left: 0; right: 6px; top: 50%; height: 2px;
  background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--c) 80%, #fff)); }
.cg-mega-arrow::after { content: ""; position: absolute; right: 0; top: 50%; transform: translateY(-50%); border: 5px solid transparent;
  border-left: 7px solid color-mix(in srgb, var(--c) 80%, #fff); }
.cg-stone { z-index: 1; width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; background: #0f1219;
  border: 1px solid color-mix(in srgb, var(--c) 60%, transparent); box-shadow: 0 0 12px -2px var(--c); }
.cg-stone img { width: 22px; height: 22px; object-fit: contain; opacity: 1; }
.cg-mega-k { font-size: .64rem; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: color-mix(in srgb, var(--c) 70%, #fff); }
.cg-mega-nm { font-size: 1.3rem; font-weight: 900; color: #fff; line-height: 1.15; }
.cg-mega-sub { font-size: .8rem; color: #8fa1bf; margin-top: 2px; }
.cg-mega-rows { display: grid; gap: 8px; margin: 14px 0 4px; }
.cg-mega-sep { color: #6f7a90; font-weight: 700; margin: 0 2px; }
.cg-mega-same { font-size: .74rem; color: #6f7a90; }
.cg-ab { position: relative; display: inline-flex; align-items: center; padding: 2px 10px; border-radius: 999px; font-size: .78rem;
  font-weight: 700; color: #c8d1e0; background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.1); cursor: help; outline: none; }
.cg-ab.new { color: #fff; background: color-mix(in srgb, var(--c) 22%, transparent); border-color: color-mix(in srgb, var(--c) 60%, transparent);
  box-shadow: 0 0 12px -4px var(--c); }
.cg-ab:hover .cg-tip, .cg-ab:focus .cg-tip { opacity: 1; visibility: visible; transform: translateX(-50%) translateY(0); }
.cg-tip.wide { width: 240px; white-space: normal; font-weight: 500; line-height: 1.4; }
.cg-tip.wide b { display: block; color: #fff; font-weight: 800; margin-bottom: 2px; }
.cg-stats { display: grid; gap: 6px; margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.06); }
.cg-stat { display: grid; grid-template-columns: 40px 1fr 34px 38px; gap: 10px; align-items: center; font-size: .8rem; }
.cg-stat .k { color: #8fa1bf; font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.cg-stat .bar { position: relative; height: 8px; border-radius: 999px; background: rgba(255,255,255,.05); overflow: hidden; }
.cg-stat .bar i { position: absolute; top: 0; bottom: 0; left: 0; border-radius: 999px; }
.cg-stat .bar .base { background: #3a4358; }
.cg-stat .bar .gain.up { background: linear-gradient(90deg, color-mix(in srgb, var(--c) 70%, #fff), var(--c)); box-shadow: 0 0 10px var(--c); }
.cg-stat .bar .gain.down { background: repeating-linear-gradient(45deg, rgba(248,113,113,.55) 0 3px, transparent 3px 6px); }
.cg-stat .v { color: #e6edf7; font-weight: 700; text-align: right; }
.cg-stat .d { font-weight: 800; font-size: .74rem; }
.cg-stat .d.up { color: #5fd38d; } .cg-stat .d.down { color: #f87171; }
.cg-smogon { margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.06); }
.cg-smogon-k { font-size: .64rem; font-weight: 800; letter-spacing: .12em; text-transform: uppercase;
  color: color-mix(in srgb, var(--c) 70%, #fff); margin-bottom: 6px; }
.cg-smogon blockquote { margin: 0; padding: 2px 0 2px 12px; border-left: 2px solid color-mix(in srgb, var(--c) 55%, transparent);
  font-size: .86rem; line-height: 1.55; color: #d6deeb; }
.cg-smogon-more { margin: 6px 0 0 14px; font-size: .84rem; line-height: 1.55; color: #aab3c5; }
.cg-smogon-more summary { cursor: pointer; font-size: .74rem; font-weight: 700; color: #7fe6ff; list-style: none; }
.cg-smogon-more summary::-webkit-details-marker { display: none; }
.cg-smogon-more summary::before { content: "+ "; }
.cg-smogon-more[open] summary::before { content: "- "; }
.cg-smogon-more p { margin: 6px 0 0; }
.cg-stat.total { margin-top: 2px; } .cg-mega-bst { color: #aab3c5; font-size: .8rem; } .cg-mega-bst b { color: #fff; }
.cg-rec { margin-top: 10px; padding-top: 9px; border-top: 1px solid rgba(255,255,255,.06); display: grid; gap: 7px; }
.cg-rec-h { font-size: .64rem; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; color: #00d4ff; }
.cg-rec-row { display: grid; grid-template-columns: 96px 1fr; gap: 8px; align-items: center; }
.cg-rec-k { color: #8fa1bf; font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; font-weight: 700; line-height: 1.25; min-width: 0; }
.cg-rec-k small { display: block; text-transform: none; letter-spacing: 0; font-weight: 500; color: #6f7a90; font-size: .7rem;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cg-tis { display: flex; flex-wrap: wrap; gap: 9px; align-items: center; }
.cg-ti { position: relative; display: inline-flex; align-items: center; gap: 5px; cursor: help; outline: none; }
.cg-ti .o { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; transition: transform .12s ease;
  background: radial-gradient(circle at 35% 30%, color-mix(in srgb, var(--c) 75%, #fff), var(--c) 60%);
  box-shadow: 0 0 10px -3px var(--c), inset 0 -3px 5px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.3); }
.cg-ti .o i { display: block; width: 13px; height: 13px; background-size: contain; background-repeat: no-repeat; background-position: center;
  filter: drop-shadow(0 1px 1px rgba(0,0,0,.35)); }
.cg-ti:hover .o { transform: scale(1.12); }
.cg-ti.mine .o { box-shadow: 0 0 0 2px #121722, 0 0 0 3.5px #00d4ff, 0 0 14px rgba(0,212,255,.55); }
.cg-ti b { font-size: .74rem; color: #c8d1e0; font-weight: 700; }
.cg-ti.mine b { color: #7fe6ff; }
.cg-tip { position: absolute; bottom: calc(100% + 7px); left: 50%; transform: translateX(-50%) translateY(3px); white-space: nowrap;
  font-size: .68rem; font-weight: 700; color: #fff; background: #0b0f17; border: 1px solid rgba(255,255,255,.14); padding: 3px 8px;
  border-radius: 7px; opacity: 0; visibility: hidden; transition: opacity .12s ease, transform .12s ease, visibility .12s;
  pointer-events: none; z-index: 45; box-shadow: 0 6px 16px rgba(0,0,0,.5); }
.cg-ti:hover .cg-tip, .cg-ti:focus .cg-tip { opacity: 1; visibility: visible; transform: translateX(-50%) translateY(0); }
.cg-rare { font-size: .76rem; color: #ffd866; display: flex; gap: 6px; align-items: center; }
.cg-rare::before { content: "!"; font-weight: 800; }
.cg-mini-h { display: flex; align-items: baseline; justify-content: space-between; margin: 14px 2px 6px; font-weight: 700;
  font-size: .86rem; color: #c8d1e0; }
.cg-mini-h span { font-size: .68rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: #6f7a90; }
.cg-minis { display: grid; gap: 6px; }
.cg-mini { display: grid; grid-template-columns: 40px minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 6px 12px 6px 8px;
  border-radius: 12px; background: rgba(255,255,255,.025); border: 1px solid rgba(255,255,255,.06); }
.cg-mini img { width: 40px; height: 40px; object-fit: contain; }
.cg-mini-nm { font-weight: 700; font-size: .88rem; color: #e6edf7; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.cg-mini-nm .cg-type { margin: 0; }
.cg-dot { width: 4px; height: 4px; border-radius: 50%; background: #3a4358; }
.cg-rare-dot { display: inline-grid; place-items: center; width: 16px; height: 16px; margin-left: 6px; border-radius: 50%; font-size: .7rem;
  font-weight: 800; color: #1a1408; background: #ffd866; vertical-align: middle; cursor: help; }
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
.cg-engs { display:grid; gap:14px; margin:4px 0 6px; }
.cg-eng { border-radius:18px; padding:16px 18px; min-width:0;
  background:radial-gradient(circle at 4% 0%, color-mix(in srgb, var(--c) 22%, transparent), transparent 45%), linear-gradient(145deg, #1c2232, #141924);
  border:1px solid color-mix(in srgb, var(--c) 35%, transparent);
  box-shadow:10px 10px 24px rgba(0,0,0,0.45), -6px -6px 16px rgba(255,255,255,0.025), inset 1px 1px 0 rgba(255,255,255,0.05); }
.cg-eng.half { border:1px dashed rgba(255,216,102,0.5); background:linear-gradient(145deg, #1c2030, #151924); }
.cg-eng-head { display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
.cg-eng-ico { width:46px; height:46px; border-radius:50%; display:grid; place-items:center; flex-shrink:0;
  background:radial-gradient(circle at 35% 30%, color-mix(in srgb, var(--c) 75%, #fff), var(--c) 60%);
  box-shadow:0 0 18px -3px var(--c), inset 0 -3px 5px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.3); }
.cg-eng.half .cg-eng-ico { filter:grayscale(0.6); }
.cg-eng-ico i { display:block; width:24px; height:24px; background-size:contain; background-repeat:no-repeat; background-position:center; }
.cg-eng-k { font-size:0.62rem; font-weight:800; letter-spacing:0.12em; text-transform:uppercase; color:#8a93a6; }
.cg-eng-t { font-size:1.25rem; font-weight:900; color:#fff; line-height:1.1; }
.cg-eng-setters { display:flex; flex-wrap:wrap; align-items:center; gap:8px; flex:1 1 260px; min-width:0; }
.cg-eng-setter { display:inline-flex; align-items:center; gap:6px; padding:3px 12px 3px 3px; border-radius:999px;
  background:rgba(0,0,0,0.25); border:1px solid rgba(255,255,255,0.08); font-size:0.8rem; color:#d6dbe6; }
.cg-eng-setter img { width:30px; height:30px; object-fit:contain; }
.cg-eng-setter b { color:#fff; }
.cg-eng-ladder { margin-left:auto; font-size:0.72rem; font-weight:700; color:#7fe6ff; padding:3px 10px; border-radius:999px;
  background:rgba(0,212,255,0.08); border:1px solid rgba(0,212,255,0.25); }
.cg-eng-users { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:10px; margin-top:14px; }
.cg-eng-user { display:grid; grid-template-columns:56px minmax(0, 1fr); gap:12px; align-items:start; padding:10px 12px; border-radius:14px;
  background:rgba(0,0,0,0.22); border:1px solid rgba(255,255,255,0.06); }
.cg-eng-user img { width:56px; height:56px; object-fit:contain; filter:drop-shadow(0 0 8px color-mix(in srgb, var(--c) 55%, transparent)); }
.cg-eng-user .nm { font-weight:800; color:#fff; margin-bottom:4px; }
.cg-eng-user .cg-point { font-size:0.82rem; }
.cg-eng-minor { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-top:10px; font-size:0.74rem; color:#8a93a6; }
.cg-eng-chip { display:inline-flex; align-items:center; gap:5px; padding:2px 10px 2px 2px; border-radius:999px; color:#d6dbe6;
  background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); }
.cg-eng-chip img { width:24px; height:24px; object-fit:contain; }
.cg-eng-foot { display:flex; flex-direction:column; gap:4px; margin-top:12px; }
.cg-eng-line { display:grid; grid-template-columns:18px 1fr; gap:6px; font-size:0.8rem; color:#c8ccd4; }
.cg-eng-line b.bad { color:#ffd866; } .cg-eng-line b.ok { color:#5fd38d; }
.cg-eng-half { font-size:0.9rem; color:#e6eaf2; margin-top:10px; }
@media (max-width: 900px) { .cg-eng-users { grid-template-columns:minmax(0, 1fr); } .cg-eng-ladder { margin-left:0; } }
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


def _ti(t, type_map, tip, mine=False, share=None):
    """A round type icon with its name and source on hover; ringed when it is the team's own Tera."""
    from metamatch.sprites import get_type_icon
    glyph = get_type_icon(t)
    inner = f'<i style="background-image:url({glyph})"></i>' if glyph else escape(t[:2])
    pct = f"<b>{share * 100:.0f}%</b>" if share is not None else ""
    return (f'<span class="cg-ti{" mine" if mine else ""}" tabindex="0" style="--c:{type_map.get(t, {}).get("color", "#666")}">'
            f'<span class="o">{inner}</span>{pct}<span class="cg-tip">{escape(tip)}</span></span>')


def _recommended(x, type_map):
    """Smogon's closest set and the ladder's top Tera types, the team's own pick ringed; '' without data."""
    rows = ""
    if x.get("smogon"):
        set_name, types = x["smogon"]
        icons = "".join(_ti(t, type_map, f"{t}: on Smogon's {set_name} set", t == x["tera"]) for t in types)
        if x.get("smogon_other"):
            icons += ('<span class="cg-dot"></span>'
                      + _ti(x["tera"], type_map, f"{x['tera']}: on Smogon's {x['smogon_other']} set", True))
        rows += (f'<div class="cg-rec-row"><span class="cg-rec-k">Smogon<small>{escape(set_name)}</small></span>'
                 f'<span class="cg-tis">{icons}</span></div>')
    if x.get("ladder"):
        icons = "".join(_ti(t, type_map, f"{t}: {share * 100:.0f}% of ladder sets this month", t == x["tera"], share)
                        for t, share in x["ladder"])
        rows += f'<div class="cg-rec-row"><span class="cg-rec-k">Ladder</span><span class="cg-tis">{icons}</span></div>'
    if not rows:
        return ""
    flag = ('<div class="cg-rare">Neither Smogon nor many ladder players use this Tera on it</div>'
            if x.get("standing") == "rare" else "")
    return f'<div class="cg-rec"><div class="cg-rec-h">Recommended</div>{rows}{flag}</div>'


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
                  f'<div class="cg-note">{escape(x["note"])}.</div>{_recommended(x, type_map)}</div></div>')
    # The rest of the team in one compact row each: its pick and what is recommended, nothing else
    rest = ""
    for x in tera[3:]:
        rec = ""
        if x.get("smogon"):
            rec += "".join(_ti(t, type_map, f"{t}: on Smogon's {x['smogon'][0]} set", t == x["tera"]) for t in x["smogon"][1])
            if x.get("smogon_other"):
                rec += _ti(x["tera"], type_map, f"{x['tera']}: on Smogon's {x['smogon_other']} set", True)
        if x.get("ladder"):
            rec += '<span class="cg-dot"></span>' if rec else ""
            rec += "".join(_ti(t, type_map, f"{t}: {s * 100:.0f}% of ladder sets this month", t == x["tera"], s)
                           for t, s in x["ladder"][:2])
        warn = '<span class="cg-rare-dot" title="Unusual pick">!</span>' if x.get("standing") == "rare" else ""
        rest += (f'<div class="cg-mini">{_img(x["name"])}<div class="cg-mini-nm">{escape(x["name"])}'
                 f'<span>{_types([x["tera"]], type_map)}{warn}</span></div><span class="cg-tis">{rec}</span></div>')
    if rest:
        rest = (f'<div class="cg-mini-h">Rest of the team <span>Smogon · ladder share</span></div>'
                f'<div class="cg-minis">{rest}</div>')
    return '<div class="cg-head">Tera plan</div><div class="cg-cards">' + cards + "</div>" + rest


MEGA_STATS = (("hp", "HP"), ("atk", "Atk"), ("def", "Def"), ("spa", "SpA"), ("spd", "SpD"), ("spe", "Spe"))


def _mega_name(forme):
    """'Lopunny-Mega' -> 'Mega Lopunny', 'Charizard-Mega-Y' -> 'Mega Charizard Y'."""
    base, _, rest = forme.partition("-Mega")
    return f"Mega {base}{' ' + rest.lstrip('-') if rest else ''}"


def _ability_chip(name, new=False):
    from metamatch.engine.abilities import describe
    tip = describe(name) or ""
    tip_html = f'<span class="cg-tip wide"><b>{escape(name)}</b>{escape(tip)}</span>' if tip else ""
    return f'<span class="cg-ab{" new" if new else ""}" tabindex="0">{escape(name)}{tip_html}</span>'


def _mega_card(x, type_map):
    from metamatch.sprites import get_item_icon
    # Tinted by the type the Mega gains (Lopunny's Fighting, not its Normal), else its main type
    gained = [t for t in x.get("mega_types") or [] if t not in (x.get("base_types") or [])]
    color = type_map.get((gained or x.get("mega_types") or ["Normal"])[0], {}).get("color", "#00d4ff")
    stone = get_item_icon(x.get("item"))
    stone_html = (f'<span class="cg-ti cg-stone" tabindex="0"><img src="{escape(stone)}" alt="">'
                  f'<span class="cg-tip">{escape(x["item"])}</span></span>') if stone else ""
    head = (f'<div class="cg-mega-head"><div class="cg-mega-evo">{_img(x["name"])}<span class="cg-mega-arrow">'
            f'{stone_html}</span><span class="cg-mega-to">{_img(x["forme"])}</span></div>'
            f'<div><div class="cg-mega-k">Mega Evolution</div><div class="cg-mega-nm">{escape(_mega_name(x["forme"]))}</div>'
            f'<div class="cg-mega-sub">{escape(x["name"])} holding {escape(x.get("item") or "its stone")}</div></div></div>')
    rows = ""
    before, after = x.get("base_types") or [], x.get("mega_types") or []
    if before or after:
        icons = lambda ts, new: "".join(_ti(t, type_map, t + (" (new with Mega Evolution)" if new and t not in before else ""),
                                            new and t not in before) for t in ts)
        change = (f'{icons(before, False)}<span class="cg-mega-sep">&rarr;</span>{icons(after, True)}'
                  if after != before else f'{icons(after, False)}<span class="cg-mega-same">unchanged</span>')
        rows += f'<div class="cg-rec-row"><span class="cg-rec-k">Typing</span><span class="cg-tis">{change}</span></div>'
    if x.get("mega_ability"):
        old = x.get("base_ability")
        change = (f'{_ability_chip(old)}<span class="cg-mega-sep">&rarr;</span>' if old and old != x["mega_ability"] else "")
        rows += (f'<div class="cg-rec-row"><span class="cg-rec-k">Ability</span><span class="cg-tis">{change}'
                 f'{_ability_chip(x["mega_ability"], new=old != x["mega_ability"])}</span></div>')
    bs, ms = x.get("base_stats") or {}, x.get("mega_stats") or {}
    bars = ""
    if bs and ms and all(bs.get(k) is not None and ms.get(k) is not None for k, _ in MEGA_STATS):
        scale = max(180, max(ms.values()))
        for k, label in MEGA_STATS:
            b, m = bs[k], ms[k]
            low, high = min(b, m), max(b, m)
            delta = m - b
            cls = "up" if delta > 0 else "down" if delta < 0 else ""
            bars += (f'<div class="cg-stat"><span class="k">{label}</span><span class="bar">'
                     f'<i class="base" style="width:{low / scale * 100:.1f}%"></i>'
                     f'<i class="gain {cls}" style="left:{low / scale * 100:.1f}%;width:{(high - low) / scale * 100:.1f}%"></i></span>'
                     f'<span class="v">{m}</span><span class="d {cls}">{f"+{delta}" if delta > 0 else delta if delta else ""}</span></div>')
        total_b, total_m = sum(bs.values()), sum(ms.values())
        bars += (f'<div class="cg-stat total"><span class="k">Total</span><span class="cg-mega-bst">{total_b} &rarr; '
                 f'<b>{total_m}</b></span><span class="v"></span><span class="d up">+{total_m - total_b}</span></div>')
        bars = f'<div class="cg-stats">{bars}</div>'
    smogon = ""
    if x.get("smogon"):
        import re
        label, preview, rest = x["smogon"]
        # Smogon's long paragraphs shown three sentences at a time; the words are left exactly as written
        chunks = []
        for p in rest:
            sentences = re.split(r"(?<=[.!?])\s+", p)
            chunks += [" ".join(sentences[i:i + 3]) for i in range(0, len(sentences), 3)]
        more = (f'<details class="cg-smogon-more"><summary>Read more</summary>'
                + "".join(f"<p>{escape(c)}</p>" for c in chunks) + "</details>") if chunks else ""
        smogon = (f'<div class="cg-smogon"><div class="cg-smogon-k">{escape(label)}</div>'
                  f'<blockquote>{escape(preview)}</blockquote>{more}</div>')
    return f'<div class="cg-mega" style="--c:{color}">{head}<div class="cg-mega-rows">{rows}</div>{bars}{smogon}</div>'


def _mega(mega, type_map=None):
    if not mega:
        return '<div class="cg-head">Mega Evolution</div><div class="cg-note">No Mega Stone on this team.</div>'
    return ('<div class="cg-head">Mega Evolution</div><div class="cg-cards">'
            + "".join(_mega_card(x, type_map or {}) for x in mega) + "</div>")


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


def _cond_icon(icon_type, type_map):
    from metamatch.sprites import get_type_icon
    glyph = get_type_icon(icon_type)
    inner = f'<i style="background-image:url({glyph})"></i>' if glyph else ""
    return f'<span class="cg-eng-ico">{inner}</span>'


def _minor_chip(u):
    """'Dragapult · Flamethrower 5 to 7 2HKOs' when the calc found a gain, else its first rule."""
    if u.damage:
        move, off, on, _ = u.damage
        label = f"{move} {off} → {on} 2HKOs"
    else:
        label = u.points[0] if u.points else ""
    return f'<span class="cg-eng-chip">{_img(u.name)}<b>{escape(u.name)}</b> · {escape(label)}</span>'


def _engine(e, type_map):
    from metamatch.engine import synergy
    color = type_map.get(e.icon, {}).get("color", "#00d4ff")
    if not e.setters:
        partners = "".join(f'<span class="cg-eng-chip">{_img(n)}{escape(n)}</span>' for n in e.partners)
        partner_line = (f'<div class="cg-eng-minor">Ladder players pair it with {partners}</div>' if partners else "")
        return (f'<div class="cg-eng half" style="--c:{color}"><div class="cg-eng-head">{_cond_icon(e.icon, type_map)}'
                f'<div><div class="cg-eng-k">Half built</div><div class="cg-eng-t">{escape(e.label)}</div></div></div>'
                f'<div class="cg-eng-half">{escape(synergy.describe(e))}.</div>'
                + "".join(f'<div class="cg-eng-line"><b class="bad">!</b><span>{escape(u.name)}: {escape(u.points[0])}</span></div>'
                          for u in e.users if u.major)
                + partner_line + "</div>")
    setters = "".join(f'<span class="cg-eng-setter">{_img(st["name"])}<b>{escape(st["name"])}</b> {escape(" · ".join(st["how"]))}</span>'
                      for st in e.setters)
    ladder = f'<span class="cg-eng-ladder">{escape(e.ladder)}</span>' if e.ladder else ""
    major = [u for u in e.users if u.major]
    minor = [u for u in e.users if not u.major]
    rows = "".join(f'<div class="cg-eng-user">{_img(u.name)}<div style="min-width:0"><div class="nm">{escape(u.name)}</div>'
                   f'{_points(u.points[:4])}</div></div>' for u in major)
    users = f'<div class="cg-eng-users">{rows}</div>' if rows else ""
    side = (f'<div class="cg-eng-minor">Also boosted {"".join(_minor_chip(u) for u in minor)}</div>' if minor else "")
    foot = "".join(f'<div class="cg-eng-line"><b class="bad">!</b><span>{escape(d)}</span></div>' for d in e.drawbacks)
    foot += "".join(f'<div class="cg-eng-line"><b class="ok">✓</b><span>{escape(d)}</span></div>' for d in e.defense)
    kicker = "Always on" if e.always_on else "Team engine"
    return (f'<div class="cg-eng" style="--c:{color}"><div class="cg-eng-head">{_cond_icon(e.icon, type_map)}'
            f'<div><div class="cg-eng-k">{kicker}</div><div class="cg-eng-t">{escape(e.label)}</div></div>'
            f'<div class="cg-eng-setters">{setters}</div>{ladder}</div>{users}{side}'
            + (f'<div class="cg-eng-foot">{foot}</div>' if foot else "") + "</div>")


def _engines(engines, type_map):
    if not engines:
        return ""
    return ('<div class="cg-head">Team engines</div><div class="cg-engs">'
            + "".join(_engine(e, type_map) for e in engines) + "</div>")


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
    if g.engines:
        st.markdown(STYLE + _engines(g.engines, type_map), unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        st.markdown(STYLE + _leads(g.leads) + _watch(g.watch), unsafe_allow_html=True)
    with right:
        st.markdown(STYLE + (_mega(g.mega, type_map) if config.format_game(format_id) == "champions" else _tera(g.tera, type_map)),
                    unsafe_allow_html=True)
    st.markdown(STYLE + _combos(g.combos), unsafe_allow_html=True)
    st.caption(f"Matchups are one on one against each threat's most common set (top {g.n_threats} by usage); "
               "switching, hazards and setup turns aren't simulated.")
