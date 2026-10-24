import re
from metamatch import config
from metamatch.auditor import load_chaos_data


def is_mega(pokemon_name: str) -> bool:
    """Check if a Pokemon is a Mega Evolution."""
    name_lower = pokemon_name.lower()
    # Matches patterns like "Charizard-Mega-X", "Gengar-Mega", etc.
    return "-mega" in name_lower


def holds_mega_stone(item: str) -> bool:
    """Champions teams declare Megas through the stone (e.g. 'Garchompite Z'), not the species name."""
    item = (item or "").strip().lower()
    return item != "eviolite" and re.search(r"ite( [xyz])?$", item) is not None


def base_species(pokemon_name: str) -> str:
    return re.split(r"-mega", pokemon_name, flags=re.IGNORECASE)[0].lower()


def _norm(s: str) -> str:
    return s.lower().replace("-", "").replace(" ", "").replace("'", "")


# Maps fillable roles to their signature moves (normalized)
ROLE_FILL_MOVES = {
    "Hazard Setter":  {"stealthrock", "spikes", "toxicspikes", "stickyweb"},
    "Hazard Remover": {"rapidspin", "defog", "courtchange", "tidyup"},
    "Pivot":          {"uturn", "voltswitch", "flipturn", "teleport", "partingshot", "shedtail"},
}
ROLE_BOOST = 1.2


def _infer_candidate_roles(moves_dict: dict, total_weight: float) -> set:
    """Return set of roles a candidate can fill based on their top moves (>5% usage)."""
    if not moves_dict or total_weight == 0:
        return set()
    top_moves = {_norm(m) for m, w in moves_dict.items() if (w / total_weight * 100) > 5.0}
    return {role for role, sig in ROLE_FILL_MOVES.items() if top_moves & sig}


def get_recommendations(current_team_names, top_n=5, format_id="gen9ou", team_roles=None, team_items=None):
    """
    Analyzes the chaos data to find the best teammates for the current team.
    Uses a simple aggregation of correlation scores across selected formats.

    Args:
        current_team_names (list): List of Pokemon names in the team.
        top_n (int): Number of recommendations to return.
        format_id (str or list): Format identifier(s) (e.g., 'gen9ou' or ['gen9ou', 'gen9uu']).
        team_roles (list[list]): Roles for each Pokemon on the team. Used to boost candidates
                                 that fill missing roles. Pass None to skip role weighting.
        team_items (list[str]): Held items, used to spot Megas declared through a stone.

    Returns:
        List of (name, score, reason) tuples. reason is a string like
        "Fills missing: Hazard Setter, Pivot" or "" if no role boost applied.
    """

    # Ensure format_id is a list
    if isinstance(format_id, str):
        format_ids = [format_id]
    else:
        format_ids = format_id

    # Determine which roles the current team is missing
    covered_roles: set = set()
    if team_roles:
        for roles in team_roles:
            covered_roles.update(roles)
    missing_roles = set(ROLE_FILL_MOVES.keys()) - covered_roles

    # Check if the current team already has a Mega Pokemon
    team_has_mega = (any(is_mega(name) for name in current_team_names)
                     or any(holds_mega_stone(item) for item in (team_items or [])))

    # Map to store aggregated scores and inferred roles per candidate
    candidate_scores: dict[str, float] = {}
    candidate_fill_roles: dict[str, set] = {}

    # Normalize current team names for matching (Smogon uses exact names)
    team_set = {name.lower() for name in current_team_names}
    team_species = {base_species(name) for name in current_team_names}

    for fmt in format_ids:
        if fmt not in config.FORMATS:
            continue
        data = load_chaos_data(fmt)
        if not data:
            continue

        for p_name in current_team_names:
            # Match name with Smogon's keys
            p_data = data.get(p_name)
            if not p_data:
                for key in data:
                    if key.lower() == p_name.lower():
                        p_data = data[key]
                        break

            if p_data:
                teammates = p_data.get('Teammates', {})
                for mate, score in teammates.items():
                    if mate.lower() in team_set or base_species(mate) in team_species:
                        continue
                    if team_has_mega and is_mega(mate):
                        continue
                    candidate_scores[mate] = candidate_scores.get(mate, 0) + score

                    # Infer candidate's fillable roles once per candidate
                    if mate not in candidate_fill_roles:
                        mate_data = data.get(mate) or {}
                        mate_weight = sum(mate_data.get('Abilities', {}).values()) or 1
                        candidate_fill_roles[mate] = _infer_candidate_roles(
                            mate_data.get('Moves', {}), mate_weight
                        )

    # Apply role boost and build reason strings
    boosted: list[tuple[str, float, str]] = []
    for name, score in candidate_scores.items():
        fills = candidate_fill_roles.get(name, set()) & missing_roles
        if fills:
            score *= ROLE_BOOST
            reason = "Fills missing: " + ", ".join(sorted(fills))
        else:
            reason = ""
        boosted.append((name, score, reason))

    boosted.sort(key=lambda x: x[1], reverse=True)
    return boosted[:top_n]
