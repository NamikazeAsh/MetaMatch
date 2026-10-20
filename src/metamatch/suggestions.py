from dotenv import load_dotenv
import json
import re
from . import auditor as auditor_module
from .team import coverageCheck
from . import config


ITEM_ABILITY_SYNERGIES = {
    "Drought":      {"must": ["Heat Rock"],              "reason": "Heat Rock extends sun from 5 to 8 turns"},
    "Drizzle":      {"must": ["Damp Rock"],              "reason": "Damp Rock extends rain from 5 to 8 turns"},
    "Sand Stream":  {"must": ["Smooth Rock"],            "reason": "Smooth Rock extends sand from 5 to 8 turns"},
    "Snow Warning": {"must": ["Icy Rock"],               "reason": "Icy Rock extends snow from 5 to 8 turns"},
    "Guts":         {"must": ["Flame Orb", "Toxic Orb"], "reason": "Guts requires a status condition to activate the Atk boost"},
    "Poison Heal":  {"must": ["Toxic Orb"],              "reason": "Toxic Orb is required to trigger Poison Heal recovery"},
    "Magic Guard":  {"prefer": ["Life Orb"],             "reason": "Life Orb recoil is negated by Magic Guard — free 1.3x power"},
}

CORE_ROLES = {"Hazard Setter", "Hazard Remover", "Pivot", "Speed Control", "Cleric"}

# Chaos file stores move names as lowercase slugs with no spaces — map common ones
MOVE_DISPLAY = {
    "rapidspin": "Rapid Spin", "headlongrush": "Headlong Rush", "icespinner": "Ice Spinner",
    "psychicnoise": "Psychic Noise", "drainingkiss": "Draining Kiss", "dragondance": "Dragon Dance",
    "calmmind": "Calm Mind", "dracometeor": "Draco Meteor", "hydrosteam": "Hydro Steam",
    "flipturn": "Flip Turn", "dragonpulse": "Dragon Pulse", "thunderclap": "Thunderclap",
    "swordsdance": "Swords Dance", "nastyplot": "Nasty Plot", "stealthrock": "Stealth Rock",
    "knockoff": "Knock Off", "kowtowcleave": "Kowtow Cleave", "ironhead": "Iron Head",
    "bodypress": "Body Press", "makeitrain": "Make It Rain", "shadowball": "Shadow Ball",
    "fireblast": "Fire Blast", "fierydance": "Fiery Dance", "sludgewave": "Sludge Wave",
    "energyball": "Energy Ball", "voltswitch": "Volt Switch", "closecombat": "Close Combat",
    "spiritbreak": "Spirit Break", "shadowsneak": "Shadow Sneak", "moonblast": "Moonblast",
    "gigadrain": "Giga Drain", "sludgebomb": "Sludge Bomb", "sleeppowder": "Sleep Powder",
    "futuresight": "Future Sight", "chillyreception": "Chilly Reception", "foulplay": "Foul Play",
    "clearsmog": "Clear Smog", "pollenpuff": "Pollen Puff", "willowisp": "Will-O-Wisp",
    "thunderwave": "Thunder Wave", "dazzlinggleam": "Dazzling Gleam", "mysticalfire": "Mystical Fire",
    "highhorsepower": "High Horsepower", "bravebird": "Brave Bird", "woodhammer": "Wood Hammer",
    "grassyglide": "Grassy Glide", "partingshot": "Parting Shot", "healingwish": "Healing Wish",
    "trickroom": "Trick Room", "tailwind": "Tailwind", "uturn": "U-turn",
    "heavyslam": "Heavy Slam", "stoneedge": "Stone Edge", "iciclecrash": "Icicle Crash",
    "aquajet": "Aqua Jet", "bulletpunch": "Bullet Punch", "extremespeed": "Extreme Speed",
    "leechseed": "Leech Seed", "shellsmash": "Shell Smash", "quiverdance": "Quiver Dance",
    "rockblast": "Rock Blast", "rockslide": "Rock Slide", "icywind": "Icy Wind",
    "aurasphere": "Aura Sphere", "airslash": "Air Slash", "poisonjab": "Poison Jab",
    "thunderbolt": "Thunderbolt", "zapcannon": "Zap Cannon", "triattack": "Tri Attack",
    "scaldingcoffee": "Scalding Coffee", "gunkshot": "Gunk Shot", "suckerpunch": "Sucker Punch",
    "powerwhip": "Power Whip", "leafstorm": "Leaf Storm", "focusblast": "Focus Blast",
    "shadowforce": "Shadow Force", "phantomforce": "Phantom Force", "darkpulse": "Dark Pulse",
    "flashcannon": "Flash Cannon", "irondefense": "Iron Defense", "calmmind": "Calm Mind",
    "wickedblow": "Wicked Blow", "surgingstrikes": "Surging Strikes", "populationbomb": "Population Bomb",
    "boosterenergy": "Booster Energy", "supremeoverlord": "Supreme Overlord",
}

