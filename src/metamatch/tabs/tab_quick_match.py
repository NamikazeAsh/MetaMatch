"""Quick Match: partners for a core of up to 6 Pokemon from how often players really pair them in this format, and a
builder that fills in each member's set and sends the team to the analysis or to Showdown as a paste."""
from html import escape

import streamlit as st

from metamatch import config
from metamatch.auditor import load_chaos_data
from metamatch.engine import builder
from metamatch.engine.completer import core_partners
from metamatch.tabs.tab_recommender import STYLE as CARD_STYLE
from metamatch.sprites import get_sprite

QM_STYLE = """
<style>
.qm-card { background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.08); border-radius: 12px; padding: 12px;
  text-align: center; margin-bottom: 6px; position: relative; }
.qm-card:hover { z-index: 60; }
.qm-card img.sprite { width: 72px; height: 72px; object-fit: contain; }
.qm-card .tc-tip { text-align: left; }
.qm-name { font-weight: 700; margin-top: 4px; }
.qm-share { font-size: .82rem; color: #c6d1e3; margin-top: 4px; }
/* The sets float over the page below the card on hover, so nothing around it moves */
.qm-sets { position: absolute; left: 10px; right: 10px; top: calc(100% - 10px); z-index: 60; text-align: left;
  background: #151a24; border: 1px solid rgba(0,212,255,.35); border-radius: 10px; padding: 4px 8px 8px;
  box-shadow: 0 12px 28px rgba(0,0,0,.55); opacity: 0; visibility: hidden; transform: translateY(-4px);
  transition: opacity .18s ease, transform .18s ease, visibility .18s; pointer-events: none; }
.qm-card:hover .qm-sets { opacity: 1; visibility: visible; transform: translateY(0); }
/* Streamlit's wrappers clip overflow and stack later rows on top; let the hovered card's box show over them */
div[data-testid="stElementContainer"]:has(.qm-card), div[data-testid="stMarkdown"]:has(.qm-card),
div[data-testid="stMarkdownContainer"]:has(.qm-card) { overflow: visible !important; }
div[data-testid="stHorizontalBlock"]:has(.qm-card:hover), div[data-testid="stColumn"]:has(.qm-card:hover),
div[data-testid="stElementContainer"]:has(.qm-card:hover) { position: relative; z-index: 60; }
.qm-set { background: rgba(255,255,255,.03); border-radius: 6px; padding: 6px 10px; margin-top: 6px; border-left: 3px solid #22d3ee; }
.qm-set b { display: block; font-size: .8rem; }
.qm-set span { font-size: .72rem; color: #aab4c6; }
</style>
"""


def _options(format_id):
    """The format's Pokemon, most used first."""
    data = load_chaos_data(format_id) or {}
    ranked = sorted(data.items(), key=lambda kv: kv[1].get("usage", 0), reverse=True)
    return [name for name, entry in ranked if entry.get("usage", 0) > 0.001]


def _chip(r):
    member, share, lift = r["pairs"][0]
    if lift >= 1.5:
        cls, text = "pair", f"Players often pair it with {escape(member)}"
    elif lift >= 1.15:
        cls, text = "pair", f"Sometimes paired with {escape(member)}"
    elif r["lift"] <= 0.8:
        cls, text = "flat", "Popular, but not with this core"
    else:
        cls, text = "flat", "Popular on every kind of team"
    rows = "".join(
        f'<div class="tc-trow"><span>On teams with {escape(m)}</span><b>{s * 100:.1f}%</b>'
        f'<em class="{"up" if l_ >= 1.15 else "down" if l_ <= 0.85 else ""}">{l_:.1f}x</em></div>' for m, s, l_ in r["pairs"][:3])
    tip = (f'<span class="tc-tip"><span class="tc-tt">How often {escape(r["name"])} shows up</span>{rows}'
           f'<div class="tc-trow all"><span>On all teams</span><b>{r["usage"]:.1f}%</b><em></em></div>'
           '<span class="tc-tfoot">From this month&#39;s ladder teams. 2.0x means twice as often as on an average team.</span></span>')
    return f'<span class="tc-chip {cls} tc-pop">{text}{tip}</span>'


