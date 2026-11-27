import json
from functools import lru_cache
from metamatch import config
from metamatch.engine.dex import dex_for_format

def load_chaos_data(format_id=config.DEFAULT_FORMAT):
    """
    Loads the Chaos JSON data for a format. Cached per file version; treat the result as read only.
    """
    chaos_path = config.STATS_DIR / (config.format_info(format_id)["stats"] + ".json")
    if not chaos_path.exists():
        return None
    return _load_chaos_file(str(chaos_path), chaos_path.stat().st_mtime)


# Pokemon the top ladder rarely brings (Sceptile in National Dex) still have real sets in Smogon's all ratings stats.
# scripts/update_meta.py keeps those, trimmed, in data/stats/<format>-allratings.json: only Pokemon missing from the
# main file, with at least this many sets behind them
ALL_RATINGS_MIN_SETS = 20
ALL_RATINGS_FIELDS = (("Abilities", 4), ("Items", 6), ("Moves", 12), ("Spreads", 5), ("Tera Types", 4), ("Teammates", 12))


def all_ratings_path(format_id):
    return config.STATS_DIR / (config.format_info(format_id)["stats"].rsplit("-", 1)[0] + "-allratings.json")


def trim_all_ratings(low, high):
    """The all ratings entries for Pokemon the main (high rating) file lacks or barely has, trimmed to the fields the
    app reads; each is marked all_ratings so answers can say where the numbers come from."""
    kept = {k for k, v in high.items() if v.get("usage", 0) > 0.001}
    out = {}
    for name, entry in low.items():
        if name in kept or sum(entry.get("Abilities", {}).values()) < ALL_RATINGS_MIN_SETS:
            continue
        out[name] = {"usage": entry.get("usage", 0), "all_ratings": True,
                     **{fld: dict(sorted((entry.get(fld) or {}).items(), key=lambda kv: -kv[1])[:n])
                        for fld, n in ALL_RATINGS_FIELDS}}
    return out


def load_all_ratings(format_id=config.DEFAULT_FORMAT):
    """{name: entry} for the format's rarely used Pokemon (see trim_all_ratings), or {} without the file."""
    path = all_ratings_path(format_id)
    if not path.exists():
        return {}
    return _load_chaos_file(str(path), path.stat().st_mtime) or {}


def format_roster(format_id, min_usage=0.001):
    """Every Pokemon a player can pick in the format, most used first: the main stats above min_usage, then the
    rarely used ones from the all ratings stats (Sceptile in National Dex), so an unusual pick is never missing."""
    data = load_chaos_data(format_id) or {}
    main = [n for n, e in sorted(data.items(), key=lambda kv: -kv[1].get("usage", 0)) if e.get("usage", 0) > min_usage]
    seen = set(main)
    rare = [n for n, _ in sorted(load_all_ratings(format_id).items(), key=lambda kv: -kv[1].get("usage", 0))
            if n not in seen]
    return main + rare


@lru_cache(maxsize=8)
def _load_chaos_file(path, mtime):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f).get('data', {})
    except (OSError, json.JSONDecodeError):
        return None

def audit_team(team_data):
    """
    Audits the team against Smogon usage stats.
    Returns a dictionary with full usage reports and a list of warnings.
    """
    chaos_data = load_chaos_data(config.team_format(team_data))
    if not chaos_data:
        return {"reports": {}, "warnings": []}

    warnings = []
    reports = {}
    dex = dex_for_format(config.team_format(team_data))

    def display(slug, kind):
        # Chaos keys are slugs ('heavydutyboots'); show the real name when the dex knows it
        name = (dex.item_name(slug) if kind == 'item' else dex.move_name(slug)) if dex else None
        return name or slug.title()
    USAGE_THRESHOLD = 5.0   # percent of sets: anything rarer is flagged

    for idx, pokemon in team_data.items():
        name = pokemon['Pokemon']
        p_data = chaos_data.get(name)
        if not p_data:
            for key in chaos_data:
                if key.lower() == name.lower():
                    p_data = chaos_data[key]
                    break

        # Champions stats key Mega holders by their Mega forme (e.g. Golisopod @ Golisopodite -> Golisopod-Mega)
        if pokemon.get('Forme'):
            p_data = chaos_data.get(pokemon['Forme']) or p_data

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

        # Held item
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
                    "suggestion": f"{display(top_name, 'item')} ({(top_val/item_weight*100):.1f}%)"
                })
        
        # Ability
        user_ability = pokemon.get('Ability', '')
        if user_ability:
            ability_stats = p_data.get('Abilities', {})
            real_name, count = find_stat(user_ability, ability_stats)
            pct = (count / total_weight * 100)
            reports[name]["ability"] = {"name": user_ability, "usage": pct}

        # Moves
        user_moves = [m['name'] for m in pokemon.get('Moves', [])]
        move_stats = p_data.get('Moves', {})
        for move in user_moves:
            real_name, count = find_stat(move, move_stats)
            pct = (count / total_weight) * 100
            reports[name]["moves"][move] = pct
            
            if pct < USAGE_THRESHOLD:
                # The two most used moves this set doesn't already run
                owned = {normalize(m) for m in user_moves}
                top_moves = [(k, v) for k, v in sorted(move_stats.items(), key=lambda x: x[1], reverse=True)
                             if normalize(k) not in owned and k][:2]
                suggestion = ", ".join([f"{display(k, 'move')} ({(v/total_weight)*100:.1f}%)" for k,v in top_moves])
                warnings.append({
                    "pokemon": name, "category": "Move", "current": move, "usage": pct,
                    "suggestion": suggestion
                })

    return {"reports": reports, "warnings": warnings}


