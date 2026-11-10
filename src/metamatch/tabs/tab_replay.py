"""Replay Auditor page: a Showdown replay reviewed from one player's side. A versus banner with both teams, the team
health race with every faint marked, the mistakes and notes from the log, a faint timeline, and both teams as they
ended, with everything the opponent revealed."""
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from metamatch import replay
from metamatch.replay.protocol import STATUS_DAMAGE
from metamatch.sprites import get_item_icon, get_sprite, get_tera_icon
from metamatch.ui import section_header

YOU, THEM = "#00d4ff", "#ff6b6b"
STATUS_NAMES = {"brn": "Burned", "par": "Paralyzed", "psn": "Poisoned", "tox": "Badly poisoned", "slp": "Asleep",
                "frz": "Frozen"}

STYLE = """
<style>
.ra-vs { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); gap: 18px; align-items: center;
  padding: 18px 22px; margin: 4px 0 6px; border-radius: 18px; border: 1px solid rgba(255,255,255,0.08);
  background: radial-gradient(120% 140% at 0% 0%, rgba(0,212,255,0.10), transparent 55%),
              radial-gradient(120% 140% at 100% 100%, rgba(255,107,107,0.10), transparent 55%), rgba(255,255,255,0.02);
  box-shadow: 0 10px 28px rgba(0,0,0,0.35); }
.ra-side { min-width: 0; }
.ra-side.them { text-align: right; }
.ra-lbl { font-size: 0.7rem; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; color: #8a93a6; }
.ra-nm { font-size: 1.2rem; font-weight: 800; color: #fff; margin-top: 2px; overflow-wrap: anywhere; }
.ra-mons { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 10px; }
.ra-side.them .ra-mons { justify-content: flex-end; }
.ra-mon { width: 46px; height: 46px; border-radius: 50%; display: grid; place-items: center; position: relative;
  background: rgba(255,255,255,0.05); box-shadow: inset 0 0 0 1px var(--ring, rgba(255,255,255,0.08)); }
.ra-mon img { width: 42px; height: 42px; object-fit: contain; }
.ra-mon.out { opacity: 0.45; } .ra-mon.out img { filter: grayscale(1); }
.ra-mon.unseen img { filter: brightness(0.35); }
.ra-mon .tip { position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%); z-index: 5;
  white-space: nowrap; padding: 4px 8px; border-radius: 8px; font-size: 0.75rem; color: #fff; background: #1b2230;
  border: 1px solid rgba(255,255,255,0.12); opacity: 0; visibility: hidden; transition: opacity 0.15s; }
.ra-mon:hover .tip, .ra-mon:focus .tip { opacity: 1; visibility: visible; }
.ra-left { font-size: 0.85rem; color: #c8ccd4; margin-top: 8px; }
.ra-left b { color: #fff; }
.ra-mid { text-align: center; }
.ra-res { font-size: 2rem; font-weight: 900; letter-spacing: 0.06em; line-height: 1; padding: 10px 18px; border-radius: 14px;
  color: var(--res); background: color-mix(in srgb, var(--res) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--res) 40%, transparent); }
.ra-meta { font-size: 0.8rem; color: #9aa3b2; margin-top: 8px; }
.ra-sum { display: flex; flex-wrap: wrap; gap: 8px; margin: 2px 0 12px; }
.ra-chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 11px; border-radius: 999px; font-size: 0.8rem;
  font-weight: 700; color: var(--c); background: color-mix(in srgb, var(--c) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--c) 35%, transparent); }
.ra-flags { display: grid; gap: 10px; }
.ra-flag { display: grid; grid-template-columns: 70px minmax(0, 1fr); gap: 14px; padding: 14px 16px; border-radius: 14px;
  background: rgba(255,255,255,0.03); border: 1px solid color-mix(in srgb, var(--c) 30%, transparent); }
.ra-turn { display: flex; flex-direction: column; align-items: center; justify-content: center; border-radius: 10px;
  background: color-mix(in srgb, var(--c) 10%, transparent); color: var(--c); font-size: 0.66rem; font-weight: 800;
  letter-spacing: 0.1em; text-transform: uppercase; padding: 6px 0; }
.ra-turn b { font-size: 1.35rem; color: #fff; letter-spacing: 0; }
.ra-ft { font-weight: 700; color: #fff; }
.ra-fd { color: #c8ccd4; font-size: 0.92rem; margin-top: 4px; line-height: 1.5; }
.ra-ok { padding: 14px 16px; border-radius: 14px; color: #d1fae5; background: rgba(52,211,153,0.07);
  border: 1px solid rgba(52,211,153,0.3); }
.ra-tl { display: flex; gap: 10px; overflow-x: auto; padding: 4px 2px 10px; }
.ra-ko { flex: 0 0 148px; padding: 10px 10px 12px; border-radius: 14px; text-align: center; background: rgba(255,255,255,0.03);
  border: 1px solid color-mix(in srgb, var(--c) 35%, transparent); }
.ra-ko img { width: 56px; height: 56px; object-fit: contain; }
.ra-ko .t { font-size: 0.7rem; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: var(--c); }
.ra-ko .n { font-weight: 700; color: #fff; font-size: 0.9rem; }
.ra-ko .c { font-size: 0.75rem; color: #aab3c5; margin-top: 4px; line-height: 1.35; }
.ra-teams { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; }
.ra-team { padding: 12px 16px 6px; border-radius: 16px; background: rgba(255,255,255,0.025);
  border: 1px solid rgba(255,255,255,0.07); min-width: 0; }
.ra-team h4 { margin: 0 0 4px; font-size: 0.95rem; color: #fff; }
.ra-team h4 span { color: #8a93a6; font-weight: 600; }
.ra-row { display: grid; grid-template-columns: 46px minmax(0, 1fr); gap: 12px; align-items: center; padding: 9px 0;
  border-top: 1px solid rgba(255,255,255,0.05); }
.ra-row img.sp { width: 46px; height: 46px; object-fit: contain; }
/* A fainted member greys its sprite and name only, so the sets it revealed stay readable */
.ra-row.out img.sp { filter: grayscale(1); opacity: 0.45; }
.ra-row.out .ra-rn { color: #8a93a6; }
.ra-rn { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 8px; font-weight: 700; color: #fff; }
.ra-rn small { font-weight: 600; color: #9aa3b2; }
.ra-pill { font-size: 0.7rem; font-weight: 700; padding: 1px 8px; border-radius: 999px; color: var(--c);
  background: color-mix(in srgb, var(--c) 12%, transparent); border: 1px solid color-mix(in srgb, var(--c) 30%, transparent); }
.ra-bar { height: 7px; border-radius: 4px; background: rgba(255,255,255,0.08); overflow: hidden; margin: 6px 0 2px; }
.ra-bar i { display: block; height: 100%; border-radius: 4px; }
.ra-set { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
.ra-tag { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 7px; font-size: 0.75rem;
  color: #d6dbe6; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08); }
.ra-tag img { width: 16px; height: 16px; object-fit: contain; }
.ra-tag.muted { color: #7f8aa0; border-style: dashed; }
.ra-legend { display: flex; flex-wrap: wrap; gap: 16px; font-size: 0.8rem; color: #aab3c5; margin: 0 0 4px; }
.ra-legend i { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 6px; vertical-align: -2px; }
@media (max-width: 900px) { .ra-teams { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 640px) {
  .ra-vs { grid-template-columns: minmax(0, 1fr); text-align: center; }
  .ra-side.them { text-align: center; } .ra-mons, .ra-side.them .ra-mons { justify-content: center; }
}
</style>
"""


