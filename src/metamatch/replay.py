"""
Replay Auditor Module
Parses Pokémon Showdown replay logs and provides tactical analysis.
"""

import re
import requests
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Pokemon:
    """Represents a Pokemon's state during battle."""
    species: str
    nickname: str
    hp: int = 100
    max_hp: int = 100
    status: Optional[str] = None
    fainted: bool = False
    boosts: dict = field(default_factory=dict)
    
    def hp_percent(self) -> int:
        return int((self.hp / self.max_hp) * 100) if self.max_hp > 0 else 0


@dataclass 
class TurnEvent:
    """Represents significant events in a turn."""
    turn: int
    event_type: str  # 'move', 'switch', 'faint', 'damage', etc.
    player: str      # 'p1' or 'p2'
    pokemon: str
    details: str
    hp_before: Optional[int] = None
    hp_after: Optional[int] = None


@dataclass
class BattleState:
    """Tracks the full battle state."""
    p1_team: dict = field(default_factory=dict)  # species -> Pokemon
    p2_team: dict = field(default_factory=dict)
    p1_active: Optional[str] = None
    p2_active: Optional[str] = None
    weather: Optional[str] = None
    terrain: Optional[str] = None
    hazards: dict = field(default_factory=lambda: {'p1': set(), 'p2': set()})
    turn: int = 0
    events: list = field(default_factory=list)
    faints: dict = field(default_factory=lambda: {'p1': [], 'p2': []})
    winner: Optional[str] = None  # 'p1', 'p2', or None
    winner_name: Optional[str] = None  # The actual username
    p1_name: str = 'Player 1'
    p2_name: str = 'Player 2'
    # New tracking fields
    setup_moves_used: dict = field(default_factory=lambda: {'p1': [], 'p2': []})  # [{turn, pokemon, move}]
    boosts_gained: dict = field(default_factory=lambda: {'p1': [], 'p2': []})  # [{turn, pokemon, stat, amount}]
    hazard_damage: dict = field(default_factory=lambda: {'p1': {}, 'p2': {}})  # {pokemon: total_damage}
    weather_setter: dict = field(default_factory=lambda: {'p1': None, 'p2': None})  # Current weather setter
    weather_history: list = field(default_factory=list)  # [{turn, weather, setter_player, setter_pokemon}]
    moves_used: dict = field(default_factory=lambda: {'p1': {}, 'p2': {}})  # {pokemon: [moves]}


@dataclass
class BlunderReport:
    """Represents a detected misplay."""
    turn: int
    severity: str  # 'minor', 'moderate', 'critical'
    description: str
    suggestion: str
    context: dict = field(default_factory=dict)


def fetch_replay(url: str) -> Optional[dict]:
    """
    Fetches replay data from Pokémon Showdown.
    Accepts full URL or just the replay ID.
    """
    # Extract replay ID from URL if needed
    if 'replay.pokemonshowdown.com' in url:
        replay_id = url.rstrip('/').split('/')[-1]
    else:
        replay_id = url.strip()
    
    # Remove .json extension if present
    replay_id = replay_id.replace('.json', '')
    
    api_url = f"https://replay.pokemonshowdown.com/{replay_id}.json"
    
    try:
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"Error fetching replay: {e}")
        return None


def parse_hp(hp_str: str) -> tuple[int, int]:
    """
    Parse HP string like '75/100' or '75%' or just '75'.
    Returns (current_hp, max_hp) as percentages.
    """
    hp_str = hp_str.split()[0]  # Remove status like 'par'
    
    if '/' in hp_str:
        parts = hp_str.split('/')
        current = int(parts[0])
        max_hp = int(parts[1]) if len(parts) > 1 else 100
        # Normalize to percentage
        if max_hp != 100:
            current = int((current / max_hp) * 100)
            max_hp = 100
        return current, max_hp
    elif hp_str.endswith('%'):
        return int(hp_str.rstrip('%')), 100
    else:
        try:
            return int(hp_str), 100
        except:
            return 0, 100


def parse_pokemon_slot(slot_str: str) -> tuple[str, str]:
    """
    Parse slot string like 'p1a: Tyranitar' -> ('p1', 'Tyranitar')
    """
    match = re.match(r'(p[12])[a-c]?: (.+)', slot_str)
    if match:
        return match.group(1), match.group(2)
    return 'p1', slot_str


