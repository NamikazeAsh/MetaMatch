import streamlit as st
import re
import requests
import json
import pandas as pd
import altair as alt
from PIL import Image
from io import BytesIO
import sys
from pathlib import Path

# Fix path to allow importing from the metamatch package
# Adds the 'src' directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from metamatch.utils import pokeSlugify
from metamatch.team import readTeam, detectRole, addComments, coverageCheck
from metamatch.suggestions import get_suggestions, get_team_guide, get_chat_response
from metamatch.scrapers import generate_speed_tiers
from metamatch.type_chart import get_multiplier
from metamatch import config
from metamatch import storage
from metamatch import recommender
from metamatch import auditor

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

# --- Helper Functions ---
def extract_pokemon_names(raw_data):
    names = []
    lines = raw_data.split('\n')
    for line in lines:
        line = line.strip()
        if not line: continue
        if '@' in line:
            raw_name = line.split('@')[0].strip()
            # Remove gender like (M), (F), (m), (f)
            clean_name = re.sub(r'\s*\([MFmf]\)$', '', raw_name)
            if clean_name and clean_name not in names:
                names.append(clean_name)
    return names

def get_pokemon_sprite(name):
    try:
        slugified_name = pokeSlugify(name)
        url = f"https://pokeapi.co/api/v2/pokemon/{slugified_name}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            sprite_url = data['sprites']['front_default']
            if sprite_url: return sprite_url
    except:
        pass
    return None

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
                if c1.button("📂 Load", use_container_width=True, key="load_btn"):
                    st.session_state.default_input = selected_team['raw_text']
                    if selected_team.get('analysis'):
                        st.session_state.analysis = selected_team['analysis']
                        st.session_state.pokemon_names = extract_pokemon_names(selected_team['raw_text'])
                        st.session_state.submitted = True
                    st.rerun()
                if c2.button("🗑️ Delete", use_container_width=True, key="del_btn"):
                    if storage.delete_team(selected_name):
                        get_cached_teams.clear() # Clear cache
                        st.success(f"Deleted {selected_name}")
                        st.rerun()
    else:
        st.info("No saved teams yet.")
    
    st.markdown("---")
    st.header("📋 Team Input")
    
    # Default Presets
    debug_team_balanced = """
Rotom-Wash @ Leftovers
Ability: Levitate
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Volt Switch
- Hydro Pump
- Will-O-Wisp
- Pain Split

Garchomp @ Rocky Helmet
Ability: Rough Skin
Tera Type: Steel
EVs: 252 HP / 4 Def / 252 Spe
Jolly Nature
- Stealth Rock
- Earthquake
- Dragon Tail
- Spikes

Kingambit @ Black Glasses
Ability: Supreme Overlord
Tera Type: Dark
EVs: 252 Atk / 4 SpD / 252 Spe
Adamant Nature
- Swords Dance
- Kowtow Cleave
- Iron Head
- Sucker Punch

Iron Valiant @ Booster Energy
Ability: Quark Drive
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Close Combat
- Thunderbolt
- Encore

Heatran @ Air Balloon
Ability: Flash Fire
Tera Type: Grass
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Magma Storm
- Earth Power
- Taunt
- Stealth Rock

Rillaboom @ Choice Band
Ability: Grassy Surge
Tera Type: Grass
EVs: 252 Atk / 4 Def / 252 Spe
Adamant Nature
- Grassy Glide
- Wood Hammer
- Knock Off
- U-turn"""

    debug_team_rain = """
Pelipper @ Damp Rock
Ability: Drizzle
EVs: 248 HP / 252 Def / 8 SpD
Bold Nature
- Surf
- Hurricane
- U-turn
- Roost

Barraskewda @ Choice Band
Ability: Swift Swim
EVs: 252 Atk / 4 SpD / 252 Spe
Adamant Nature
- Liquidation
- Close Combat
- Flip Turn
- Aqua Jet

Archaludon @ Power Herb
Ability: Stamina
EVs: 252 SpA / 4 SpD / 252 Spe
Modest Nature
- Electro Shot
- Draco Meteor
- Flash Cannon
- Body Press

Iron Treads @ Booster Energy
Ability: Quark Drive
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Rapid Spin
- Earthquake
- Iron Head
- Stealth Rock

Greninja @ Life Orb
Ability: Battle Bond
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Hydro Pump
- Dark Pulse
- Water Shuriken
- Spikes

Zapdos @ Heavy-Duty Boots
Ability: Static
EVs: 252 HP / 104 Def / 152 Spe
Timid Nature
- Thunder
- Hurricane
- Volt Switch
- Roost"""

    debug_team_stall = """
Alomomola @ Heavy-Duty Boots
Ability: Regenerator
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Wish
- Protect
- Flip Turn
- Scald

Clodsire @ Leftovers
Ability: Unaware
EVs: 248 HP / 8 Def / 252 SpD
Careful Nature
- Earthquake
- Toxic
- Recover
- Stealth Rock

Blissey @ Heavy-Duty Boots
Ability: Natural Cure
EVs: 252 HP / 252 Def / 4 SpD
Bold Nature
- Seismic Toss
- Soft-Boiled
- Stealth Rock
- Thunder Wave

Dondozo @ Leftovers
Ability: Unaware
EVs: 252 HP / 252 Def / 4 SpD
Impish Nature
- Liquidation
- Body Press
- Curse
- Rest

Corviknight @ Leftovers
Ability: Pressure
EVs: 248 HP / 252 Def / 8 SpD
Impish Nature
- Brave Bird
- Roost

Garganacl @ Leftovers
Ability: Purifying Salt
EVs: 252 HP / 4 Def / 252 SpD
Careful Nature
- Salt Cure
- Recover
- Iron Defense
- Body Press"""

    debug_team_sand = """
Tyranitar @ Smooth Rock
Ability: Sand Stream
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Stealth Rock
- Stone Edge
- Knock Off
- Earthquake

Excadrill @ Life Orb
Ability: Sand Rush
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Swords Dance
- Iron Head
- Rock Slide
- High Horsepower

Garganacl @ Covert Cloak
Ability: Purifying Salt
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Salt Cure
- Recover
- Stone Edge
- Earthquake

Corviknight @ Leftovers
Ability: Pressure
EVs: 252 HP / 4 Def / 252 SpD
Impish Nature
- Defog
- Roost
- Brave Bird
- U-turn

Rotom-Wash @ Leftovers
Ability: Levitate
EVs: 252 HP / 252 Def / 4 SpA
Bold Nature
- Volt Switch
- Hydro Pump
- Will-O-Wisp
- Pain Split

Glimmora @ Focus Sash
Ability: Toxic Debris
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Mortal Spin
- Power Gem
- Sludge Wave
- Stealth Rock"""

    debug_team_bulky = """
Great Tusk @ Booster Energy
Ability: Protosynthesis
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Headlong Rush
- Close Combat
- Ice Spinner
- Rapid Spin

Garganacl @ Leftovers
Ability: Purifying Salt
EVs: 252 HP / 252 Def / 4 SpD
Impish Nature
- Salt Cure
- Recover
- Iron Defense
- Protect

Corviknight @ Rocky Helmet
Ability: Pressure
EVs: 248 HP / 252 Def / 8 SpD
Impish Nature
- Brave Bird
- Roost
- Defog
- U-turn

Glimmora @ Heavy-Duty Boots
Ability: Toxic Debris
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Mortal Spin
- Power Gem
- Stealth Rock
- Spikes

Volcarona @ Heavy-Duty Boots
Ability: Flame Body
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Quiver Dance
- Fiery Dance
- Bug Buzz
- Giga Drain

Dragapult @ Choice Specs
Ability: Infiltrator
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Draco Meteor
- Shadow Ball
- U-turn
- Flamethrower"""

    st.caption("🐞 Quick Load Presets:")
    b1, b2, b3, b4, b5 = st.columns(5)
    if b1.button("⚖️ Bal", use_container_width=True):
        st.session_state.default_input = debug_team_balanced
        st.rerun()
    if b2.button("🌧️ Rain", use_container_width=True):
        st.session_state.default_input = debug_team_rain
        st.rerun()
    if b3.button("🐢 Stall", use_container_width=True):
        st.session_state.default_input = debug_team_stall
        st.rerun()
    if b4.button("🏜️ Sand", use_container_width=True):
        st.session_state.default_input = debug_team_sand
        st.rerun()
    if b5.button("💪 Bulky", use_container_width=True):
        st.session_state.default_input = debug_team_bulky
        st.rerun()

    with st.form("pokemon_form"):
        pokemon_data = st.text_area(
            "Paste Showdown Export:",
            value=st.session_state.default_input,
            placeholder="Pikachu @ Light Ball...",
            height=400,
            help="Paste your team from Pokemon Showdown here."
        )
        
        submit_button = st.form_submit_button("Analyze Team", type="primary")
        
        if submit_button and pokemon_data:
            st.session_state.pokemon_data = pokemon_data
            st.session_state.pokemon_names = extract_pokemon_names(pokemon_data)
            
            with st.spinner("Analyzing team dynamics..."):
                team, team_weakness = readTeam(pokemon_data)
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
        st.code("""
Pikachu @ Light Ball
Ability: Static
EVs: 252 Atk / 4 HP

Charizard @ Charcoal  
Ability: Blaze""", language="text")

