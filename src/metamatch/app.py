import os
from html import escape
import warnings
import logging

# --- Suppress Startup Warnings ---
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
warnings.filterwarnings('ignore', category=UserWarning, module='triton')
warnings.filterwarnings('ignore', category=FutureWarning, module='google.api_core')
logging.getLogger('tensorflow').setLevel(logging.ERROR)

import streamlit as st
import sys
from pathlib import Path

# Fix path to allow importing from the metamatch package
# Adds the 'src' directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from metamatch.utils import is_pokepaste_url, fetch_pokepaste, extract_pokemon_names

from metamatch.team import readTeam, detectRole, addComments, coverageCheck, looks_like_champions
from metamatch.suggestions import get_suggestions
from metamatch import config
from metamatch import storage
from metamatch import strategy_data
from metamatch import meta_pulse
from metamatch.ui import page_header, section_header
from metamatch.tabs import (
    tab_banner,
    tab_quick_match, tab_move_search, tab_replay,
    tab_overview as tab_overview_mod, tab_audit, tab_threats,
    tab_coach_guide, tab_recommender as tab_recommender_mod, tab_matrix as tab_matrix_mod,
    tab_speed_tiers, tab_chat as tab_chat_mod, tab_meta_pulse, tab_spread_lab, tab_preview,
)

st.set_page_config(page_title="MetaMatch", page_icon="⚪", layout="wide")

