import streamlit as st
import re
import requests
from PIL import Image
from io import BytesIO
from helper import *
from team_read import *
from suggestion_call import *
from smogon_scrape import *

st.set_page_config(page_title="MetaMatch", page_icon="⚪", layout="wide")

st.markdown("""
<style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 0rem;
    }
    .stApp > header {
        background-color: transparent;
    }
    .stApp {
        background-color: #1a1f2e;
    }
    .main {
        background-color: #1a1f2e;
    }
</style>
""", unsafe_allow_html=True)

# --- Helper Functions ---
def extract_pokemon_names(raw_data):
    # Pattern now matches: Start of line, (Letters, spaces, hyphens, dots), followed by @
    pattern = r'^([A-Za-z][A-Za-z\s\-\.]*?)\s*@'
    names = []
    lines = raw_data.split('\n')
    for line in lines:
        line = line.strip()
        if not line: continue
        match = re.search(pattern, line)
        if match:
            name = match.group(1).strip()
            if name and name not in names:
                names.append(name)
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
    except: pass
    return None

def format_pokemon_name(name):
    return name.capitalize()

# --- Main UI Layout ---
col1, col2, col3 = st.columns([2, 1, 2])
with col2:
    st.image("logo/dark_logo_transp.png", width=350)

# Initialize Session State
if 'submitted' not in st.session_state:
    st.session_state.submitted = False
if 'pokemon_names' not in st.session_state:
    st.session_state.pokemon_names = []
if 'default_input' not in st.session_state:
    st.session_state.default_input = ""

# --- Sidebar: Input & Controls ---
with st.sidebar:
    st.header("📋 Team Input")
    
    # Define Debug Teams
    debug_team_balanced = """Rotom-Wash @ Leftovers
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

    debug_team_rain = """Pelipper @ Damp Rock
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

    debug_team_stall = """Alomomola @ Heavy-Duty Boots
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
- Defog
- U-turn

Garganacl @ Leftovers
Ability: Purifying Salt
EVs: 252 HP / 4 Def / 252 SpD
Careful Nature
- Salt Cure
- Recover
- Iron Defense
- Body Press"""

    st.caption("🐞 Quick Load Presets:")
    b1, b2, b3 = st.columns(3)
    if b1.button("⚖️ Bal", use_container_width=True):
        st.session_state.default_input = debug_team_balanced
        st.rerun()
    if b2.button("🌧️ Rain", use_container_width=True):
        st.session_state.default_input = debug_team_rain
        st.rerun()
    if b3.button("🐢 Stall", use_container_width=True):
        st.session_state.default_input = debug_team_stall
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
            
            # Run Analysis
            with st.spinner("Analyzing team dynamics..."):
                team, team_weakness = readTeam(pokemon_data)
                detectRole(team)
                addComments(team)
                coverage = coverageCheck(team)
                
                suggestions = get_suggestions(team)
                
                st.session_state.analysis = {
                    'team': team,
                    'weakness': team_weakness,
                    'coverage': coverage,
                    'suggestions': suggestions
                }
                
                st.session_state.submitted = True
                st.rerun()

    with st.expander("ℹ️ Supported Formats"):
        st.code("""
        Pikachu @ Light Ball
        Ability: Static
        EVs: 252 Atk / 4 HP

        Charizard @ Charcoal  
        Ability: Blaze""", language="text")

# --- Main Content Area ---
if not st.session_state.submitted:
    st.info("👈 Use the sidebar to paste your team and start analysis!")
    
# --- Main Content Area ---
if not st.session_state.submitted:
    st.info("👈 Use the sidebar to paste your team and start analysis!")
    
