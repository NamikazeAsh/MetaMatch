"""
Move Search: pick moves, see every Pokemon in the format that runs or can learn all of them (engine/move_search.py),
from Smogon sets down to the ones nobody runs yet, and add any of them to the Quick Match team.
"""
from html import escape

import streamlit as st

from metamatch import config
from metamatch.engine import move_search
from metamatch.sprites import get_sprite, get_type_icon

SHOW = 9   # cards per section before the rest fold away

STYLE = """
<style>
.ms-strip { display:flex; flex-wrap:wrap; gap:8px; margin:4px 0 2px; }
.ms-chip { position:relative; display:inline-flex; align-items:center; gap:8px; padding:5px 12px 5px 6px; border-radius:999px;
  background:linear-gradient(90deg, color-mix(in srgb, var(--c) 30%, transparent), rgba(255,255,255,.03));
  border:1px solid color-mix(in srgb, var(--c) 55%, transparent); font-size:.82rem; color:#fff; font-weight:700; cursor:help; }
.ms-chip i { width:22px; height:22px; border-radius:50%; flex-shrink:0;
  background:var(--c) center / 13px no-repeat; box-shadow:0 0 10px -3px var(--c), inset 0 -2px 4px rgba(0,0,0,.25); }
.ms-chip small { font-weight:600; color:#c6d1e3; font-size:.72rem; }
.ms-chip .ms-tip { position:absolute; left:0; top:calc(100% + 6px); width:240px; z-index:40; padding:8px 10px; border-radius:9px;
  background:#0b0f17; border:1px solid rgba(255,255,255,.14); color:#d6dbe6; font-size:.74rem; font-weight:500; line-height:1.4;
  opacity:0; visibility:hidden; transition:opacity .12s ease, visibility .12s; pointer-events:none; box-shadow:0 8px 20px rgba(0,0,0,.5); }
.ms-chip:hover .ms-tip { opacity:1; visibility:visible; }
.ms-sum { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:14px 0 2px; }
.ms-sum b { font-size:1.15rem; color:#fff; font-weight:800; margin-right:4px; }
.ms-pill { font-size:0.74rem; font-weight:700; padding:3px 10px; border-radius:999px; border:1px solid; }
.ms-pill.smogon { color:#5fd38d; background:rgba(95,211,141,.10); border-color:rgba(95,211,141,.3); }
.ms-pill.ladder { color:#7fe6ff; background:rgba(0,212,255,.10); border-color:rgba(0,212,255,.28); }
.ms-pill.learn { color:#c9a6ff; background:rgba(167,123,255,.10); border-color:rgba(167,123,255,.3); }
.ms-pill.near { color:#ffd866; background:rgba(255,204,51,.10); border-color:rgba(255,204,51,.28); }
.ms-sec { margin:22px 2px 10px; }
.ms-sec-k { font-size:0.66rem; font-weight:800; letter-spacing:2px; text-transform:uppercase; }
.ms-sec-k.smogon { color:#5fd38d; } .ms-sec-k.ladder { color:#00d4ff; } .ms-sec-k.learn { color:#c9a6ff; } .ms-sec-k.near { color:#ffd866; }
.ms-sec-t { font-weight:900; font-size:1.25rem; color:#fff; margin-top:2px; }
.ms-sec-c { font-size:0.82rem; color:#8a93a6; margin-top:2px; }
.ms-card { border-radius:14px; padding:14px 16px; min-width:0; min-height:196px; margin-bottom:6px;
  background:linear-gradient(160deg, var(--tc1a), rgba(255,255,255,0.015) 55%); border:1px solid var(--tc44);
  box-shadow:0 0 18px -12px var(--tc); }
.ms-top { display:flex; gap:12px; align-items:center; }
.ms-top > img { width:60px; height:60px; object-fit:contain; flex-shrink:0; filter:drop-shadow(0 0 10px var(--tc88)); }
.ms-name { font-weight:800; font-size:1.02rem; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ms-row { display:flex; align-items:center; gap:6px; margin-top:4px; }
.ms-use { font-size:.74rem; color:#aab3c5; margin-left:4px; }
.ms-sets { display:flex; flex-wrap:wrap; gap:5px; margin-top:10px; }
.ms-sets span { font-size:.72rem; font-weight:700; color:#8ff0b5; padding:2px 9px; border-radius:999px;
  background:rgba(95,211,141,.10); border:1px solid rgba(95,211,141,.25); }
.ms-bars { display:flex; flex-direction:column; gap:6px; margin-top:10px; }
.ms-bar-row { display:flex; justify-content:space-between; font-size:0.78rem; color:#d6dbe6; }
.ms-bar-row b { color:#fff; font-variant-numeric:tabular-nums; }
.ms-bar { height:5px; border-radius:4px; background:rgba(255,255,255,0.07); overflow:hidden; margin-top:3px; }
.ms-bar i { display:block; height:100%; background:var(--tc); box-shadow:0 0 8px -2px var(--tc); }
.ms-bar i.off { background:rgba(255,255,255,.18); box-shadow:none; }
.ms-note { font-size:.78rem; color:#aab3c5; margin-top:10px; line-height:1.4; }
.ms-note b { color:#fff; }
.ms-empty { border:1px dashed rgba(255,255,255,0.12); border-radius:14px; padding:22px; text-align:center; color:#8a93a6; font-size:0.9rem; }
.ms-team { display:flex; align-items:center; gap:8px; font-size:.85rem; color:#c6d1e3; }
[class*="st-key-ms_ex_"] button { padding:4px 14px !important; border-radius:999px !important; }
.ms-team img { width:34px; height:34px; object-fit:contain; margin-right:-4px; }
</style>
"""