# --- Global CSS ---
st.html(r'''
<style>

    /* Global Base */
    .main .block-container { padding-top: 2rem; padding-bottom: 0rem; }
    .stApp { background: radial-gradient(circle at 50% 50%, #1a1f2e 0%, #0f1219 100%); color: #e0e0e0; font-family: 'Inter', sans-serif; }

    /* Transparent Header */
    .stApp > header { background-color: transparent; }

    /* Loading: the MetaMatch logo spins in place of Streamlit's default spinner */
    [data-testid="stSpinnerIcon"] { width: 30px !important; height: 30px !important; border: none !important;
        background: url("/app/static/logo_spinner.png") center / contain no-repeat !important;
        animation: mm-spin 1.1s linear infinite !important; filter: drop-shadow(0 0 6px rgba(0, 212, 255, .35)); }
    [data-testid="stSpinnerIcon"] > * { display: none !important; }
    [data-testid="stSpinner"] { color: #9fb0cc; font-weight: 500; }
    @keyframes mm-spin { to { transform: rotate(360deg); } }
    @media (prefers-reduced-motion: reduce) { [data-testid="stSpinnerIcon"] { animation: mm-pulse 1.6s ease-in-out infinite !important; } }
    @keyframes mm-pulse { 50% { opacity: .45; } }

    /* Sidebar Glassmorphism */
    [data-testid="stSidebar"] { background: rgba(255, 255, 255, 0.02) !important; backdrop-filter: blur(20px); border-right: 1px solid rgba(255, 255, 255, 0.05); }
    [data-testid="stSidebar"] .stMarkdown h1, [data-testid="stSidebar"] .stMarkdown h2 { color: #00d4ff; text-shadow: 0 0 10px rgba(0, 212, 255, 0.3); }

    /* Metrics Glowing Style */
    div[data-testid="stMetric"] { background: rgba(255, 255, 255, 0.03); padding: 15px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.05); box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
    div[data-testid="stMetricValue"] { font-family: 'Inter', sans-serif; font-weight: 800 !important; color: #fff !important; text-shadow: 0 0 15px rgba(255,255,255,0.2); font-size: clamp(1.4rem, 2.2vw, 2.1rem) !important; }
    div[data-testid="stMetricLabel"] { color: #888 !important; text-transform: uppercase; letter-spacing: 1px; font-size: 0.75rem !important; }

    /* Recent team cards: link and remove button stay on one line, a long label ends in an ellipsis */
    [class*="st-key-recentrow_"] { flex-wrap: nowrap !important; }
    [class*="st-key-recentrow_"] [data-testid="stPageLink"] { flex: 1 1 auto; min-width: 0; overflow: hidden; }
    [class*="st-key-recentrow_"] [data-testid="stPageLink"] a, [class*="st-key-recentrow_"] [data-testid="stPageLink"] p {
        min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    [class*="st-key-forget_"] { flex: 0 0 auto; }

    /* Small remove buttons on the sidebar's recent team cards */
    [class*="st-key-forget_"] button { width: auto !important; min-height: 0 !important; padding: 2px 4px !important;
        background: transparent !important; border: none !important; color: #6b7487 !important; box-shadow: none !important; }
    [class*="st-key-forget_"] button:hover { color: #ff7b7b !important; transform: none !important; }

    /* Glass Buttons */
    .stButton > button { background: rgba(0, 212, 255, 0.1) !important; color: #00d4ff !important; border: 1px solid #00d4ff !important; backdrop-filter: blur(5px); border-radius: 8px !important; font-weight: 600 !important; transition: all 0.3s ease !important; width: 100%; }
    .stButton > button:hover { background: rgba(0, 212, 255, 0.2) !important; box-shadow: 0 0 20px rgba(0, 212, 255, 0.4) !important; transform: scale(1.02); }

    /* Form buttons: solid cyan primary with dark text (white on cyan is unreadable), glass secondary */
    [data-testid="stBaseButton-primaryFormSubmit"] { background: #00d4ff !important; color: #04141a !important; border: 1px solid #00d4ff !important; font-weight: 600 !important; }
    [data-testid="stBaseButton-primaryFormSubmit"]:hover { box-shadow: 0 0 20px rgba(0, 212, 255, 0.45) !important; }
    [data-testid="stBaseButton-secondaryFormSubmit"] { background: rgba(0, 212, 255, 0.1) !important; color: #00d4ff !important; border: 1px solid #00d4ff !important; font-weight: 600 !important; }
    [data-testid="stBaseButton-secondaryFormSubmit"]:hover { background: rgba(0, 212, 255, 0.2) !important; }

    /* Saved team preview: sprite tiles glowing in each member's type colour */
    .mm-sprites { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 4px 0 6px; }
    .mm-sprite { position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
                 padding: 6px 4px 5px; border-radius: 10px; background: rgba(255, 255, 255, 0.03);
                 border: 1px solid color-mix(in srgb, var(--glow) 45%, transparent);
                 box-shadow: 0 0 14px -5px var(--glow), inset 0 0 16px -11px var(--glow); transition: transform 0.2s ease, box-shadow 0.2s ease; }
    .mm-sprite:hover { transform: translateY(-2px); box-shadow: 0 0 18px -3px var(--glow), inset 0 0 18px -10px var(--glow); }
    .mm-sprite img { width: 56px; height: 56px; object-fit: contain; filter: drop-shadow(0 0 6px color-mix(in srgb, var(--glow) 70%, transparent)); }
    .mm-sprite small { max-width: 100%; font-size: 0.62rem; color: #aab3c5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .mm-strip { display: flex; gap: 4px; margin: 2px 0 4px; }
    .mm-mini { width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
               background: rgba(255, 255, 255, 0.04); border: 1px solid color-mix(in srgb, var(--glow) 55%, transparent);
               box-shadow: 0 0 10px -4px var(--glow); }
    .mm-mini img { width: 30px; height: 30px; object-fit: contain; }
    [data-testid="stSidebar"] [class*="st-key-recent_"] { padding: 8px 10px !important; gap: 2px !important; }
    .mm-sprite-missing { width: 56px; height: 56px; display: flex; align-items: center; justify-content: center; color: #6b7487; font-weight: 700; }
    /* Set card on hover or keyboard focus; edge columns align to their edge so the narrow sidebar never clips it */
    .mm-sprite:focus-visible { outline: 2px solid var(--glow); outline-offset: 2px; }
    .mm-set { position: absolute; top: calc(100% + 6px); left: 50%; transform: translateX(-50%); z-index: 20; width: 220px;
              padding: 10px 12px; border-radius: 10px; background: #141a26; border: 1px solid color-mix(in srgb, var(--glow) 55%, transparent);
              box-shadow: 0 8px 28px rgba(0, 0, 0, 0.55), 0 0 16px -6px var(--glow);
              font-size: 0.74rem; line-height: 1.45; color: #d5dbe7; text-align: left;
              opacity: 0; visibility: hidden; pointer-events: none; transition: opacity 0.15s ease; }
    .mm-set b { color: #fff; font-weight: 600; }
    .mm-set ul { margin: 6px 0 0 !important; padding-left: 16px !important; }
    .mm-set li { margin: 0 !important; padding: 0 !important; font-size: 0.74rem !important; line-height: 1.45 !important; }
    .mm-sprite:nth-child(3n+1) .mm-set { left: 0; transform: none; }
    .mm-sprite:nth-child(3n) .mm-set { left: auto; right: 0; transform: none; }
    .mm-sprite:hover .mm-set, .mm-sprite:focus-visible .mm-set { opacity: 1; visibility: visible; }
    .mm-sprite:hover, .mm-sprite:focus-visible { z-index: 21; }
    @media (prefers-reduced-motion: reduce) { .mm-sprite { transition: none; } .mm-sprite:hover { transform: none; } }

    /* Logo glow */
    [data-testid="stMarkdownContainer"] img[alt="MetaMatch logo"], .st-key-brand_logo img { display: block; margin: 0 auto; width: 210px; max-width: 60vw; height: auto; filter: drop-shadow(0 0 22px rgba(0, 212, 255, 0.35)) drop-shadow(0 0 6px rgba(0, 212, 255, 0.25)); }

    /* Futuristic Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: transparent; }
    .stTabs [data-baseweb="tab"] { background: rgba(255, 255, 255, 0.02) !important; border: 1px solid rgba(255, 255, 255, 0.05) !important; border-radius: 8px 8px 0 0 !important; color: #888 !important; padding: 10px 20px !important; }
    .stTabs [aria-selected="true"] { background: rgba(0, 212, 255, 0.05) !important; border-color: #00d4ff !important; color: #00d4ff !important; box-shadow: 0 -4px 10px rgba(0, 212, 255, 0.1); }

    /* Text Area / Inputs */
    .stTextArea textarea { background: rgba(0, 0, 0, 0.2) !important; color: #00ffcc !important; font-family: 'JetBrains Mono', monospace !important; border: 1px solid rgba(255, 255, 255, 0.1) !important; border-radius: 10px !important; }
    .stTextArea textarea:focus { border-color: #00d4ff !important; box-shadow: 0 0 10px rgba(0, 212, 255, 0.2) !important; }

    /* Pokemon Card Glassmorphism */
    .pokemon-card { background: rgba(255, 255, 255, 0.03); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border-radius: 16px; padding: 20px; margin-bottom: 20px; transition: transform 0.3s ease, box-shadow 0.3s ease; position: relative; overflow: hidden; }
    .pokemon-card:hover { transform: translateY(-5px); }
    .poke-name { font-size: 1.4rem; font-weight: 700; margin-bottom: 5px; color: #fff; }
    .role-badge { display: inline-block; background: rgba(255, 255, 255, 0.05); padding: 2px 8px; border-radius: 6px; font-size: 0.75rem; margin-right: 4px; border: 1px solid rgba(255,255,255,0.1); color: #ddd; }

    /* Custom Scrollbar */
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: rgba(0,0,0,0.1); }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(0, 212, 255, 0.3); }

    /* Animations */
    @keyframes fadeInUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }

    @keyframes pulseGlow { 0% { box-shadow: 0 0 10px rgba(0, 212, 255, 0.2); } 50% { box-shadow: 0 0 20px rgba(0, 212, 255, 0.4); } 100% { box-shadow: 0 0 10px rgba(0, 212, 255, 0.2); } }

    .pokemon-card { animation: fadeInUp 0.6s ease-out forwards; }

    /* Progress Bar Overhaul */
    div[data-testid="stProgress"] > div > div > div > div { background-image: linear-gradient(90deg, #00d4ff, #00ffcc) !important; box-shadow: 0 0 15px rgba(0, 212, 255, 0.5); }

    /* Neon Dividers */
    hr { border: 0; height: 1px; background: linear-gradient(90deg, transparent, rgba(0, 212, 255, 0.5), transparent); margin: 2rem 0; }

    /* Background Atmospheric Particles */
    .stApp::before { content: ""; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background:
            radial-gradient(circle at 20% 30%, rgba(0, 212, 255, 0.05) 0%, transparent 20%),
            radial-gradient(circle at 80% 70%, rgba(0, 255, 204, 0.05) 0%, transparent 20%);
            pointer-events: none; z-index: -1; }
</style>
''')

