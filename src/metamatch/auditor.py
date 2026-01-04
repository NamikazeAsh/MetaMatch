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
    Returns a dictionary with full usage reports and a list of warnings.
    """
    chaos_data = load_chaos_data()
    if not chaos_data:
        return {"reports": {}, "warnings": []}

    warnings = []
    reports = {}
    USAGE_THRESHOLD = 5.0 # Percent

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

        reports[name] = {"item": {}, "ability": {}, "moves": {}}
        total_weight = sum(p_data.get('Abilities', {}).values())
        if total_weight == 0: continue

        def normalize(s):
            return s.lower().replace("-", "").replace(" ", "").replace("'", "")

        def find_stat(target, stats_dict):
            target_norm = normalize(target)
            for s_name, s_val in stats_dict.items():
                if normalize(s_name) == target_norm:
                    return s_name, s_val
            return None, 0

        # Audit Item
        user_item = pokemon.get('Item', '')
        if user_item:
            item_stats = p_data.get('Items', {})
            item_weight = sum(item_stats.values())
            real_name, count = find_stat(user_item, item_stats)
            pct = (count / item_weight * 100) if item_weight > 0 else 0
            reports[name]["item"] = {"name": user_item, "usage": pct}
            
            if pct < USAGE_THRESHOLD:
                top_name, top_val = max(item_stats.items(), key=lambda x: x[1])
                warnings.append({
                    "pokemon": name, "category": "Item", "current": user_item, "usage": pct,
                    "suggestion": f"{top_name.title()} ({(top_val/item_weight*100):.1f}%)"
                })
        
        # Audit Ability
        user_ability = pokemon.get('Ability', '')
        if user_ability:
            ability_stats = p_data.get('Abilities', {})
            real_name, count = find_stat(user_ability, ability_stats)
            pct = (count / total_weight * 100)
            reports[name]["ability"] = {"name": user_ability, "usage": pct}

        # Audit Moves
        user_moves = [m['name'] for m in pokemon.get('Moves', [])]
        move_stats = p_data.get('Moves', {})
        for move in user_moves:
            real_name, count = find_stat(move, move_stats)
            pct = (count / total_weight) * 100
            reports[name]["moves"][move] = pct
            
            if pct < USAGE_THRESHOLD:
                top_moves = sorted(move_stats.items(), key=lambda x:x[1], reverse=True)[:2]
                suggestion = ", ".join([f"{k} ({(v/total_weight)*100:.1f}%)" for k,v in top_moves])
                warnings.append({
                    "pokemon": name, "category": "Move", "current": move, "usage": pct,
                    "suggestion": f"Common: {suggestion}"
                })

    return {"reports": reports, "warnings": warnings}


