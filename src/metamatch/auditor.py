import json
from metamatch import config

def load_chaos_data():
    """
    Loads the Chaos JSON data.
    """
    chaos_path = config.STATS_DIR / "gen9ou-1825.json"
    if not chaos_path.exists():
        return None
    try:
        with open(chaos_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('data', {})
    except:
        return None

def audit_team(team_data):
    """
    Audits the team against Smogon usage stats.
    Returns a list of warnings.
    """
    chaos_data = load_chaos_data()
    if not chaos_data:
        return []

    warnings = []
    USAGE_THRESHOLD = 3.0 # Percent

    for idx, pokemon in team_data.items():
        name = pokemon['Pokemon']
        p_data = chaos_data.get(name)
        if not p_data:
            for key in chaos_data:
                if key.lower() == name.lower():
                    p_data = chaos_data[key]
                    break
        
        if not p_data:
            continue

        # Total weighted usage for this Pokemon
        # Sum of abilities is the most reliable "total weight"
        total_weight = sum(p_data.get('Abilities', {}).values())
        if total_weight == 0: continue

        def normalize(s):
            return s.lower().replace("-", "").replace(" ", "").replace("'", "")

        def find_stat(target, stats_dict):
            target_norm = normalize(target)
            for s_name, s_val in stats_dict.items():
                if normalize(s_name) == target_norm:
                    return s_val
            return 0

        # 2. Audit Item
        user_item = pokemon.get('Item', '')
        if user_item and user_item.lower() != "none":
            item_stats = p_data.get('Items', {})
            # Total items might be less than total_weight if some players use "nothing"
            item_weight = sum(item_stats.values())
            count = find_stat(user_item, item_stats)
            pct = (count / item_weight * 100) if item_weight > 0 else 0
            
            if pct < USAGE_THRESHOLD:
                top_name, top_val = max(item_stats.items(), key=lambda x: x[1])
                warnings.append({
                    "pokemon": name, "category": "Item", "current": user_item, "usage": pct,
                    "suggestion": f"{top_name.title()} ({(top_val/item_weight*100):.1f}%)"
                })
        
        # 3. Audit Ability
        user_ability = pokemon.get('Ability', '')
        if user_ability:
            ability_stats = p_data.get('Abilities', {})
            count = find_stat(user_ability, ability_stats)
            pct = (count / total_weight * 100)
            if pct < USAGE_THRESHOLD:
                top_name, top_val = max(ability_stats.items(), key=lambda x: x[1])
                warnings.append({
                    "pokemon": name, "category": "Ability", "current": user_ability, "usage": pct,
                    "suggestion": f"{top_name.title()} ({(top_val/total_weight*100):.1f}%)"
                })

        # 4. Audit Moves
        user_moves = [m['name'] for m in pokemon.get('Moves', [])]
        move_stats = p_data.get('Moves', {})
        
        for move in user_moves:
            count = find_stat(move, move_stats)
            # Move usage % is (count / total_pokemon_weight) * 100
            pct = (count / total_weight) * 100
            
            if pct < USAGE_THRESHOLD:
                top_moves = sorted(move_stats.items(), key=lambda x:x[1], reverse=True)[:3]
                suggestion = ", ".join([f"{k.title()} ({(v/total_weight)*100:.1f}%)" for k,v in top_moves])
                warnings.append({
                    "pokemon": name, "category": "Move", "current": move, "usage": pct,
                    "suggestion": f"Common: {suggestion}"
                })

    return warnings