TYPE_MAP = {
    'Fire': {'color': '#FF4422', 'icon': '🔥'}, 'Water': {'color': '#3399FF', 'icon': '💧'},
    'Grass': {'color': '#77CC55', 'icon': '🌿'}, 'Electric': {'color': '#FFCC33', 'icon': '⚡'},
    'Psychic': {'color': '#FF5599', 'icon': '🔮'}, 'Ice': {'color': '#66CCFF', 'icon': '❄️'},
    'Fighting': {'color': '#BB5544', 'icon': '🥊'}, 'Poison': {'color': '#AA5599', 'icon': '☠️'},
    'Ground': {'color': '#DDBB55', 'icon': '🏜️'}, 'Flying': {'color': '#8899FF', 'icon': '🕊️'},
    'Bug': {'color': '#AABB22', 'icon': '🐞'}, 'Rock': {'color': '#BBAA66', 'icon': '🪨'},
    'Ghost': {'color': '#6666BB', 'icon': '👻'}, 'Dragon': {'color': '#7766EE', 'icon': '🐲'},
    'Dark': {'color': '#775544', 'icon': '🌑'}, 'Steel': {'color': '#AAAABB', 'icon': '⚙️'},
    'Fairy': {'color': '#EE99AA', 'icon': '✨'}, 'Normal': {'color': '#AAAA99', 'icon': '⚪'}
}

