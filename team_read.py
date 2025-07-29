import requests
from pprint import pprint

def slugify(name):
    return name.lower().replace(' ', '-').replace('.', '').replace("'", '')

def getType(name):
    url = f"https://pokeapi.co/api/v2/pokemon/{name.lower()}"
    res = requests.get(url)

    if res.status_code != 200:
        return []

    data = res.json()
    types = [t["type"]["name"].capitalize() for t in data["types"]]
    return types

def get_move_metadata(move_name):
    url = f"https://pokeapi.co/api/v2/move/{slugify(move_name)}"
    res = requests.get(url)
    if res.status_code != 200:
        return {'type': None, 'power': None, 'accuracy': None, 'category': None}
    
    data = res.json()
    return {
        'type': data['type']['name'].capitalize(),
        'power': data['power'],
        'accuracy': data['accuracy'],
        'category': data['damage_class']['name'].capitalize()
    }

def readTeam(teamRaw):
    team = {}
    teamRaw = teamRaw.strip().split('\n\n')

    for i, block in enumerate(teamRaw):
        lines = block.strip().split('\n')
        poke_data = {
            'Pokemon': '',
            'Type': [],
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

        for line in lines:
            line = line.strip()
            if '@' in line:
                poke_data['Pokemon'] = line.split('@')[0].strip()
                poke_data['Type'] = getType(slugify(poke_data['Pokemon']))
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
                    val, stat = ev.strip().split(' ')
                    poke_data['EVs'][stat] = int(val)
            elif line.endswith('Nature'):
                poke_data['Nature'] = line.replace('Nature', '').strip()
            elif line.startswith('-'):
                move_name = line.strip('-').strip()
                move_data = get_move_metadata(move_name)
                poke_data['Moves'].append({
                    'name': move_name,
                    **move_data
                })

        dmg_from, dmg_to = damageRelations(poke_data['Type'])
        poke_data['Damage From'] = dmg_from
        poke_data['Damage To'] = dmg_to

        team[i] = poke_data

    return team

def detectRole(team):
    
    hazard_moves = {"Stealth Rock", "Spikes", "Toxic Spikes", "Sticky Web"}
    removal_moves = {"Defog", "Rapid Spin", "Court Change"}
    setup_moves = {"Swords Dance", "Dragon Dance", "Calm Mind", "Nasty Plot", "Agility", "Bulk Up", "Quiver Dance"}
    support_moves = {"Wish", "Protect", "Heal Bell", "Aromatherapy", "Thunder Wave", "Taunt", "Toxic", "Leech Seed", "Encore", "Light Screen", "Reflect"}
    pivot_moves = {"U-turn", "Volt Switch", "Teleport"}
    recovery_moves = {"Recover", "Roost", "Slack Off", "Moonlight", "Soft-Boiled"}
    choice_items = {"choice scarf": "Speed Control","choice band": "Physical Breaker","choice specs": "Special Breaker"}

    for poke in team:
        moves = team[poke]["Moves"]
        
        #move based shi
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
        if any(move in moves for move in recovery_moves):
            if 'HP' in team[poke]["EVs"] and team[poke]["EVs"].get('Def',0)>100 or team[poke]["EVs"].get('SpD',0)>100:
                team[poke]["Roles"].append("Recovery")
        
        #stat based shi
        if team[poke]["EVs"].get("Atk", 0) >= 200:
            team[poke]["Roles"].append("Physical Sweeper")
        if team[poke]["EVs"].get("SpA", 0) >= 200:
            team[poke]["Roles"].append("Special Sweeper")

        #item based shi
        item = team[poke]["Item"].lower()
        if item in choice_items:
            team[poke]["Roles"].append(choice_items[item])
        if item=='Life Orb':
            team[poke]["Roles"].append("Wallbreaker")
        
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

team = readTeam(teamRaw)
detectRole(team)
addComments(team)
coverage = coverageCheck(team)
pprint(coverage)
# pprint(team,sort_dicts=False)