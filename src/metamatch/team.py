import requests
from pprint import pprint
import json
from .utils import fetch_pokemon_data, calculate_speed, pokeSlugify
from . import config

def get_move_metadata(move_name):
    # Keep this local for now or move to helper if needed later
    slug = move_name.lower().replace(' ', '-').replace("'", "")
    url = f"https://pokeapi.co/api/v2/move/{slug}"
    try:
        res = requests.get(url, timeout=2)
        if res.status_code != 200:
            return {'type': None, 'power': None, 'accuracy': None, 'category': None}
        
        data = res.json()
        return {
            'type': data['type']['name'].capitalize(),
            'power': data['power'],
            'accuracy': data['accuracy'],
            'category': data['damage_class']['name'].capitalize()
        }
    except:
        return {'type': None, 'power': None, 'accuracy': None, 'category': None}


def readTeam(teamRaw):
    team = {}
    teamRaw = teamRaw.strip().split('\n\n')
    
    types = ["normal", "fire", "water", "electric", "grass", "ice","fighting", "poison", "ground", "flying", "psychic", "bug","rock", "ghost", "dragon", "dark", "steel", "fairy"]
    team_weakness = {t: {"weak": 0, "resist": 0, "immune": 0} for t in types}
    
    # Speed Nature Modifiers
    speed_plus = ["Timid", "Jolly", "Hasty", "Naive"]
    speed_minus = ["Brave", "Relaxed", "Quiet", "Sassy"]

    for i, block in enumerate(teamRaw):
        lines = block.strip().split('\n')
        poke_data = {
            'Pokemon': '',
            'Type': [],
            'Base Stats': {}, # New
            'Speed': 0,       # New
            'Item': '',
            'Ability': '',
            'Shiny': False,
            'Tera Type': '',
            'EVs': {},
            'Nature': '',
            'Moves': [],
            'Roles': [],
            'Comments': [],
            'Damage To': {},
            'Damage From': {}
        }

        # 1. Parse Raw Text
        for line in lines:
            line = line.strip()
            if '@' in line:
                poke_data['Pokemon'] = line.split('@')[0].strip()
                poke_data['Item'] = line.split('@')[1].strip()
            elif line.startswith('Ability:'):
                poke_data['Ability'] = line.split('Ability:')[1].strip()
            elif line.startswith('Shiny:'):
                poke_data['Shiny'] = line.split('Shiny:')[1].strip().lower() == 'yes'
            elif line.startswith('Tera Type:'):
                poke_data['Tera Type'] = line.split('Tera Type:')[1].strip()
            elif line.startswith('EVs:'):
                evs = line.split('EVs:')[1].strip().split('/')
                for ev in evs:
                    parts = ev.strip().split(' ')
                    if len(parts) >= 2:
                        val = int(parts[0])
                        stat = parts[1]
                        poke_data['EVs'][stat] = val
            elif line.endswith('Nature'):
                poke_data['Nature'] = line.replace('Nature', '').strip()
            elif line.startswith('-'):
                move_name = line.strip('-').strip()
                move_data = get_move_metadata(move_name)
                poke_data['Moves'].append({
                    'name': move_name,
                    **move_data
                })

        # 2. Enrich with API Data (Types, Base Stats, Sprite)
        api_data = fetch_pokemon_data(poke_data['Pokemon'])
        if api_data:
            poke_data['Type'] = api_data['types']
            poke_data['Base Stats'] = api_data['stats']
            
            # 3. Calculate Real Speed
            base_spe = api_data['stats'].get('speed', 100)
            ev_spe = poke_data['EVs'].get('Spe', 0)
            nature_mod = 1.0
            if poke_data['Nature'] in speed_plus: nature_mod = 1.1
            elif poke_data['Nature'] in speed_minus: nature_mod = 0.9
            
            poke_data['Speed'] = calculate_speed(base_spe, ev_spe, 31, nature_mod, poke_data['Item'])
        else:
            # Fallback if API fails
            poke_data['Type'] = [] 
            poke_data['Speed'] = 0

        # 4. Calculate Weaknesses (Resisting existing logic)
        dmg_from, dmg_to = damageRelations(poke_data['Type'])
        
        # --- Apply Ability/Item Immunities ---
        ability = poke_data['Ability'].lower()
        item = poke_data['Item'].lower()

        # Ground Immunities
        if 'levitate' in ability or 'earth eater' in ability or item == 'air balloon':
            dmg_from['ground'] = 0.0
            
        # Electric Immunities
        if ability in ['volt absorb', 'lightning rod', 'motor drive']:
            dmg_from['electric'] = 0.0
            
        # Water Immunities
        if ability in ['water absorb', 'storm drain', 'dry skin']:
            dmg_from['water'] = 0.0
            
        # Fire Immunities
        if ability in ['flash fire', 'well-baked body']:
            dmg_from['fire'] = 0.0
            
        # Grass Immunities
        if ability == 'sap sipper':
            dmg_from['grass'] = 0.0
        # -------------------------------------

        poke_data['Damage From'] = dmg_from
        poke_data['Damage To'] = dmg_to

        for dmg in dmg_from:
            if dmg_from[dmg] > 1:
                team_weakness[dmg]['weak'] += 1
            elif dmg_from[dmg] == 0:
                team_weakness[dmg]['immune'] += 1
            elif dmg_from[dmg] < 1:
                team_weakness[dmg]['resist'] += 1

        team[i] = poke_data


    return team,team_weakness


