"""Threat Board tab: the format's most used Pokemon against each team member, one on one, from the damage calc."""
import json
from html import escape

import streamlit as st

from metamatch import config
from metamatch.engine import threat_board as tb

N_THREATS = 12
STYLE = """
<style>
.tb-wrap { overflow-x: auto; }
.tb { border-collapse: separate !important; border-spacing: 4px; width: 100%; min-width: 640px; border: none !important; }
.tb th, .tb td { border: none !important; }
.tb th { font-size: .78rem; font-weight: 600; color: #9fb0cc; text-align: center; padding: 2px 4px; }
.tb td.name { font-weight: 600; white-space: nowrap; padding-right: 8px; }
.tb td.name small { display: block; font-weight: 400; color: #8fa1bf; font-family: monospace; }
.tb td.c { text-align: center; border-radius: 7px; font: 600 .72rem monospace; letter-spacing: .05em; padding: 10px 4px; cursor: help; }
.tb td.win { background: rgba(52,211,153,.16); color: #34d399; }
.tb td.lose { background: rgba(248,113,113,.16); color: #f87171; }
.tb td.even { background: rgba(123,138,166,.16); color: #9aa7bf; }
.tb tr.hole td.name { color: #f87171; }
.tb-line { font-size: .92rem; margin: 2px 0; }
.tb-line b { color: #e6edf7; }
</style>
"""


@st.cache_data(show_spinner=False, max_entries=16)
def _board(team_json, format_id, stats_month):
    """Board rows as plain dicts (cached per team, format and stats month)."""
    team = json.loads(team_json)
    rows = tb.threat_board(team, n=N_THREATS, format_id=format_id)
    return [{"name": r.name, "usage": r.usage, "answers": r.answers, "losses": r.losses, "cc": r.checks_data,
             "cells": {m: {"verdict": c.verdict, "reason": c.reason} for m, c in r.cells.items()}} for r in rows]


def _stats_month():
    try:
        return json.loads((config.STATS_DIR / "manifest.json").read_text(encoding="utf-8")).get("month", "")
    except (OSError, ValueError):
        return ""


def _grid(rows, members):
    head = "<tr><th></th>" + "".join(f"<th>{escape(m)}</th>" for m in members) + "</tr>"
    body = []
    for r in rows:
        cells = []
        for m in members:
            c = r["cells"].get(m)
            if not c:
                cells.append('<td class="c even" title="No calc data">?</td>')
                continue
            tip = escape(f"{m} vs {r['name']}: {c['reason'] or 'no clear knockout either way'}")
            cells.append(f'<td class="c {c["verdict"]}" title="{tip}">{c["verdict"].upper()}</td>')
        hole = " hole" if not r["answers"] else ""
        body.append(f'<tr class="{hole.strip()}"><td class="name">{escape(r["name"])}<small>{r["usage"]:g}% of teams</small></td>'
                    + "".join(cells) + "</tr>")
    return f'<div class="tb-wrap"><table class="tb">{head}{"".join(body)}</table></div>'


def render(team_data):
    format_id = config.team_format(team_data)
    label = config.format_info(format_id)["label"]
    st.caption(f"Your team against the {N_THREATS} most used Pokémon in {label}, each on its most common set. "
               "Every verdict is worked out by the damage calculator: speed, the best hit each way, and how many hits each side needs.")
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
    st.caption("Hover a cell for the numbers. Red names have no answer on your team.")

    names = [r["name"] for r in rows]
    pick = st.selectbox("Look at a threat", names, index=names.index(weakest["name"]), key="threat_pick")
    r = rows[names.index(pick)]
    left, right = st.columns(2)
    with left:
        st.markdown(f"**Answers to {escape(pick)}**")
        if r["answers"]:
            for m in r["answers"]:
                st.markdown(f'<div class="tb-line"><b>{escape(m)}</b>: {escape(r["cells"][m]["reason"])}</div>', unsafe_allow_html=True)
        else:
            st.markdown("Nobody on your team beats it one on one.")
        if r["cc"]:
            st.caption("Smogon's checks data agrees on: " + ", ".join(r["cc"]))
    with right:
        st.markdown(f"**Loses to {escape(pick)}**")
        if r["losses"]:
            for m in r["losses"]:
                st.markdown(f'<div class="tb-line"><b>{escape(m)}</b>: {escape(r["cells"][m]["reason"])}</div>', unsafe_allow_html=True)
        else:
            st.markdown("No one on your team loses to it one on one.")
    st.caption("One on one on the most common set: switching, hazards, setup and Tera are not counted. "
               "Ask the Coach Chat \"what checks Kyurem?\" for the same answer in words.")