SECTIONS = {
    "smogon": ("Smogon sets", "Run them on a Smogon set",
               "Pokémon with a Smogon set for this format that runs every move you picked."),
    "ladder": ("Ladder", "Run them on the ladder",
               "Players run every one of these moves on them this month, though not always on the same set."),
    "learn": ("Learnsets", "Can learn them",
              "Pokémon in this format that learn every move but rarely run them together. Hidden picks live here."),
    "near": ("Close", "Runs all but one", "Pokémon that run every move you picked except one."),
}
EXAMPLES = (("Trick Room", "Healing Wish"), ("Stealth Rock", "U-turn"), ("Knock Off", "U-turn"), ("Swords Dance", "Roost"))


@st.cache_data(show_spinner=False, ttl=3600)
def _options(format_id):
    return move_search.move_options(format_id)


def _picker_key(format_id):
    return f"move_search_select_{format_id}"


def _set_moves(format_id, moves):
    st.session_state[_picker_key(format_id)] = list(moves)


def _team_key(format_id):
    return f"quick_match_select_{format_id}"


def _pending_key(format_id):
    return f"qm_pending_{format_id}"


def _team(format_id):
    """Quick Match's team for this format, plus what was added here and not yet picked up there."""
    team = list(st.session_state.get(_team_key(format_id)) or [])
    return team + [n for n, _ in st.session_state.get(_pending_key(format_id), []) if n not in team]


def _add(format_id, name, set_name):
    """'Add to team': queued for Quick Match (tab_quick_match.take_pending), which owns its widgets. Writing them
    from this page doesn't stick, since Streamlit keeps a widget's state only on the page that draws it."""
    team = _team(format_id)
    if name not in team and len(team) < 6:
        st.session_state.setdefault(_pending_key(format_id), []).append((name, set_name))
        st.toast(f"Added {name} to your team")


def _vars(name, dex, type_map):
    species = dex.species(name) if dex else None
    color = type_map.get(((species or {}).get("types") or ["Normal"])[0], {}).get("color", "#00d4ff")
    return f"--tc:{color}; --tc1a:{color}1a; --tc44:{color}44; --tc88:{color}88;"


def _strip(moves, type_map):
    """The picked moves as chips in their type's color, with Showdown's description on hover."""
    chips = []
    for m in moves:
        info = move_search.move_info(m)
        color = type_map.get(info["type"], {}).get("color", "#8a93a6")
        glyph = get_type_icon(info["type"]) if info["type"] else None
        icon = f'<i style="background-image:url({escape(glyph)})"></i>' if glyph else "<i></i>"
        power = f" · {info['power']}" if info["power"] else ""
        detail = f"{info['category']}{power}" if info["category"] else ""
        tip = f'<span class="ms-tip">{escape(info["short"])}</span>' if info["short"] else ""
        chips.append(f'<span class="ms-chip" style="--c:{color}">{icon}{escape(m)}<small>{escape(detail)}</small>{tip}</span>')
    return '<div class="ms-strip">' + "".join(chips) + "</div>"


def _bars(r):
    return '<div class="ms-bars">' + "".join(
        f'<div><div class="ms-bar-row"><span>{escape(m)}</span><b>{v * 100:.0f}%</b></div>'
        f'<div class="ms-bar"><i class="{"" if v >= move_search.MIN_SHARE else "off"}" style="width:{min(v * 100, 100):.0f}%"></i></div></div>'
        for m, v in r["shares"].items()) + "</div>"


def _evidence(r, n_moves):
    tier = r["tier"]
    if tier == "smogon":
        sets = "".join(f"<span>{escape(s.rsplit(' (', 1)[0])}</span>" for s in r["sets"])
        return f'<div class="ms-sets">{sets}</div>' + (_bars(r) if any(r["shares"].values()) else "")
    if tier == "ladder":
        if n_moves == 1:
            return _bars(r)
        line = (f'At least <b>{r["together"] * 100:.0f}%</b> of its sets run all of them.' if r["together"] >= 0.05 else
                "Often on different sets, so check which ones pair up.")
        return _bars(r) + f'<div class="ms-note">{line}</div>'
    if tier == "learn":
        return '<div class="ms-note">Learns every move you picked, but players rarely run them together. Worth a try.</div>'
    learn = " It can learn it." if r.get("learns_missing") else " It can't learn it."
    return _bars(r) + f'<div class="ms-note">Doesn&#39;t run <b>{escape(r["missing"])}</b>.{learn}</div>'


