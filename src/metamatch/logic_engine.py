from .utils import fetch_pokemon_data, calculate_speed
from . import config
from .type_chart import TYPE_CHART
from .engine import calc
from .engine.dex import dex_for_format
from .engine.sets import likely_set, calc_spec, describe_spread
from .engine.solvers import user_spec
from .engine.names import find_pokemon

# Abilities that make the holder immune to a move type (lowercase display names)
ABILITY_IMMUNITY = {
    "ground": ("levitate", "earth eater"),
    "electric": ("volt absorb", "lightning rod", "motor drive"),
    "water": ("water absorb", "storm drain", "dry skin"),
    "fire": ("flash fire", "well-baked body"),
    "grass": ("sap sipper",),
}

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
def find_pokemon_in_query(query):
    """Returns Pokemon named in the query (exact names, nicknames, Mega names, small typos), in order."""
    return find_pokemon(query)

# --- MATH ENGINE ---
def get_type_effectiveness(attack_type, defender_types):
    multiplier = 1.0
    for dtype in defender_types:
        if attack_type in TYPE_CHART and dtype in TYPE_CHART[attack_type]:
            multiplier *= TYPE_CHART[attack_type][dtype]
    return multiplier

def _pct(x):
    return f"{x * 100:.0f}%"


def _ko(result):
    return f" ({result['ko']})" if result['ko'] else ""


def _speed_facts(user_name, user_speed, opponent_name, opp_set, opp_base_speed, game):
    """Speed comparison against the opponent's real spread distribution, or max speed guesses without usage data."""
    speeds = opp_set["speeds"] if opp_set else []
    if speeds:
        faster = sum(share for spe, share in speeds if spe < user_speed)
        tied = sum(share for spe, share in speeds if spe == user_speed)
        top_spe, top_share = speeds[0]
        fact = (f"SPEED: {user_name} ({user_speed}) outspeeds {_pct(faster)} of {opponent_name} sets"
                + (f" and ties {_pct(tied)}" if tied >= 0.01 else "")
                + f". Most common {opponent_name} Speed is {top_spe} ({_pct(top_share)} of sets).")
        facts = [fact]
        if opp_set.get("item") == "Choice Scarf":
            facts.append(f"SPEED: {_pct(opp_set['item_share'])} of {opponent_name} run Choice Scarf ({int(top_spe * 1.5)} Speed).")
        return facts

    # No usage data: fall back to neutral and positive max speed guesses
    max_invest = config.CHAMPIONS_SP_MAX if game == "champions" else 252
    neutral = calculate_speed(opp_base_speed, ev=max_invest, iv=31, nature_mod=1.0, game=game)
    plus = calculate_speed(opp_base_speed, ev=max_invest, iv=31, nature_mod=1.1, game=game)
    if user_speed > plus:
        return [f"SPEED: {user_name} ({user_speed}) is FASTER than max speed {opponent_name} ({plus})."]
    if user_speed > neutral:
        return [f"SPEED: {user_name} ({user_speed}) outspeeds neutral {opponent_name} ({neutral}) but not max speed ({plus})."]
    if user_speed == neutral:
        return [f"SPEED: {user_name} ({user_speed}) Speed Ties with neutral max speed {opponent_name}."]
    return [f"SPEED: {user_name} ({user_speed}) is SLOWER than {opponent_name} ({neutral})."]


def _damage_facts(user_pokemon, opp_set, game, dex):
    """Real damage ranges both ways from the calc, best two moves each way."""
    mine = user_spec(user_pokemon, game)
    opp_spec = calc_spec(opp_set)
    user_moves = [m['name'] for m in user_pokemon.get('Moves', []) if m.get('category') not in (None, 'Status')]
    opp_moves = [m for m, _ in opp_set['moves'] if (dex.move(m) or {}).get('category') not in (None, 'Status')]

    requests = ([{"game": game, "attacker": mine, "defender": opp_spec, "move": m} for m in user_moves]
                + [{"game": game, "attacker": opp_spec, "defender": mine, "move": m} for m in opp_moves])
    results = calc.calculate_many(requests)
    if not any(results):
        return []

    def best(pairs):
        hits = [(m, r) for m, r in pairs if r and r['range'][1] > 0]
        return sorted(hits, key=lambda x: x[1]['percent'][1], reverse=True)[:2]

    user_name, opp_name = user_pokemon['Pokemon'], opp_set['name']
    facts = []
    dealt = best(zip(user_moves, results[:len(user_moves)]))
    taken = best(zip(opp_moves, results[len(user_moves):]))
    if dealt:
        facts.append(f"DAMAGE DEALT: " + "; ".join(
            f"{m} does {r['percent'][0]}-{r['percent'][1]}% to {opp_name}{_ko(r)}" for m, r in dealt) + ".")
    elif user_moves:
        facts.append(f"DAMAGE DEALT: none of {user_name}'s attacks damage {opp_name}.")
    if taken:
        facts.append(f"DAMAGE TAKEN: " + "; ".join(
            f"{opp_name}'s {m} does {r['percent'][0]}-{r['percent'][1]}% to {user_name}{_ko(r)}" for m, r in taken) + ".")
    return facts


