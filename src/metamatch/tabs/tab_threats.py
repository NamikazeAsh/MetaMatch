"""Threat Board tab: the format's most used Pokemon against each team member, one on one, from the damage calc."""
import json
from html import escape

import streamlit as st

from metamatch import config
from metamatch.engine import threat_board as tb
from metamatch.sprites import get_sprite

N_THREATS = 12
VERDICT_WORD = {"win": "beats", "lose": "loses to", "even": "trades evenly with"}
STYLE = """
<style>
.tb { border-collapse: separate !important; border-spacing: 5px; width: 100%; border: none !important; }
.tb th, .tb td { border: none !important; }
.tb th { font-size: .78rem; font-weight: 600; color: #9fb0cc; text-align: center; padding: 2px 4px; }
.tb td.name { font-weight: 600; white-space: nowrap; padding-right: 10px; }
.tb td.name small { display: block; font-weight: 400; color: #8fa1bf; font-size: .74rem; }
.tb tr.hole td.name { color: #f87171; }
.tb td.c { position: relative; text-align: center; border-radius: 8px; font: 700 .7rem system-ui, sans-serif; letter-spacing: .08em;
  padding: 11px 4px; transition: transform .12s, box-shadow .12s; }
.tb td.win { background: rgba(52,211,153,.15); color: #34d399; }
.tb td.lose { background: rgba(248,113,113,.15); color: #f87171; }
.tb td.even { background: rgba(148,163,184,.15); color: #a3b1c9; }
.tb td.c:hover { transform: scale(1.06); box-shadow: 0 0 0 1px currentColor; z-index: 5; }
.tb .tip { visibility: hidden; opacity: 0; position: absolute; left: 50%; transform: translateX(-50%); top: calc(100% + 8px);
  width: 270px; z-index: 20; text-align: left; letter-spacing: 0; text-transform: none; padding: 12px 14px; border-radius: 12px;
  background: #0f1729; border: 1px solid rgba(255,255,255,.12); box-shadow: 0 14px 30px rgba(0,0,0,.45); color: #dbe4f3;
  font: 400 .82rem/1.45 system-ui, sans-serif; transition: opacity .12s; pointer-events: none; }
.tb tr.up .tip { top: auto; bottom: calc(100% + 8px); }
.tb td.c:hover .tip { visibility: visible; opacity: 1; }
.tip .tt { font-weight: 700; font-size: .88rem; margin-bottom: 8px; }
.tip .tt.win { color: #34d399; } .tip .tt.lose { color: #f87171; } .tip .tt.even { color: #a3b1c9; }
.tip .row { display: grid; grid-template-columns: 72px 1fr; gap: 8px; padding: 3px 0; }
.tip .k { color: #8fa1bf; font-size: .74rem; text-transform: uppercase; letter-spacing: .06em; padding-top: 1px; }
.tip .ko { display: inline-block; margin-left: 6px; font-size: .7rem; font-weight: 700; padding: 0 6px; border-radius: 999px;
  background: rgba(34,211,238,.14); color: #22d3ee; }
.tb-cards { display: grid; gap: 10px; }
.tb-card { display: grid; grid-template-columns: 48px 1fr; gap: 12px; align-items: center; padding: 10px 12px; border-radius: 12px;
  background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.07); }
.tb-card.win { border-left: 3px solid #34d399; } .tb-card.lose { border-left: 3px solid #f87171; }
.tb-card img { width: 48px; height: 48px; object-fit: contain; }
.tb-card .nm { font-weight: 700; }
.tb-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.tb-chip { font-size: .74rem; padding: 2px 9px; border-radius: 999px; background: rgba(148,163,184,.14); color: #c6d1e3; }
.tb-chip.good { background: rgba(52,211,153,.14); color: #34d399; }
.tb-chip.bad { background: rgba(248,113,113,.14); color: #f87171; }
.tb-head { font-weight: 700; margin: 4px 0 8px; }
.tb-empty { color: #8fa1bf; font-size: .9rem; padding: 10px 0; }
.tb-note { font-size: .78rem; color: #8fa1bf; margin-top: 8px; }
</style>
"""


@st.cache_data(show_spinner=False, max_entries=16)
def _board(team_json, format_id, stats_month):
    """Board rows as plain dicts (cached per team, format and stats month)."""
    team = json.loads(team_json)
    rows = tb.threat_board(team, n=N_THREATS, format_id=format_id)
    return [{"name": r.name, "usage": r.usage, "answers": r.answers, "losses": r.losses, "cc": r.checks_data,
             "cells": {m: {"verdict": c.verdict, "parts": c.parts} for m, c in r.cells.items()}} for r in rows]


def _stats_month():
    try:
        return json.loads((config.STATS_DIR / "manifest.json").read_text(encoding="utf-8")).get("month", "")
    except (OSError, ValueError):
        return ""


def _tip(member, threat, cell):
    p = cell["parts"]
    if not p:
        return ""
    ko = lambda k: f'<span class="ko">{escape(k)}</span>' if k else ""
    rows = [("Speed", escape(p["speed"]) + (f"<br>{escape(p['priority'])}" if p["priority"] else "")),
            ("Hits with", escape(p["dealt"]) + ko(p["dealt_ko"])),
            ("Takes", escape(p["taken"]) + ko(p["taken_ko"]))]
    body = "".join(f'<div class="row"><span class="k">{k}</span><span>{v}</span></div>' for k, v in rows)
    title = f"{escape(member)} {VERDICT_WORD[cell['verdict']]} {escape(threat)}"
    return f'<div class="tip"><div class="tt {cell["verdict"]}">{title}</div>{body}</div>'