def parse_replay_log(log: str, p1_name: str = "p1", p2_name: str = "p2") -> BattleState:
    """
    Parses the battle log and builds a complete battle state history.
    """
    state = BattleState()
    state.p1_name = p1_name
    state.p2_name = p2_name
    lines = log.strip().split('\n')
    
    current_turn = 0
    # Track last move used (to attribute KOs)
    last_move = {'player': None, 'pokemon': None, 'move': None}
    # Track last damage dealt to each side (for faint damage display)
    last_damage = {'p1': 0, 'p2': 0}
    
    for line in lines:
        if not line.startswith('|'):
            continue
            
        parts = line.split('|')
        if len(parts) < 2:
            continue
        
        cmd = parts[1]
        args = parts[2:] if len(parts) > 2 else []
        
        # Track turns
        if cmd == 'turn':
            current_turn = int(args[0]) if args else current_turn + 1
            state.turn = current_turn
            
        # Team preview - initial team info
        elif cmd == 'poke':
            player = args[0]  # 'p1' or 'p2'
            species_info = args[1] if len(args) > 1 else ''
            species = species_info.split(',')[0].strip()
            
            team = state.p1_team if player == 'p1' else state.p2_team
            team[species] = Pokemon(species=species, nickname=species)
            
        # Switch/drag
        elif cmd in ('switch', 'drag'):
            if len(args) >= 2:
                player, nickname = parse_pokemon_slot(args[0])
                species_info = args[1]
                species = species_info.split(',')[0].strip()
                hp_str = args[2] if len(args) > 2 else '100/100'
                
                hp, max_hp = parse_hp(hp_str)
                
                team = state.p1_team if player == 'p1' else state.p2_team
                
                if species not in team:
                    team[species] = Pokemon(species=species, nickname=nickname)
                
                team[species].hp = hp
                team[species].nickname = nickname
                
                if player == 'p1':
                    state.p1_active = species
                else:
                    state.p2_active = species
                
                state.events.append(TurnEvent(
                    turn=current_turn,
                    event_type='switch',
                    player=player,
                    pokemon=species,
                    details=f"Sent out {species}",
                    hp_after=hp
                ))
        
        # Moves
        elif cmd == 'move':
            if len(args) >= 2:
                player, pokemon = parse_pokemon_slot(args[0])
                move_name = args[1]
                target = args[2] if len(args) > 2 else ''
                
                # Track last move for KO attribution
                # Get the actual species name for the user
                if player == 'p1':
                    attacker_species = state.p1_active or pokemon
                else:
                    attacker_species = state.p2_active or pokemon
                
                last_move = {'player': player, 'pokemon': attacker_species, 'move': move_name}
                
                # Track moves used per Pokemon
                if attacker_species not in state.moves_used[player]:
                    state.moves_used[player][attacker_species] = []
                if move_name not in state.moves_used[player][attacker_species]:
                    state.moves_used[player][attacker_species].append(move_name)
                
                # Track setup moves
                setup_moves = [
                    'swords dance', 'dragon dance', 'nasty plot', 'calm mind', 'quiver dance',
                    'bulk up', 'iron defense', 'amnesia', 'agility', 'rock polish', 'shell smash',
                    'coil', 'shift gear', 'belly drum', 'curse', 'growth', 'work up', 'hone claws',
                    'tail glow', 'geomancy', 'cotton guard', 'cosmic power', 'stockpile',
                    'victory dance', 'clangorous soul', 'no retreat', 'howl', 'swords dance'
                ]
                if move_name.lower() in setup_moves:
                    state.setup_moves_used[player].append({
                        'turn': current_turn,
                        'pokemon': attacker_species,
                        'move': move_name
                    })
                
                state.events.append(TurnEvent(
                    turn=current_turn,
                    event_type='move',
                    player=player,
                    pokemon=pokemon,
                    details=f"used {move_name}" + (f" on {target}" if target and '|' not in target else '')
                ))
        
        # Damage
        elif cmd == '-damage':
            if len(args) >= 2:
                player, pokemon = parse_pokemon_slot(args[0])
                hp_str = args[1]
                hp, _ = parse_hp(hp_str)
                
                team = state.p1_team if player == 'p1' else state.p2_team
                species = state.p1_active if player == 'p1' else state.p2_active
                
                if species and species in team:
                    hp_before = team[species].hp
                    team[species].hp = hp
                    
                    # Track damage for faint attribution
                    damage_dealt = hp_before - hp
                    last_damage[player] = damage_dealt
                    
                    # Check for hazard damage (Stealth Rock, Spikes, etc.)
                    damage_source = args[2] if len(args) > 2 else ''
                    hazard_sources = ['stealth rock', 'spikes', 'toxic spikes', 'g-max steelsurge']
                    is_hazard_damage = any(h in damage_source.lower() for h in hazard_sources)
                    
                    if is_hazard_damage and damage_dealt > 0:
                        if species not in state.hazard_damage[player]:
                            state.hazard_damage[player][species] = 0
                        state.hazard_damage[player][species] += damage_dealt
                    
                    # Check for faint
                    if hp == 0:
                        team[species].fainted = True
                    
                    state.events.append(TurnEvent(
                        turn=current_turn,
                        event_type='damage',
                        player=player,
                        pokemon=species,
                        details=f"took damage" + (f" from hazards" if is_hazard_damage else ""),
                        hp_before=hp_before,
                        hp_after=hp
                    ))
        
        # Healing
        elif cmd == '-heal':
            if len(args) >= 2:
                player, pokemon = parse_pokemon_slot(args[0])
                hp_str = args[1]
                hp, _ = parse_hp(hp_str)
                
                team = state.p1_team if player == 'p1' else state.p2_team
                species = state.p1_active if player == 'p1' else state.p2_active
                
                if species and species in team:
                    team[species].hp = hp
        
        # Faint
        elif cmd == 'faint':
            if args:
                player, pokemon = parse_pokemon_slot(args[0])
                species = state.p1_active if player == 'p1' else state.p2_active
                
                team = state.p1_team if player == 'p1' else state.p2_team
                if species and species in team:
                    team[species].fainted = True
                    team[species].hp = 0
                
                # Determine what caused the KO
                killer_pokemon = None
                killer_move = None
                killing_damage = last_damage.get(player, 0)
                is_self_ko = False
                
                # Self-KO moves (user faints after using these)
                self_ko_moves = ['explosion', 'self-destruct', 'selfdestruct', 'misty explosion', 
                                 'final gambit', 'healing wish', 'lunar dance', 'memento']
                
                if last_move['player'] and last_move['player'] != player:
                    # Killed by opponent's move
                    killer_pokemon = last_move['pokemon']
                    killer_move = last_move['move']
                elif last_move['player'] and last_move['player'] == player:
                    # Check if it's a self-KO move (Explosion, Self-Destruct, etc.)
                    if last_move['move'] and last_move['move'].lower().replace(' ', '') in [m.replace(' ', '').replace('-', '') for m in self_ko_moves]:
                        killer_pokemon = last_move['pokemon']
                        killer_move = last_move['move']
                        is_self_ko = True
                
                state.faints[player].append({
                    'turn': current_turn,
                    'species': species or pokemon,
                    'killed_by': killer_pokemon,
                    'move': killer_move,
                    'damage': killing_damage,
                    'self_ko': is_self_ko
                })
                
                state.events.append(TurnEvent(
                    turn=current_turn,
                    event_type='faint',
                    player=player,
                    pokemon=species or pokemon,
                    details="fainted"
                ))
        
        # Weather
        elif cmd == '-weather':
            if args:
                weather = args[0]
                if weather == 'none':
                    state.weather = None
                    state.weather_setter = {'p1': None, 'p2': None}
                elif '[upkeep]' not in line:
                    state.weather = weather
                    # Track who set the weather
                    setter_player = None
                    setter_pokemon = None
                    for arg in args:
                        if '[of]' in arg:
                            # Extract player and pokemon from [of] p2a: Torkoal
                            of_part = arg.replace('[of]', '').strip()
                            setter_player, setter_pokemon = parse_pokemon_slot(of_part)
                            break
                    
                    if setter_player:
                        state.weather_setter[setter_player] = setter_pokemon
                        # Clear opponent's weather setter since weather changed
                        opp = 'p2' if setter_player == 'p1' else 'p1'
                        state.weather_setter[opp] = None
                        
                        state.weather_history.append({
                            'turn': current_turn,
                            'weather': weather,
                            'setter_player': setter_player,
                            'setter_pokemon': setter_pokemon
                        })
        
        # Boosts
        elif cmd == '-boost':
            if len(args) >= 3:
                player, pokemon = parse_pokemon_slot(args[0])
                stat = args[1]
                amount = int(args[2]) if args[2].isdigit() else 1
                
                species = state.p1_active if player == 'p1' else state.p2_active
                state.boosts_gained[player].append({
                    'turn': current_turn,
                    'pokemon': species or pokemon,
                    'stat': stat,
                    'amount': amount
                })
        
        # Hazards
        elif cmd == '-sidestart':
            if len(args) >= 2:
                side = args[0].split(':')[0] if ':' in args[0] else args[0]
                hazard = args[1].replace('move: ', '')
                player = 'p1' if 'p1' in side else 'p2'
                state.hazards[player].add(hazard)
                
        elif cmd == '-sideend':
            if len(args) >= 2:
                side = args[0].split(':')[0] if ':' in args[0] else args[0]
                hazard = args[1].replace('move: ', '')
                player = 'p1' if 'p1' in side else 'p2'
                state.hazards[player].discard(hazard)
        
        # Status
        elif cmd == '-status':
            if len(args) >= 2:
                player, pokemon = parse_pokemon_slot(args[0])
                status = args[1]
                
                team = state.p1_team if player == 'p1' else state.p2_team
                species = state.p1_active if player == 'p1' else state.p2_active
                
                if species and species in team:
                    team[species].status = status

        # Cure status
        elif cmd == '-curestatus':
            if len(args) >= 2:
                player, pokemon = parse_pokemon_slot(args[0])
                
                team = state.p1_team if player == 'p1' else state.p2_team
                species = state.p1_active if player == 'p1' else state.p2_active
                
                if species and species in team:
                    team[species].status = None
        
        # Winner declaration (handles forfeits, timer, disconnects, KOs)
        elif cmd == 'win':
            if args:
                winner_name = args[0].strip()
                state.winner_name = winner_name
                # Map winner name to p1/p2
                if winner_name.lower() == p1_name.lower():
                    state.winner = 'p1'
                elif winner_name.lower() == p2_name.lower():
                    state.winner = 'p2'
                else:
                    # Fallback: check partial match
                    if p1_name.lower() in winner_name.lower() or winner_name.lower() in p1_name.lower():
                        state.winner = 'p1'
                    elif p2_name.lower() in winner_name.lower() or winner_name.lower() in p2_name.lower():
                        state.winner = 'p2'
    
    return state