if st.session_state.submitted and st.session_state.pokemon_names:
    
    type_map = {
        'Fire': {'color': '#FF4422', 'icon': '🔥'}, 
        'Water': {'color': '#3399FF', 'icon': '💧'}, 
        'Grass': {'color': '#77CC55', 'icon': '🌿'},
        'Electric': {'color': '#FFCC33', 'icon': '⚡'}, 
        'Psychic': {'color': '#FF5599', 'icon': '🔮'}, 
        'Ice': {'color': '#66CCFF', 'icon': '❄️'},
        'Fighting': {'color': '#BB5544', 'icon': '🥊'}, 
        'Poison': {'color': '#AA5599', 'icon': '☠️'}, 
        'Ground': {'color': '#DDBB55', 'icon': '🏜️'},
        'Flying': {'color': '#8899FF', 'icon': '🕊️'}, 
        'Bug': {'color': '#AABB22', 'icon': '🐞'}, 
        'Rock': {'color': '#BBAA66', 'icon': '🪨'},
        'Ghost': {'color': '#6666BB', 'icon': '👻'}, 
        'Dragon': {'color': '#7766EE', 'icon': '🐲'}, 
        'Dark': {'color': '#775544', 'icon': '🌑'},
        'Steel': {'color': '#AAAABB', 'icon': '⚙️'}, 
        'Fairy': {'color': '#EE99AA', 'icon': '✨'}, 
        'Normal': {'color': '#AAAA99', 'icon': '⚪'}
    }

    # --- Metrics Dashboard ---
    st.markdown("## 📊 Team Dashboard")
    
    # Calculate Metrics
    coverage = st.session_state.analysis['coverage']
    weakness = st.session_state.analysis['weakness']
    team_data = st.session_state.analysis['team']
    
    covered_count = sum(1 for v in coverage.values() if v)
    most_weak_type = max(weakness.items(), key=lambda x: x[1]['weak'])
    
    # Determine Team Archetype
    roles = []
    for p in team_data.values():
        roles.extend(p['Roles'])
    
    archetype = "Balanced"
    arch_icon = "⚖️"
    if roles.count("Wall") + roles.count("Tank") >= 3: 
        archetype = "Stall / Bulky"
        arch_icon = "🐢"
    elif roles.count("Sweeper") + roles.count("Wallbreaker") >= 4: 
        archetype = "Hyper Offense"
        arch_icon = "⚔️"
    
    # Custom CSS for Metrics & Cards
    st.markdown("""
        <style>
        div[data-testid="stMetricValue"] {
            font-size: 28px;
            font-weight: bold;
        }
        div[data-testid="stMetricLabel"] {
            font-weight: bold;
            color: #888;
        }
        </style>
    """, unsafe_allow_html=True)

    m1, m2, m3 = st.columns(3)
    m1.metric("Archetype", f"{arch_icon} {archetype}")
    
    with m2:
        st.metric("Type Coverage", f"{covered_count}/18")
        st.progress(covered_count / 18)
    
    # Un-bland the Top Weakness metric
    weak_type_name = most_weak_type[0].capitalize()
    t_info_m = type_map.get(weak_type_name, {'color': '#777', 'icon': '❓'})
    weak_label = f"{t_info_m['icon']} {weak_type_name}"
    
    if most_weak_type[1]['weak'] >= 3:
        m3.metric("Critical Weakness", weak_label, f"-{most_weak_type[1]['weak']} Mons", delta_color="inverse")
    else:
        m3.metric("Top Weakness", weak_label, f"-{most_weak_type[1]['weak']} Mons", delta_color="off")

    # --- Pokemon Trading Cards ---
    st.markdown("## 🦸 Your Squad")
    
    # Robust Grid Layout: Process in chunks of 3
    names = st.session_state.pokemon_names
    for i in range(0, len(names), 3):
        cols = st.columns(3)
        batch_names = names[i:i+3]
        
        for j, name in enumerate(batch_names):
            idx = i + j
            poke_data = team_data[idx]
            
            with cols[j]:
                with st.container(border=True):
                    # 1. Header: Name & Sprite
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        sprite_url = get_pokemon_sprite(name)
                        if sprite_url:
                            st.image(sprite_url, width=80)
                        else:
                            st.text("👾")
                    with c2:
                        st.markdown(f"**{name}**")
                        # Type Badges
                        badges = ""
                        for t in poke_data['Type']:
                            t_info = type_map.get(t, {'color': '#777', 'icon': '❓'})
                            badges += (
                                f'<span style="background-color:{t_info["color"]};'
                                f'color:white;padding:2px 6px;border-radius:4px;font-size:12px;margin-right:4px">'
                                f'{t_info["icon"]} {t}</span>'
                            )
                        st.markdown(badges, unsafe_allow_html=True)

                    st.markdown("---")
                    
                    # 2. Key Stats
                    # Roles
                    if poke_data['Roles']:
                        role_str = " • ".join(poke_data['Roles'][:3]) # Limit to 3 roles
                        st.caption(f"🛡️ {role_str}")
                    
                    # Item / Ability
                    st.caption(f"🎒 **{poke_data['Item']}**")
                    st.caption(f"✨ {poke_data['Ability']}")
                    
                    # EV Quick Look
                    if poke_data['EVs']:
                        top_evs = sorted(poke_data['EVs'].items(), key=lambda x: x[1], reverse=True)[:2]
                        ev_str = ", ".join([f"{k} {v}" for k, v in top_evs])
                        st.caption(f"💪 {ev_str}")

    st.markdown("---")
    
    st.header("Detailed Analysis")
    tab1, tab2, tab3, tab4 = st.tabs(["Coverage", "Weaknesses", "Suggestions", "Meta Threats"])

    with tab1:
        coverage = st.session_state.analysis['coverage']
        covered = sum(1 for v in coverage.values() if v)
        total = len(coverage)
        st.metric("Type Coverage", f"{covered}/{total} types")
        
        # Display covered types as badges
        st.write("**Covered Types:**")
        covered_html = ""
        for t, is_covered in coverage.items():
            if is_covered:
                t_info = type_map.get(t.capitalize(), {'color': '#777', 'icon': '❓'})
                covered_html += (
                    f'<span style="background-color:{t_info["color"]};'
                    f'color:white;padding:4px 8px;border-radius:4px;font-size:14px;margin:4px;display:inline-block">'
                    f'{t_info["icon"]} {t.capitalize()}</span>'
                )
        st.markdown(covered_html, unsafe_allow_html=True)
        
        missing = [t for t, v in coverage.items() if not v]
        if missing:
            st.warning("⚠️ Missing offensive coverage for several types.")

    with tab2:
        team_weakness = st.session_state.analysis['weakness']
        st.write("**Team Vulnerabilities:**")
        
        for type_name, counts in team_weakness.items():
            cap_type = type_name.capitalize()
            if counts['weak'] >= 2:
                t_info = type_map.get(cap_type, {'color': '#777', 'icon': '❓'})
                
                # Colors for alert box
                bg_color = "rgba(255, 75, 75, 0.2)" if counts['weak'] >= 3 else "rgba(255, 165, 0, 0.1)"
                border_color = "#ff4b4b" if counts['weak'] >= 3 else "#ffa500"
                critical_tag = "— ⚠️ CRITICAL" if counts['weak'] >= 3 else ""
                
                # Construct HTML using standard triple quotes
                alert_html = f"""
                <div style="background-color:{bg_color}; padding:10px; border-radius:5px; border-left: 5px solid {border_color}; margin-bottom:10px;">
                    <span style="background-color:{t_info['color']}; color:white; padding:2px 8px; border-radius:4px; font-size:14px; margin-right:10px;">
                        {t_info['icon']} {cap_type}
                    </span>
                    <b>{counts['weak']} Weaknesses</b> {critical_tag}
                </div>
                """
                st.markdown(alert_html, unsafe_allow_html=True)

    with tab3:
        if st.session_state.analysis['suggestions']:
            sugg = st.session_state.analysis['suggestions']
            st.subheader("🛡️ Team Analysis")
            if 'team_analysis' in sugg:
                for point in sugg['team_analysis']:
                    st.write(f"• {point}")
            st.markdown("---")
            st.subheader("🔍 Pokemon Specific Tips")
            if 'pokemon_specific' in sugg and isinstance(sugg['pokemon_specific'], dict):
                for poke_name, advice in sugg['pokemon_specific'].items():
                    with st.expander(f"Tips for **{poke_name}**", expanded=True):
                        st.write(advice)
        else:
            st.info("Run analysis to see suggestions.")

    with tab4:
        if st.session_state.analysis['suggestions'] and 'threats' in st.session_state.analysis['suggestions']:
            threats = st.session_state.analysis['suggestions']['threats']
            if not threats:
                st.info("No specific threats identified.")
            for threat in threats:
                with st.container():
                    t_col1, t_col2 = st.columns([1, 5])
                    name = threat.get('pokemon', 'Unknown')
                    desc = threat.get('explanation', '')
                    counter = threat.get('counter_play', '')
                    with t_col1:
                        sprite_url = get_pokemon_sprite(name)
                        if sprite_url:
                            st.image(sprite_url, width=80)
                        else:
                            st.text("👾")
                    with t_col2:
                        st.subheader(name)
                        st.write(f"**Why:** {desc}")
                        if counter:
                            st.info(f"**Counter Strategy:** {counter}")
                    st.markdown("---")
        else:
            st.info("Run analysis to see meta threats.")



    


                                