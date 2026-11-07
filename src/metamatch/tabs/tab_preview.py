"""Matchup Preview: your team against one specific opposing team, and which three to bring in Champions."""
import math
from html import escape

import streamlit as st

from metamatch import config
from metamatch.engine import preview as pv
from metamatch.tabs.tab_threats import STYLE, _cards, _grid
from metamatch.team import readTeam
from metamatch.sprites import get_sprite

EXAMPLE = "Samurott-Hisui, Slowking-Galar, Dragapult, Golisopod-Mega, Aegislash, Rillaboom"
BRING_STYLE = """
<style>
.pv-vs { display: grid; grid-template-columns: 1fr auto 1fr; gap: 18px; align-items: center; padding: 16px 20px; margin: 6px 0 14px;
  border-radius: 16px; background: linear-gradient(90deg, rgba(34,211,238,.10), rgba(255,255,255,.02) 45%, rgba(255,255,255,.02) 55%, rgba(248,113,113,.10));
  border: 1px solid rgba(255,255,255,.08); }
.pv-side .lbl { font: 700 .72rem system-ui, sans-serif; letter-spacing: .14em; text-transform: uppercase; color: #22d3ee; margin-bottom: 6px; }
.pv-side.them .lbl { color: #f87171; text-align: right; }
.pv-mons { display: flex; flex-wrap: wrap; gap: 4px; }
.pv-side.them .pv-mons { justify-content: flex-end; }
.pv-mons img { width: 58px; height: 58px; object-fit: contain; filter: drop-shadow(0 2px 4px rgba(0,0,0,.5)); }
.pv-vsword { font: 900 1.6rem system-ui, sans-serif; letter-spacing: .06em; color: #e6edf7; opacity: .85; }
.pv-trio { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 10px; }
.pv-trio div { display: flex; flex-direction: column; align-items: center; gap: 2px; font-weight: 700; font-size: .9rem; }
.pv-trio img { width: 72px; height: 72px; object-fit: contain; }
.pv-bring { background: rgba(34,211,238,.06); border: 1px solid rgba(34,211,238,.35); border-radius: 14px; padding: 16px 18px; }
.pv-bring .big { font-weight: 800; font-size: 1.3rem; color: #e6edf7; }
.pv-bring .sub { color: #9fb0cc; margin-top: 4px; }
.pv-alt { color: #9fb0cc; font-size: .88rem; margin-top: 8px; }
</style>
"""


def _as_rows(rows):
    return [{"name": r.name, "usage": r.usage, "answers": r.answers, "losses": r.losses, "cc": [],
             "cells": {m: {"verdict": c.verdict, "parts": c.parts} for m, c in r.cells.items()}} for r in rows]


CHAMPIONS_SAMPLE = """Garchomp @ Garchompite Z
Ability: Rough Skin
EVs: 2 HP / 32 Atk / 32 Spe
Jolly Nature
- Earthquake
- Dragon Claw
- Stone Edge
- Swords Dance

Kingambit @ Black Glasses
Ability: Supreme Overlord
EVs: 32 HP / 32 Atk / 2 Def
Adamant Nature
- Sucker Punch
- Kowtow Cleave
- Iron Head
- Swords Dance

Corviknight @ Leftovers
Ability: Pressure
EVs: 32 HP / 32 Def / 2 SpD
Impish Nature
- Brave Bird
- Body Press
- Roost
- U-turn

Hatterene @ Life Orb
Ability: Magic Bounce
EVs: 32 HP / 32 SpA / 2 SpD
Modest Nature
- Dazzling Gleam
- Psychic
- Mystical Fire
- Trick Room

Rotom-Wash @ Sitrus Berry
Ability: Levitate
EVs: 32 HP / 32 Def / 2 SpA
Bold Nature
- Hydro Pump
- Volt Switch
- Will-O-Wisp
- Pain Split

Glimmora @ Focus Sash
Ability: Toxic Debris
EVs: 2 HP / 32 SpA / 32 Spe
Timid Nature
- Power Gem
- Sludge Wave
- Stealth Rock
- Earth Power"""


