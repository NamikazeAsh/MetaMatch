import re
from metamatch import config
from metamatch.auditor import load_chaos_data


def is_mega(pokemon_name: str) -> bool:
    """True for Mega formes by name: 'Gengar-Mega', 'Charizard-Mega-X'."""
    name_lower = pokemon_name.lower()
    return "-mega" in name_lower


def holds_mega_stone(item: str) -> bool:
    """Champions teams declare Megas through the stone (e.g. 'Garchompite Z'), not the species name."""
    item = (item or "").strip().lower()
    return item != "eviolite" and re.search(r"ite( [xyz])?$", item) is not None


def base_species(pokemon_name: str) -> str:
    return re.split(r"-mega", pokemon_name, flags=re.IGNORECASE)[0].lower()


def _norm(s: str) -> str:
    return s.lower().replace("-", "").replace(" ", "").replace("'", "")


# Moves that fill a core role (ids without spaces or hyphens)
ROLE_FILL_MOVES = {
    "Hazard Setter":  {"stealthrock", "spikes", "toxicspikes", "stickyweb"},
    "Hazard Remover": {"rapidspin", "defog", "courtchange", "tidyup"},
    "Pivot":          {"uturn", "voltswitch", "flipturn", "teleport", "partingshot", "shedtail"},
}
ROLE_BOOST = 1.2


def _infer_candidate_roles(moves_dict: dict, total_weight: float) -> set:
    """Core roles a candidate fills through the moves on more than 5% of its sets."""
    if not moves_dict or total_weight == 0:
        return set()
    top_moves = {_norm(m) for m, w in moves_dict.items() if (w / total_weight * 100) > 5.0}
    return {role for role, sig in ROLE_FILL_MOVES.items() if top_moves & sig}


def get_recommendations(current_team_names, top_n=5, format_id="gen9ou", team_roles=None, team_items=None):
    """
    The usage based teammate recommender: each candidate scores the sum of its Smogon teammate counts with
    the current members, across one format id or a list of them, boosted when it fills a core role the
    team is missing (team_roles: each member's roles; None skips the boost). team_items spots Megas held
    as a stone, so a team with a Mega isn't offered a second one.
    Returns [(name, score, reason)], reason like 'Fills missing: Hazard Setter, Pivot' or ''.
    """
    if isinstance(format_id, str):
        format_ids = [format_id]
    else:
        format_ids = format_id

    covered_roles: set = set()
    if team_roles:
        for roles in team_roles:
            covered_roles.update(roles)
    missing_roles = set(ROLE_FILL_MOVES.keys()) - covered_roles

    # One Mega per team
    team_has_mega = (any(is_mega(name) for name in current_team_names)
                     or any(holds_mega_stone(item) for item in (team_items or [])))

    candidate_scores: dict[str, float] = {}
    candidate_fill_roles: dict[str, set] = {}

    # Team names and base species, so neither a member nor another forme of one is suggested
    team_set = {name.lower() for name in current_team_names}
    team_species = {base_species(name) for name in current_team_names}

    for fmt in format_ids:
        if fmt not in config.FORMATS:
            continue
        data = load_chaos_data(fmt)
        if not data:
            continue

        for p_name in current_team_names:
            # Smogon keys are exact names; fall back to a case insensitive match
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

                    # Roles are read once per candidate
                    if mate not in candidate_fill_roles:
                        mate_data = data.get(mate) or {}
                        mate_weight = sum(mate_data.get('Abilities', {}).values()) or 1
                        candidate_fill_roles[mate] = _infer_candidate_roles(
                            mate_data.get('Moves', {}), mate_weight
                        )

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
