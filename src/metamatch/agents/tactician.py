from .client import get_agent_client
from metamatch.logic_engine import generate_mechanics_report, find_pokemon_in_query

class TacticianAgent:
    def __init__(self, model_name=None):
        self.client, self.model = get_agent_client()
        if model_name:
            self.model = model_name

    def run(self, query: str, team_context: dict, team_weakness: dict = None) -> str:
        """
        Clemont, the mechanics agent: type matchups, Speed and damage for questions the planner can't turn into a
        single verdict. The model only restates the computed matchups and the team's defensive profile.
        """
        # Opponents are the Pokemon named in the question that aren't on the user's team
        team_names = {p['Pokemon'].lower() for p in team_context.values()}
        subjects = [n for n in find_pokemon_in_query(query) if n.lower() not in team_names]

        mechanics_str = generate_mechanics_report(team_context, subjects)

        # Each member's immunities (and what grants them) and 2x or worse weaknesses, from its Damage From table
        defensive_str = ""
        if team_weakness:
            defensive_str = "### GENERAL DEFENSIVE PROFILE (TYPE CHART + ABILITIES)\n"
            for p in team_context.values():
                p_name = p['Pokemon']
                p_immunities = []
                p_weaknesses = []

                dmg_from = p.get('Damage From', {})
                ability = p.get('Ability', '').lower()
                item = p.get('Item', '').lower()
                
                for t, mult in dmg_from.items():
                    if mult == 0.0:
                        reason = ""
                        # An immunity the typing alone doesn't explain comes from the ability or Air Balloon
                        if t == 'ground' and ('levitate' in ability or 'earth eater' in ability):
                            reason = f" (via {p['Ability']})"
                        elif t == 'ground' and item == 'air balloon':
                            reason = f" (via {p['Item']})"
                        elif t == 'electric' and ability in ['volt absorb', 'lightning rod', 'motor drive']:
                            reason = f" (via {p['Ability']})"
                        elif t == 'water' and ability in ['water absorb', 'storm drain', 'dry skin']:
                            reason = f" (via {p['Ability']})"
                        elif t == 'fire' and ability in ['flash fire', 'well-baked body']:
                            reason = f" (via {p['Ability']})"
                        elif t == 'grass' and ability == 'sap sipper':
                            reason = f" (via {p['Ability']})"
                            
                        p_immunities.append(f"{t.capitalize()}{reason}")
                    elif mult >= 2.0:
                        p_weaknesses.append(f"{t.capitalize()} ({mult}x)")
                
                if p_immunities:
                    defensive_str += f"[{p_name}]: HARD IMMUNE to {', '.join(p_immunities)}.\n"
                if p_weaknesses:
                    defensive_str += f"[{p_name}]: WEAK to {', '.join(p_weaknesses)}.\n"
        
        if not mechanics_str and not defensive_str:
            mechanics_str = "No specific matchup data calculated."

        system_content = f"""
        You are Clemont, the brilliant engineer and logic expert.
        The future is now thanks to science! You function as a deterministic Battle Mechanics Calculator.
        Respond in plain prose only. No JSON. Be concise: 3–5 sentences.

        INPUT DATA (IRREFUTABLE FACTS):
        {defensive_str}
        {mechanics_str}

        INSTRUCTIONS:
        1. Answer the user's question using ONLY the calculated data above.
        2. If the data provides a reason (e.g. "via Levitate"), you MAY state it.
        3. DO NOT use external knowledge.
        4. If the data says a Pokemon is IMMUNE, say it is IMMUNE.
        5. Be robotic, precise, and extremely brief.
        """

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": query}
            ],
            temperature=0.0,
            stream=True
        )
        
        return response