def _sets_html(name, strat_data, label):
    sets = [(s, info) for s, info in (strat_data.get(name, {}).get("sets", {}) or {}).items() if f"({label})" in s][:3]
    if not sets:
        return ""
    out = []
    for set_name, info in sets:
        item = info.get("item", "")
        item = item[0] if isinstance(item, list) and item else item
        ability = info.get("ability", "")
        ability = ability[0] if isinstance(ability, list) and ability else ability
        detail = " · ".join(x for x in (item, ability) if x and x != "None")
        out.append(f'<div class="qm-set"><b>{escape(set_name.rsplit(" (", 1)[0])}</b><span>{escape(detail)}</span></div>')
    return '<div class="qm-sets">' + "".join(out) + "</div>"


PASTE_STYLE = """<style>
.qm-pp { margin: 0; }
.qm-pp button { width: 100%; height: 40px; border-radius: 8px; border: 1px solid #00d4ff; background: rgba(0,212,255,.1);
  color: #00d4ff; font-family: Inter, "Source Sans", sans-serif; font-size: 14px; font-weight: 400; cursor: pointer;
  transition: all .2s ease; }
.qm-pp button:hover { background: rgba(0,212,255,.2); box-shadow: 0 0 20px rgba(0,212,255,.4); }
</style>"""


def _remove(key, name):
    """The minus on a member's card: drops it from the picker before it redraws."""
    st.session_state[key] = [n for n in (st.session_state.get(key) or []) if n != name]


def _add(key, name):
    """'Add to team': runs before the core picker redraws, so it can change the picker's value."""
    picked = list(st.session_state.get(key) or [])
    if name not in picked and len(picked) < TEAM_SIZE:
        st.session_state[key] = picked + [name]


TEAM_SIZE = 6


def _partners(core, format_id, key, strat_data, label):
    # The pairing ranking, reordered by what the closest real ladder teams run (engine/team_neighbors.reorder)
    from metamatch.engine import team_neighbors
    partners = team_neighbors.reorder(core, format_id, core_partners(core, format_id, n=30))[:16]
    if not partners:
        st.caption("No ladder data pairs with this core yet.")
        return
    st.markdown("**Best partners for your core**")
    for i in range(0, len(partners), 4):
        cols = st.columns(4)
        for col, r in zip(cols, partners[i:i + 4]):
            with col:
                sprite = escape(get_sprite(r["name"]) or "")
                core_word = "your core" if len(core) > 1 else escape(core[0])
                st.markdown(
                    CARD_STYLE + QM_STYLE +
                    f'<div class="qm-card"><img class="sprite" src="{sprite}" alt="">'
                    f'<div class="qm-name">{escape(r["name"])}</div>'
                    f'<div class="qm-share">On {r["share"] * 100:.0f}% of teams with {core_word}</div>'
                    f'<div>{_chip(r)}</div>{_sets_html(r["name"], strat_data, label)}</div>',
                    unsafe_allow_html=True)
                st.button("Add to team", key=f"qm_add_{format_id}_{r['name']}", icon=":material/add:", width="stretch",
                          on_click=_add, args=(key, r["name"]))
    st.caption("Ranked by how often teams with your core run each partner and by what the closest real ladder teams run. "
               "Hover a card for its sets and a chip for the numbers.")


@st.dialog("Export for Showdown", width="medium")
def _export(paste):
    """The team as Showdown text, with the copy button in the corner of the box."""
    st.caption("Copy it, then in Showdown's teambuilder pick New team and Import from text. Spreads and moves are the "
               "most common on this month's ladder, so tweak them there.")
    st.code(paste, language=None)