def _faint_cause(battle, f):
    """Short description of what made a Pokémon faint."""
    by = battle.name(f["by"]) if f.get("by") else None
    source, cause = f.get("source"), f["cause"]
    if cause == "move":
        return f"{by}'s {source}" + (f" ({f['damage']}%)" if f.get("damage") else "")
    if cause == "hazard":
        return source
    if cause == "status":
        return STATUS_DAMAGE.get(source, source) + (f" from {by}" if by else "")
    if cause == "weather":
        return source
    if cause == "indirect":
        return f"{by}'s {source}"
    if cause == "self":
        return f"{source} (self inflicted)"
    if cause == "residual":
        return source + (f" from {by}" if by else "")
    if cause == "destiny_bond":
        return f"Destiny Bond from {by}"
    if cause == "perish":
        return "Perish Song"
    if cause == "self_ko":
        return f"{source} (self KO)"
    return "unknown"


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch(replay_id):
    """Replay JSON by id, cached so refreshing a /replay-auditor?id= link doesn't refetch."""
    return replay.fetch_replay(replay_id)


def _img(name, cls=""):
    return f'<img class="{cls}" src="{escape(get_sprite(name) or "")}" alt="{escape(name)}">'


def _icon(url):
    return f'<img src="{escape(url)}" alt="">' if url else ""


