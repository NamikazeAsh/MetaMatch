import os
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
from metamatch.suggestions import get_suggestions, get_team_guide
from metamatch.scrapers import generate_speed_tiers
from metamatch import config
from metamatch import storage
from metamatch import auditor
from metamatch import strategy_data
from metamatch.tabs import (
    tab_quick_match, tab_move_search, tab_replay,
    tab_overview as tab_overview_mod, tab_audit, tab_threats,
    tab_coach_guide, tab_recommender as tab_recommender_mod, tab_matrix as tab_matrix_mod,
    tab_speed_tiers, tab_chat as tab_chat_mod,
)

st.set_page_config(page_title="MetaMatch", page_icon="⚪", layout="wide")

# --- Global CSS ---
st.markdown(r'''
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap');

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
    div[data-testid="stMetricValue"] { font-family: 'Inter', sans-serif; font-weight: 800 !important; color: #fff !important; text-shadow: 0 0 15px rgba(255,255,255,0.2); }
    div[data-testid="stMetricLabel"] { color: #888 !important; text-transform: uppercase; letter-spacing: 1px; font-size: 0.75rem !important; }

    /* Glass Buttons */
    .stButton > button { background: rgba(0, 212, 255, 0.1) !important; color: #00d4ff !important; border: 1px solid #00d4ff !important; backdrop-filter: blur(5px); border-radius: 8px !important; font-weight: 600 !important; transition: all 0.3s ease !important; width: 100%; }
    .stButton > button:hover { background: rgba(0, 212, 255, 0.2) !important; box-shadow: 0 0 20px rgba(0, 212, 255, 0.4) !important; transform: scale(1.02); }

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
''', unsafe_allow_html=True)

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

# --- Sidebar: Input & Controls ---
with st.sidebar:
    st.header("📂 Saved Teams")
    saved_teams_data = get_cached_teams()
    if saved_teams_data:
        team_names = [t['name'] for t in saved_teams_data]
        selected_name = st.selectbox("Load a saved team:", ["Select..."] + team_names)

        if selected_name != "Select...":
            selected_team = next((t for t in saved_teams_data if t['name'] == selected_name), None)

            if selected_team:
                # Render Preview
                pk_list = selected_team.get('pokemon_names', [])
                if pk_list:
                    preview_html = '<div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 10px; margin-bottom: 10px;">'
                    preview_html += '<div style="font-size: 0.7rem; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Squad Preview</div>'
                    preview_html += '<div style="display: flex; flex-wrap: wrap; gap: 4px;">'
                    for pk in pk_list[:6]:
                        preview_html += f'<span style="background: rgba(0, 212, 255, 0.1); border: 1px solid rgba(0, 212, 255, 0.2); color: #00d4ff; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600;">{pk}</span>'
                    preview_html += '</div></div>'
                    st.markdown(preview_html, unsafe_allow_html=True)

                c1, c2 = st.columns(2)
                if c1.button("📂 Load", use_container_width=True):
                    st.session_state.default_input = selected_team['raw_text']
                    if selected_team.get('analysis'):
                        st.session_state.analysis = selected_team['analysis']
                        st.session_state.pokemon_names = extract_pokemon_names(selected_team['raw_text'])
                        st.session_state.submitted = True
                    st.rerun()
                if c2.button("🗑️ Delete", use_container_width=True):
                    if storage.delete_team(selected_name):
                        get_cached_teams.clear() # Clear cache
                        st.success(f"Deleted {selected_name}")
                        st.rerun()
    else:
        st.info("No saved teams yet.")

    st.markdown("---")
    st.header("📋 Team Input")

    # Format drives which usage stats and mechanics (SV EVs/Tera vs Champions stat points/Megas) are used
    format_ids = list(config.FORMATS.keys())
    st.session_state.format_id = st.selectbox(
        "Format:",
        format_ids,
        index=format_ids.index(st.session_state.format_id),
        format_func=lambda f: config.FORMATS[f]["label"],
    )

    with st.form("pokemon_form"):
        pokemon_data = st.text_area(
            "Paste Showdown Export or pokepast.es link:",
            value=st.session_state.default_input,
            placeholder="Pikachu @ Light Ball...\n\nOR paste a pokepast.es link",
            height=400,
            help="Paste your team from Pokemon Showdown or a pokepast.es URL."
        )

        submit_button = st.form_submit_button("Analyze Team", type="primary")

        if submit_button and pokemon_data:
            # Auto-detect pokepast.es URLs and fetch
            if is_pokepaste_url(pokemon_data):
                with st.spinner("Fetching team from pokepast.es..."):
                    fetched = fetch_pokepaste(pokemon_data)
                    if fetched:
                        pokemon_data = fetched
                        st.toast("✅ Loaded team from pokepast.es!")
                    else:
                        st.error("Failed to fetch from pokepast.es. Check the URL.")
                        st.stop()

            st.session_state.pokemon_data = pokemon_data
            st.session_state.pokemon_names = extract_pokemon_names(pokemon_data)

            with st.spinner("Analyzing team dynamics..."):
                fmt_id = st.session_state.format_id
                if looks_like_champions(pokemon_data) != (config.format_game(fmt_id) == "champions"):
                    st.toast(f"⚠️ This team doesn't look like a {config.FORMATS[fmt_id]['label']} team. Check the Format picker.")
                team, team_weakness = readTeam(pokemon_data, fmt_id)
                detectRole(team)
                addComments(team)
                coverage = coverageCheck(team)
                suggestions = get_suggestions(team)
                guide = get_team_guide(team)

                st.session_state.analysis = {
                    'team': team,
                    'weakness': team_weakness,
                    'coverage': coverage,
                    'suggestions': suggestions,
                    'guide': guide
                }
                st.session_state.submitted = True
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
                        <div style="font-weight: bold; color: #ffa500;">{w['pokemon']} - {w['category']}</div>
                        <div style="font-size: 0.9rem;">
                            You are running <b>{w['current']}</b> (Used by only {w['usage']:.1f}%).<br>
                            <span style="opacity: 0.8;">Standard: {w['suggestion']}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        st.markdown("---")
        with st.expander("💾 Save Analysis", expanded=True):
            team_name = st.text_input("Team Name:", placeholder="e.g. My Rain Team v1")
            if st.button("💾 Save Current Analysis", use_container_width=True):
                if team_name:
                    storage.save_team(team_name, st.session_state.pokemon_data, st.session_state.analysis)
                    get_cached_teams.clear() # Clear cache
                    st.success(f"Saved '{team_name}'!")
                    st.rerun()
                else:
                    st.error("Please enter a name for the team.")

    with st.expander("ℹ️ Supported Formats"):
        st.markdown("""
        MetaMatch supports the standard **Pokémon Showdown Export** format.
        You can copy your team directly from the 'Export' button in the Showdown Teambuilder.

        **Recognized Fields:**
        - `Pokemon @ Item` (Optional item)
        - `Ability: Name`
        - `Tera Type: Type` (SV only)
        - `EVs: 252 HP / 252 Def` (in Champions this line holds stat points, e.g. `EVs: 32 HP / 32 Def / 2 SpD`)
        - `Nature Name Nature` (e.g., *Adamant Nature*)
        - `- Move Name` (Starting with a hyphen)

        *Note: Nicknames are currently not supported. Please use the species name directly.*
        """)
        st.code("""
Rotom-Wash @ Leftovers
Ability: Levitate
Tera Type: Steel
EVs: 252 HP / 252 Def / 4 SpD
Bold Nature
- Volt Switch
- Hydro Pump
- Will-O-Wisp
- Pain Split
        """, language="text")