SLOT_STYLE = """<style>
/* Each team member is a card like the team banner's, with its set dropdown inside */
[class*="st-key-qm_slot_"] { border-radius: 18px; padding: 14px 14px 12px; min-height: 252px; gap: 10px;
  background: radial-gradient(circle at 12% 22%, var(--tc33, rgba(0,212,255,.15)), transparent 46%),
              linear-gradient(145deg, #1c2232, #141924);
  border: 1px solid rgba(255,255,255,0.06);
  box-shadow: 10px 10px 24px rgba(0,0,0,0.45), -6px -6px 16px rgba(255,255,255,0.025), inset 1px 1px 0 rgba(255,255,255,0.05); }
.qm-tile { display: grid; grid-template-columns: 76px minmax(0, 1fr); gap: 12px; }
.qm-tile .bn-ped { width: 76px; height: 76px; }
.qm-tile .bn-ped > img { width: 68px; height: 68px; }
.qm-tile .bn-item { width: 30px; height: 30px; } .qm-tile .bn-item img { width: 22px; height: 22px; }
.qm-tile .bn-moves { grid-column: 1 / -1; padding-top: 2px; }
/* Open slots up to six */
.qm-empty { min-height: 252px; border-radius: 18px; border: 1.5px dashed rgba(0,212,255,.25); display: grid; place-items: center;
  text-align: center; color: #7f8aa0; font-size: .85rem; background: rgba(0,212,255,.02); }
.qm-empty b { display: block; font-size: 1.6rem; color: rgba(0,212,255,.55); font-weight: 400; line-height: 1; margin-bottom: 6px; }
/* The minus in a member card's corner removes it */
[class*="st-key-qm_slot_"] { position: relative; }
[class*="st-key-qm_rm_"] { position: absolute; top: 10px; right: 10px; width: auto !important; z-index: 5; }
[class*="st-key-qm_rm_"] button { width: 26px !important; height: 26px !important; min-width: 0 !important; min-height: 0 !important;
  padding: 0 !important; border-radius: 50% !important; display: grid !important; place-items: center;
  background: rgba(255,255,255,.05) !important; border: 1px solid rgba(255,255,255,.16) !important; color: #aab4c6 !important; }
[class*="st-key-qm_rm_"] button p { font-size: 18px !important; line-height: 1 !important; margin: 0 0 2px !important; font-weight: 600; }
[class*="st-key-qm_rm_"] button:hover { background: rgba(255,107,107,.15) !important; border-color: rgba(255,107,107,.6) !important;
  color: #ff8a8a !important; box-shadow: none !important; }
/* Analyze is the main action: solid, like Home's */
[class*="st-key-qm_analyze_"] button { background: #00d4ff !important; color: #04141a !important; border-color: #00d4ff !important; }
[class*="st-key-qm_analyze_"] button p { font-weight: 700; }
[class*="st-key-qm_analyze_"] button:hover { box-shadow: 0 0 20px rgba(0,212,255,.45) !important; }
</style>"""


def _types(name, dex):
    return ((dex.species(name) if dex else None) or {}).get("types") or ["Normal"]


def _tile(s, name, dex, type_map):
    """A member's card: sprite with its item, types and Tera, ability, and the four moves tinted by type."""
    from metamatch.sprites import get_item_icon, get_tera_icon
    from metamatch.tabs.tab_banner import _ability_pill, _type_icon
    item_icon = get_item_icon(s.get("item"))
    item = (f'<span class="bn-ico bn-item" tabindex="0"><img src="{escape(item_icon)}" alt="">'
            f'<span class="bn-tip">{escape(s["item"])}</span></span>') if item_icon else ""
    tera_icon = get_tera_icon(s.get("tera")) if s.get("tera") else None
    tera = (f'<span class="bn-sep"></span><span class="bn-ico bn-tera" tabindex="0" '
            f'style="--c:{type_map.get(s["tera"], {}).get("color", "#777")}"><img src="{escape(tera_icon)}" alt="">'
            f'<span class="bn-tip">Tera {escape(s["tera"])}</span></span>') if tera_icon else ""
    moves = ""
    for m in s["moves"]:
        mtype = ((dex.move(m) if dex else None) or {}).get("type")
        moves += f'<span class="bn-mv" style="--mc:{type_map.get(mtype, {}).get("color", "#5a6375")}">{escape(m)}</span>'
    return (f'<div class="qm-tile"><div class="bn-ped"><img src="{escape(get_sprite(name) or "")}" alt="">{item}</div>'
            f'<div class="bn-body"><div class="bn-nm">{escape(name)}</div>'
            f'<div class="bn-icons">{"".join(_type_icon(t, type_map) for t in _types(name, dex))}{tera}</div>'
            f'{_ability_pill(s.get("ability"))}</div><div class="bn-moves">{moves}</div></div>')