@st.cache_data(ttl=300)
def get_cached_teams():
    return storage.list_teams_detailed()

# Initialize Session State. The analysed team lives in session; /team?t=<id> can rebuild it from the local store
if 'pokemon_names' not in st.session_state:
    st.session_state.pokemon_names = []
if 'default_input' not in st.session_state:
    st.session_state.default_input = ""
if 'chat_messages' not in st.session_state:
    st.session_state.chat_messages = []
if 'format_id' not in st.session_state:
    # A new session (first load or refresh): a ?format= link wins, then the last format used on this machine
    linked = st.query_params.get("format")
    remembered = storage.get_pref("format") if config.LOCAL_MODE else None
    st.session_state.format_id = next((f for f in (linked, remembered) if f in config.FORMATS), config.DEFAULT_FORMAT)

# A real OU team, so anyone can see the dashboard without a Showdown export
SAMPLE_TEAM = """Gholdengo @ Choice Scarf
Ability: Good as Gold
Tera Type: Steel
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Trick
- Focus Blast

Great Tusk @ Booster Energy
Ability: Protosynthesis
Tera Type: Ground
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Headlong Rush
- Ice Spinner
- Rapid Spin
- Knock Off

Kingambit @ Black Glasses
Ability: Supreme Overlord
Tera Type: Dark
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Swords Dance
- Kowtow Cleave
- Sucker Punch
- Iron Head

Dragapult @ Heavy-Duty Boots
Ability: Infiltrator
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Draco Meteor
- Shadow Ball
- U-turn
- Will-O-Wisp

Corviknight @ Leftovers
Ability: Pressure
Tera Type: Dragon
EVs: 252 HP / 168 Def / 88 SpD
Impish Nature
- Body Press
- Brave Bird
- Roost
- Defog

Slowking-Galar @ Heavy-Duty Boots
Ability: Regenerator
Tera Type: Water
EVs: 252 HP / 4 Def / 252 SpD
Sassy Nature
- Future Sight
- Sludge Bomb
- Chilly Reception
- Slack Off"""


def load_team(pokemon_data, fmt_id):
    """Analyses a paste into session state. Returns the team id, or None after showing an error."""
    if is_pokepaste_url(pokemon_data):
        with st.spinner("Fetching team from pokepast.es..."):
            fetched = fetch_pokepaste(pokemon_data)
        if not fetched:
            st.error("Couldn't fetch that pokepast.es link. Check the URL and try again.")
            return None
        pokemon_data = fetched
        st.toast("Loaded team from pokepast.es")

    with st.spinner("Analyzing team dynamics..."):
        if looks_like_champions(pokemon_data) != (config.format_game(fmt_id) == "champions"):
            st.toast(f"This team doesn't look like a {config.FORMATS[fmt_id]['label']} team. Check the format picker.")
        team, team_weakness = readTeam(pokemon_data, fmt_id)
        unknown = [p['Pokemon'] for p in team.values() if not p.get('Type')]
        if unknown:
            st.error(f"Couldn't recognise {', '.join(unknown)}. Check the spelling, or paste a Showdown export.")
            return None
        detectRole(team)
        addComments(team)
        analysis = {
            'team': team,
            'weakness': team_weakness,
            'coverage': coverageCheck(team),
            'suggestions': get_suggestions(team),
        }

    # The id is a hash of format + paste, so the same team always gets the same link
    tid = storage.remember_team(pokemon_data, fmt_id) if config.LOCAL_MODE else storage.team_id(pokemon_data, fmt_id)
    st.session_state.update(
        analysis=analysis, pokemon_data=pokemon_data, default_input=pokemon_data,
        pokemon_names=extract_pokemon_names(pokemon_data), format_id=fmt_id, team_id=tid,
        # Each team keeps its own coach conversation; a new team never inherits the last one's chat
        chat_messages=storage.chat_messages(tid) if config.LOCAL_MODE else [],
    )
    return tid