@st.cache_resource
def get_master_strategy_data():
    return strategy_data.ensure_strategy_data()

@st.cache_resource
def get_usage_data():
    return strategy_data.load_usage_stats()

# --- Main UI Layout ---
col1, col2, col3 = st.columns([2, 1, 2])
with col2:
    logo_path = config.IMAGES_DIR / "dark_logo_transp.png"
    if logo_path.exists():
        st.image(str(logo_path), width=350)
    else:
        st.title("MetaMatch")

if not st.session_state.submitted:
    tool_tab1, tool_tab2, tool_tab3 = st.tabs(["🤝 Quick Match", "🔎 Move Search", "📼 Replay Auditor"])

    with tool_tab1:
        tab_quick_match.render(get_master_strategy_data)

    with tool_tab2:
        tab_move_search.render(get_master_strategy_data, get_usage_data)

    with tool_tab3:
        tab_replay.render()

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

    wall_tank_count = roles.count("Wall") + roles.count("Tank")
    sweeper_count = sum(1 for r in roles if "Sweeper" in r or "Breaker" in r)
    weather_count = roles.count("Weather Setter") + roles.count("Weather Abuser")
    pivot_count = roles.count("Pivot")
    tr_count = roles.count("Trick Room Setter")
    bulky_offense_count = roles.count("Bulky Attacker") + roles.count("Tank")

    if tr_count >= 1:
        archetype = "Trick Room"
        arch_icon = "🌀"
    elif weather_count >= 2:
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
        m3.metric("Critical Weakness", weak_label, f"-{most_weak_type[1]['weak']} Mons", delta_color="inverse")
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
                        <div class="poke-name">{name}</div>
                        <div style="display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 8px;">
                            {''.join([f'<span style="background:{TYPE_MAP.get(t, {}).get("color", "#555")}; color:white; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; text-shadow: 0 1px 2px rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.2);">{TYPE_MAP.get(t, {}).get("icon", "")} {t}</span>' for t in poke['Type']])}
                        </div>
                    </div>
                </div>
                <div style="margin-top: 15px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 12px;">
                    <div class="stat-text" style="margin-bottom: 6px;">
                        {' '.join([f'<span class="role-badge">🛡️ {r}</span>' for r in poke['Roles'][:3]]) if poke['Roles'] else '<span style="opacity:0.5; font-size:0.8rem">No specific roles</span>'}
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: #ddd; margin-top: 8px;">
                        <span>🎒 {poke['Item']}</span>
                        <span style="opacity: 0.8;">✨ {poke['Ability']}</span>
                    </div>
                     <div class="stat-text" style="font-size: 0.75rem; margin-top:8px; color: {type_color}; opacity: 0.9; font-family: monospace;">
                        {poke['Nature']} Nature • {', '.join([f'{v} {k}' for k, v in sorted((poke.get('SP') or poke['EVs']).items(), key=lambda x: x[1], reverse=True)[:2]])}
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
