import streamlit as st
import re
import requests
from PIL import Image
from io import BytesIO

st.set_page_config(page_title="MetaMatch", page_icon="⚪")
st.title("MetaMatch")

# Input field for raw pokemon data
pokemon_data = st.text_area(
    "Paste Pokemon Data:",
    placeholder="Paste your raw pokemon data here...",
    height=300
)

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
        
        # Common typos/alternatives
        "dundunsparce": "dudunsparce",
        "tatsugiri": "tatsugiri-stretchy",
    }
    
    return name_x.get(name, name)

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

if pokemon_data:
    pokemon_names = extract_pokemon_names(pokemon_data)
    
    if pokemon_names:
        st.subheader("Your team:")
        
        # Display in columns for better layout (3 per row)
        cols = st.columns(3)
        
        for idx, name in enumerate(pokemon_names):
            col_idx = idx % 3
            col = cols[col_idx]
            
            with col:
                sprite_url = get_pokemon_sprite(name)
                
                if sprite_url:
                    try:
                        response = requests.get(sprite_url)
                        img = Image.open(BytesIO(response.content))
                        st.image(img, width=100)
                    except:
                        st.text("🔲")  # Fallback if image fails
                else:
                    st.text("🔲")  # Fallback if no sprite
                
                st.text(format_pokemon_name(name))
            
            # Add expand icon aligned to the right of the row
            if col_idx == 2 or idx == len(pokemon_names) - 1:
                st.markdown("---")
    else:
        st.warning("No Pokemon detected. Try pasting showdown format or similar.")
else:
    st.info("Paste your Pokemon data in Showdown's format for analysis & suggestions")

# Example format hint
with st.expander("Supported Data Formats"):
    st.code("""
Example formats:
    
Pikachu @ Light Ball
Ability: Static
EVs: 252 Atk / 252 Spe / 4 HP

Charizard @ Charcoal  
Ability: Blaze""")