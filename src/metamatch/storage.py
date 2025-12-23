import json
import re
from pathlib import Path
from datetime import datetime
from metamatch import config

def extract_pokemon_names(raw_data):
    """Extracted from app.py to avoid circular imports and keep logic dry."""
    pattern = r'^([A-Za-z][A-Za-z\s\-\.]*?)\s*@'
    names = []
    lines = raw_data.split('\n')
    for line in lines:
        line = line.strip()
        if not line: continue
        match = re.search(pattern, line)
        if match:
            name = match.group(1).strip()
            if name and name not in names:
                names.append(name)
    return names

def save_team(name, raw_text, analysis=None, user_id="default"):
    """
    Saves a team and its analysis to a JSON file.
    """
    user_path = config.USER_DIR / f"{user_id}.json"
    
    if user_path.exists():
        with open(user_path, "r") as f:
            try:
                user_data = json.load(f)
            except json.JSONDecodeError:
                user_data = {"teams": {}}
    else:
        user_data = {"teams": {}}
    
    # Store pokemon names for easy preview without parsing
    pokemon_names = extract_pokemon_names(raw_text)
    
    user_data["teams"][name] = {
        "name": name,
        "raw_text": raw_text,
        "analysis": analysis,
        "pokemon_names": pokemon_names,
        "updated_at": datetime.now().isoformat()
    }
    
    with open(user_path, "w") as f:
        json.dump(user_data, f, indent=4)
    
    return True

def list_teams_detailed(user_id="default"):
    """
    Returns a sorted list of team metadata for preview and sorting.
    Sorted by updated_at DESC (newest first).
    """
    user_path = config.USER_DIR / f"{user_id}.json"
    if not user_path.exists():
        return []
    
    with open(user_path, "r") as f:
        try:
            user_data = json.load(f)
            teams = list(user_data.get("teams", {}).values())
            # Sort by date
            teams.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
            return teams
        except json.JSONDecodeError:
            return []

def list_teams(user_id="default"):
    """Legacy support - returns just names."""
    teams = list_teams_detailed(user_id)
    return [t['name'] for t in teams]

def load_team(name, user_id="default"):
    """
    Loads a specific team's data.
    """
    user_path = config.USER_DIR / f"{user_id}.json"
    if not user_path.exists():
        return None
    
    with open(user_path, "r") as f:
        try:
            user_data = json.load(f)
            team_data = user_data.get("teams", {}).get(name)
            
            # JSON keys are always strings. Convert team keys back to integers.
            if team_data and 'analysis' in team_data and 'team' in team_data['analysis']:
                raw_team = team_data['analysis']['team']
                converted_team = {}
                for k, v in raw_team.items():
                    try:
                        converted_team[int(k)] = v
                    except ValueError:
                        converted_team[k] = v
                team_data['analysis']['team'] = converted_team
                
            return team_data
        except json.JSONDecodeError:
            return None

def delete_team(name, user_id="default"):
    """
    Deletes a specific team.
    """
    user_path = config.USER_DIR / f"{user_id}.json"
    if not user_path.exists():
        return False
    
    with open(user_path, "r") as f:
        try:
            user_data = json.load(f)
        except json.JSONDecodeError:
            return False
            
    if name in user_data.get("teams", {}):
        del user_data["teams"][name]
        with open(user_path, "w") as f:
            json.dump(user_data, f, indent=4)
        return True
    
    return False