def open_team(pokemon_data, fmt_id):
    """Analyses a paste and opens it on the Team page as /team?t=<id>, a real history entry Back understands."""
    tid = load_team(pokemon_data, fmt_id)
    if tid:
        st.switch_page(TEAM_PAGE, query_params={"t": tid})


def set_card(name, p):
    """Hover card with a saved Pokemon's set, laid out like a Showdown export."""
    if not p:
        return ""
    head = escape(name) + (f" @ {escape(p['Item'])}" if p.get('Item') else "")
    lines = [f'<b>{head}</b>']
    meta = [f"Ability: {escape(p['Ability'])}"] if p.get('Ability') else []
    if p.get('Tera Type'):
        meta.append(f"Tera: {escape(p['Tera Type'])}")
    if meta:
        lines.append(" · ".join(meta))
    spread = p.get('SP') or p.get('EVs') or {}
    unit = " SP" if p.get('SP') else ""
    evs = " / ".join(f"{v} {k}" for k, v in spread.items() if v)
    nature = f"{escape(p['Nature'])} " if p.get('Nature') else ""
    if nature or evs:
        lines.append(f"{nature}{escape(evs)}{unit}".strip())
    moves = "".join(f"<li>{escape(m['name'])}</li>" for m in p.get('Moves', []))
    return f'<div class="mm-set">{"<br>".join(lines)}<ul>{moves}</ul></div>'


@st.cache_data(show_spinner=False)
def parsed_team(raw_text, fmt_id):
    """Members of a stored paste ({name: set}) for previews; cheap, the dex is local."""
    team, _ = readTeam(raw_text, fmt_id)
    return {p.get('Pokemon'): p for p in team.values()}


def team_tiles(t):
    """Sprite tiles glowing in each member's type colour, with the set on hover, for a stored team."""
    sets = parsed_team(t['raw_text'], t['format'])
    tiles = []
    for name in t['pokemon_names'][:6]:
        p = sets.get(name, {})
        glow = TYPE_MAP.get((p.get('Type') or ['Normal'])[0], {'color': '#00d4ff'})['color']
        sprite = meta_pulse.sprite_urls(name)[0]
        tiles.append(f'<div class="mm-sprite" style="--glow: {glow}" tabindex="0">'
                     f'<img src="{sprite}" alt=""><small>{escape(name)}</small>{set_card(name, p)}</div>')
    return f'<div class="mm-sprites">{"".join(tiles)}</div>'


def paste_help():
    with st.expander("What can I paste?", icon=":material/help:"):
        st.markdown("""
        * A Showdown export, from the **Export** button in the Teambuilder
        * A `pokepast.es` link
        * Nicknames work, for example `Bob (Great Tusk) @ Leftovers`
        * In Champions the `EVs:` line holds stat points, for example `EVs: 32 HP / 32 Def / 2 SpD`
        """)


def team_strip(t):
    """One row of small sprites for a sidebar team card, glowing in each member's type colour."""
    sets = parsed_team(t['raw_text'], t['format'])
    icons = []
    for name in t['pokemon_names'][:6]:
        glow = TYPE_MAP.get((sets.get(name, {}).get('Type') or ['Normal'])[0], {'color': '#00d4ff'})['color']
        icons.append(f'<span class="mm-mini" style="--glow: {glow}" title="{escape(name)}">'
                     f'<img src="{meta_pulse.sprite_urls(name)[0]}" alt="{escape(name)}"></span>')
    return f'<div class="mm-strip">{"".join(icons)}</div>'


def sidebar_rule():
    """A slim divider between sidebar sections (Markdown's --- leaves tall empty gaps)."""
    st.html('<div style="height:1px;margin:2px 0;background:linear-gradient(90deg, rgba(0,212,255,0.35), '
            'rgba(255,255,255,0.06) 60%, transparent)"></div>')