def detect_blunders(state: BattleState, user_player: str = 'p1') -> list[BlunderReport]:
    """
    Analyzes the battle state to detect potential misplays.
    """
    blunders = []
    opponent = 'p2' if user_player == 'p1' else 'p1'
    user_team = state.p1_team if user_player == 'p1' else state.p2_team
    opp_team = state.p2_team if user_player == 'p1' else state.p1_team
    
    # --- 1. LOST ONLY HAZARD REMOVER ---
    hazard_removers = set()
    for species, poke in user_team.items():
        spinner_species = ['great tusk', 'excadrill', 'iron treads', 'forretress', 
                          'tentacruel', 'donphan', 'claydol', 'armaldo', 'tsareena']
        defogger_species = ['corviknight', 'mandibuzz', 'skarmory', 'moltres', 
                           'tornadus', 'landorus', 'gliscor', 'pelipper', 'zapdos']
        
        if species.lower() in spinner_species or species.lower() in defogger_species:
            hazard_removers.add(species)
    
    hazards_up_turns = set()
    for event in state.events:
        if state.hazards.get(user_player):
            hazards_up_turns.add(event.turn)
    
    for faint_data in state.faints.get(user_player, []):
        species = faint_data['species']
        turn = faint_data['turn']
        
        if species in hazard_removers and turn in hazards_up_turns:
            remaining_removers = [s for s in hazard_removers 
                                  if s != species and not user_team.get(s, Pokemon(species='')).fainted]
            
            if not remaining_removers:
                blunders.append(BlunderReport(
                    turn=turn,
                    severity='critical',
                    description=f"{species} fainted while it was your only hazard removal.",
                    suggestion=f"Preserve {species} until hazards are cleared, or trade it more carefully.",
                    context={'hazards': list(state.hazards.get(user_player, set()))}
                ))
    
    # --- 2. SETUP FODDER (Opponent used setup moves without punishment) ---
    opp_setups = state.setup_moves_used.get(opponent, [])
    for setup in opp_setups:
        setup_turn = setup['turn']
        setup_mon = setup['pokemon']
        setup_move = setup['move']
        
        # Check if the setup mon survived and got more boosts or KO'd something after
        mon_faints = [f for f in state.faints.get(opponent, []) if f['species'] == setup_mon]
        if not mon_faints:
            # The setup mon survived the game - that's bad
            boosts_after = [b for b in state.boosts_gained.get(opponent, []) 
                          if b['pokemon'] == setup_mon and b['turn'] >= setup_turn]
            if len(boosts_after) >= 2:  # Got multiple boosts off
                blunders.append(BlunderReport(
                    turn=setup_turn,
                    severity='moderate',
                    description=f"Opponent's {setup_mon} used {setup_move} and got multiple boosts off.",
                    suggestion=f"Consider attacking or forcing a switch when opponent sets up. Phaze moves or priority can help.",
                    context={'setup_pokemon': setup_mon, 'move': setup_move}
                ))
    
    # --- 3. WASTED SWEEPER (Your setup mon died without using setup moves) ---
    setup_pokemon = ['dragonite', 'volcarona', 'salamence', 'gyarados', 'kingambit',
                    'iron valiant', 'roaring moon', 'walking wake', 'iron moth',
                    'quaquaval', 'espathra', 'lucario', 'blaziken', 'baxcalibur']
    
    for faint_data in state.faints.get(user_player, []):
        species = faint_data['species']
        turn = faint_data['turn']
        
        if species.lower() in setup_pokemon:
            # Check if this Pokemon ever used a setup move
            user_setups = [s for s in state.setup_moves_used.get(user_player, []) 
                          if s['pokemon'] == species]
            
            if not user_setups:
                blunders.append(BlunderReport(
                    turn=turn,
                    severity='moderate',
                    description=f"{species} (a potential sweeper) fainted without ever setting up.",
                    suggestion="Try to find a safe turn to set up, or save your sweeper for late-game when threats are weakened.",
                    context={'pokemon': species}
                ))
    
    # --- 4. HAZARD CHIP DEATH (Significant damage from hazards) ---
    for species, total_hazard_dmg in state.hazard_damage.get(user_player, {}).items():
        if total_hazard_dmg >= 25:  # Took 25%+ total from hazards
            # Check if this mon fainted
            mon_fainted = any(f['species'] == species for f in state.faints.get(user_player, []))
            if mon_fainted:
                blunders.append(BlunderReport(
                    turn=state.turn,  # End of battle
                    severity='minor',
                    description=f"{species} took {total_hazard_dmg}% total damage from hazards before fainting.",
                    suggestion="Prioritize hazard removal or avoid unnecessary switches. Consider Heavy-Duty Boots.",
                    context={'hazard_damage': total_hazard_dmg, 'pokemon': species}
                ))
    
    # --- 5. WEATHER WAR LOSS ---
    # Check if opponent has weather setter alive and yours is dead
    weather_setters = {
        'tyranitar': 'Sandstorm', 'hippowdon': 'Sandstorm', 'gigalith': 'Sandstorm',
        'pelipper': 'RainDance', 'politoed': 'RainDance', 'kyogre': 'RainDance',
        'torkoal': 'SunnyDay', 'ninetales': 'SunnyDay', 'groudon': 'SunnyDay',
        'abomasnow': 'Snow', 'ninetales-alola': 'Snow', 'vanilluxe': 'Snow'
    }
    
    user_setters = [s for s in user_team.keys() if s.lower() in weather_setters]
    opp_setters = [s for s in opp_team.keys() if s.lower() in weather_setters]
    
    if user_setters and opp_setters:
        user_setter_dead = all(user_team[s].fainted for s in user_setters)
        opp_setter_alive = any(not opp_team[s].fainted for s in opp_setters)
        
        if user_setter_dead and opp_setter_alive:
            dead_setter = user_setters[0]
            blunders.append(BlunderReport(
                turn=state.turn,
                severity='moderate',
                description=f"Your weather setter ({dead_setter}) is down while opponent's is still alive.",
                suggestion="In weather wars, try to preserve your setter or KO theirs first.",
                context={'your_setter': dead_setter}
            ))
    
    # --- 6. MOMENTUM COLLAPSE (Went from winning to losing badly) ---
    user_faints = state.faints.get(user_player, [])
    opp_faints = state.faints.get(opponent, [])
    
    # Track faint differential over time
    if len(user_faints) >= 4 and len(opp_faints) <= 2:
        # Lost 4+ while opponent lost 2 or less
        # Check if there was a point where user was ahead
        user_faint_turns = sorted([f['turn'] for f in user_faints])
        opp_faint_turns = sorted([f['turn'] for f in opp_faints])
        
        # Find the turn where collapse started (3+ faints in a row without trading)
        consecutive_losses = 0
        collapse_start = None
        for turn in user_faint_turns:
            opp_faints_before = len([t for t in opp_faint_turns if t <= turn])
            user_faints_before = len([t for t in user_faint_turns if t <= turn])
            
            if user_faints_before > opp_faints_before + 1:
                consecutive_losses += 1
                if consecutive_losses >= 3 and collapse_start is None:
                    collapse_start = turn
        
        if collapse_start:
            blunders.append(BlunderReport(
                turn=collapse_start,
                severity='critical',
                description=f"Momentum collapsed around turn {collapse_start}. Lost {len(user_faints)} Pokemon while opponent lost {len(opp_faints)}.",
                suggestion="When falling behind, consider playing more conservatively or identifying a win condition to play toward.",
                context={'user_faints': len(user_faints), 'opp_faints': len(opp_faints)}
            ))
    
    return blunders


