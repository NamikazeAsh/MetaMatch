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
        st.markdown(STYLE + (_mega(g.mega) if config.format_game(format_id) == "champions" else _tera(g.tera, type_map)),
                    unsafe_allow_html=True)
    st.markdown(STYLE + _combos(g.combos), unsafe_allow_html=True)
    st.caption(f"Matchups are one on one against each threat's most common set (top {g.n_threats} by usage); "
               "switching, hazards and setup turns aren't simulated.")
