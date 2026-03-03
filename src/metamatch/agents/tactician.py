from .client import get_agent_client
from metamatch.logic_engine import generate_mechanics_report
from metamatch.rag import store

class TacticianAgent:
    def __init__(self, model_name=None):
        self.client, self.model = get_agent_client()
        if model_name:
            self.model = model_name

    def run(self, query: str, team_context: dict, team_weakness: dict = None) -> str:
        """
        Executes the Mechanics Agent.
        Focus: Deterministic calculations, Type matchups, Speed tiers.
        Temperature: 0.0 (Strict)
        """
        
        # 1. Retrieve RAG hits ONLY to identify the subject (e.g. "Rotom-Wash")
        rag_hits = store.query_strategies(query, n_results=1)
        
        # 2. Generate the Hard Facts (Specific Matchups)
        mechanics_str = generate_mechanics_report(team_context, rag_hits)
        
        # 3. Generate General Defensive Profile (from Team Weakness Map)
        defensive_str = ""
        if team_weakness:
            defensive_str = "### GENERAL DEFENSIVE PROFILE (TYPE CHART + ABILITIES)\n"
            # Invert the map to show Pokemon -> Weaknesses/Immunities
            # team_weakness structure: {type: {'weak': count, 'resist': count, 'immune': count, 'pokemon': [list of weak ones]}}
            # We need to dig a bit deeper or just list the known immunities for the team
            
            # Since team_weakness is type-centric, let's iterate through team_context to get per-pokemon defensive facts
            for p in team_context.values():
                p_name = p['Pokemon']
                p_immunities = []
                p_weaknesses = []
                
                # Check the pre-calculated 'Damage From' if available (it is added in team.py readTeam)
                dmg_from = p.get('Damage From', {})
                ability = p.get('Ability', '').lower()
                item = p.get('Item', '').lower()
                
                for t, mult in dmg_from.items():
                    if mult == 0.0:
                        reason = ""
                        # Detect source of immunity
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

        # 4. Strict System Prompt
        system_content = f"""
        You are Clemont, the brilliant engineer and logic expert. 
        The future is now thanks to science! You function as a deterministic Battle Mechanics Calculator.
        
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
            temperature=0.0, # STRICT
            stream=True
        )
        
        return response