def recent_teams_sidebar(exclude=None):
    """'Pick up where you left off': the last few analysed teams, each a link to its /team page.
    True when it showed anything, so callers only draw a divider between sections that exist."""
    if not config.LOCAL_MODE:
        return False
    recents = [t for t in storage.recent_teams(limit=5) if t['id'] != exclude][:4]
    if not recents:
        return False
    st.markdown("**Pick up where you left off**")
    for t in recents:
        with st.container(border=True, key=f"recent_{t['id']}"):
            st.html(team_strip(t))
            names = t['pokemon_names']
            label = t['name'] or (names[0] + (f" + {len(names) - 1}" if len(names) > 1 else "") if names else "Team")
            with st.container(horizontal=True, vertical_alignment="center", gap="small", key=f"recentrow_{t['id']}"):
                st.page_link(TEAM_PAGE, label=f"{label} · {config.FORMATS.get(t['format'], {}).get('label', '')}",
                             icon=":material/history:", query_params={"t": t['id']}, width="stretch")
                # Saved teams only leave this list; unsaved ones are deleted with their chat
                if st.button("", icon=":material/close:", key=f"forget_{t['id']}", type="tertiary",
                             help="Remove from recent" + (" (stays in Saved teams)" if t['name'] else "")):
                    storage.forget_team(t['id'])
                    st.rerun()
    return True


def render_home_sidebar():
    """Recent teams, saved teams (each opens as a /team link) and paste help."""
    with st.sidebar:
        shown = recent_teams_sidebar()
        saved_teams_data = get_cached_teams() if config.LOCAL_MODE else []
        if saved_teams_data:
            if shown:
                sidebar_rule()
            shown = True
            team_names = [t['name'] for t in saved_teams_data]
            selected_name = st.selectbox("Saved teams", ["Select..."] + team_names)
            selected_team = next((t for t in saved_teams_data if t['name'] == selected_name), None)
            if selected_team:
                st.html(team_tiles(selected_team))
                c1, c2 = st.columns(2)
                with c1:
                    # A link, not a button: opening a saved team is a navigation the browser can go Back from
                    st.page_link(TEAM_PAGE, label="Open", icon=":material/folder_open:",
                                 query_params={"t": selected_team['id']}, width="stretch")
                if c2.button("Delete", icon=":material/delete:", width="stretch"):
                    if storage.delete_team(selected_name):
                        get_cached_teams.clear()
                        st.success(f"Deleted {selected_name}")
                        st.rerun()
        if shown:
            sidebar_rule()
        paste_help()


def render_team_sidebar():
    """Back to Home, recent teams and the save box for the team on screen."""
    with st.sidebar:
        st.page_link(HOME_PAGE, label="Analyze another team", icon=":material/edit_note:", width="stretch")
        # Each section draws its own divider only when it renders, so empty ones never leave a double line
        if config.LOCAL_MODE and [t for t in storage.recent_teams(limit=5) if t['id'] != st.session_state.get("team_id")]:
            sidebar_rule()
            recent_teams_sidebar(exclude=st.session_state.get("team_id"))

        if config.LOCAL_MODE:
            sidebar_rule()
            with st.expander("💾 Save Team", expanded=True):
                saved = storage.get_team(st.session_state.team_id) or {}
                team_name = st.text_input("Team Name:", value=saved.get("name") or "", placeholder="e.g. My Rain Team v1")
                if st.button("💾 Save Team", width="stretch"):
                    if team_name.strip():
                        storage.save_team(team_name.strip(), st.session_state.pokemon_data, st.session_state.format_id)
                        get_cached_teams.clear()
                        st.success(f"Saved '{team_name.strip()}'!")
                    else:
                        st.error("Please enter a name for the team.")


@st.cache_resource
def get_master_strategy_data():
    return strategy_data.ensure_strategy_data()

@st.cache_resource
def get_usage_data():
    return strategy_data.load_usage_stats()


# No st.logo: it forces a sidebar onto every page, and only Home has sidebar content
LOGO_FILE = Path(__file__).parent / "static" / "logo.png"


def render_logo():
    # Served from src/metamatch/static (server.enableStaticServing) and shown as a plain Markdown image:
    # st.image and HTML elements wait for lazily loaded frontend code, which made the logo pop in late
    if LOGO_FILE.exists() and st.get_option("server.enableStaticServing"):
        st.markdown("![MetaMatch logo](app/static/logo.png)")
    elif LOGO_FILE.exists():
        # Run without .streamlit/config.toml (e.g. from another folder): no static serving, so use st.image
        with st.container(horizontal_alignment="center", key="brand_logo"):
            st.image(str(LOGO_FILE), width=210)
    else:
        st.title("MetaMatch", anchor=False)