def detectRole(team):
    
    hazard_moves = {"Stealth Rock", "Spikes", "Toxic Spikes", "Sticky Web"}
    removal_moves = {"Defog", "Rapid Spin", "Court Change", "Tidy Up"}
    setup_moves = {"Swords Dance", "Dragon Dance", "Calm Mind", "Nasty Plot", "Agility", "Bulk Up", "Quiver Dance", "Shell Smash", "Shift Gear", "Coil"}
    support_moves = {"Wish", "Protect", "Heal Bell", "Aromatherapy", "Thunder Wave", "Taunt", "Toxic", "Leech Seed", "Encore", "Light Screen", "Reflect", "Aurora Veil", "Memento", "Parting Shot", "Healing Wish", "Lunar Dance"}
    pivot_moves = {"U-turn", "Volt Switch", "Teleport", "Baton Pass", "Parting Shot", "Chilly Reception"}
    recovery_moves = {"Recover", "Roost", "Slack Off", "Moonlight", "Soft-Boiled", "Rest", "Shore Up", "Synthesis", "Morning Sun"}
    status_moves = {"Will-O-Wisp", "Toxic", "Thunder Wave", "Sleep Powder", "Spore", "Glare", "Nuzzle"}
    priority_moves = {"Aqua Jet", "Bullet Punch", "Ice Shard", "Mach Punch", "Shadow Sneak", "Sucker Punch", "Extreme Speed", "First Impression"}
    revenge_moves = {"Sucker Punch", "Ice Shard", "Bullet Punch", "Mach Punch", "Aqua Jet"}
    contact_punish = {"Rough Skin", "Iron Barbs", "Rocky Helmet", "Flame Body", "Static", "Poison Point"}
    trapping_moves = {"Block", "Mean Look", "Spider Web", "Shadow Tag", "Arena Trap", "Magnet Pull"}
    entry_hazard_immune = {"Magic Guard", "Heavy-Duty Boots"}
    ko_moves = {"Destiny Bond", "Explosion", "Self-Destruct", "Final Gambit", "Memento"}
    cleric_moves = {"Heal Bell", "Aromatherapy", "Refresh", "Natural Cure"}
    screen_moves = {"Light Screen", "Reflect", "Aurora Veil"}
    trickroom_moves = {"Trick Room"}
    spinblock_types = {"Ghost"}
    weather_abilities = {"Swift Swim": "rain", "Chlorophyll": "sun", "Sand Rush": "sand", "Sand Force": "sand", "Sand Veil": "sand", "Slush Rush": "hail", "Snow Cloak": "hail", "Solar Power": "sun"}
    choice_items = {"choice scarf": "Speed Control","choice band": "Physical Breaker","choice specs": "Special Breaker"}
    defensive_items = {"leftovers", "rocky helmet", "assault vest", "eviolite", "heavy-duty boots"}
    offensive_items = {"life orb", "expert belt", "muscle band", "wise glasses"}
    utility_items = {"mental herb", "lum berry", "sitrus berry", "wiki berry", "mago berry", "aguav berry", "figy berry", "iapapa berry"}

    for poke in team:
        moves = team[poke]["Moves"]
        item = team[poke]["Item"].lower()
        ability = team[poke].get("Ability", "").lower()
        nature = team[poke].get("Nature", "")
        evs = team[poke]["EVs"]
        
        # Core roles
        if any(move in moves for move in hazard_moves):
            team[poke]["Roles"].append("Hazard Setter")
        if any(move in moves for move in removal_moves):
            team[poke]["Roles"].append("Hazard Remover")
        if any(move in moves for move in setup_moves):
            team[poke]["Roles"].append("Setup Sweeper")
        if any(move in moves for move in support_moves):
            team[poke]["Roles"].append("Support")
        if any(move in moves for move in pivot_moves):
            team[poke]["Roles"].append("Pivot")
        
        # Defensive roles
        if any(move in moves for move in recovery_moves):
            if evs.get('HP', 0) > 100 or evs.get('Def', 0) > 200 or evs.get('SpD', 0) > 200:
                team[poke]["Roles"].append("Wall")
        if (evs.get('HP', 0) + evs.get('Def', 0) + evs.get('SpD', 0)) >= 400:
            team[poke]["Roles"].append("Tank")
        if item == "assault vest":
            team[poke]["Roles"].append("Special Tank")
        if any(move in moves for move in status_moves) and (evs.get('HP', 0) > 150 or evs.get('Def', 0) > 150):
            team[poke]["Roles"].append("Status Spreader")
        
        # Offensive roles
        if evs.get("Atk", 0) >= 252:
            team[poke]["Roles"].append("Physical Sweeper")
        if evs.get("SpA", 0) >= 252:
            team[poke]["Roles"].append("Special Sweeper")
        if evs.get("Spe", 0) >= 252 and (evs.get("Atk", 0) >= 200 or evs.get("SpA", 0) >= 200):
            team[poke]["Roles"].append("Fast Sweeper")
        if any(move in moves for move in priority_moves):
            team[poke]["Roles"].append("Priority User")
        if any(move in moves for move in revenge_moves):
            team[poke]["Roles"].append("Revenge Killer")
        
        # Specialized roles
        if item in choice_items:
            team[poke]["Roles"].append(choice_items[item])
        if item == "life orb" or item in offensive_items:
            team[poke]["Roles"].append("Wallbreaker")
        if "Prankster" in ability and any(move in moves for move in support_moves):
            team[poke]["Roles"].append("Prankster Support")
        if item == "focus sash" and evs.get("Spe", 0) >= 200:
            team[poke]["Roles"].append("Lead")
        if "Intimidate" in ability:
            team[poke]["Roles"].append("Intimidate Support")
        if item == "rocky helmet" or ability in ["rough skin", "iron barbs"]:
            team[poke]["Roles"].append("Contact Punisher")
        if "Magic Bounce" in ability or "Mirror Armor" in ability:
            team[poke]["Roles"].append("Status Absorber")
        if evs.get("HP", 0) >= 252 and (evs.get("Atk", 0) >= 100 or evs.get("SpA", 0) >= 100):
            team[poke]["Roles"].append("Bulky Attacker")
            
        # Weather/Terrain setters
        weather_moves = {"Sunny Day", "Rain Dance", "Sandstorm", "Hail", "Snow"}
        terrain_moves = {"Electric Terrain", "Grassy Terrain", "Misty Terrain", "Psychic Terrain"}
        
        if any(move in moves for move in weather_moves):
            team[poke]["Roles"].append("Weather Setter")
        if any(move in moves for move in terrain_moves):
            team[poke]["Roles"].append("Terrain Setter")
            
        # Advanced utility roles
        if any(move in moves for move in trapping_moves) or "Shadow Tag" in ability or "Arena Trap" in ability or "Magnet Pull" in ability:
            team[poke]["Roles"].append("Trapper")
        if any(move in moves for move in ko_moves):
            team[poke]["Roles"].append("Sacrificial")
        if any(move in moves for move in cleric_moves) or "Natural Cure" in ability:
            team[poke]["Roles"].append("Cleric")
        if any(move in moves for move in screen_moves):
            team[poke]["Roles"].append("Screen Setter")
        if any(move in moves for move in trickroom_moves):
            team[poke]["Roles"].append("Trick Room Setter")
            
        # Mixed attackers
        if evs.get("Atk", 0) >= 100 and evs.get("SpA", 0) >= 100:
            team[poke]["Roles"].append("Mixed Attacker")
            
        # Weather abusers
        if ability in weather_abilities:
            team[poke]["Roles"].append("Weather Abuser")
        if "Ghost" in team[poke].get("Types", []):
            team[poke]["Roles"].append("Spin Blocker")
        if item == "heavy-duty boots" or "Magic Guard" in ability:
            team[poke]["Roles"].append("Hazard Immune")
        if "Regenerator" in ability:
            team[poke]["Roles"].append("Pivot")  # Natural pivoting ability
        if "Guts" in ability or "Quick Feet" in ability:
            team[poke]["Roles"].append("Status Absorber")
        if evs.get("HP", 0) <= 4 and evs.get("Def", 0) <= 4 and evs.get("SpD", 0) <= 4:
            team[poke]["Roles"].append("Glass Cannon")
            
        # Mixed attackers
        if evs.get("Atk", 0) >= 100 and evs.get("SpA", 0) >= 100:
            team[poke]["Roles"].append("Mixed Attacker")
            
        # Utility items
        if item in utility_items:
            team[poke]["Roles"].append("Utility")
            
        # Z-Move/Tera
        if "Z-" in item:
            team[poke]["Roles"].append("Z-Move User")
            
        # Speed control
        if evs.get("Spe", 0) >= 252 and any(move in ["Sticky Web", "Thunder Wave", "Icy Wind"] for move in moves):
            team[poke]["Roles"].append("Speed Control")
            
        # Baton Pass chains
        if "Baton Pass" in moves and any(move in setup_moves for move in moves):
            team[poke]["Roles"].append("Baton Passer")
            
            
        team[poke]["Roles"] = list(set(team[poke]["Roles"]))
        
    return team


