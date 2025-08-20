import streamlit as st
import re
import requests
from PIL import Image
from io import BytesIO

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
</style>
""", unsafe_allow_html=True)

st.title("MetaMatch")

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

def pokeSlugify(name):
    name = name.lower().replace(' ', '-').replace('.', '').replace("'", '').replace(':', '')
    
    name_x = {
        # Forms and variants
        "ogerpon-wellspring": "ogerpon-wellspring-mask",
        "ogerpon-hearthflame": "ogerpon-hearthflame-mask", 
        "ogerpon-cornerstone": "ogerpon-cornerstone-mask",
        "keldeo": "keldeo-ordinary",
        "enamorus": "enamorus-incarnate",
        "indeedee": "indeedee-male",
        "mimikyu": "mimikyu-disguised",
        "maushold": "maushold-family-of-four",
        "basculegion": "basculegion-male",
        "basculegion-f": "basculegion-female",
        "thundurus": "thundurus-incarnate",
        "tornadus": "tornadus-incarnate",
        "landorus": "landorus-incarnate",
        "aegislash": "aegislash-shield",
        "pumpkaboo": "pumpkaboo-average",
        "gourgeist": "gourgeist-average",
        "zygarde": "zygarde-50",
        "oricorio": "oricorio-baile",
        "lycanroc": "lycanroc-midday",
        "wishiwashi": "wishiwashi-solo",
        "toxapex": "toxapex",
        "minior": "minior-red-meteor",
        "necrozma": "necrozma",
        "urshifu": "urshifu-single-strike",
        "calyrex": "calyrex",
        
        # Paradox Pokemon
        "iron-treads": "iron-treads",
        "iron-bundle": "iron-bundle",
        "iron-hands": "iron-hands", 
        "iron-jugulis": "iron-jugulis",
        "iron-moth": "iron-moth",
        "iron-thorns": "iron-thorns",
        "iron-valiant": "iron-valiant",
        "iron-leaves": "iron-leaves",
        "iron-boulder": "iron-boulder",
        "iron-crown": "iron-crown",
        "roaring-moon": "roaring-moon",
        "sandy-shocks": "sandy-shocks", 
        "scream-tail": "scream-tail",
        "brute-bonnet": "brute-bonnet",
        "flutter-mane": "flutter-mane",
        "slither-wing": "slither-wing",
        "great-tusk": "great-tusk",
        "walking-wake": "walking-wake",
        "gouging-fire": "gouging-fire",
        "raging-bolt": "raging-bolt",
        
        # Special cases
        "nidoran-f": "nidoran-f",
        "nidoran-m": "nidoran-m",
        "mr-mime": "mr-mime",
        "farfetchd": "farfetchd",
        "ho-oh": "ho-oh",
        "porygon-z": "porygon-z",
        "jangmo-o": "jangmo-o",
        "hakamo-o": "hakamo-o", 
        "kommo-o": "kommo-o",
        "tapu-koko": "tapu-koko",
        "tapu-lele": "tapu-lele",
        "tapu-bulu": "tapu-bulu",
        "tapu-fini": "tapu-fini",
        "type-null": "type-null",
        "wo-chien": "wo-chien",
        "chien-pao": "chien-pao",
        "ting-lu": "ting-lu",
        "chi-yu": "chi-yu",
        
        "dundunsparce": "dudunsparce",
        "tatsugiri": "tatsugiri-stretchy",
    }
    
    return name_x.get(name, name)

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
            "Paste Pokemon Data",
            placeholder="Paste your raw pokemon data here...",
            height=300
        )
        
        submit_button = st.form_submit_button("Analyze Team")
        
        if submit_button and pokemon_data:
            st.session_state.pokemon_names = extract_pokemon_names(pokemon_data)
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
                                st.subheader(format_pokemon_name(name))
                                st.write(get_pokemon_description(name))
                            
                            st.markdown("---")
    else:
        st.warning("No Pokemon detected. Try going back and pasting showdown format.")