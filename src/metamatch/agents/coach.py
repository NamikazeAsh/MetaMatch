from openai import OpenAI
import os
from dotenv import load_dotenv
from metamatch.rag import store

class CoachAgent:
    def __init__(self, model_name="llama3.2:3b-instruct-q4_K_M"):
        load_dotenv()
        base_url = os.getenv('OLLAMA_HOST', 'http://localhost:11434') + '/v1'
        self.client = OpenAI(base_url=base_url, api_key='ollama')
        self.model = model_name

    def run(self, query: str, team_context: dict) -> str:
        """
        Executes the Strategy Agent.
        Focus: Game plans, win conditions, advice.
        Temperature: 0.4 (Creative but grounded)
        """
        
        # 1. Retrieve Strategy Guides
        rag_hits = store.query_strategies(query, n_results=2)
        
        rag_context = ""
        if rag_hits:
            rag_context = "### SMOGON STRATEGY DATABASE (REFERENCE)\n"
            for hit in rag_hits:
                rag_context += f"SOURCE [{hit['metadata'].get('pokemon')}]: {hit['text']}\n\n"

        # 2. Format Team for Context
        team_str = "### USER TEAM\n"
        for p in team_context.values():
            moves = ", ".join([m['name'] for m in p.get('Moves', [])])
            team_str += f"- {p['Pokemon']} ({p.get('Item')}) | Moves: {moves}\n"

        # 3. Strategy Prompt
        system_content = f"""
        You are Professor Oak, the legendary Pokemon researcher and mentor. 
        It's time to help this trainer understand the big picture!
        
        CONTEXT:
        {rag_context}
        
        {team_str}
        
        INSTRUCTIONS:
        1. Use the 'SMOGON STRATEGY DATABASE' to explain HOW to use the Pokemon/Team.
        2. Focus on "Win Conditions", "Checks", and "Counters".
        3. Be encouraging and strategic, like a wise professor.
        """

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": query}
            ],
            temperature=0.4, # BALANCED
            stream=True
        )
        
        return response