def compute_threats(team: dict, format_id: str | None = None, top_n: int = 5) -> list[dict]:
    """
    Identifies top meta threats using STAB type coverage vs the team.
    Scoring: members_hit^2 * usage_pct (prioritises breadth of coverage over mere usage).
    Returns list of dicts matching the existing threats render format.
    """
    # Load stats
    format_id = format_id or config.team_format(team)
    stats_path = config.STATS_DIR / (config.format_info(format_id)["stats"] + ".json")
    try:
        with open(stats_path) as f:
            raw = json.load(f)
        poke_stats = raw.get("data", {})
    except Exception:
        return []

    # Load types
    try:
        with open(config.JSON_DIR / "topPoke.json") as f:
            type_map = json.load(f)
    except Exception:
        return []

    team_names = {p["Pokemon"] for p in team.values()}
    total_raw = sum(v.get("Raw count", 0) for v in poke_stats.values())
    if total_raw == 0:
        return []

    scores = []

    for meta_name, data in poke_stats.items():
        if meta_name in team_names:
            continue

        usage_pct = data.get("Raw count", 0) / total_raw * 100
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
        raw_moves = data.get("Moves", {})
        total_move_weight = sum(raw_moves.values()) or 1
        top_moves = sorted(raw_moves.items(), key=lambda x: x[1], reverse=True)[:3]
        move_strs = []
        for m, v in top_moves:
            pct = v / total_move_weight * 100
            if pct < 10:
                continue
            pretty = MOVE_DISPLAY.get(m.lower(), m.replace("-", " ").title())
            move_strs.append(f"{pretty} ({pct:.0f}%)")

        stab_str = "/".join(types)
        threatens_str = ", ".join(threatened)

        # Build explanation
        explanation = f"{stab_str} STAB coverage hits {len(threatened)}/6 team members ({threatens_str}). Present on {usage_pct:.1f}% of ladder teams."
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


def get_chat_response(user_query, team_context=None, team_weakness=None, model_name=None):
    from .agents.manager import AgentManager
    manager = AgentManager()
    return manager.get_response(user_query, team_context, team_weakness)