def _card(r, n_moves, dex, type_map):
    from metamatch.tabs.tab_banner import _type_icon
    types = ((dex.species(r["name"]) if dex else None) or {}).get("types") or []
    icons = "".join(_type_icon(t, type_map, small=True) for t in types)
    return (f'<div class="ms-card" style="{_vars(r["name"], dex, type_map)}"><div class="ms-top">'
            f'<img src="{escape(get_sprite(r["name"]) or "")}" alt=""><div style="min-width:0">'
            f'<div class="ms-name">{escape(r["name"])}</div>'
            f'<div class="ms-row">{icons}<span class="ms-use">{r["usage"] * 100:.1f}% usage</span></div></div></div>'
            f'{_evidence(r, n_moves)}</div>')


def _grid(results, format_id, n_moves, dex, type_map, team):
    for i in range(0, len(results), 3):
        cols = st.columns(3)
        for col, r in zip(cols, results[i:i + 3]):
            with col:
                st.html(_card(r, n_moves, dex, type_map))
                on_team = r["name"] in team
                st.button("On your team" if on_team else "Add to team", key=f"ms_add_{format_id}_{r['name']}",
                          icon=":material/check:" if on_team else ":material/add:", width="stretch",
                          disabled=on_team or len(team) >= 6, on_click=_add,
                          args=(format_id, r["name"], (r["sets"] or [None])[0]))


def _team_bar(format_id, open_quick_match_fn):
    team = _team(format_id)
    if not team:
        return team
    with st.container(horizontal=True, vertical_alignment="center"):
        sprites = "".join(f'<img src="{escape(get_sprite(n) or "")}" alt="" title="{escape(n)}">' for n in team)
        st.html(STYLE + f'<div class="ms-team">{sprites}<span style="margin-left:8px">Your team: <b>{len(team)} of 6</b></span></div>')
        if st.button("Open in Quick Match", icon=":material/group_add:", key=f"ms_open_qm_{format_id}"):
            open_quick_match_fn()
    return team


def render(get_strat_data_fn, type_map=None, open_quick_match_fn=None):
    from metamatch.engine.dex import dex_for_format
    type_map = type_map or {}
    format_id = st.session_state.get("format_id") or config.DEFAULT_FORMAT
    label = config.format_info(format_id)["label"]
    options = _options(format_id)
    key = _picker_key(format_id)
    moves = st.multiselect("Moves", options=options, key=key, max_selections=4,
                           placeholder="Type up to 4 moves, for example Scald or Thunder Wave", label_visibility="collapsed")
    team = _team_bar(format_id, open_quick_match_fn)
    if not moves:
        st.html(STYLE)
        st.caption(f"Pick moves to see every {label} Pokémon that runs or can learn all of them. Or try one of these:")
        with st.container(horizontal=True):
            for ex in EXAMPLES:
                if all(m in options for m in ex):
                    st.button(" + ".join(ex), key=f"ms_ex_{format_id}_{'_'.join(ex)}", type="tertiary",
                              on_click=_set_moves, args=(format_id, ex))
        return
    strat_data = get_strat_data_fn()
    dex = dex_for_format(format_id)
    results = move_search.search(moves, format_id, strat_data)
    from metamatch.tabs.tab_banner import STYLE as BANNER_STYLE
    html = BANNER_STYLE + STYLE + _strip(moves, type_map)
    full = [r for r in results if r["tier"] != "near"]
    counts = {t: sum(r["tier"] == t for r in results) for t in SECTIONS}
    words = {"smogon": "on Smogon sets", "ladder": "on the ladder", "learn": "can learn", "near": "close"}
    pills = "".join(f'<span class="ms-pill {t}">{counts[t]} {words[t]}</span>' for t in SECTIONS if counts[t])
    word = "it" if len(moves) == 1 else "all of them"
    html += f'<div class="ms-sum"><b>{len(full)} Pokémon with {word}</b>{pills}</div>'
    st.html(html)
    if not results:
        st.html(STYLE + f'<div class="ms-empty">Nothing in {escape(label)} runs or learns {escape(", ".join(moves))}. '
                        'Try dropping a move, or pick another format above.</div>')
        return
    for tier, (kicker, title, caption) in SECTIONS.items():
        rows = [r for r in results if r["tier"] == tier]
        if not rows:
            continue
        st.html(STYLE + f'<div class="ms-sec"><div class="ms-sec-k {tier}">{kicker}</div><div class="ms-sec-t">{title}</div>'
                        f'<div class="ms-sec-c">{caption}</div></div>')
        _grid(rows[:SHOW], format_id, len(moves), dex, type_map, team)
        if len(rows) > SHOW:
            with st.expander(f"{len(rows) - SHOW} more"):
                _grid(rows[SHOW:], format_id, len(moves), dex, type_map, team)
