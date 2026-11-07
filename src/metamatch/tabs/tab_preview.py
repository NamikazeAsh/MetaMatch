"""Matchup Preview: your team against one specific opposing team, and which three to bring in Champions."""
import math
from html import escape

import streamlit as st

from metamatch import config
from metamatch.engine import preview as pv
from metamatch.tabs.tab_threats import STYLE, _cards, _grid
from metamatch.team import readTeam

EXAMPLE = "Samurott-Hisui, Slowking-Galar, Dragapult, Golisopod-Mega, Aegislash, Rillaboom"
BRING_STYLE = """
<style>
.pv-bring { background: rgba(34,211,238,.06); border: 1px solid rgba(34,211,238,.35); border-radius: 14px; padding: 16px 18px; }
.pv-bring .big { font-weight: 800; font-size: 1.3rem; color: #e6edf7; }
.pv-bring .sub { color: #9fb0cc; margin-top: 4px; }
.pv-alt { color: #9fb0cc; font-size: .88rem; margin-top: 8px; }
</style>
"""


def _as_rows(rows):
    return [{"name": r.name, "usage": r.usage, "answers": r.answers, "losses": r.losses, "cc": [],
             "cells": {m: {"verdict": c.verdict, "parts": c.parts} for m, c in r.cells.items()}} for r in rows]


def render(team=None):
    format_id = st.session_state.get("format_id") or config.DEFAULT_FORMAT
    if team:
        format_id = config.team_format(team)
        st.caption(f"Using your open team ({config.format_info(format_id)['label']}). Paste the team you're facing.")
    else:
        mine_text = st.text_area("Your team", height=140, key="pv_mine",
                                 placeholder="Paste your Showdown export, or open a team first and it's used here.")
        team = readTeam(mine_text, format_id)[0] if mine_text.strip() else None
    theirs = st.text_area("Their team", height=110, key=f"pv_theirs_{format_id}",
                          placeholder=f"Paste their Showdown export, or just the six names from team preview, like: {EXAMPLE}")
    if not team or not theirs.strip():
        st.caption("Names alone work: each Pokémon gets its most common ladder set. A full paste is used exactly as written.")
        return

    sets, unknown = pv.opponent_sets(theirs, format_id)
    if unknown:
        st.warning("No usage data for " + ", ".join(unknown) + " in this format, so they're left out.")
    if not sets:
        st.info("Couldn't find any Pokémon in that paste.")
        return
    with st.spinner("Running every matchup..."):
        rows = pv.preview(team, sets, format_id)
    if not rows:
        st.info("The damage calculator isn't available. Make sure Node is installed.")
        return
    members = [p["Pokemon"] for p in team.values()]
    stated = {s["name"] for s in sets if s.get("stated")}
    data = _as_rows(rows)
    sub = lambda r: "set from your paste" if r["name"] in stated else "on its most common set"
    st.markdown(STYLE + _grid(data, members, sub=sub), unsafe_allow_html=True)

    open_threats = [r["name"] for r in data if not r["answers"]]
    if open_threats:
        st.markdown(f"**Nothing on your team beats:** {escape(', '.join(open_threats))}")

    if pv.is_bring_three(format_id):
        picks = pv.bring_three(rows, members)
        if picks:
            trio, worst, avg = picks[0]
            alts = ", ".join(" / ".join(t) for t, _, _ in picks[1:3])
            st.markdown(BRING_STYLE + f'<div class="pv-bring"><div class="sub">Bring these three</div>'
                        f'<div class="big">{escape(" · ".join(trio))}</div>'
                        f'<div class="sub">Whatever three they bring, at least {worst} of them have an answer here '
                        f'(checked against all {math.comb(len(rows), 3)} trios they could pick).</div>'
                        + (f'<div class="pv-alt">Close alternatives: {escape(alts)}</div>' if alts else "") + "</div>",
                        unsafe_allow_html=True)

    names = [r["name"] for r in data]
    pick = st.pills("Look closer", names, default=names[0], key=f"pv_pick_{format_id}") or names[0]
    r = data[names.index(pick)]
    left, right = st.columns(2)
    with left:
        st.markdown(STYLE + f'<div class="tb-head">Answers to {escape(pick)} ({len(r["answers"])})</div>'
                    + _cards(r["answers"], pick, r, "win"), unsafe_allow_html=True)
    with right:
        st.markdown(STYLE + f'<div class="tb-head">Loses to {escape(pick)} ({len(r["losses"])})</div>'
                    + _cards(r["losses"], pick, r, "lose"), unsafe_allow_html=True)
    st.caption("One on one: switching, hazards, setup and Tera aren't counted. No win chances and no guesses about their picks.")