def _format_changed():
    """Only a user's click writes the URL: any query param write adds a browser history entry,
    and writing during a render would wipe the Forward history."""
    picked = st.session_state.get("format_picker")
    if picked and picked in config.FORMATS:
        st.session_state.format_id = picked
        st.query_params["format"] = picked
        if config.LOCAL_MODE:
            storage.set_pref("format", picked)


def format_picker():
    """The one format picker, shared by Home, Quick Match and Move Search through session state."""
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="center", key="format_row"):
        st.markdown("**Format**")
        st.segmented_control(
            "Format",
            list(config.FORMATS.keys()),
            default=st.session_state.format_id,
            format_func=lambda f: config.FORMATS[f]["label"],
            key="format_picker",
            label_visibility="collapsed",
            width="content",
            on_change=_format_changed,
        )


def _icon(paths):
    """A small cyan line icon as a data URI image (st.html strips inline SVG)."""
    import base64
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" stroke-width="2" '
           f'stroke-linecap="round" stroke-linejoin="round">{paths}</svg>')
    return f'<img alt="" src="data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}">'
HERO_HEAD = """
<style>
.th-row { display:flex; align-items:center; justify-content:space-between; gap:12px 16px; flex-wrap:wrap; margin:2px 0 4px; }
.th-t { font-size:1.35rem; font-weight:700; color:#e8ecf3; letter-spacing:-0.2px; line-height:1.3; }
.th-pills { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.th-lbl { font-size:0.72rem; font-weight:700; letter-spacing:1.6px; text-transform:uppercase; color:#7f8aa0; }
.th-pill { display:inline-flex; align-items:center; gap:6px; padding:4px 11px 4px 9px; border-radius:999px;
  font-size:0.8rem; font-weight:600; color:#bdefff; background:rgba(0,212,255,0.08);
  border:1px solid rgba(0,212,255,0.32); box-shadow:inset 0 1px 0 rgba(255,255,255,0.04); white-space:nowrap; }
.th-pill img { width:14px; height:14px; flex-shrink:0; }
@media (max-width: 520px) { .th-lbl { display:none; } }
</style>
<div class="th-row"><div class="th-t">Paste your team to get the full dashboard</div>
<div class="th-pills"><span class="th-lbl">Accepts</span>
<span class="th-pill">""" + _icon('<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14'
                                   'a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M8 12h8M8 16h5"/>') + \
    """Showdown export</span>
<span class="th-pill">""" + _icon('<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>'
                                   '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>') + \
    """PokéPaste link</span></div></div>
"""


def home_page():
    render_home_sidebar()
    render_logo()
    # Start screen: the team input is the hero, this month's MetaFlash sits under it; recent teams live in the sidebar
    format_picker()
    with st.container(border=True, key="team_hero"):
        st.html(HERO_HEAD)
        with st.form("team_form", border=False):
            pokemon_data = st.text_area(
                "Team",
                value=st.session_state.default_input,
                placeholder="Paste a Showdown export or a pokepast.es link\n\nGholdengo @ Choice Scarf\nAbility: Good as Gold\n...",
                height=220,
                label_visibility="collapsed",
            )
            with st.container(horizontal=True, vertical_alignment="center"):
                analyze_clicked = st.form_submit_button("Analyze team", type="primary", icon=":material/insights:")
                sample_clicked = st.form_submit_button("Try a sample team", icon=":material/science:")
                st.caption("Damage calcs, threats, speed tiers and the coach chat, all from one paste.")

        if sample_clicked:
            open_team(SAMPLE_TEAM, "gen9ou")
        elif analyze_clicked:
            if pokemon_data.strip():
                open_team(pokemon_data, st.session_state.format_id)
            else:
                st.warning("Paste a team first, or try the sample team.")

    # MetaFlash: this month's featured story, top 10 and movers on the ladder
    tab_meta_pulse.render(st.session_state.format_id, TYPE_MAP)


def team_empty_state(message):
    page_header("Your team", "Team Dashboard")
    st.info(message)
    st.page_link(HOME_PAGE, label="Paste a team on Home", icon=":material/home:")