def _sample_opponents(format_id, exclude):
    """The format's six most used Pokemon not on your team, as a team preview line."""
    from metamatch.engine.threat_board import top_threats
    return ", ".join(name for name, _ in top_threats(format_id, exclude=exclude, n=6))


def _load_sample(format_id, sample_team, has_team, mine_names):
    """Fills both boxes (or just theirs when a team is already open). Runs as a button callback, before the widgets."""
    champions = config.format_game(format_id) == "champions"
    if not has_team:
        mine = CHAMPIONS_SAMPLE if champions else (sample_team or "")
        st.session_state["pv_mine"] = mine
        mine_names = [block.split("@")[0].strip() for block in mine.split("\n\n") if block.strip()]
    st.session_state[f"pv_theirs_{format_id}"] = _sample_opponents(format_id, mine_names)


def _vs_banner(mine, theirs):
    img = lambda names: "".join(f'<img src="{escape(get_sprite(n) or "")}" alt="{escape(n)}" title="{escape(n)}">' for n in names)
    return (f'<div class="pv-vs"><div class="pv-side"><div class="lbl">Your team</div><div class="pv-mons">{img(mine)}</div></div>'
            f'<div class="pv-vsword">VS</div>'
            f'<div class="pv-side them"><div class="lbl">Their team</div><div class="pv-mons">{img(theirs)}</div></div></div>')


def render(team=None, sample_team=None):
    format_id = st.session_state.get("format_id") or config.DEFAULT_FORMAT
    has_team = bool(team)
    if team:
        format_id = config.team_format(team)
    mine_names = [p["Pokemon"] for p in (team or {}).values()]
    top, button = st.columns([4, 1], vertical_alignment="bottom")
    with top:
        st.caption(f"Using your open team ({config.format_info(format_id)['label']}). Paste the team you're facing."
                   if has_team else "Paste both teams, or try it with a sample first.")
    with button:
        st.button("Try a sample", key="pv_sample", width="stretch",
                  help="Fills in sample teams so you can see how it works." if not has_team
                  else "Fills their side with this format's six most used Pokémon.",
                  on_click=_load_sample, args=(format_id, sample_team, has_team, mine_names))
    left_in, right_in = st.columns(2) if not has_team else (None, st.container())
    if not has_team:
        with left_in:
            mine_text = st.text_area("Your team", height=150, key="pv_mine",
                                     placeholder="Paste your Showdown export, or open a team first and it's used here.")
        team = readTeam(mine_text, format_id)[0] if mine_text.strip() else None
    with right_in:
        theirs = st.text_area("Their team", height=150 if not has_team else 90, key=f"pv_theirs_{format_id}",
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
    st.markdown(BRING_STYLE + _vs_banner(members, [r["name"] for r in data]), unsafe_allow_html=True)

    answered = [r for r in data if r["answers"]]
    wins = {m: sum(1 for r in data if r["cells"].get(m, {}).get("verdict") == "win") for m in members}
    best = max(members, key=lambda m: wins[m])
    worst_row = min(data, key=lambda r: len(r["answers"]))
    c1, c2, c3 = st.columns(3)
    c1.metric("Their Pokémon you can beat", f"{len(answered)} of {len(data)}",
              help="Each has at least one member of your team that wins one on one.")
    c2.metric("Your best answer", best, help=f"Beats {wins[best]} of their {len(data)} one on one.")
    n_ans = len(worst_row["answers"])
    c3.metric("Hardest to handle", worst_row["name"],
              help="Nothing on your team beats it one on one." if not n_ans else f"Only {n_ans} answer{'s' if n_ans != 1 else ''} on your team.")
    st.markdown(STYLE + _grid(data, members, sub=sub), unsafe_allow_html=True)
    st.caption("Hover a cell to see how it plays out.")

    if pv.is_bring_three(format_id):
        picks = pv.bring_three(rows, members)
        if picks:
            trio, worst, avg = picks[0]
            alts = ", ".join(" / ".join(t) for t, _, _ in picks[1:3])
            sprites = "".join(f'<div><img src="{escape(get_sprite(m) or "")}" alt="">{escape(m)}</div>' for m in trio)
            st.markdown(BRING_STYLE + f'<div class="pv-bring"><div class="sub">Bring these three</div>'
                        f'<div class="pv-trio">{sprites}</div>'
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