def _grid(rows, members, sub=None):
    """The win or lose grid. sub(row) gives the line under each threat's name (its usage by default)."""
    sub = sub or (lambda r: f"on {r['usage']:g}% of teams")
    head = "<tr><th></th>" + "".join(f"<th>{escape(m)}</th>" for m in members) + "</tr>"
    body = []
    for i, r in enumerate(rows):
        cells = []
        for m in members:
            c = r["cells"].get(m)
            if not c:
                cells.append('<td class="c even">?</td>')
                continue
            cells.append(f'<td class="c {c["verdict"]}">{c["verdict"].upper()}{_tip(m, r["name"], c)}</td>')
        cls = " ".join(x for x in ("hole" if not r["answers"] else "", "up" if i >= len(rows) / 2 else "") if x)
        body.append(f'<tr class="{cls}"><td class="name">{escape(r["name"])}<small>{escape(sub(r))}</small></td>'
                    + "".join(cells) + "</tr>")
    return f'<table class="tb">{head}{"".join(body)}</table>'


def _cards(names, threat, row, kind):
    if not names:
        return ('<div class="tb-empty">Nobody on your team beats it one on one.</div>' if kind == "win"
                else '<div class="tb-empty">Nobody on your team loses to it one on one.</div>')
    out = []
    for m in names:
        p = row["cells"][m]["parts"]
        speed_good = p["speed"].startswith("Faster")
        chips = [f'<span class="tb-chip {"good" if speed_good else ""}">{escape(p["speed"])}</span>']
        if p["priority"]:
            chips.append(f'<span class="tb-chip {"good" if p["priority"].startswith("Finishes") else "bad"}">{escape(p["priority"])}</span>')
        chips.append(f'<span class="tb-chip good">Hits: {escape(p["dealt"])}{" · " + p["dealt_ko"] if p["dealt_ko"] else ""}</span>')
        chips.append(f'<span class="tb-chip bad">Takes: {escape(p["taken"])}{" · " + p["taken_ko"] if p["taken_ko"] else ""}</span>')
        sprite = escape(get_sprite(m) or "")
        out.append(f'<div class="tb-card {kind}"><img src="{sprite}" alt=""><div><div class="nm">{escape(m)}</div>'
                   f'<div class="tb-chips">{"".join(chips)}</div></div></div>')
    return '<div class="tb-cards">' + "".join(out) + "</div>"


def render(team_data):
    format_id = config.team_format(team_data)
    label = config.format_info(format_id)["label"]
    st.caption(f"Your team against the {N_THREATS} most used Pokémon in {label}, each on its most common set. "
               "Every verdict comes from the damage calculator.")
    with st.spinner("Running the matchups..."):
        rows = _board(json.dumps(team_data, sort_keys=True, default=str), format_id, _stats_month())
    if not rows:
        st.info("No threat data for this format yet. Run `python scripts/update_meta.py` to download usage stats, "
                "and make sure Node is installed for the damage calculator.")
        return

    members = [p["Pokemon"] for p in team_data.values()]
    answered = [r for r in rows if r["answers"]]
    total = sum(r["usage"] for r in rows) or 1
    holes = sorted(rows, key=lambda r: (len(r["answers"]), -r["usage"]))
    thin = [r for r in rows if len(r["answers"]) <= 1]
    weakest = holes[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Threats you answer", f"{len(answered)} of {len(rows)}",
              help=f"{sum(r['usage'] for r in answered) / total * 100:.0f}% of these threats' usage has at least one answer.")
    c2.metric("Thin spots", str(len(thin)), help="Threats with one answer or none: lose that Pokémon and nothing else beats it.")
    n = len(weakest["answers"])
    c3.metric("Weakest matchup", weakest["name"], help=f"{n} answer{'s' if n != 1 else ''} on your team.")

    st.markdown(STYLE + _grid(rows, members), unsafe_allow_html=True)
    st.caption("Hover a cell to see how it plays out. Red names have no answer on your team.")

    names = [r["name"] for r in rows]
    pick = st.pills("Look closer at a threat", names, default=weakest["name"], key="threat_pick") or weakest["name"]
    r = rows[names.index(pick)]
    left, right = st.columns(2)
    with left:
        st.markdown(STYLE + f'<div class="tb-head">Answers to {escape(pick)} ({len(r["answers"])})</div>'
                    + _cards(r["answers"], pick, r, "win")
                    + (f'<div class="tb-note">Smogon\'s checks data agrees on {escape(", ".join(r["cc"]))}.</div>' if r["cc"] else ""),
                    unsafe_allow_html=True)
    with right:
        st.markdown(STYLE + f'<div class="tb-head">Loses to {escape(pick)} ({len(r["losses"])})</div>'
                    + _cards(r["losses"], pick, r, "lose"), unsafe_allow_html=True)
    st.caption("One on one, on each threat's most common set. Switching, hazards, setup and Tera aren't counted. "
               "You can also ask the Coach Chat \"what checks Kyurem?\".")
