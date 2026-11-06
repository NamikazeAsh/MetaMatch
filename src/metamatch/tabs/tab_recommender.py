"""Team Completer tab: the next team member chosen by the threats it answers and how well it pairs, not popularity."""
import json
from html import escape

import streamlit as st

from metamatch import config
from metamatch.engine import completer
from metamatch.utils import get_pokemon_sprite

STYLE = """
<style>
.tc-card { background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.08); border-radius: 12px; padding: 14px; min-height: 220px; }
.tc-card.dim { opacity: .55; }
.tc-head { display: flex; gap: 12px; align-items: center; }
.tc-head img { width: 64px; }
.tc-name { font-weight: 700; font-size: 1.1rem; }
.tc-sub { font-size: .8rem; color: #8fa1bf; }
.tc-line { font-size: .88rem; margin-top: 8px; }
.tc-chip { display: inline-block; font: 600 .72rem monospace; padding: 2px 8px; border-radius: 999px; margin: 6px 4px 0 0; }
.tc-chip.pair { background: rgba(52,211,153,.14); color: #34d399; }
.tc-chip.flat { background: rgba(148,163,184,.14); color: #9aa7bf; }
.tc-chip.role { background: rgba(250,204,21,.12); color: #facc15; }
.tc-bar { height: 7px; border-radius: 4px; background: rgba(255,255,255,.08); margin-top: 10px; overflow: hidden; }
.tc-bar i { display: block; height: 100%; background: #22d3ee; border-radius: 4px; }
</style>
"""


@st.cache_data(show_spinner=False, max_entries=24)
def _complete(team_json, format_id, stats_month):
    team = json.loads(team_json)
    picks, redundant, board = completer.complete(team, format_id)
    holes = [(r.name, len(r.answers)) for r in board if len(r.answers) <= 1]
    as_dict = lambda c: {"name": c.name, "usage": c.usage, "gain": c.gain, "covers": c.covers, "lift": c.lift,
                         "best_pair": c.best_pair, "roles": c.roles}
    return [as_dict(c) for c in picks], [as_dict(c) for c in redundant], holes


def _stats_month():
    try:
        return json.loads((config.STATS_DIR / "manifest.json").read_text(encoding="utf-8")).get("month", "")
    except (OSError, ValueError):
        return ""


def _card(c, dim=False):
    sprite = get_pokemon_sprite(c["name"]) or ""
    covers = (f"Answers {escape(', '.join(c['covers']))}" if c["covers"] else "Adds no new answers to your weak spots")
    if c["lift"]:
        pair_cls = "pair" if c["lift"] >= 1.15 else "flat"
        member, best = c["best_pair"]
        pair = (f'<span class="tc-chip {pair_cls}">pairs {best:.2f}x with {escape(member)}</span>'
                if pair_cls == "pair" else f'<span class="tc-chip flat">pairs {c["lift"]:.2f}x with your team</span>')
    else:
        pair = ""
    roles = "".join(f'<span class="tc-chip role">Fills {escape(r)}</span>' for r in c["roles"])
    return (f'<div class="tc-card{" dim" if dim else ""}"><div class="tc-head">'
            f'<img src="{escape(sprite)}" alt=""><div><div class="tc-name">{escape(c["name"])}</div>'
            f'<div class="tc-sub">{c["usage"]:g}% of teams</div></div></div>'
            f'<div class="tc-line">{covers}</div>{pair}{roles}'
            f'<div class="tc-bar" title="Share of your weak spots it fills"><i style="width:{c["gain"] * 100:.0f}%"></i></div>'
            f'<div class="tc-sub">Fills {c["gain"] * 100:.0f}% of your weak spots</div></div>')


def render(team_data: dict, pokemon_names: list):
    st.subheader("Team Completer")
    format_id = config.team_format(team_data)
    st.caption("The next teammate, picked by which of the format's top threats it answers where your team is thin, "
               "and by how often players really pair it with your Pokémon (not just how popular it is).")

    members = [p["Pokemon"] for p in team_data.values()]
    team = dict(team_data)
    if len(members) >= 6:
        weakest = st.selectbox("Your team is full. Which member would you replace?", members, key="tc_replace",
                               help="The suggestions treat this slot as open.")
        team = {k: v for k, v in team_data.items() if v["Pokemon"] != weakest}
    with st.spinner("Scoring candidates against the top threats..."):
        picks, redundant, holes = _complete(json.dumps(team, sort_keys=True, default=str), format_id, _stats_month())
    if holes:
        st.markdown("**Weak spots:** " + ", ".join(
            f"{escape(n)} ({'no answer' if k == 0 else 'one answer'})" for n, k in holes))
    else:
        st.markdown("**Weak spots:** none. Every top threat has two or more answers, so these picks lean on pairing.")
    if not picks:
        st.info("No candidates found. Make sure usage stats are downloaded and Node is installed for the damage calculator.")
        return

    html = [STYLE]
    cols = st.columns(3)
    for i, c in enumerate(picks):
        with cols[i % 3]:
            st.markdown(STYLE + _card(c), unsafe_allow_html=True)
    if redundant:
        st.markdown("**Popular, but adds nothing new here**")
        cols = st.columns(3)
        for i, c in enumerate(redundant):
            with cols[i % 3]:
                st.markdown(STYLE + _card(c, dim=True), unsafe_allow_html=True)
    st.caption("Answers are one on one verdicts from the damage calculator on each Pokémon's most common set. "
               "Pairing is lift from this month's teammate data: 2x means players put them together twice as often as chance.")