def _hp_color(hp):
    return "#34d399" if hp > 50 else "#facc15" if hp > 20 else "#f87171"


def _strip(battle, side):
    """The side's six as sprites: fainted ones greyed out, ones never sent out darkened."""
    cells = []
    for m in battle.mons[side].values():
        state = "out" if m.fainted else ""
        tip = f"{m.species}: fainted" if m.fainted else f"{m.species}: {m.hp}% left"
        cells.append(f'<span class="ra-mon {state}" tabindex="0">{_img(m.species)}<span class="tip">{escape(tip)}</span></span>')
    for species in battle.unrevealed(side):
        cells.append(f'<span class="ra-mon unseen" tabindex="0">{_img(species)}'
                     f'<span class="tip">{escape(species)}: never sent out</span></span>')
    return f'<div class="ra-mons">{"".join(cells)}</div>'


def _banner(battle, me, them):
    winner = battle.winner
    if winner in (None, "tie"):
        result, color = ("TIE" if winner == "tie" else "UNFINISHED"), "#facc15"
    else:
        result, color = ("WIN", "#34d399") if winner == me else ("LOSS", "#f87171")

    def side(s, label, cls):
        left = battle.remaining(s)
        return (f'<div class="ra-side {cls}"><div class="ra-lbl">{label}</div>'
                f'<div class="ra-nm">{escape(battle.players[s])}</div>{_strip(battle, s)}'
                f'<div class="ra-left"><b>{left}</b> of {battle.teamsize[s]} left</div></div>')

    return (f'<div class="ra-vs">{side(me, "You", "me")}'
            f'<div class="ra-mid"><div class="ra-res" style="--res:{color}">{result}</div>'
            f'<div class="ra-meta">{escape(battle.format_name)} · {len(battle.turns)} turns</div></div>'
            f'{side(them, "Opponent", "them")}</div>')


def _health_chart(battle, me, them):
    """Both teams' total HP turn by turn, with a dot wherever a Pokémon fainted."""
    you, opp = battle.players[me], battle.players[them]
    rows = [{"Turn": h["turn"], "Player": name, "HP": h[s]} for h in battle.health for s, name in ((me, you), (them, opp))]
    at = {(h["turn"], s): h[s] for h in battle.health for s in (me, them)}
    dots = [{"Turn": f["turn"], "Player": you if f["side"] == me else opp, "HP": at.get((f["turn"], f["side"]), 0),
             "Fainted": f["species"], "Cause": _faint_cause(battle, f)} for f in battle.faints]
    color = alt.Color("Player:N", scale=alt.Scale(domain=[you, opp], range=[YOU, THEM]), legend=None)
    x = alt.X("Turn:Q", axis=alt.Axis(tickMinStep=1, title="Turn", labelColor="#8a93a6", titleColor="#8a93a6"))
    y = alt.Y("HP:Q", scale=alt.Scale(domain=[0, 100]),
              axis=alt.Axis(title="Team HP %", labelColor="#8a93a6", titleColor="#8a93a6"))
    lines = alt.Chart(pd.DataFrame(rows)).mark_line(strokeWidth=2.5).encode(
        x=x, y=y, color=color, tooltip=["Player", "Turn", alt.Tooltip("HP:Q", title="Team HP %")])
    chart = lines
    if dots:
        chart = lines + alt.Chart(pd.DataFrame(dots)).mark_point(filled=True, size=110, opacity=1, stroke="#0f1219",
                                                                 strokeWidth=1.5).encode(
            x=x, y=y, color=color, tooltip=["Fainted", "Cause", "Turn", "Player"])
    return chart.properties(height=280).configure(background="transparent").configure_view(strokeWidth=0).configure_axis(
        gridColor="rgba(255,255,255,0.06)", domain=False, ticks=False)


