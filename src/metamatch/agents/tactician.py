from .client import chat
from metamatch.engine import rules
from metamatch.logic_engine import generate_mechanics_report, find_pokemon_in_query

# The calc block is about 1200 tokens per opponent; three keep the prompt inside the context
MAX_SUBJECTS = 3
# Immunities the typing alone doesn't explain: (attack type, what grants it on the member)
GRANTED = {"ground": ("levitate", "earth eater"), "electric": ("volt absorb", "lightning rod", "motor drive"),
           "water": ("water absorb", "storm drain", "dry skin"), "fire": ("flash fire", "well-baked body"),
           "grass": ("sap sipper",)}


def _matchup_line(p):
    """'- Your Rotom-Wash: immune to Ground (from Levitate); resists Fire, Water; weak to Grass (2x).'"""
    ability, item = p.get("Ability", "").lower(), p.get("Item", "").lower()
    immune, resist, weak = [], [], []
    for t, mult in p.get("Damage From", {}).items():
        if mult == 0.0:
            reason = ""
            if ability in GRANTED.get(t, ()):
                reason = f" (from {p['Ability']})"
            elif t == "ground" and item == "air balloon":
                reason = f" (from {p['Item']})"
            immune.append(f"{t.capitalize()}{reason}")
        elif mult < 1.0:
            resist.append(t.capitalize())
        elif mult >= 2.0:
            weak.append(f"{t.capitalize()} ({mult:g}x)")
    parts = [f"immune to {', '.join(immune)}" if immune else "", f"resists {', '.join(resist)}" if resist else "",
             f"weak to {', '.join(weak)}" if weak else ""]
    return f"- Your {p['Pokemon']}: " + ("; ".join(x for x in parts if x) or "no immunities, resistances or weaknesses") + "."


class TacticianAgent:
    def __init__(self, model_name=None):
        self.model = model_name

    def run(self, query: str, team_context: dict, team_weakness: dict = None):
        """
        Clemont, the mechanics agent: type matchups, Speed and damage for questions the planner can't turn into a
        single verdict. The model only restates the computed matchups and the team's defensive profile.
        Yields the answer as text pieces.
        """
        # Opponents are the Pokemon named in the question that aren't on the user's team
        team_names = {p['Pokemon'].lower() for p in team_context.values()}
        subjects = [n for n in find_pokemon_in_query(query) if n.lower() not in team_names][:MAX_SUBJECTS]

        mechanics_str = generate_mechanics_report(team_context, subjects)
        defensive_str = ""
        if team_weakness:
            defensive_str = ("Your team's type matchups (type chart plus abilities):\n"
                             + "\n".join(_matchup_line(p) for p in team_context.values()))
        if not mechanics_str and not defensive_str:
            mechanics_str = "No specific matchup data calculated."
        rules_str = "Rules (Pokemon Showdown's own text):\n" + "\n".join(f"- {line}" for line in rules.team_rules(team_context, query))

        system_content = (
            "You are Clemont, an upbeat young inventor who explains exactly how battle mechanics work.\n"
            "Answer in 2 to 4 sentences of plain prose, no lists.\n"
            "Use only the facts below. Never add a type, number, move, ability or Pokemon they do not state. "
            "If they do not settle the question, say what they do show.\n\n"
            f"{defensive_str}\n\n{mechanics_str}\n\n{rules_str}"
        )
        return chat([{"role": "system", "content": system_content}, {"role": "user", "content": query}],
                    temperature=0.0, max_tokens=250, stream=True, model=self.model)
