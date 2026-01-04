from openai import OpenAI
import os
import json
from dotenv import load_dotenv
from metamatch import auditor, recommender
from metamatch.rag import store

class AuditorAgent:
    def __init__(self, model_name="llama3.2:3b-instruct-q4_K_M"):
        load_dotenv()
        base_url = os.getenv('OLLAMA_HOST', 'http://localhost:11434') + '/v1'
        self.client = OpenAI(base_url=base_url, api_key='ollama')
        self.model = model_name

    def run(self, query: str, team_context: dict) -> str:
        """
        Executes the Builder Agent.
        Focus: Sets, Items, EVs, Teammates, Usage Stats.
        Temperature: 0.2 (Data-driven)
        """
        
        # 1. Run Statistical Audits (Real Code)
        audit_res = auditor.audit_team(team_context)
        reports = audit_res.get("reports", {})
        warnings = audit_res.get("warnings", [])
        
        # 2. Run Recommender (Real Code)
        team_names = [p['Pokemon'] for p in team_context.values()]
        recommendations = recommender.get_recommendations(team_names, top_n=3)

        # 3. Retrieve RAG Context for 'Why' (Grounded Reasoning)
        rag_hits = store.query_strategies(query, n_results=1)
        rag_context = ""
        if rag_hits:
            rag_context = f"### STRATEGY CONTEXT (EXPLAINER)\n{rag_hits[0]['text']}\n"
        
        # 4. Format Data for LLM
        audit_str = "### METAGAME USAGE REPORT\n"
        for p_name, report in reports.items():
            audit_str += f"- {p_name}: Item '{report['item']['name']}' ({report['item']['usage']:.1f}%), Ability '{report['ability']['name']}' ({report['ability']['usage']:.1f}%)\n"
            m_list = [f"{m}({v:.1f}%)" for m,v in report['moves'].items()]
            audit_str += f"  Moves: {', '.join(m_list)}\n"
        
        warn_str = ""
        if warnings:
            warn_str = "### SUBOPTIMAL WARNINGS\n"
            for w in warnings:
                warn_str += f"- {w['pokemon']} {w['category']} usage is low ({w['usage']:.1f}%). Popular: {w['suggestion']}\n"
            
        rec_str = "### SYNERGY RECOMMENDATIONS\n"
        if recommendations:
            rec_str += ", ".join([f"{name} (Score: {score})" for name, score in recommendations])
        
        # 5. Builder Prompt
        system_content = f"""
        You are Brock, the experienced Pokemon breeder and analyst. 
        You have a keen eye for team synergy and metagame trends!
        
        USAGE DATA:
        {audit_str}
        
        {warn_str}
        
        {rec_str}
        
        {rag_context}
        
        INSTRUCTIONS:
        1. Answer strictly using the USAGE DATA and STRATEGY CONTEXT.
        2. If the user asks about an item or move, cite its usage percentage.
        3. Guide the trainer based on what's effective in the current meta.
        4. Be supportive and grounded in your analysis.
        """

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": query}
            ],
            temperature=0.2, # DATA DRIVEN
            stream=True
        )
        
        return response