def addComments(team):
    
    tera_types = ["normal", "fire", "water", "electric", "grass", "ice","fighting", "poison", "ground", "flying", "psychic", "bug","rock", "ghost", "dragon", "dark", "steel", "fairy"]
    
    for poke in team:
        
        if len(team[poke]["Moves"]) != 4:
            team[poke]["Comments"].append("Missing moves")
        if sum(team[poke]["EVs"].values()) != 508:
            team[poke]["Comments"].append("Missing EV values")
        if team[poke]["Item"] == "":
            team[poke]["Comments"].append("Has no item")
        if team[poke]["Tera Type"].lower() not in tera_types:
            team[poke]["Comments"].append("Has improper tera type")


def damageRelations(ptypes):
    
    # print(ptypes)
    damage_d = {}
    attack_d = {}
    for ptype in ptypes:
        url = f"https://pokeapi.co/api/v2/type/{ptype.lower()}"
        res = requests.get(url)

        if res.status_code != 200:
            return []

        data = res.json()
        # print(data['damage_relations'].keys())
        
        dvals = data['damage_relations']['double_damage_from'] #weakness
        hdvals = data['damage_relations']['half_damage_from'] #resists
        ndvals = data['damage_relations']['no_damage_from'] #immunity
        
        rvals = data['damage_relations']['double_damage_to']
        hrdata = data['damage_relations']['half_damage_to']
        ndrvals = data['damage_relations']['no_damage_to']
        
        for d in dvals:
            if d['name'] not in damage_d:
                damage_d[d['name']] = 2
            else:
                damage_d[d['name']] *= 2
        for d in hdvals:
            if d['name'] not in damage_d:
                damage_d[d['name']] = 0.5
            else:
                damage_d[d['name']] *= 0.5
        for d in ndvals:
            damage_d[d['name']] = 0.0
            
        
        for d in rvals: #supereff dmg to
            if d['name'] not in attack_d:
                attack_d[d['name']] = 2
            else:
                attack_d[d['name']] *= 2
        for d in hrdata: #half dmg to
            if d['name'] not in attack_d:
                attack_d[d['name']] = 0.5
            else:
                attack_d[d['name']] *= 0.5
        for d in ndrvals: #no dmg to
            attack_d[d['name']] = 0.0
    
    return damage_d,attack_d