def _flags(flags):
    mistakes = sum(f.kind == "mistake" for f in flags)
    notes = len(flags) - mistakes
    chips = (f'<span class="ra-chip" style="--c:#f87171">{mistakes} mistake{"s" if mistakes != 1 else ""}</span>'
             f'<span class="ra-chip" style="--c:#00d4ff">{notes} note{"s" if notes != 1 else ""}</span>')
    cards = "".join(
        f'<div class="ra-flag" style="--c:{"#f87171" if f.kind == "mistake" else "#00d4ff"}">'
        f'<div class="ra-turn">{"Lead" if f.turn == 0 else f"Turn<b>{f.turn}</b>"}</div>'
        f'<div><span class="ra-pill" style="--c:{"#f87171" if f.kind == "mistake" else "#00d4ff"}">{escape(f.kind)}</span>'
        f'<div class="ra-ft" style="margin-top:6px">{escape(f.title)}</div><div class="ra-fd">{escape(f.detail)}</div></div></div>'
        for f in flags)
    return f'<div class="ra-sum">{chips}</div><div class="ra-flags">{cards}</div>'


def _timeline(battle, me):
    cards = []
    for f in battle.faints:
        mine = f["side"] == me
        color = "#f87171" if mine else "#34d399"
        cards.append(f'<div class="ra-ko" style="--c:{color}"><div class="t">Turn {f["turn"]} · {"yours" if mine else "theirs"}</div>'
                     f'{_img(f["species"])}<div class="n">{escape(f["species"])}</div>'
                     f'<div class="c">{escape(_faint_cause(battle, f))}</div></div>')
    return f'<div class="ra-tl">{"".join(cards)}</div>'


def _row(m, scouted):
    """One member as it ended: HP and status, hazard chip taken, and (for the opponent) everything it revealed."""
    status = (f'<span class="ra-pill" style="--c:#facc15">{escape(STATUS_NAMES.get(m.status, m.status))}</span>'
              if m.status and not m.fainted else "")
    hazard = (f'<span class="ra-pill" style="--c:#fb923c">{m.hazard_damage}% from hazards</span>' if m.hazard_damage else "")
    hp = 0 if m.fainted else m.hp
    state = "fainted" if m.fainted else f"{hp}%"
    tags = ""
    if scouted:
        bits = []
        if m.item:
            lost = " (lost)" if m.item_lost else ""
            bits.append(f'<span class="ra-tag">{_icon(get_item_icon(m.item))}{escape(m.item)}{lost}</span>')
        if m.ability:
            bits.append(f'<span class="ra-tag">{escape(m.ability)}</span>')
        if m.tera:
            bits.append(f'<span class="ra-tag">{_icon(get_tera_icon(m.tera))}Tera {escape(m.tera)}</span>')
        bits += [f'<span class="ra-tag">{escape(move)}</span>' for move in m.moves]
        bits += ['<span class="ra-tag muted">not seen</span>'] * max(0, 4 - len(m.moves))
        tags = f'<div class="ra-set">{"".join(bits)}</div>'
    bar = "" if m.fainted else f'<div class="ra-bar"><i style="width:{hp}%;background:{_hp_color(hp)}"></i></div>'
    return (f'<div class="ra-row{" out" if m.fainted else ""}">{_img(m.species, "sp")}<div style="min-width:0">'
            f'<div class="ra-rn">{escape(m.species)}<small>{state}</small>{status}{hazard}</div>{bar}{tags}</div></div>')


