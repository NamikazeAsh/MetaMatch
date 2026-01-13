import json
from pathlib import Path
from metamatch import config

def get_recommendations(current_team_names, top_n=5, format_id="gen9ou"):
    """
    Analyzes the chaos data to find the best teammates for the current team.
    Uses a simple aggregation of correlation scores across selected formats.
    
    Args:
        current_team_names (list): List of Pokemon names in the team.
        top_n (int): Number of recommendations to return.
        format_id (str or list): Format identifier(s) (e.g., 'gen9ou' or ['gen9ou', 'gen9uu']).
    """
    
    file_map = {
        "gen9ou": "gen9ou-1825.json",
        "gen9uu": "gen9uu-1760.json",
        "gen9natdex": "gen9nationaldex-1760.json"
    }
    
    # Ensure format_id is a list
    if isinstance(format_id, str):
        format_ids = [format_id]
    else:
        format_ids = format_id

    # Map to store aggregated scores: {TeammateName: TotalScore}
    candidate_scores = {}
    
    # Normalize current team names for matching (Smogon uses exact names)
    team_set = {name.lower() for name in current_team_names}

    for fmt in format_ids:
        filename = file_map.get(fmt)
        if not filename:
            continue
            
        chaos_path = config.STATS_DIR / filename
        if not chaos_path.exists():
            continue

        try:
            with open(chaos_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data = data.get('data', {})
        except (json.JSONDecodeError, FileNotFoundError):
            continue

        for p_name in current_team_names:
            # Match name with Smogon's keys
            p_data = data.get(p_name)
            if not p_data:
                # Try case-insensitive fallback
                for key in data:
                    if key.lower() == p_name.lower():
                        p_data = data[key]
                        break
            
            if p_data:
                teammates = p_data.get('Teammates', {})
                for mate, score in teammates.items():
                    if mate.lower() not in team_set:
                        candidate_scores[mate] = candidate_scores.get(mate, 0) + score

    # Sort candidates by total score
    sorted_candidates = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)
    
    return sorted_candidates[:top_n]