def get_suggestions(team):
    """
    Fully deterministic team analysis. No LLM.
    Checks item-ability synergies, role gaps, type coverage, and Smogon usage warnings.
    """
    audit_res = auditor_module.audit_team(team)
    audit_reports = audit_res.get("reports", {})

    # --- Team-level analysis ---
    team_analysis = []

    team_roles = {r for p in team.values() for r in p.get("Roles", [])}
    missing_roles = CORE_ROLES - team_roles
    if missing_roles:
        team_analysis.append(f"Missing core roles: {', '.join(sorted(missing_roles))}. Consider adding a Pokemon that can fill these.")

    try:
        coverage = coverageCheck(team)
        uncovered = [t for t, covered in coverage.items() if not covered]
        if uncovered:
            team_analysis.append(f"No offensive coverage against: {', '.join(sorted(uncovered))} types.")
    except Exception:
        pass

    if not team_analysis:
        team_analysis.append("Team has solid role distribution and type coverage.")

    # --- Per-Pokemon analysis ---
    pokemon_specific = {}

    for p in team.values():
        name = p["Pokemon"]
        issues = []

        # Item-ability synergy check
        rule = ITEM_ABILITY_SYNERGIES.get(p.get("Ability", ""))
        if rule:
            allowed = rule.get("must") or rule.get("prefer", [])
            if p.get("Item") not in allowed:
                preferred = " or ".join(allowed)
                issues.append(f"Item mismatch: {p['Ability']} works best with {preferred} — {rule['reason']}.")

        # Smogon usage warnings (low-usage item or moves)
        for w in audit_res.get("warnings", []):
            if w["pokemon"] == name:
                issues.append(f"Low-usage {w['category'].lower()}: '{w['current']}' ({w['usage']:.1f}% on ladder). {w['suggestion']}.")

        pokemon_specific[name] = " ".join(issues) if issues else "No issues detected."

    threats = compute_threats(team)

    return {
        "team_analysis": team_analysis,
        "pokemon_specific": pokemon_specific,
        "threats": threats
    }


def get_team_guide(team):
    load_dotenv()
    is_champions = config.format_game(config.team_format(team)) == "champions"
    gimmick_key, gimmick_q, gimmick_example = (
        ("mega_strategy", "Who should Mega Evolve, and when?",
         "Garchomp Mega Evolves once its checks are removed to clean with boosted Earthquake.")
        if is_champions else
        ("tera_strategy", "Who is the best Tera Captain?",
         "Kingambit Teras Dark for a powerful unresisted STAB sweep.")
    )

    clean_team = []
    for p in team.values():
        clean_team.append({
            "Pokemon": p["Pokemon"],
            "Item": p["Item"],
            "Ability": p["Ability"],
            "Moves": [m["name"] for m in p["Moves"]],
            "EVs": p.get("SP") if is_champions else p["EVs"],
            "Nature": p["Nature"],
            "Base Stats": p.get("Base Stats", {}),
            "Real Speed": p.get("Speed", 0),
            "Roles": p.get("Roles", [])
        })

    max_retries = 3
    attempt = 0
    client, model = get_client()

    while attempt < max_retries:
        attempt += 1

        try:
            prompt_content = f"""
            You are a competitive Pokemon coach teaching a player how to pilot this specific team.

            **Team Data:**
            {json.dumps(clean_team, indent=2)}

            **Task:**
            Write a strategic guide on how to play this team. Focus on game flow, not specific movesets.

            Return a JSON object with this EXACT structure:
            {{
                "win_condition": "One or two sentences explaining the primary goal.",
                "lead_options": [
                    {{
                        "pokemon": "Name",
                        "scenario": "When to lead with this."
                    }}
                ],
                "key_combos": [
                    {{
                        "name": "Combo Name",
                        "description": "Explain synergy."
                    }}
                ],
                "{gimmick_key}": "{gimmick_q}"
            }}

            Example output:
            {{
                "win_condition": "Set up Stealth Rock early with Great Tusk and sweep late-game with Kingambit once checks are worn down.",
                "lead_options": [
                    {{
                        "pokemon": "Great Tusk",
                        "scenario": "Lead when opponent has no clear spinner; guarantees rocks."
                    }}
                ],
                "key_combos": [
                    {{
                        "name": "Tusk + Kingambit",
                        "description": "Tusk removes hazards and chips walls; Kingambit cleans with boosted Kowtow Cleave."
                    }}
                ],
                "{gimmick_key}": "{gimmick_example}"
            }}
            """

            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt_content}],
                response_format={"type": "json_object"} if "gpt" in model else None,
                temperature=0.4,
                max_tokens=2000,
                stream=False,
            )

            result_text = completion.choices[0].message.content

            if "{" in result_text and "}" in result_text:
                json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
                if json_match:
                    result_text = json_match.group()

            return json.loads(result_text)

        except Exception as e:
            print(f"Guide generation error on attempt {attempt}: {e}")
            continue

    return None