def analyze_matchup(user_pokemon, opponent_name, opp_set=None):
    """
    Compares a User Pokemon (dict) vs an Opponent Pokemon (name string).
    opp_set is the opponent's likely set (engine.sets.likely_set); without it only
    type and max speed facts are produced.
    Returns a list of 'Hard Facts' about the matchup.
    """
    facts = []
    format_id = user_pokemon.get('Format')
    game = config.format_game(format_id)
    dex = dex_for_format(format_id)

    # 1. Opponent types and base Speed, from the bundled dex when possible
    species = dex.species(opp_set['name'] if opp_set else opponent_name) if dex else None
    if species:
        opp_types, opp_base_speed = species['types'], species['baseStats']['spe']
    else:
        opp_data = fetch_pokemon_data(opponent_name)
        if not opp_data:
            return []
        opp_types, opp_base_speed = opp_data['types'], opp_data['stats'].get('speed', 100)

    user_name = user_pokemon['Pokemon']
    facts += _speed_facts(user_name, user_pokemon.get('Speed', 0), opponent_name, opp_set, opp_base_speed, game)

    # 2. Defensive type profile vs the opponent's STAB types
    user_types = user_pokemon.get('Type', [])
    ability = (user_pokemon.get('Mega Ability') or user_pokemon.get('Ability', '')).lower()
    item = user_pokemon.get('Item', '').lower()
    weaknesses, resistances, immunities = [], [], []

    for atk_type in opp_types:
        if ABILITY_IMMUNITY.get(atk_type.lower()) and (ability in ABILITY_IMMUNITY[atk_type.lower()]
                                                       or (atk_type == 'Ground' and item == 'air balloon')):
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
        facts.append(f"DEFENSE: {user_name} takes SUPER EFFECTIVE (Weak) damage from {opponent_name}'s {', '.join(weaknesses)} moves.")
    if immunities:
        facts.append(f"DEFENSE: {user_name} is HARD IMMUNE to {opponent_name}'s {', '.join(immunities)} moves.")
    if resistances:
        facts.append(f"DEFENSE: {user_name} RESISTS {opponent_name}'s {', '.join(resistances)} moves.")

    # 3. Real damage numbers when we know the opponent's likely set and the calc is running
    damage = _damage_facts(user_pokemon, opp_set, game, dex) if opp_set and dex else []
    if damage:
        return facts + damage

    # 4. Fallback: type effectiveness of the user's attacks, using the opponent's likely ability
    opp_ability = (opp_set or {}).get('ability') or ''
    super_moves = []
    for move in user_pokemon.get('Moves', []):
        m_type, m_cat, m_name = move.get('type'), move.get('category'), move.get('name')
        if m_cat == 'Status' or not m_type:
            continue
        if opp_ability.lower() in ABILITY_IMMUNITY.get(m_type.lower(), ()):
            continue
        mult = get_type_effectiveness(m_type, opp_types)
        if mult >= 4.0:
            super_moves.append(f"{m_name} ({m_type} - 4x FATAL)")
        elif mult >= 2.0:
            super_moves.append(f"{m_name} ({m_type} - 2x SUPER EFFECTIVE)")
    if super_moves:
        facts.append(f"OFFENSE: {user_name} has SUPER EFFECTIVE moves against {opponent_name}: {', '.join(super_moves)}.")

    return facts


def describe_likely_set(s, format_id):
    """One line summary of an opponent's likely set for the LLM."""
    game = config.format_game(format_id)
    moves = ", ".join(f"{m} {_pct(share)}" for m, share in s['moves'])
    line = (f"Likely {s['name']} set ({_pct(s['usage'])} usage): {describe_spread(s, game)} ({_pct(s['spread_share'])})"
            f" @ {s['item']} ({_pct(s['item_share'])}), {s['ability']}. Moves: {moves}.")
    if s.get('tera') and game != "champions":
        line += f" Most common Tera: {s['tera'][0]} ({_pct(s['tera'][1])})."
    return line


def generate_mechanics_report(team, subjects):
    """
    The Orchestrator for Mechanics.
    Runs matchups for every team member vs each opponent named in `subjects`
    (assuming each opponent runs its most likely set) and returns a formatted string of Facts.
    """
    if not subjects:
        return ""

    format_id = config.team_format(team)
    report = "### DETERMINISTIC BATTLE CALCULATIONS (FACTS)\n"

    for subject in subjects:
        opp_set = likely_set(subject, format_id)
        report += f"--- Matchups vs {subject} ---\n"
        if opp_set:
            report += describe_likely_set(opp_set, format_id) + "\n"

        # Calculate matchup for each teammate
        for p in team.values():
            facts = analyze_matchup(p, subject, opp_set)
            if facts:
                # Combine facts into a dense line
                line = " | ".join(facts)
                report += f"[{p['Pokemon']}]: {line}\n"
        report += "\n"

    return report