def calculate_momentum(state: BattleState) -> list[dict]:
    """
    Calculates momentum swings throughout the battle.
    Returns a list of {turn, p1_momentum, p2_momentum} dicts.
    """
    momentum = []
    
    p1_score = 0
    p2_score = 0
    
    current_turn = 0
    
    for event in state.events:
        if event.turn != current_turn:
            momentum.append({
                'turn': current_turn,
                'p1': p1_score,
                'p2': p2_score
            })
            current_turn = event.turn
        
        if event.event_type == 'faint':
            if event.player == 'p1':
                p2_score += 20  # Opponent gained advantage
                p1_score -= 10
            else:
                p1_score += 20
                p2_score -= 10
        
        elif event.event_type == 'damage':
            if event.hp_before and event.hp_after:
                damage = event.hp_before - event.hp_after
                if event.player == 'p1':
                    p2_score += damage // 10
                else:
                    p1_score += damage // 10
    
    # Final state
    momentum.append({
        'turn': state.turn,
        'p1': p1_score,
        'p2': p2_score
    })
    
    return momentum


def generate_summary(replay_data: dict, user_player: str = 'p1') -> dict:
    """
    Generates a complete battle summary from replay data.
    """
    if not replay_data:
        return {'error': 'Could not fetch replay data'}
    
    log = replay_data.get('log', '')
    players = replay_data.get('players', ['Player 1', 'Player 2'])
    format_name = replay_data.get('format', 'Unknown Format')
    
    # Determine which player the user is
    p1_name = players[0] if len(players) > 0 else 'Player 1'
    p2_name = players[1] if len(players) > 1 else 'Player 2'
    
    state = parse_replay_log(log, p1_name, p2_name)
    blunders = detect_blunders(state, user_player)
    momentum = calculate_momentum(state)
    
    # Calculate final scores
    p1_alive = sum(1 for p in state.p1_team.values() if not p.fainted)
    p2_alive = sum(1 for p in state.p2_team.values() if not p.fainted)
    
    # Use the parsed winner from |win| event (handles forfeits, timer, etc.)
    # Fallback to faint-based detection if not found
    winner = state.winner
    if winner is None:
        if p1_alive == 0:
            winner = 'p2'
        elif p2_alive == 0:
            winner = 'p1'
    
    return {
        'format': format_name,
        'players': {
            'p1': p1_name,
            'p2': p2_name
        },
        'winner': winner,
        'user_player': user_player,
        'final_score': {
            'p1': p1_alive,
            'p2': p2_alive
        },
        'teams': {
            'p1': {species: {
                'hp': p.hp,
                'fainted': p.fainted,
                'status': p.status
            } for species, p in state.p1_team.items()},
            'p2': {species: {
                'hp': p.hp,
                'fainted': p.fainted,
                'status': p.status
            } for species, p in state.p2_team.items()}
        },
        'total_turns': state.turn,
        'faints': state.faints,
        'blunders': blunders,
        'momentum': momentum,
        'hazard_damage': state.hazard_damage,
        'setup_moves': state.setup_moves_used,
        'key_events': [e for e in state.events if e.event_type in ('faint', 'switch')]
    }
