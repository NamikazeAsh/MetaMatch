import re
from .utils import fetch_pokemon_data, calculate_speed
from .type_chart import TYPE_CHART

# --- INTENT ROUTER ---
def detect_intent(query):
    """
    Classifies the user query into 'mechanics' or 'strategy'.
    """
    query = query.lower()
    
    mechanics_keywords = [
        "vs", "against", "beat", "counter", "stop", "wall", "switch", "lead", 
        "damage", "speed", "faster", "slower", "check", "kill", "ohko", "survive"
    ]
    
    strategy_keywords = [
        "set", "build", "role", "evs", "nature", "item", "guide", "how to", "use",
        "synergy", "partner", "advice", "struggling"
    ]
    
    # Simple keyword matching score
    mech_score = sum(1 for w in mechanics_keywords if w in query)
    strat_score = sum(1 for w in strategy_keywords if w in query)
    
    if mech_score >= strat_score:
        return "mechanics"
    return "strategy"

# --- ENTITY EXTRACTION ---
def extract_pokemon_names(query):
    """
    Very basic heuristic to find potential Pokemon names in a query.
    Ideally, this would use a list of all 1000+ Pokemon, but for now
    we rely on checking capitalized words or known context.
    
    Actually, looking at RAG hits metadata is safer if available.
    But for pure logic, let's try to match capitalized words against valid API calls?
    That's too slow.
    
    Better approach: The RAG retrieval usually finds the relevant document.
    We can use the RAG metadata to confirm the subject.
    """
    # Placeholder: The Logic Engine is best used *after* RAG has identified the subject.
    pass

# --- MATH ENGINE ---
def get_type_effectiveness(attack_type, defender_types):
    multiplier = 1.0
    for dtype in defender_types:
        if attack_type in TYPE_CHART and dtype in TYPE_CHART[attack_type]:
            multiplier *= TYPE_CHART[attack_type][dtype]
    return multiplier

def analyze_matchup(user_pokemon, opponent_name):
    """
    Compares a User Pokemon (dict) vs an Opponent Pokemon (name string).
    Returns a list of 'Hard Facts' about the matchup.
    """
    facts = []
    
    # 1. Fetch Opponent Data
    opp_data = fetch_pokemon_data(opponent_name)
    if not opp_data:
        return []

    opp_stats = opp_data['stats']
    opp_types = opp_data['types']
    # Assume standard opponent build
    opp_base_speed = opp_stats.get('speed', 100)
    opp_est_speed = calculate_speed(opp_base_speed, ev=252, iv=31, nature_mod=1.0) # Neutral
    opp_est_speed_plus = calculate_speed(opp_base_speed, ev=252, iv=31, nature_mod=1.1) # Positive

    # 2. Speed Check
    user_speed = user_pokemon.get('Speed', 0)
    user_name = user_pokemon['Pokemon']
    
    if user_speed > opp_est_speed_plus:
        facts.append(f"SPEED: {user_name} ({user_speed}) is FASTER than max speed {opponent_name} ({opp_est_speed_plus}).")
    elif user_speed > opp_est_speed:
        facts.append(f"SPEED: {user_name} ({user_speed}) outspeeds neutral {opponent_name} ({opp_est_speed}).")
    elif user_speed == opp_est_speed:
        facts.append(f"SPEED: {user_name} ({user_speed}) Speed Ties with {opponent_name}.")
    else:
        facts.append(f"SPEED: {user_name} ({user_speed}) is SLOWER than {opponent_name} ({opp_est_speed}).")

    # 3. Defensive Analysis (Incoming Damage)
    user_types = user_pokemon.get('Type', [])
    ability = user_pokemon.get('Ability', '').lower()
    item = user_pokemon.get('Item', '').lower()
    
    # We check if the User is WEAK to any of the Opponent's STAB types
    # (Opponent likely attacks with their own type)
    weaknesses = []
    resistances = []
    immunities = []
    
    for atk_type in opp_types:
        # Check Special Immunities FIRST
        is_immune = False
        atk_lower = atk_type.lower()
        
        # Ground
        if atk_lower == 'ground':
            if 'levitate' in ability or 'earth eater' in ability or item == 'air balloon':
                is_immune = True
                
        # Electric
        if atk_lower == 'electric':
            if ability in ['volt absorb', 'lightning rod', 'motor drive']:
                is_immune = True
                
        # Water
        if atk_lower == 'water':
            if ability in ['water absorb', 'storm drain', 'dry skin']:
                is_immune = True
                
        # Fire
        if atk_lower == 'fire':
            if ability in ['flash fire', 'well-baked body']:
                is_immune = True
        
        # Grass
        if atk_lower == 'grass':
            if ability == 'sap sipper':
                is_immune = True

        if is_immune:
            immunities.append(f"{atk_type} (Ability/Item)")
            continue

        mult = get_type_effectiveness(atk_type, user_types)
        if mult >= 2.0:
            weaknesses.append(f"{atk_type} ({mult}x)")
        elif mult == 0.0:
            immunities.append(atk_type)
        elif mult <= 0.5:
            resistances.append(f"{atk_type} ({mult}x)")
            
    if weaknesses:
        facts.append(f"DEFENSE: {user_name} takes SUPER EFFECTIVE damage from {opponent_name}'s {', '.join(weaknesses)} moves.")
    if immunities:
        facts.append(f"DEFENSE: {user_name} is IMMUNE to {opponent_name}'s {', '.join(immunities)} moves.")
    if resistances:
        facts.append(f"DEFENSE: {user_name} RESISTS {opponent_name}'s {', '.join(resistances)} moves.")

    # 4. Offensive Analysis (Outgoing Damage)
    moves = user_pokemon.get('Moves', [])
    super_moves = []
    
    for move in moves:
        m_type = move.get('type')
        m_cat = move.get('category')
        m_name = move.get('name')
        
        if m_cat == 'Status' or not m_type:
            continue
            
        mult = get_type_effectiveness(m_type, opp_types)
        if mult >= 4.0:
            super_moves.append(f"{m_name} ({m_type} - 4x FATAL)")
        elif mult >= 2.0:
            super_moves.append(f"{m_name} ({m_type} - 2x SUPER EFFECTIVE)")
            
    if super_moves:
        facts.append(f"OFFENSE: {user_name} has SUPER EFFECTIVE moves against {opponent_name}: {', '.join(super_moves)}.")
        
    return facts

def generate_mechanics_report(team, rag_hits):
    """
    The Orchestrator for Mechanics.
    1. Identify the 'Enemy' from RAG hits metadata.
    2. Run Matchups for every team member vs that Enemy.
    3. Return a formatted string of Facts.
    """
    if not rag_hits:
        return ""

    # Identify unique subjects
    subjects = set()
    for hit in rag_hits:
        p_name = hit['metadata'].get('pokemon')
        if p_name:
            subjects.add(p_name)
    
    if not subjects:
        return ""

    report = "### DETERMINISTIC BATTLE CALCULATIONS (FACTS)\n"
    
    for subject in subjects:
        report += f"--- Matchups vs {subject} ---\n"
        
        # Calculate matchup for each teammate
        for p in team.values():
            facts = analyze_matchup(p, subject)
            if facts:
                # Combine facts into a dense line
                line = " | ".join(facts)
                report += f"[{p['Pokemon']}]: {line}\n"
        report += "\n"
                
    return report
