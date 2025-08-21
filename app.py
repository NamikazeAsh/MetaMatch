import streamlit as st
import re
import requests
from PIL import Image
from io import BytesIO
from helper import *


st.set_page_config(page_title="MetaMatch", page_icon="⚪", layout="wide")

# Custom CSS to reduce top padding
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

# Add logo instead of title
col1, col2, col3 = st.columns([2, 1, 2])
with col2:
    st.image("logo/dark_logo.png", width=300)

# Initialize session state
if 'submitted' not in st.session_state:
    st.session_state.submitted = False
if 'pokemon_names' not in st.session_state:
    st.session_state.pokemon_names = []

def extract_pokemon_names(raw_data):
    """Extract pokemon names from raw data"""
    # Pattern for Pokemon @ Item format (handles multi-word names)
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
    """Get pokemon sprite from PokeAPI"""
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
    """Format pokemon name for display"""
    return name.capitalize()

def get_pokemon_description(name):
    """Get custom description for each Pokemon"""
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

# Show input form if not submitted
if not st.session_state.submitted:
    with st.form("pokemon_form"):
        pokemon_data = st.text_area(
            "Paste Pokemon Data:",
            placeholder="Paste your raw pokemon data here...",
            height=300
        )
        
        submit_button = st.form_submit_button("Analyze Team")
        
        if submit_button and pokemon_data:
            st.session_state.pokemon_names = extract_pokemon_names(pokemon_data)
            st.session_state.submitted = True
            st.rerun()

    # Example format hint
    with st.expander("Supported Data Formats"):
        st.code("""
Example formats:
    
Pikachu @ Light Ball
Ability: Static
EVs: 252 Atk / 252 Spe / 4 HP

Charizard @ Charcoal  
Ability: Blaze""")

# Show team analysis if submitted
else:
    # Add button to go back to input
    if st.button("← Analyze New Team"):
        st.session_state.submitted = False
        st.session_state.pokemon_names = []
        st.rerun()
    
    if st.session_state.pokemon_names:
        st.header("Your Team Analysis")
        
        # Display in 2 columns, 3 rows (6 Pokemon max)
        for row in range(3):
            cols = st.columns(2)
            
            for col_idx in range(2):
                pokemon_idx = row * 2 + col_idx
                
                if pokemon_idx < len(st.session_state.pokemon_names):
                    name = st.session_state.pokemon_names[pokemon_idx]
                    
                    with cols[col_idx]:
                        # Create a container for each Pokemon
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
                                st.subheader(format_pokemon_name(name))
                                st.write(get_pokemon_description(name))
                            
                            st.markdown("---")
    else:
        st.warning("No Pokemon detected. Try going back and pasting showdown format.")