def coverageCheck(team):
    
    coverage = {'Normal': False,'Fire': False,'Water': False,'Electric': False,'Grass': False,'Ice': False,'Fighting': False,
    'Poison': False,'Ground': False,'Flying': False,'Psychic': False,'Bug': False,'Rock': False,
    'Ghost': False,'Dragon': False,'Dark': False,'Steel': False,'Fairy': False}
    
    for poke in team:
        moves = team[poke]['Moves']
        for move in moves:
            if (move['category'] != 'Status') &  (coverage[move['type']] == False):
                coverage[move['type']] = True
        
    return coverage


def save_analysis(team, coverage, team_weakness):
    with open(config.JSON_DIR / "team.json", "w") as f:
        json.dump(team, f, indent=2)
    with open(config.JSON_DIR / "coverage.json", "w") as f:
        json.dump(coverage, f, indent=2)
    with open(config.JSON_DIR / "team_weak.json","w") as f:
        json.dump(team_weakness,f,indent=2)


if __name__ == "__main__":
    teamRaw = """Araquanid @ Mental Herb  
    Ability: Water Bubble  
    Shiny: Yes  
    Tera Type: Ghost  
    EVs: 252 HP / 252 Def / 4 SpD  
    Impish Nature  
    - Lunge  
    - Liquidation  
    - Sticky Web  
    - Endeavor

    Cinderace @ Shuca Berry  
    Ability: Blaze  
    Tera Type: Fairy
    EVs: 252 Atk / 4 Def / 252 Spe  
    Jolly Nature  
    - Swords Dance  
    - Pyro Ball  
    - Gunk Shot  
    - Sucker Punch  

    Kingambit @ Black Glasses  
    Ability: Supreme Overlord  
    Tera Type: Dark  
    EVs: 252 Atk / 4 SpD / 252 Spe  
    Adamant Nature  
    - Swords Dance  
    - Kowtow Cleave  
    - Iron Head  
    - Sucker Punch  

    Dragonite @ Lum Berry  
    Ability: Multiscale  
    Tera Type: Ground  
    EVs: 252 Atk / 4 SpD / 252 Spe  
    Adamant Nature      
    - Earthquake  
    - Dragon Tail  

    Iron Treads @ Booster  
    Ability: Quark Drive  
    Tera Type: Ghost  
    EVs: 252 Atk / 4 SpD / 252 Spe  
    Adamant Nature  
    - Rapid Spin  
    - Iron Head  
    - Supercell Slam  

    Pecharunt @ Air Balloon  
    Ability: Poison Puppeteer  
    Tera Type: Fighting  
    EVs: 252 SpA / 4 SpD / 252 Spe  
    Timid Nature  
    - Nasty Plot  
    - Shadow Ball  
    - Malignant Chain 
    - Tera Blast
    """ 

    team,team_weakness = readTeam(teamRaw)
    detectRole(team)
    addComments(team)
    coverage = coverageCheck(team)
    save_analysis(team, coverage, team_weakness)