def _teams(battle, me, them):
    def team(side, label, scouted):
        rows = "".join(_row(m, scouted) for m in battle.mons[side].values())
        rows += "".join(f'<div class="ra-row">{_img(s, "sp")}<div><div class="ra-rn">{escape(s)}<small>never sent out</small>'
                        f'</div></div></div>' for s in battle.unrevealed(side))
        return f'<div class="ra-team"><h4>{label} <span>{escape(battle.players[side])}</span></h4>{rows}</div>'
    return f'<div class="ra-teams">{team(me, "Your team", False)}{team(them, "Their team", True)}</div>'


def _keep_side():
    """The player picker never ends up with nobody selected: clicking the chosen name again keeps it."""
    if st.session_state.get("replay_perspective") is None:
        st.session_state.replay_perspective = st.session_state.get("replay_me", "p1")
    st.session_state.replay_me = st.session_state.replay_perspective


def render():
    # /replay-auditor?id=<replay id> opens straight onto that replay (refresh and bookmarks work)
    linked = st.query_params.get("id")
    if linked and "replay_url_input" not in st.session_state:
        st.session_state.replay_url_input = linked

    with st.container(horizontal=True, vertical_alignment="bottom"):
        replay_url = st.text_input("Replay link", placeholder="https://replay.pokemonshowdown.com/gen9ou-...",
                                   key="replay_url_input", label_visibility="collapsed")
        analyze_btn = st.button("Analyze replay", icon=":material/search:", type="primary")

    auto = bool(linked) and st.session_state.get("replay_id") != linked and not analyze_btn
    if (analyze_btn and replay_url) or auto:
        with st.spinner("Fetching and analyzing replay..."):
            try:
                replay_id, link_side = replay.parse_replay_link(linked if auto else replay_url)
                st.session_state.replay_analysis = replay.analyze(_fetch(replay_id))
                st.session_state.replay_id = replay_id
                st.session_state.replay_perspective = st.session_state.replay_me = link_side or "p1"
                if analyze_btn and st.query_params.get("id") != replay_id:
                    st.query_params["id"] = replay_id  # only on a click: URL writes add history entries
            except replay.ReplayError as e:
                st.error(str(e))
            except Exception as e:  # a log this parser has never seen; never show a traceback
                print(f"Replay analysis failed: {e}")
                st.error("Something in this replay couldn't be analysed. Try another replay.")

    analysis = st.session_state.get("replay_analysis")
    if not analysis:
        st.caption("Works with any public Showdown replay link or replay id, in any singles format.")
        return
    battle = analysis.battle

    # Pick yourself by username; changing it reuses the analysis instead of refetching
    sides = ["p1", "p2"]
    if st.session_state.get("replay_perspective") not in sides:
        st.session_state.replay_perspective = st.session_state.replay_me = "p1"
    me = st.segmented_control("You played as", sides, format_func=lambda s: battle.players[s],
                              key="replay_perspective", on_change=_keep_side) or "p1"
    them = "p2" if me == "p1" else "p1"

    st.html(STYLE + _banner(battle, me, them))

    if len(battle.health) > 2:
        section_header("How it went", "Team Health",
                       "Each team's total HP at the end of every turn; Pokémon not sent out yet count as full. "
                       "A dot marks a faint: hover it for who and why.")
        st.html(f'<div class="ra-legend"><span><i style="background:{YOU}"></i>{escape(battle.players[me])}</span>'
                f'<span><i style="background:{THEM}"></i>{escape(battle.players[them])}</span></div>')
        st.altair_chart(_health_chart(battle, me, them), width="stretch")

    section_header("Review", "Mistakes and Notes", "Mistakes are clear from the log. Notes are worth knowing but not "
                   "necessarily wrong.")
    flags = analysis.flags[me]
    st.html(STYLE + (_flags(flags) if flags else '<div class="ra-ok">No clear mistakes found in the log.</div>'))

    if battle.faints:
        section_header("Timeline", "Every Faint", "In turn order, with what caused it.")
        st.html(STYLE + _timeline(battle, me))

    section_header("End of game", "Both Teams", "How each Pokémon ended the game, and everything the opponent revealed.")
    st.html(STYLE + _teams(battle, me, them))