# --- Main UI Layout ---
col1, col2, col3 = st.columns([2, 1, 2])
with col2:
    logo_path = config.IMAGES_DIR / "dark_logo_transp.png"
    if logo_path.exists():
        st.image(str(logo_path), width=350)
    else:
        st.title("MetaMatch")

if not st.session_state.submitted:
    # --- Quick Match Feature ---
    st.markdown("### 🤝 Quick Match")
    st.caption("Don't have a full team? Pick 1-5 Pokémon to find their best partners.")
    
    # Format Selection Pills
    tgt_format = st.pills(
        "Competitive Format",
        options=["OU", "UU", "NatDex"],
        default=["OU"],
        selection_mode="multi",
        label_visibility="collapsed"
    )
    fmt_map = {"OU": "gen9ou", "UU": "gen9uu", "NatDex": "gen9natdex"}

    # Load meta mons for selection
    try:
        with open(config.JSON_DIR / "topPoke.json", "r") as f:
            meta_pokes = list(json.load(f).keys())
    except:
        meta_pokes = []

    qm_selection = st.multiselect(
        "Select your core (Max 5):", 
        options=meta_pokes,
        max_selections=5,
        placeholder="Search for a Pokémon...",
        key="quick_match_select"
    )
    
    if qm_selection:
        # Convert selected labels (e.g. "OU") to internal IDs (e.g. "gen9ou")
        # Handle case where user deselects all (tgt_format is empty list) -> default to OU
        selected_fmts = [fmt_map.get(f) for f in tgt_format] if tgt_format else ["gen9ou"]
        recs = recommender.get_recommendations(qm_selection, top_n=16, format_id=selected_fmts)
        
        if recs:
            st.markdown(f"**Top recommended partners for your squad:**")
            # recs is list of (name, score)
            max_score = recs[0][1]
            
            for i in range(0, len(recs), 4):
                cols = st.columns(4)
                batch = recs[i:i+4]
                for j, (name, score) in enumerate(batch):
                    match_pct = int((score / max_score) * 100) if max_score > 0 else 0
                    glow_color = "#00ff88" if match_pct > 80 else "#00d4ff"
                    
                    with cols[j]:
                        sprite_url = get_pokemon_sprite(name) or ""
                        st.markdown(f"""
                        <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid {glow_color}44; border-radius: 12px; padding: 10px; text-align: center; transition: transform 0.2s; margin-bottom: 15px;">
                            <img src="{sprite_url}" width="70" style="filter: drop-shadow(0 0 5px rgba(0,0,0,0.5));">
                            <div style="font-weight: 700; font-size: 0.9rem; margin-top: 5px; color: #fff;">{name}</div>
                            <div title="Based on high-ladder weighted usage statistics from Smogon." style="cursor: help; margin-top: 5px; background: rgba(0,0,0,0.3); padding: 2px 8px; border-radius: 15px; display: inline-block; border: 1px solid {glow_color}66;">
                                <span style="color: {glow_color}; font-weight: bold; font-size: 0.8rem;">{match_pct}% Synergy</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
        else:
            st.caption("No specific recommendations found for this combination.")

    st.markdown("---")
    st.info("👈 **To start a full analysis:** Paste your Showdown team export in the sidebar!")
    
if st.session_state.submitted and st.session_state.pokemon_names:
    
    type_map = {
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
    t_info_m = type_map.get(weak_type_name, {'color': '#777', 'icon': '❓'})
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
            type_color = type_map.get(primary_type, {'color': '#777'})['color']
            
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
                            {''.join([f'<span style="background:{type_map.get(t, {}).get("color", "#555")}; color:white; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; text-shadow: 0 1px 2px rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.2);">{type_map.get(t, {}).get("icon", "")} {t}</span>' for t in poke['Type']])}
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
                        {poke['Nature']} Nature • {', '.join([f'{v} {k}' for k, v in sorted(poke['EVs'].items(), key=lambda x: x[1], reverse=True)[:2]])}
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
        "Team Overview", "Suggestions", "Meta Threats", "Coach Guide", "Recommendations", "Matchup Matrices", "Speed Tiers", "Coach Chat"
    ])

    with tab_chat:
        st.subheader("💬 Ask the Coach (Powered by RAG)")
        st.caption("Ask specific questions about counters, mechanics, or strategy. The AI uses Smogon data to answer.")
        
        # Chat History Container
        chat_container = st.container()
        
        # Render History
        with chat_container:
            if "chat_messages" not in st.session_state:
                st.session_state.chat_messages = []
                
            for msg in st.session_state.chat_messages:
                # Use name and avatar if stored, fallback to role defaults
                display_name = msg.get("name", msg["role"])
                with st.chat_message(display_name, avatar=msg.get("avatar")):
                    if msg["role"] == "assistant" and "name" in msg:
                         st.markdown(f"**{msg['name']}**")
                    st.markdown(msg["content"])
        
        # RAG Guide
        with st.expander("💡 How to use the AI Coach efficiently", expanded=False):
            st.markdown("""
            **Meet your Coaching Staff:**
            
            🧪 **Clemont** (Mechanics Engine)
            *Ask him about math, specific interactions, and speed tiers.*
            *   "Is Rotom-Wash weak to Ground?"
            *   "Who is faster: Dragapult or Zamazenta?"
            
            📜 **Professor Oak** (Strategy Mentor)
            *Ask him about win conditions, game plans, and high-level concepts.*
            *   "How do I beat Stall teams?"
            *   "What is the best lead for this team?"
            
            🍳 **Brock** (Team Builder)
            *Ask him about sets, items, and meta usage stats.*
            *   "What is the most popular item for Great Tusk?"
            *   "Is this moveset good?"
            """)

        # Input
        if prompt := st.chat_input("How do I beat Kingambit?"):
            # 1. User Message
            st.session_state.chat_messages.append({"role": "user", "content": prompt})
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)
            
            # 2. AI Response
            with chat_container:
                from metamatch.agents import AgentManager
                manager = AgentManager()
                agent_name = manager.get_active_agent_name(prompt)
                
                # Extract emoji for avatar
                avatar = "🤖"
                if "🧪" in agent_name: avatar = "🧪"
                elif "📜" in agent_name: avatar = "📜"
                elif "🍳" in agent_name: avatar = "🍳"

                with st.chat_message(agent_name, avatar=avatar):
                    st.markdown(f"**{agent_name}**")
                    response_placeholder = st.empty()
                    full_response = ""
                    
                    # Call RAG Chat Stream
                    stream = get_chat_response(
                        prompt, 
                        st.session_state.analysis['team'],
                        st.session_state.analysis['weakness']
                    )
                    
                    for chunk in stream:
                        content = chunk.choices[0].delta.content or ""
                        full_response += content
                        response_placeholder.markdown(full_response + "▌")
                    
                    response_placeholder.markdown(full_response)
            
            # 3. Save to History with persona details
            st.session_state.chat_messages.append({
                "role": "assistant", 
                "name": agent_name,
                "avatar": avatar,
                "content": full_response
            })

    with tab_overview:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Offensive Coverage")
            st.metric("Type Coverage", f"{covered_count}/18 types")
            covered_html = ""
            for t, is_covered in coverage.items():
                if is_covered:
                    t_i = type_map.get(t.capitalize(), {'color': '#777', 'icon': '❓'})
                    covered_html += f'<span style="background-color:{t_i["color"]};color:white;padding:4px 8px;border-radius:4px;font-size:14px;margin:4px;display:inline-block">{t_i["icon"]} {t.capitalize()}</span>'
            st.markdown(covered_html, unsafe_allow_html=True)
            if [t for t, v in coverage.items() if not v]: st.warning("⚠️ Missing offensive coverage for several types.")

        with c2:
            st.subheader("Defensive Vulnerabilities")
            for t_n, counts in weakness.items():
                cap_t = t_n.capitalize()
                if counts['weak'] >= 2:
                    t_i = type_map.get(cap_t, {'color': '#777', 'icon': '❓'})
                    bg = "rgba(255, 75, 75, 0.2)" if counts['weak'] >= 3 else "rgba(255, 165, 0, 0.1)"
                    bc = "#ff4b4b" if counts['weak'] >= 3 else "#ffa500"
                    tag = "— ⚠️ CRITICAL" if counts['weak'] >= 3 else ""
                    
                    # On-the-fly lookup for weak Pokémon
                    weak_mons = []
                    for p in team_data.values():
                        # Check multiplier from 'Damage From' dict
                        if p.get('Damage From', {}).get(t_n.lower(), 1.0) > 1:
                            weak_mons.append(p['Pokemon'])
                    
                    tooltip = f"Weak: {', '.join(weak_mons)}"
                    
                    alert = f'''
                    <div title="{tooltip}" style="background-color:{bg}; padding:10px; border-radius:5px; border-left: 5px solid {bc}; margin-bottom:10px; cursor: help;">
                        <span style="background-color:{t_i["color"]}; color:white; padding:2px 8px; border-radius:4px; font-size:14px; margin-right:10px;">{t_i["icon"]} {cap_t}</span>
                        <b>{counts["weak"]} Weaknesses</b> {tag}
                    </div>
                    '''
                    st.markdown(alert, unsafe_allow_html=True)

    with tab3:
        if st.session_state.analysis.get('suggestions'):
            sugg = st.session_state.analysis['suggestions']
            
            # --- Team Analysis Section ---
            st.subheader("🛡️ Strategic Overview")
            if 'team_analysis' in sugg and isinstance(sugg['team_analysis'], list):
                for p in sugg['team_analysis']:
                    st.markdown(f"""
                    <div style="background: rgba(0, 212, 255, 0.05); border-left: 4px solid #00d4ff; padding: 12px 16px; margin-bottom: 12px; border-radius: 0 8px 8px 0;">
                        <span style="font-size: 1.1rem; margin-right: 8px;">💡</span>
                        <span style="color: #e0e0e0; font-size: 0.95rem;">{p}</span>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # --- Pokemon Specific Section ---
            st.subheader("🔍 Optimization Tips")
            if 'pokemon_specific' in sugg and isinstance(sugg['pokemon_specific'], dict):
                for pk, adv in sugg['pokemon_specific'].items():
                    # Format advice text
                    advice_text = str(adv)
                    if isinstance(adv, dict):
                        advice_text = ", ".join([str(v) for v in adv.values()])
                    
                    sprite_url = get_pokemon_sprite(pk) or ""
                    
                    st.markdown(f"""
                    <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 16px; margin-bottom: 12px; display: flex; align-items: start; gap: 15px; transition: all 0.2s;">
                        <div style="flex-shrink: 0; background: rgba(255, 255, 255, 0.05); border-radius: 50%; width: 60px; height: 60px; display: flex; align-items: center; justify-content: center;">
                            <img src="{sprite_url}" width="50" style="filter: drop-shadow(0 0 3px rgba(0,0,0,0.5));">
                        </div>
                        <div>
                            <div style="font-weight: 700; font-size: 1.1rem; color: #00d4ff; margin-bottom: 4px;">{pk}</div>
                            <div style="color: #ccc; font-size: 0.9rem; line-height: 1.5;">{advice_text}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        else: st.info("Run analysis to see suggestions.")

    with tab4:
        sugg = st.session_state.analysis.get('suggestions')
        if sugg and 'threats' in sugg:
            threats = sugg['threats']
            if threats:
                st.caption("⚠️ High-priority threats identified by AI analysis based on your team composition.")
                for threat in threats:
                    name = threat.get('pokemon', 'Unknown')
                    explanation = threat.get('explanation', 'No explanation provided.')
                    counter = threat.get('counter_play', 'No specific counter play provided.')
                    sprite_url = get_pokemon_sprite(name) or ""
                    
                    threat_html = f"""
                    <div style="background: rgba(255, 50, 50, 0.05); border: 1px solid rgba(255, 75, 75, 0.2); border-radius: 12px; padding: 16px; margin-bottom: 16px; display: flex; align-items: flex-start; gap: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.2);">
                        <div style="flex-shrink: 0; text-align: center; width: 80px;">
                            <div style="background: rgba(255, 0, 0, 0.1); width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 8px auto;">
                                <img src="{sprite_url}" width="60" style="filter: drop-shadow(0 0 5px rgba(255,0,0,0.4));">
                            </div>
                        </div>
                        <div style="flex-grow: 1;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <span style="font-size: 1.2rem; font-weight: 700; color: #ff6b6b; letter-spacing: 0.5px;">{name}</span>
                                <span style="font-size: 0.7rem; background: rgba(255, 75, 75, 0.2); color: #ff9999; padding: 2px 8px; border-radius: 10px; border: 1px solid rgba(255, 75, 75, 0.3);">MAJOR THREAT</span>
                            </div>
                            <div style="font-size: 0.9rem; color: #e0e0e0; margin-bottom: 12px; line-height: 1.5;">
                                {explanation}
                            </div>
                            <div style="background: rgba(0, 0, 0, 0.2); border-left: 3px solid #ff6b6b; padding: 10px; border-radius: 0 6px 6px 0;">
                                <div style="font-size: 0.75rem; color: #ff6b6b; text-transform: uppercase; font-weight: bold; margin-bottom: 4px;">🛡️ Counter Strategy</div>
                                <div style="font-size: 0.85rem; color: #ccc;">{counter}</div>
                            </div>
                        </div>
                    </div>
                    """
                    st.markdown(threat_html, unsafe_allow_html=True)
            else:
                st.success("✅ No major meta threats identified based on current context!")
        elif st.session_state.submitted:
             st.warning("⚠️ No threat data returned from analysis.")
        else:
             st.info("Run analysis to see meta threats.")

    with tab8:
        if st.session_state.analysis.get('guide'):
            g = st.session_state.analysis['guide']
            st.subheader("🎓 Team Pilot Guide")
            
            st.info(f"**🏆 Win Condition:** {g.get('win_condition', 'N/A')}")
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("### 🏁 Lead Options")
                for l in g.get('lead_options', []):
                    st.success(f"**{l.get('pokemon')}**: {l.get('scenario')}")
            
            with c2:
                st.markdown("### 💎 Tera Strategy")
                tera = g.get('tera_strategy')
                if isinstance(tera, dict):
                     st.warning(f"**{tera.get('pokemon')}**: {tera.get('when_to_use')}")
                else:
                    st.write(str(tera))

            st.markdown("### 🤝 Key Combinations")
            for c in g.get('key_combos', []):
                with st.expander(f"🔗 {c.get('name')}", expanded=True):
                    st.write(c.get('description'))
        else:
            st.warning("Guide generation failed or is unavailable.")

    with tab_rec:
        st.subheader("🤖 Statistical Teammate Recommendations")
        st.caption("Based on real Smogon usage data and teammate correlation matrices.")
        
        # Format Selection Pills
        tgt_format_rec = st.pills(
            "Target Format",
            options=["OU", "UU", "NatDex"],
            default=["OU"],
            selection_mode="multi",
            key="rec_format_pills"
        )
        fmt_map = {"OU": "gen9ou", "UU": "gen9uu", "NatDex": "gen9natdex"}

        selected_fmts_rec = [fmt_map.get(f) for f in tgt_format_rec] if tgt_format_rec else ["gen9ou"]
        recs = recommender.get_recommendations(
            st.session_state.pokemon_names, 
            format_id=selected_fmts_rec
        )
        
        if recs:
            rec_cols = st.columns(3)
            max_score = recs[0][1]
            
            for i, (name, score) in enumerate(recs):
                col = rec_cols[i % 3]
                match_pct = int((score / max_score) * 100)
                
                # Determine color based on match %
                glow_color = "#00d4ff" # Default Cyan
                if match_pct > 80: glow_color = "#00ff88" # Green
                elif match_pct < 50: glow_color = "#ffaa00" # Orange
                
                with col:
                    rec_html = f"""
                    <div class="pokemon-card" style="border: 1px solid {glow_color}44; box-shadow: 0 0 15px -5px {glow_color}, inset 0 0 20px -15px {glow_color}; min-height: 180px;">
                        <div style="text-align: center;">
                            <div style="position: relative; display: inline-block;">
                                <div style="position: absolute; width: 60px; height: 60px; background: {glow_color}; filter: blur(30px); opacity: 0.4; z-index: 0; top: 10px; left: 10px;"></div>
                                <img src="{get_pokemon_sprite(name) or ''}" width="100" style="position: relative; z-index: 1; filter: drop-shadow(0 0 5px rgba(0,0,0,0.5)); transition: transform 0.3s;">
                            </div>
                            <div class="poke-name" style="font-size: 1.2rem; margin-top: 10px;">{name}</div>
                            <div style="margin-top: 10px; background: rgba(0,0,0,0.3); padding: 5px 10px; border-radius: 20px; display: inline-block; border: 1px solid {glow_color}66;">
                                <span style="color: {glow_color}; font-weight: 800; font-size: 1.1rem;">{match_pct}%</span> <span style="font-size: 0.8rem; opacity: 0.8;">Synergy</span>
                            </div>
                        </div>
                    </div>
                    """
                    st.markdown(rec_html, unsafe_allow_html=True)
        else:
            st.info("No recommendations available. Try analyzing a different team or update meta data.")
            
    with tab_matrix:
        st.subheader("🛡️ Defensive Matchup Matrix", help="Damage taken from each type. Red = Weak.")
        st.markdown(r'''<div style="display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap;"><span style="background-color: #7b1e1e; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟥 4x Weak</span><span style="background-color: #c0392b; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟧 2x Weak</span><span style="border: 1px solid #ccc; color: #888; padding: 4px 8px; border-radius: 4px; font-size: 12px;">⬜ 1x Neutral</span><span style="background-color: #27ae60; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟩 0.5x Resist</span><span style="background-color: #1e8449; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🌲 0.25x Resist</span><span style="background-color: #2c3e50; color: #ecf0f1; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟦 0x Immune</span></div>''', unsafe_allow_html=True)
        all_types = ["Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"]
        rows = []
        for p in team_data.values():
            r = {"Pokemon": p['Pokemon']}
            for t in all_types: r[t] = p['Damage From'].get(t.lower(), 1.0)
            rows.append(r)
        df = pd.DataFrame(rows).set_index("Pokemon")
        def c_c(v):
            if v == 0: return 'background-color: #2c3e50; color: #ecf0f1'
            if v >= 4: return 'background-color: #7b1e1e; color: white'
            if v >= 2: return 'background-color: #c0392b; color: white'
            if v <= 0.25: return 'background-color: #1e8449; color: white'
            if v <= 0.5: return 'background-color: #27ae60; color: white'
            return ''
        st.dataframe(df.style.map(c_c).format("{:.1f}"), width='stretch', height=250)

        st.markdown("---")
        st.subheader("⚔️ Offensive Coverage Matrix", help="Best damage you deal to each type. Green = Super Effective.")
        st.markdown(r'''<div style="display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap;"><span style="background-color: #27ae60; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟩 2x SE</span><span style="border: 1px solid #ccc; color: #888; padding: 4px 8px; border-radius: 4px; font-size: 12px;">⬜ 1x Neutral</span><span style="background-color: #c0392b; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟥 0.5x Resisted</span><span style="background-color: #2c3e50; color: #ecf0f1; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">🟦 0x Immune</span></div>''', unsafe_allow_html=True)
        o_rows = []
        for p in team_data.values():
            r = {"Pokemon": p['Pokemon']}
            for t_d in all_types:
                m_m = 0.0
                for m in p['Moves']:
                    if m['category'] != 'Status':
                        mult = get_multiplier(m['type'], t_d)
                        if mult > m_m: m_m = mult
                if not p['Moves'] and m_m == 0.0: m_m = 1.0
                r[t_d] = m_m
            o_rows.append(r)
        o_df = pd.DataFrame(o_rows).set_index("Pokemon")
        def c_c_o(v):
            if v >= 2: return 'background-color: #27ae60; color: white'
            if v == 0: return 'background-color: #2c3e50; color: #ecf0f1'
            if v <= 0.5: return 'background-color: #c0392b; color: white'
            return ''
        st.dataframe(o_df.style.map(c_c_o).format("{:.1f}"), width='stretch', height=250)

    with tab7:
        st.subheader("⚡ Speed Tiers", help="Compare team speed against meta threats.")
        try:
            with open(config.JSON_DIR / "meta_speeds.json", "r") as f:
                m_s = json.load(f)
        except:
            m_s = []
        u_s = [{'Name': p['Pokemon'], 'Speed': p.get('Speed', 0), 'Type': 'Your Team'} for p in team_data.values()]
        c_d = u_s + [{'Name': m['label'], 'Speed': m['speed'], 'Type': 'Meta'} for m in m_s[:40]]
        df_c = pd.DataFrame(c_d).sort_values(by="Speed", ascending=False)
        base = alt.Chart(df_c).encode(y=alt.Y('Name', sort='-x', axis=alt.Axis(title=None)), x=alt.X('Speed', axis=alt.Axis(title='Speed Stat')), tooltip=['Name', 'Speed', 'Type'])
        dots = base.mark_circle(size=100).encode(color=alt.Color('Type', scale=alt.Scale(domain=['Your Team', 'Meta'], range=['#3399FF', '#888888'])), opacity=alt.condition(alt.datum.Type == 'Your Team', alt.value(1.0), alt.value(0.5)))
        text = base.mark_text(align='left', dx=10, color='#3399FF', fontWeight='bold').encode(text=alt.Text('Speed'), opacity=alt.condition(alt.datum.Type == 'Your Team', alt.value(1.0), alt.value(0.0)))
        st.altair_chart((dots + text).properties(height=600), use_container_width=True)
