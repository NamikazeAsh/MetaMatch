import json
from . import auditor as auditor_module
from .engine.dex import dex_for_format
from .team import coverageCheck
from . import config


ITEM_ABILITY_SYNERGIES = {
    "Drought":      {"must": ["Heat Rock"],              "reason": "Heat Rock extends sun from 5 to 8 turns"},
    "Drizzle":      {"must": ["Damp Rock"],              "reason": "Damp Rock extends rain from 5 to 8 turns"},
    "Sand Stream":  {"must": ["Smooth Rock"],            "reason": "Smooth Rock extends sand from 5 to 8 turns"},
    "Snow Warning": {"must": ["Icy Rock"],               "reason": "Icy Rock extends snow from 5 to 8 turns"},
    "Guts":         {"must": ["Flame Orb", "Toxic Orb"], "reason": "Guts requires a status condition to activate the Atk boost"},
    "Poison Heal":  {"must": ["Toxic Orb"],              "reason": "Toxic Orb is required to trigger Poison Heal recovery"},
    "Magic Guard":  {"prefer": ["Life Orb"],             "reason": "Magic Guard ignores Life Orb recoil, so the 1.3x boost is free"},
}

# Roles nearly every singles team wants. Cleric and Speed Control were dropped: Heal Bell and
# Aromatherapy are gone in SV, and "Speed Control" had no consistent definition across modules.
ROLE_TEXT = {
    "Hazard Setter": ("Hazard setter", "Stealth Rock or Spikes on one member wears down everything that switches in."),
    "Hazard Remover": ("Hazard removal", "Rapid Spin or Defog stops rocks from chipping your team on every switch."),
    "Pivot": ("Pivot", "U-turn, Volt Switch or Flip Turn lets you deal damage and switch out safely."),
}
CORE_ROLES = set(ROLE_TEXT)