def _team(core, format_id, strat_data, label, open_team_fn, type_map, key):
    """Each member's card with its set (the ladder's most common, or a Smogon set), open slots up to six, and where
    to take the team."""
    from metamatch.engine.dex import dex_for_format
    from metamatch.tabs.tab_banner import STYLE as BANNER_STYLE
    dex = dex_for_format(format_id)
    tints = "".join(f'.st-key-qm_slot_{i} {{ --tc33: {type_map.get(_types(n, dex)[0], {}).get("color", "#00d4ff")}40; }}'
                    for i, n in enumerate(core))
    st.html(BANNER_STYLE + SLOT_STYLE + f"<style>{tints}</style>")
    st.markdown("**Your team**")
    sets, missing = [], []
    for row in range(0, TEAM_SIZE, 3):
        cols = st.columns(3)
        for i in range(row, row + 3):
            with cols[i - row]:
                if i >= len(core):
                    st.html('<div class="qm-empty"><div><b>+</b>Add a Pokémon<br>above or from the partners below</div></div>')
                    continue
                name = core[i]
                options = [builder.LADDER] + builder.smogon_options(name, strat_data, label)
                with st.container(key=f"qm_slot_{i}"):
                    st.button("−", key=f"qm_rm_{format_id}_{name}", type="tertiary", on_click=_remove, args=(key, name))
                    tile = st.empty()
                    pick = builder.LADDER
                    if len(options) > 1:
                        pick = st.selectbox("Set", options, key=f"qm_set_{format_id}_{name}", label_visibility="collapsed",
                                            format_func=lambda o: o.rsplit(" (", 1)[0])
                    info = None if pick == builder.LADDER else strat_data[builder.paste_species(name)]["sets"][pick]
                    s = builder.member_set(name, format_id, info)
                    if s:
                        sets.append(s)
                        tile.html(_tile(s, name, dex, type_map))
                    else:
                        missing.append(name)
                        tile.html(f'<div class="bn-nm">{escape(name)}</div>')
    if missing:
        st.caption(f"No ladder set for {', '.join(missing)} this month, so it's left out of the paste.")
    paste = builder.team_paste(sets, format_id)
    if not paste:
        return
    b1, b2, b3 = st.columns([2, 1, 1])
    analyze = b1.button("Analyze team", type="primary", icon=":material/insights:", width="stretch",
                        key=f"qm_analyze_{format_id}")
    if b2.button("Export for Showdown", icon=":material/content_copy:", width="stretch", key=f"qm_export_{format_id}"):
        _export(paste)
    # The browser posts the team to PokéPaste itself (as Showdown's own upload does) and opens the new link in a tab
    b3.html(PASTE_STYLE + '<form class="qm-pp" action="https://pokepast.es/create" method="post" target="_blank">'
            f'<input type="hidden" name="paste" value="{escape(paste)}">'
            # No title field: st.html's sanitizer strips name="title" (it clobbers a DOM property)
            '<input type="hidden" name="author" value="">'
            f'<input type="hidden" name="notes" value="{escape(label)} team built with MetaMatch: '
            'https://metamatch.streamlit.app">'
            '<button type="submit">Get a PokéPaste link</button></form>')
    if analyze:
        open_team_fn(paste, format_id)


def take_pending(format_id, key):
    """Pokemon added from Move Search (tab_move_search._add) join the team before the picker draws, with the
    Smogon set they were found on picked."""
    pending = st.session_state.pop(f"qm_pending_{format_id}", None)
    if not pending:
        return
    team = list(st.session_state.get(key) or [])
    for name, set_name in pending:
        if name not in team and len(team) < TEAM_SIZE:
            team.append(name)
            if set_name:
                st.session_state[f"qm_set_{format_id}_{name}"] = set_name
    st.session_state[key] = team


GUIDE = (
    (":material/search:", "Pick one you like",
     "Search for a Pokémon you want to build around in {label}. One is enough to start."),
    (":material/group_add:", "Add its partners",
     "Cards show who players pair with it most this month in {label}. Add the ones you like until you have six."),
    (":material/rocket_launch:", "Analyze or play",
     "Every member gets its usual set. Analyze the team here, export it to Showdown or share a PokéPaste link."),
)


def _guide(label):
    """How Quick Match works, in three short steps, while the team is still empty."""
    with st.container(horizontal=True, gap="small", key="qm_guide"):
        for n, (icon, title, text) in enumerate(GUIDE, 1):
            with st.container(border=True):
                st.markdown(f"{icon} **{n}. {title}**")
                st.caption(text.format(label=label))


def render(get_strat_data_fn, open_team_fn, type_map):
    format_id = st.session_state.get("format_id") or config.DEFAULT_FORMAT
    label = config.format_info(format_id)["label"]
    key = f"quick_match_select_{format_id}"
    take_pending(format_id, key)
    core = st.multiselect("Your team (up to 6)", options=_options(format_id), max_selections=TEAM_SIZE,
                          placeholder="Search for a Pokémon...", key=key)
    if not core:
        _guide(label)
        return
    strat_data = get_strat_data_fn()
    _team(core, format_id, strat_data, label, open_team_fn, type_map, key)
    st.markdown("---")
    if len(core) < TEAM_SIZE:
        _partners(core, format_id, key, strat_data, label)
    else:
        st.caption("Your team is full. Remove a member above to see partners again.")
