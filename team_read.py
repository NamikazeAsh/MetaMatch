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
        if any(move in moves for move in recovery_moves): #REWORK This shit lil bro, ts dont make sense
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
        
        
    print(team)
    return team

def readTeam(teamRaw):
    team = {}
    teamRaw = teamRaw.strip().split('\n\n')

    for i, block in enumerate(teamRaw):
        lines = block.strip().split('\n')
        poke_data = {
            'Pokemon': '',
            'Item': '',
            'Ability': '',
            'Shiny': False,
            'Tera Type': '',
            'EVs': {},
            'Nature': '',
            'Moves': [],
            'Roles':[],
            'Comments':[]
        }

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
                    val, stat = ev.strip().split(' ')
                    poke_data['EVs'][stat] = int(val)
            elif line.endswith('Nature'):
                poke_data['Nature'] = line.replace('Nature', '').strip()
            elif line.startswith('-'):
                poke_data['Moves'].append(line.strip('-').strip())

        team[i] = poke_data

    return team



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