import json
from pathlib import Path
from metamatch import config

def get_recommendations(current_team_names, top_n=5):
    """
    Analyzes the chaos data to find the best teammates for the current team.
    Uses a simple aggregation of correlation scores.
    """
    chaos_path = config.STATS_DIR / "gen9ou-1825.json"
    
    if not chaos_path.exists():
        return []

    try:
        with open(chaos_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            data = data.get('data', {})
    except (json.JSONDecodeError, FileNotFoundError):
        return []

    # Map to store aggregated scores: {TeammateName: TotalScore}
    candidate_scores = {}
    
    # Normalize current team names for matching (Smogon uses exact names)
    team_set = {name.lower() for name in current_team_names}

    for p_name in current_team_names:
        # Match name with Smogon's keys (case-sensitive usually, but we'll try a flexible match)
        # Smogon keys are usually like 'Great Tusk'
        p_data = data.get(p_name)
        if not p_data:
            # Try case-insensitive fallback if exact match fails
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