def team_page():
    """The dashboard for the team in session, or the one named by ?t=<id> (refresh, bookmark, second tab)."""
    linked = st.query_params.get("t")
    if linked and st.session_state.get("team_id") != linked:
        stored = storage.get_team(linked) if config.LOCAL_MODE else None
        if not stored:
            team_empty_state("That team isn't saved on this machine. Paste it on Home to analyse it again.")
            return
        if not load_team(stored['raw_text'], stored['format']):
            return
    if not st.session_state.get("analysis") or not st.session_state.get("pokemon_names"):
        team_empty_state("No team yet. Paste a Showdown export on Home to build the dashboard.")
        return

    render_team_sidebar()

    coverage = st.session_state.analysis['coverage']
    weakness = st.session_state.analysis['weakness']
    team_data = st.session_state.analysis['team']
    # The team banner: archetype and jobs, one card per Pokemon with its set, and the team's numbers this month
    saved = (storage.get_team(st.session_state.get("team_id")) or {}) if config.LOCAL_MODE else {}
    tab_banner.render(team_data, coverage, weakness, TYPE_MAP, team_name=saved.get("name"))
    st.markdown("---")

    # --- Detailed Analysis Tabs ---
    section_header("Go deeper", "Detailed Analysis")
    # Only the open tab runs: the Threat Board, Team Completer and Speed Tiers each run the damage calc,
    # and hidden tabs would otherwise compute on every load
    (tab_overview, tab3, tab4, tab_rec, tab_matrix, tab7, tab8, tab_chat) = st.tabs([
        "Team Overview", "Audit", "Threat Board", "Recommendations", "Matchup Matrices", "Speed Tiers",
        "Coach Guide", "Coach Chat"
    ], on_change="rerun", key="dashboard_tab")
    tabs = [
        (tab_overview, lambda: tab_overview_mod.render(coverage, weakness, team_data, TYPE_MAP)),
        (tab3, tab_audit.render),
        (tab4, lambda: tab_threats.render(team_data)),
        (tab_rec, lambda: tab_recommender_mod.render(team_data, st.session_state.pokemon_names)),
        (tab_matrix, lambda: tab_matrix_mod.render(team_data, TYPE_MAP)),
        (tab7, lambda: tab_speed_tiers.render(team_data, TYPE_MAP)),
        (tab8, lambda: tab_coach_guide.render(TYPE_MAP)),
        (tab_chat, tab_chat_mod.render),
    ]
    for tab, draw in tabs:
        if tab.open:
            with tab:
                draw()


def quick_match_page():
    page_header("Team building", "Quick Match", "No team yet? Pick a core and get the partners that pair best with it on the ladder.",
                st.session_state.get("format_id"))
    format_picker()
    tab_quick_match.render(get_master_strategy_data)


def move_search_page():
    page_header("Research", "Move Search", "Find sets that run a combination of moves, from the Strategy Dex and ladder usage.",
                st.session_state.get("format_id"))
    format_picker()
    tab_move_search.render(get_master_strategy_data, get_usage_data, TYPE_MAP)


def spread_lab_page():
    page_header("Team building", "Spread Lab", "The smallest spread that hits every benchmark you need, checked by the damage calculator.",
                st.session_state.get("format_id"))
    format_picker()
    tab_spread_lab.render((st.session_state.get("analysis") or {}).get("team"))


def matchup_preview_page():
    page_header("Before the battle", "Matchup Preview",
                "Your team against the one you're about to face, every matchup worked out by the damage calculator.",
                st.session_state.get("format_id"))
    team = (st.session_state.get("analysis") or {}).get("team")
    if not team:
        format_picker()
    tab_preview.render(team, sample_team=SAMPLE_TEAM)


def replay_page():
    page_header("After the battle", "Replay Auditor", "Paste a Showdown replay for a turn by turn review of your battle.")
    tab_replay.render()


# Team is always routable (so /team?t=<id> links work in a fresh session) but only shows in the bar once a team is open
HOME_PAGE = st.Page(home_page, title="Home", icon=":material/home:", default=True)
TEAM_PAGE = st.Page(team_page, title="Team", icon=":material/insights:", url_path="team",
                    visibility="visible" if st.session_state.get("analysis") else "hidden")
nav = st.navigation([
    HOME_PAGE,
    TEAM_PAGE,
    st.Page(quick_match_page, title="Quick Match", icon=":material/group_add:", url_path="quick-match"),
    st.Page(move_search_page, title="Move Search", icon=":material/search:", url_path="move-search"),
    st.Page(spread_lab_page, title="Spread Lab", icon=":material/tune:", url_path="spread-lab"),
    st.Page(matchup_preview_page, title="Matchup Preview", icon=":material/swords:", url_path="matchup-preview"),
    st.Page(replay_page, title="Replay Auditor", icon=":material/smart_display:", url_path="replay-auditor"),
], position="top")
nav.run()