def _and(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def compute_threats(team: dict, format_id: str | None = None, top_n: int = 5) -> list[dict]:
    """
    Identifies top meta threats using STAB type coverage vs the team.
    Scoring: members_hit^2 * usage_pct (prioritises breadth of coverage over mere usage).
    Returns list of dicts matching the existing threats render format.
    """
    format_id = format_id or config.team_format(team)
    poke_stats = auditor_module.load_chaos_data(format_id)
    if not poke_stats:
        return []

    # Load types
    try:
        with open(config.JSON_DIR / "topPoke.json") as f:
            type_map = json.load(f)
    except Exception:
        return []

    team_names = {p["Pokemon"] for p in team.values()}
    dex = dex_for_format(format_id)
    scores = []

    for meta_name, data in poke_stats.items():
        if meta_name in team_names:
            continue

        # "usage" is the rating weighted share of teams running this Pokemon
        usage_pct = data.get("usage", 0) * 100
        if usage_pct < 1.0:
            continue

        types = type_map.get(meta_name, [])
        if not types:
            continue

        # Which team members are hit super-effectively by this Pokemon's STAB types?
        threatened = []
        for p in team.values():
            damage_from = p.get("Damage From", {})
            for t in types:
                if damage_from.get(t.lower(), 1.0) >= 2.0:
                    threatened.append(p["Pokemon"])
                    break

        if not threatened:
            continue

        # Improvement 2: weight members_hit heavily so breadth beats usage
        score = (len(threatened) ** 2) * usage_pct

        # Improvement 1: which team members can hit back super-effectively?
        offensive_answers = []
        for p in team.values():
            damage_to = p.get("Damage To", {})
            for t in types:
                if damage_to.get(t.lower(), 1.0) >= 2.0:
                    offensive_answers.append(p["Pokemon"])
                    break

        # Defensive checks: resist all STAB types
        defensive_checks = []
        for p in team.values():
            damage_from = p.get("Damage From", {})
            if all(damage_from.get(t.lower(), 1.0) <= 0.5 for t in types):
                defensive_checks.append(p["Pokemon"])

        # Improvement 4: top moves from chaos data (>10% usage, prettified)
        # Moves sum to ~4x the Pokemon's weight (one per slot), so divide by the ability total instead
        raw_moves = data.get("Moves", {})
        total_move_weight = sum(data.get("Abilities", {}).values()) or 1
        top_moves = sorted(raw_moves.items(), key=lambda x: x[1], reverse=True)[:3]
        move_strs = []
        for m, v in top_moves:
            pct = v / total_move_weight * 100
            if pct < 10:
                continue
            pretty = (dex.move_name(m) if dex else None) or m.title()
            move_strs.append(f"{pretty} ({pct:.0f}%)")

        stab_str = "/".join(types)
        threatens_str = ", ".join(threatened)

        # Build explanation
        explanation = f"{stab_str} STAB coverage hits {len(threatened)}/{len(team)} team members ({threatens_str}). Present on {usage_pct:.1f}% of ladder teams."
        if move_strs:
            explanation += f" Key moves: {', '.join(move_strs)}."

        # Build counter_play combining offensive + defensive answers
        counter_parts = []
        if offensive_answers:
            counter_parts.append(f"{', '.join(offensive_answers)} can hit back super-effectively.")
        if defensive_checks:
            counter_parts.append(f"{', '.join(defensive_checks)} resists its STAB." if len(defensive_checks) == 1 else f"{', '.join(defensive_checks)} resist its STAB.")
        if not counter_parts:
            counter_parts.append("No team member resists or threatens back — consider adding a counter.")
        counter_str = " ".join(counter_parts)

        scores.append({
            "pokemon": meta_name,
            "explanation": explanation,
            "counter_play": counter_str,
            "_score": score,
        })

    scores.sort(key=lambda x: x["_score"], reverse=True)
    for s in scores:
        del s["_score"]

    return scores[:top_n]


def get_client():
    from .agents.client import get_agent_client
    return get_agent_client()


def get_chat_response(user_query, team_context=None, team_weakness=None, history=None):
    """Generator of answer text chunks for a chat question about the team."""
    from .agents.manager import AgentManager
    manager = AgentManager()
    return manager.get_response(user_query, team_context, team_weakness, history)


def get_suggestions(team):
    """
    Fully deterministic team analysis. No LLM.
    Checks item-ability synergies, role gaps, type coverage, and Smogon usage warnings.
    """
    audit_res = auditor_module.audit_team(team)

    # Team level: one line per core role plus type coverage, each marked ok or missing
    team_analysis = []
    for role, (label, why) in ROLE_TEXT.items():
        who = [p["Pokemon"] for p in team.values() if role in p.get("Roles", [])]
        team_analysis.append({"label": label, "ok": bool(who),
                              "text": f"{_and(who)}." if who else f"Missing. {why}"})
    try:
        uncovered = sorted(t for t, covered in coverageCheck(team).items() if not covered)
        team_analysis.append({"label": "Coverage", "ok": not uncovered,
                              "text": f"Nothing on the team hits {_and(uncovered)} super effectively." if uncovered
                              else "Something on the team hits every type super effectively."})
    except Exception:
        pass

    # Per member: a list of findings, empty when the set looks standard
    pokemon_specific = {}
    for p in team.values():
        name = p["Pokemon"]
        issues = []
        rule = ITEM_ABILITY_SYNERGIES.get(p.get("Ability", ""))
        if rule:
            allowed = rule.get("must") or rule.get("prefer", [])
            if p.get("Item") not in allowed:
                issues.append(f"{p['Ability']} works best with {' or '.join(allowed)}: {rule['reason']}.")
        for w in audit_res.get("warnings", []):
            if w["pokemon"] == name:
                more = f" Most run {w['suggestion']}." if w["category"] == "Item" else                     (f" More common: {w['suggestion']}." if w["suggestion"] else "")
                issues.append(f"{w['current']} is on only {w['usage']:.1f}% of {name} sets.{more}")
        pokemon_specific[name] = issues

    threats = compute_threats(team)

    return {
        "team_analysis": team_analysis,
        "pokemon_specific": pokemon_specific,
        "threats": threats
    }
