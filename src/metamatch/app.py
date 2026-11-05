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

from metamatch.utils import pokeSlugify, is_pokepaste_url, fetch_pokepaste, extract_pokemon_names, get_pokemon_sprite
from metamatch.team import readTeam, detectRole, addComments, coverageCheck, looks_like_champions
from metamatch.suggestions import get_suggestions
from metamatch.scrapers import generate_speed_tiers
from metamatch import config
from metamatch import storage
from metamatch import auditor
from metamatch import strategy_data
from metamatch.tabs import (
    tab_quick_match, tab_move_search, tab_replay,
    tab_overview as tab_overview_mod, tab_audit, tab_threats,
    tab_coach_guide, tab_recommender as tab_recommender_mod, tab_matrix as tab_matrix_mod,
    tab_speed_tiers, tab_chat as tab_chat_mod, tab_meta_pulse,
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

    /* Sidebar Glassmorphism */
    [data-testid="stSidebar"] { background: rgba(255, 255, 255, 0.02) !important; backdrop-filter: blur(20px); border-right: 1px solid rgba(255, 255, 255, 0.05); }
    [data-testid="stSidebar"] .stMarkdown h1, [data-testid="stSidebar"] .stMarkdown h2 { color: #00d4ff; text-shadow: 0 0 10px rgba(0, 212, 255, 0.3); }

    /* Metrics Glowing Style */
    div[data-testid="stMetric"] { background: rgba(255, 255, 255, 0.03); padding: 15px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.05); box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
    div[data-testid="stMetricValue"] { font-family: 'Inter', sans-serif; font-weight: 800 !important; color: #fff !important; text-shadow: 0 0 15px rgba(255,255,255,0.2); font-size: clamp(1.4rem, 2.2vw, 2.1rem) !important; }
    div[data-testid="stMetricLabel"] { color: #888 !important; text-transform: uppercase; letter-spacing: 1px; font-size: 0.75rem !important; }

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

# Initialize Session State
if 'submitted' not in st.session_state:
    st.session_state.submitted = False
if 'pokemon_names' not in st.session_state:
    st.session_state.pokemon_names = []
if 'default_input' not in st.session_state:
    st.session_state.default_input = ""
if 'chat_messages' not in st.session_state:
    st.session_state.chat_messages = []
if 'format_id' not in st.session_state:
    st.session_state.format_id = config.DEFAULT_FORMAT

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


def analyze_team(pokemon_data, fmt_id):
    """Parses and analyses a pasted team (or pokepast.es link) and opens the dashboard."""
    if is_pokepaste_url(pokemon_data):
        with st.spinner("Fetching team from pokepast.es..."):
            fetched = fetch_pokepaste(pokemon_data)
        if not fetched:
            st.error("Couldn't fetch that pokepast.es link. Check the URL and try again.")
            return
        pokemon_data = fetched
        st.toast("Loaded team from pokepast.es")

    st.session_state.pokemon_data = pokemon_data
    st.session_state.default_input = pokemon_data
    st.session_state.pokemon_names = extract_pokemon_names(pokemon_data)

    with st.spinner("Analyzing team dynamics..."):
        if looks_like_champions(pokemon_data) != (config.format_game(fmt_id) == "champions"):
            st.toast(f"This team doesn't look like a {config.FORMATS[fmt_id]['label']} team. Check the format picker.")
        team, team_weakness = readTeam(pokemon_data, fmt_id)
        unknown = [p['Pokemon'] for p in team.values() if not p.get('Type')]
        if unknown:
            st.error(f"Couldn't recognise {', '.join(unknown)}. Check the spelling, or paste a Showdown export.")
            return
        detectRole(team)
        addComments(team)
        st.session_state.analysis = {
            'team': team,
            'weakness': team_weakness,
            'coverage': coverageCheck(team),
            'suggestions': get_suggestions(team),
            'guide': None,  # written on demand in the Coach Guide tab, it's a slow LLM call
        }
    st.session_state.submitted = True
    st.rerun()


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


def render_sidebar():
    """Saved teams, the meta audit and save box for the analysed team, and paste help (Home only)."""
    with st.sidebar:
        if st.session_state.submitted:
            if st.button("Analyze another team", icon=":material/edit_note:", width="stretch"):
                st.session_state.submitted = False
                st.rerun()

        saved_teams_data = get_cached_teams()
        if saved_teams_data:
            if st.session_state.submitted:
                st.markdown("---")
            team_names = [t['name'] for t in saved_teams_data]
            selected_name = st.selectbox("Saved teams", ["Select..."] + team_names)

            if selected_name != "Select...":
                selected_team = next((t for t in saved_teams_data if t['name'] == selected_name), None)

                if selected_team:
                    pk_list = selected_team.get('pokemon_names', [])
                    if pk_list:
                        # Sprites glow in each member's main type colour, like the squad cards
                        saved_team = (selected_team.get('analysis') or {}).get('team', {})
                        sets = {p.get('Pokemon'): p for p in saved_team.values()}
                        tiles = []
                        for name in pk_list[:6]:
                            p = sets.get(name, {})
                            glow = TYPE_MAP.get((p.get('Type') or ['Normal'])[0], {'color': '#00d4ff'})['color']
                            sprite = get_pokemon_sprite(name)
                            art = f'<img src="{sprite}" alt="">' if sprite else '<span class="mm-sprite-missing">?</span>'
                            tiles.append(f'<div class="mm-sprite" style="--glow: {glow}" tabindex="0">'
                                         f'{art}<small>{escape(name)}</small>{set_card(name, p)}</div>')
                        st.html(f'<div class="mm-sprites">{"".join(tiles)}</div>')

                    c1, c2 = st.columns(2)
                    if c1.button("Load", icon=":material/folder_open:", width="stretch"):
                        st.session_state.default_input = selected_team['raw_text']
                        if selected_team.get('analysis'):
                            st.session_state.analysis = selected_team['analysis']
                            st.session_state.pokemon_data = selected_team['raw_text']
                            st.session_state.pokemon_names = extract_pokemon_names(selected_team['raw_text'])
                            st.session_state.submitted = True
                        st.rerun()
                    if c2.button("Delete", icon=":material/delete:", width="stretch"):
                        if storage.delete_team(selected_name):
                            get_cached_teams.clear()
                            st.success(f"Deleted {selected_name}")
                            st.rerun()

        if st.session_state.submitted:
            # --- Meta Auditor ---
            audit_results = auditor.audit_team(st.session_state.analysis['team'])
            audit_warnings = audit_results.get("warnings", [])
            if audit_warnings:
                st.markdown("---")
                with st.expander(f"⚠️ Meta Audit ({len(audit_warnings)} Warnings)", expanded=True):
                    st.caption("We detected some statistically unusual choices compared to the current high-ladder meta.")
                    for w in audit_warnings:
                        st.markdown(f"""
                        <div style="background: rgba(255, 165, 0, 0.1); border-left: 4px solid #ffa500; padding: 10px; margin-bottom: 8px; border-radius: 4px;">
                            <div style="font-weight: bold; color: #ffa500;">{escape(str(w['pokemon']))} - {escape(str(w['category']))}</div>
                            <div style="font-size: 0.9rem;">
                                You are running <b>{escape(str(w['current']))}</b> (Used by only {w['usage']:.1f}%).<br>
                                <span style="opacity: 0.8;">Standard: {escape(str(w['suggestion']))}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

            st.markdown("---")
            with st.expander("💾 Save Analysis", expanded=True):
                team_name = st.text_input("Team Name:", placeholder="e.g. My Rain Team v1")
                if st.button("💾 Save Current Analysis", width="stretch"):
                    if team_name:
                        storage.save_team(team_name, st.session_state.pokemon_data, st.session_state.analysis)
                        get_cached_teams.clear()
                        st.success(f"Saved '{team_name}'!")
                        st.rerun()
                    else:
                        st.error("Please enter a name for the team.")

        st.markdown("---")
        with st.expander("What can I paste?", icon=":material/help:"):
            st.markdown("""
            * A Showdown export, from the **Export** button in the Teambuilder
            * A `pokepast.es` link
            * Nicknames work, for example `Bob (Great Tusk) @ Leftovers`
            * In Champions the `EVs:` line holds stat points, for example `EVs: 32 HP / 32 Def / 2 SpD`
            """)


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


def format_picker():
    """The one format picker, shared by Home, Quick Match and Move Search through session state."""
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="center", key="format_row"):
        st.markdown("**Format**")
        format_ids = list(config.FORMATS.keys())
        picked = st.segmented_control(
            "Format",
            format_ids,
            default=st.session_state.format_id,
            format_func=lambda f: config.FORMATS[f]["label"],
            key="format_picker",
            label_visibility="collapsed",
            width="content",
        )
        st.session_state.format_id = picked or st.session_state.format_id


def page_header(title, blurb):
    st.markdown(f"## {title}")
    st.caption(blurb)


def home_page():
    render_sidebar()
    render_logo()
    if not st.session_state.submitted:
        # Start screen: the team input is the hero, this month's Meta Pulse sits under it
        format_picker()
        with st.container(border=True, key="team_hero"):
            st.markdown("#### Paste your team to get the full dashboard")
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
                st.session_state.format_id = "gen9ou"
                analyze_team(SAMPLE_TEAM, "gen9ou")
            elif analyze_clicked:
                if pokemon_data.strip():
                    analyze_team(pokemon_data, st.session_state.format_id)
                else:
                    st.warning("Paste a team first, or try the sample team.")

        # This month's Meta Pulse: a swipeable strip of what's moving on the ladder
        tab_meta_pulse.render(st.session_state.format_id, TYPE_MAP)

    if st.session_state.submitted and st.session_state.pokemon_names:

        # --- Metrics Dashboard ---
        st.markdown("## 📊 Team Dashboard")

        coverage = st.session_state.analysis['coverage']
        weakness = st.session_state.analysis['weakness']
        team_data = st.session_state.analysis['team']

        covered_count = sum(1 for v in coverage.values() if v)
        most_weak_type = max(weakness.items(), key=lambda x: x[1]['weak'])

        roles = []
        for p in team_data.values():
            roles.extend(p['Roles'])

        archetype = "Balanced"
        arch_icon = "⚖️"

        # Count Pokemon, not role labels: one mon can be both a Wall and a Tank
        mon_roles = [set(p.get("Roles", [])) for p in team_data.values() if isinstance(p, dict)]
        wall_tank_count = sum(1 for r in mon_roles if r & {"Wall", "Tank"})
        sweeper_count = sum(1 for r in mon_roles if any("Sweeper" in x or "Breaker" in x for x in r))
        weather_count = roles.count("Weather Setter") + roles.count("Weather Abuser")
        setter_count = roles.count("Weather Setter")
        pivot_count = roles.count("Pivot")
        tr_count = roles.count("Trick Room Setter")
        bulky_offense_count = sum(1 for r in mon_roles if r & {"Bulky Attacker", "Tank"})

        if tr_count >= 1:
            archetype = "Trick Room"
            arch_icon = "🌀"
        elif setter_count >= 1 and weather_count >= 2:
            archetype = "Weather Offense"
            arch_icon = "🌦️"
        elif pivot_count >= 3:
            archetype = "Volt-Turn / Pivot"
            arch_icon = "🔄"
        elif wall_tank_count >= 4: # Increased threshold for pure stall
            archetype = "Stall"
            arch_icon = "🐢"
        elif sweeper_count >= 4:
            archetype = "Hyper Offense"
            arch_icon = "⚔️"
        elif bulky_offense_count >= 3:
            archetype = "Bulky Offense"
            arch_icon = "🛡️⚔️"

        m1, m2, m3 = st.columns(3)
        m1.metric("Archetype", f"{arch_icon} {archetype}")
        with m2:
            st.metric("Type Coverage", f"{covered_count}/18")
            st.progress(covered_count / 18)

        weak_type_name = most_weak_type[0].capitalize()
        t_info_m = TYPE_MAP.get(weak_type_name, {'color': '#777', 'icon': '❓'})
        weak_label = f"{t_info_m['icon']} {weak_type_name}"

        if most_weak_type[1]['weak'] >= 3:
            m3.metric("Critical Weakness", weak_label, f"-{most_weak_type[1]['weak']} Mons", delta_color="normal")
        else:
            m3.metric("Top Weakness", weak_label, f"-{most_weak_type[1]['weak']} Mons", delta_color="off")

        # --- Squad Section ---
        st.markdown("## 🦸 Your Squad")
        st.markdown("<br>", unsafe_allow_html=True) # Spacer
        names = st.session_state.pokemon_names

        for i in range(0, len(names), 3):
            cols = st.columns(3)
            batch = names[i:i+3]
            for j, name in enumerate(batch):
                idx = i + j
                # Handle potential key mismatch (int vs string) from JSON loading
                poke = team_data.get(idx) or team_data.get(str(idx))
                if not poke: continue

                # Get Type Color for Glow
                primary_type = poke['Type'][0] if poke['Type'] else 'Normal'
                type_color = TYPE_MAP.get(primary_type, {'color': '#777'})['color']

                # Construct Glassmorphism Card HTML
                card_html = f"""
                <div class="pokemon-card" style="border: 1px solid {type_color}44; box-shadow: 0 0 15px -5px {type_color}, inset 0 0 20px -15px {type_color};">
                    <div style="display: flex; align-items: center; gap: 15px;">
                        <div style="flex-shrink: 0; position: relative;">
                            <div style="position: absolute; width: 60px; height: 60px; background: {type_color}; filter: blur(30px); opacity: 0.4; z-index: 0; top: 10px; left: 10px;"></div>
                            <img src="{get_pokemon_sprite(name) or ''}" width="90" style="position: relative; z-index: 1; filter: drop-shadow(0 0 5px rgba(0,0,0,0.5));">
                        </div>
                        <div style="flex-grow: 1;">
                            <div class="poke-name">{escape(name)}</div>
                            <div style="display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 8px;">
                                {''.join([f'<span style="background:{TYPE_MAP.get(t, {}).get("color", "#555")}; color:white; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; text-shadow: 0 1px 2px rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.2);">{TYPE_MAP.get(t, {}).get("icon", "")} {t}</span>' for t in poke['Type']])}
                            </div>
                        </div>
                    </div>
                    <div style="margin-top: 15px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 12px;">
                        <div class="stat-text" style="margin-bottom: 6px;">
                            {' '.join([f'<span class="role-badge">🛡️ {escape(r)}</span>' for r in poke['Roles'][:3]]) if poke['Roles'] else '<span style="opacity:0.5; font-size:0.8rem">No specific roles</span>'}
                        </div>
                        <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: #ddd; margin-top: 8px;">
                            <span>🎒 {escape(str(poke['Item']))}</span>
                            <span style="opacity: 0.8;">✨ {escape(str(poke['Ability']))}</span>
                        </div>
                         <div class="stat-text" style="font-size: 0.75rem; margin-top:8px; color: {type_color}; opacity: 0.9; font-family: monospace;">
                            {escape(str(poke['Nature']))} Nature • {', '.join([f'{v} {k}' for k, v in sorted((poke.get('SP') or poke['EVs']).items(), key=lambda x: x[1], reverse=True)[:2]])}
                         </div>
                    </div>
                </div>
                """

                with cols[j]:
                    st.markdown(card_html, unsafe_allow_html=True)
        st.markdown("---")

        # --- Detailed Analysis Tabs ---
        st.header("Detailed Analysis")
        tab_overview, tab3, tab4, tab8, tab_rec, tab_matrix, tab7, tab_chat = st.tabs([
            "Team Overview", "Audit", "Meta Threats", "Coach Guide", "Recommendations", "Matchup Matrices", "Speed Tiers", "Coach Chat"
        ])

        with tab_chat:
            tab_chat_mod.render()

        with tab_overview:
            tab_overview_mod.render(coverage, weakness, team_data, TYPE_MAP)

        with tab3:
            tab_audit.render()

        with tab4:
            tab_threats.render()

        with tab8:
            tab_coach_guide.render()

        with tab_rec:
            tab_recommender_mod.render(team_data, st.session_state.pokemon_names)

        with tab_matrix:
            tab_matrix_mod.render(team_data)

        with tab7:
            tab_speed_tiers.render(team_data)


def quick_match_page():
    page_header("🤝 Quick Match", "No team yet? Pick a core and get the partners that pair best with it on the ladder.")
    format_picker()
    tab_quick_match.render(get_master_strategy_data)


def move_search_page():
    page_header("🔎 Move Search", "Find sets that run a combination of moves, from the Strategy Dex and ladder usage.")
    format_picker()
    tab_move_search.render(get_master_strategy_data, get_usage_data)


def replay_page():
    page_header("📼 Replay Auditor", "Paste a Showdown replay for a turn by turn post mortem of your battle.")
    tab_replay.render()


nav = st.navigation([
    st.Page(home_page, title="Home", icon=":material/home:", default=True),
    st.Page(quick_match_page, title="Quick Match", icon=":material/group_add:", url_path="quick-match"),
    st.Page(move_search_page, title="Move Search", icon=":material/search:", url_path="move-search"),
    st.Page(replay_page, title="Replay Auditor", icon=":material/smart_display:", url_path="replay-auditor"),
], position="top")
nav.run()
