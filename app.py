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

col1, col2, col3 = st.columns([2, 1, 2])
with col2:
    st.image("logo/dark_logo_transp.png", width=350)

if 'submitted' not in st.session_state:
    st.session_state.submitted = False
if 'pokemon_names' not in st.session_state:
    st.session_state.pokemon_names = []

def extract_pokemon_names(raw_data):
    pattern = r'^([A-Za-z][A-Za-z\s]+?)\s*@'
    
    names = []
    lines = raw_data.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
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
            if sprite_url:
                return sprite_url
    except:
        pass
    return None

def format_pokemon_name(name):
    return name.capitalize()

def get_pokemon_description(name):
    descriptions = {
        "pikachu": "ash's pikachu - the electric mouse that never gives up",
        "charizard": "ashwins charizard - fire-flying powerhouse",
        "araquanid": "water spider pokemon - traps foes in water bubbles",
        "cinderace": "fire rabbit striker - kicks pyro balls with precision", 
        "kingambit": "supreme overlord - grows stronger as allies fall",
        "dragonite": "friendly dragon - gentle giant with incredible power",
        "iron treads": "paradox ground type - futuristic donphan variant",
        "pecharunt": "poison puppeteer - mythical toxic peach pokemon"
    }
    return descriptions.get(name.lower(), f"A powerful {name} ready for battle!")


if not st.session_state.submitted:
    with st.form("pokemon_form"):
        pokemon_data = st.text_area(
            "Paste Pokemon Data:",
            placeholder="Paste your raw pokemon data here...",
            height=300
        )
        
        submit_button = st.form_submit_button("Analyze Team")
        
        if submit_button and pokemon_data:
            st.session_state.pokemon_data = pokemon_data
            st.session_state.pokemon_names = extract_pokemon_names(pokemon_data)
            
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


    with st.expander("Supported Data Formats"):
        st.code("""
        Example formats:
            
        Pikachu @ Light Ball
        Ability: Static
        EVs: 252 Atk / 252 Spe / 4 HP

        Charizard @ Charcoal  
        Ability: Blaze""")

else:
    if st.button("← Analyze New Team"):
        st.session_state.submitted = False
        st.session_state.pokemon_names = []
        st.rerun()
    
    if st.session_state.pokemon_names:
        st.header("Your Team Analysis")

        for row in range(3):
            cols = st.columns(2)
            
            for col_idx in range(2):
                pokemon_idx = row * 2 + col_idx
                
                if pokemon_idx < len(st.session_state.pokemon_names):
                    name = st.session_state.pokemon_names[pokemon_idx]
                    
                    with cols[col_idx]:
                        with st.container():
                            sprite_url = get_pokemon_sprite(name)
                            
                            col1, col2 = st.columns([1, 2])
                            
                            with col1:
                                if sprite_url:
                                    try:
                                        response = requests.get(sprite_url)
                                        img = Image.open(BytesIO(response.content))
                                        st.image(img, width=150)
                                    except:
                                        st.text("🔲")
                                else:
                                    st.text("🔲")
                            
                            with col2:
                                poke_data = st.session_state.analysis['team'][pokemon_idx]
                                st.subheader(f"{poke_data['Pokemon']}")

                                type_colors = {
                                    'Fire': '#F08030', 'Water': '#6890F0', 'Grass': '#78C850',
                                    'Electric': '#F8D030', 'Psychic': '#F85888', 'Ice': '#98D8D8',
                                    'Fighting': '#C03028', 'Poison': '#A040A0', 'Ground': '#E0C068',
                                    'Flying': '#A890F0', 'Bug': '#A8B820', 'Rock': '#B8A038',
                                    'Ghost': '#705898', 'Dragon': '#7038F8', 'Dark': '#705848',
                                    'Steel': '#B8B8D0', 'Fairy': '#EE99AC', 'Normal': '#A8A878'
                                }
                                
                                type_html = "".join([
                                    f'<span style="background-color:{type_colors.get(t,"#68A090")};'
                                    f'color:white;padding:2px 8px;border-radius:4px;margin:2px">{t}</span>'
                                    for t in poke_data['Type']
                                ])
                                st.markdown(type_html, unsafe_allow_html=True)
                                
                                if poke_data['Roles']:
                                    st.caption(f"**Roles:** {', '.join(poke_data['Roles'])}")
                                
                                st.caption(f"**Item:** {poke_data['Item']} | **Ability:** {poke_data['Ability']}")
                            
                            st.markdown("---")
        
        
        st.header("Team Analysis")

        tab1, tab2, tab3, tab4 = st.tabs(["Coverage", "Weaknesses", "Suggestions", "Meta Threats"])

        with tab1:
            coverage = st.session_state.analysis['coverage']
            covered = sum(1 for v in coverage.values() if v)
            total = len(coverage)
            st.metric("Type Coverage", f"{covered}/{total} types")
            
            missing = [t for t, v in coverage.items() if not v]
            if missing:
                st.warning(f"No coverage for: {', '.join(missing)}")

        with tab2:
            team_weakness = st.session_state.analysis['weakness']
            st.write("**Team Weaknesses:**")
            for type_name, counts in team_weakness.items():
                if counts['weak'] >= 3:
                    st.error(f"{type_name}: {counts['weak']} weaknesses")
                elif counts['weak'] >= 2:
                    st.warning(f"{type_name}: {counts['weak']} weaknesses")

        with tab3:
            if st.session_state.analysis['suggestions']:
                sugg = st.session_state.analysis['suggestions']
                if 'suggestions' in sugg:
                    for s in sugg['suggestions']:
                        st.write(f"• {s}")

        with tab4:
            st.info("Meta threats analysis coming soon...")

    else:
        st.warning("No Pokemon detected. Try going back and pasting showdown format.")