"""Team Completer tab: the next team member chosen by the threats it answers and how well it pairs, not popularity."""
import json
from html import escape

import streamlit as st

from metamatch import config
from metamatch.engine import completer
from metamatch.sprites import get_sprite

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
.tc-pop { position: relative; cursor: help; }
.tc-tip { visibility: hidden; opacity: 0; position: absolute; left: 0; bottom: calc(100% + 8px); width: 290px; z-index: 30;
  padding: 12px 14px; border-radius: 12px; background: #0f1729; border: 1px solid rgba(255,255,255,.12);
  box-shadow: 0 14px 30px rgba(0,0,0,.45); color: #dbe4f3; font: 400 .82rem/1.45 system-ui, sans-serif;
  letter-spacing: 0; transition: opacity .12s; pointer-events: none; }
.tc-pop:hover .tc-tip { visibility: visible; opacity: 1; }
.tc-tt { display: block; font-weight: 700; font-size: .88rem; margin-bottom: 8px; color: #e6edf7; }
.tc-trow { display: grid; grid-template-columns: 1fr auto 44px; gap: 10px; align-items: baseline; padding: 3px 0; }
.tc-trow b { font-variant-numeric: tabular-nums; color: #e6edf7; }
.tc-trow em { font-style: normal; font-weight: 700; font-size: .74rem; text-align: right; color: #9aa7bf; }
.tc-trow em.up { color: #34d399; } .tc-trow em.down { color: #f87171; }
.tc-trow.all { border-top: 1px solid rgba(255,255,255,.1); margin-top: 4px; padding-top: 6px; color: #9aa7bf; }
.tc-tfoot { display: block; margin-top: 8px; font-size: .72rem; color: #8fa1bf; }
</style>
"""


@st.cache_data(show_spinner=False, max_entries=24)
def _complete(team_json, format_id, stats_month):
    team = json.loads(team_json)
    picks, redundant, board = completer.complete(team, format_id)
    # Weak spots, worst first: no answer before one answer, then by usage (the board is already in usage order)
    holes = sorted(((r.name, len(r.answers)) for r in board if len(r.answers) <= 1), key=lambda h: h[1])
    as_dict = lambda c: {"name": c.name, "usage": c.usage, "gain": c.gain, "covers": c.covers, "lift": c.lift,
                         "best_pair": c.best_pair, "pairs": c.pairs, "roles": c.roles}
    return [as_dict(c) for c in picks], [as_dict(c) for c in redundant], holes


def _stats_month():
    try:
        return json.loads((config.STATS_DIR / "manifest.json").read_text(encoding="utf-8")).get("month", "")
    except (OSError, ValueError):
        return ""


ROLE_WORDS = {"Hazard Setter": "Adds a hazard setter", "Hazard Remover": "Adds hazard removal", "Pivot": "Adds a pivot"}


def _join(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _coverage_line(covers, holes):
    """Why this pick, in one plain sentence about the team's weak spots."""
    if not holes:
        return ""
    if not covers:
        return "Doesn't beat any of your weak spots"
    worst = holes[0][0]
    if worst in covers:
        rest = [t for t in covers if t != worst]
        return f"Beats {worst}, your weakest matchup" + (f", and {_join(rest)}" if rest else "")
    return f"Beats {_join(covers)}, {'one' if len(covers) == 1 else len(covers)} of your weak spots"


def _coverage_count(covers, holes):
    if not holes:
        return ""
    if len(holes) == 1:
        return "Covers your only weak spot" if covers else "Doesn't cover your weak spot"
    return f"Covers {len(covers)} of your {len(holes)} weak spots"


def _pair_tip(c):
    """Hover card with the ladder numbers behind a pairing chip."""
    rows = "".join(
        f'<div class="tc-trow"><span>On teams with {escape(m)}</span><b>{share * 100:.1f}%</b>'
        f'<em class="{"up" if lift_ >= 1.15 else "down" if lift_ <= 0.85 else ""}">{lift_:.1f}x</em></div>'
        for m, share, lift_ in c["pairs"][:3])
    return (f'<span class="tc-tip"><span class="tc-tt">How often {escape(c["name"])} shows up</span>{rows}'
            f'<div class="tc-trow all"><span>On all teams</span><b>{c["usage"]:.1f}%</b><em></em></div>'
            '<span class="tc-tfoot">From this month&#39;s ladder teams. 2.0x means twice as often as on an average team.</span></span>')


def _pair_chip(c):
    """How often players put it with your Pokemon, in words; the numbers are in a hover card."""
    if not c["lift"] or not c["pairs"]:
        return ""
    member, best = c["best_pair"]
    if best >= 1.5:
        cls, text = "pair", f"Players often pair it with {escape(member)}"
    elif best >= 1.15:
        cls, text = "pair", f"Sometimes paired with {escape(member)}"
    elif c["lift"] <= 0.8:
        cls, text = "flat", "Rarely seen on teams like yours"
    else:
        return ""
    return f'<span class="tc-chip {cls} tc-pop">{text}{_pair_tip(c)}</span>'


def _card(c, holes, dim=False, current=None):
    sprite = get_sprite(c["name"]) or ""
    mine = '<span class="tc-chip role">Your current pick</span>' if c["name"] == current else ""
    line = _coverage_line(c["covers"], holes)
    count = _coverage_count(c["covers"], holes)
    share = (len(c["covers"]) / len(holes) * 100) if holes else 0
    roles = "".join(f'<span class="tc-chip role">{escape(ROLE_WORDS.get(r, r))}</span>' for r in c["roles"])
    bar = (f'<div class="tc-bar"><i style="width:{share:.0f}%"></i></div><div class="tc-sub">{escape(count)}</div>'
           if holes else "")
    return (f'<div class="tc-card{" dim" if dim else ""}"><div class="tc-head">'
            f'<img src="{escape(sprite)}" alt=""><div><div class="tc-name">{escape(c["name"])}</div>'
            f'<div class="tc-sub">On {c["usage"]:g}% of teams</div></div></div>'
            + (f'<div class="tc-line">{escape(line)}</div>' if line else "")
            + f'<div>{mine}{_pair_chip(c)}{roles}</div>{bar}</div>')


def render(team_data: dict, pokemon_names: list):
    st.subheader("Team Completer")
    format_id = config.team_format(team_data)
    st.caption("Picks for your next teammate: Pokémon that beat the top threats your team struggles with, "
               "and that players actually pair with your team, not just the most popular ones.")

    members = [p["Pokemon"] for p in team_data.values()]
    team, weakest = dict(team_data), None
    if len(members) >= 6:
        weakest = st.selectbox("Your team is full. Which member would you replace?", members, key="tc_replace",
                               help="The suggestions treat this slot as open.")
        team = {k: v for k, v in team_data.items() if v["Pokemon"] != weakest}
    with st.spinner("Scoring candidates against the top threats..."):
        picks, redundant, holes = _complete(json.dumps(team, sort_keys=True, default=str), format_id, _stats_month())
    if holes:
        st.markdown("**Your weak spots:** " + ", ".join(
            f"{escape(n)} ({'nothing on your team beats it' if k == 0 else 'only one answer'})" for n, k in holes))
    else:
        st.markdown("**Your weak spots:** none. Every top threat already has two or more answers, "
                    "so these picks are about how well they fit your team.")
    if not picks:
        st.info("No candidates found. Make sure usage stats are downloaded and Node is installed for the damage calculator.")
        return

    cols = st.columns(3)
    for i, c in enumerate(picks):
        with cols[i % 3]:
            st.markdown(STYLE + _card(c, holes, current=weakest), unsafe_allow_html=True)
    if redundant:
        st.markdown("**Popular picks that don't fix anything here**")
        cols = st.columns(3)
        for i, c in enumerate(redundant):
            with cols[i % 3]:
                st.markdown(STYLE + _card(c, holes, dim=True, current=weakest), unsafe_allow_html=True)
    st.caption("\"Beats\" means it wins one on one on both Pokémon's most common sets, worked out by the damage calculator. "
               "Pairing comes from this month's ladder teams; hover a chip for the numbers.")
