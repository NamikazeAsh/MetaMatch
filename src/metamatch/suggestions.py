from openai import OpenAI
import os
from dotenv import load_dotenv
import json
from pprint import pprint
import re
import openai
from . import config
from .rag import store

def get_chat_response(user_query, team_context=None, team_weakness=None):
    """
    RAG-enabled chat function with pre-calculated "Hard Facts" to prevent hallucinations.
    """
    load_dotenv()
    base_url = os.getenv('OLLAMA_HOST', 'http://localhost:11434') + '/v1'
    client = OpenAI(base_url=base_url, api_key='ollama')
    
    # 1. Retrieve RAG Context
    rag_hits = store.query_strategies(user_query, n_results=3)
    rag_context = ""
    if rag_hits:
        rag_context = "### SMOGON STRATEGY DATABASE (READ THIS FOR MOVES/COUNTERS)\n"
        for hit in rag_hits:
            rag_context += f"SOURCE [{hit['metadata'].get('pokemon')}]: {hit['text']}\n\n"
            
    # 2. Format Team Context with "TRUE FACTS"
    team_str = ""
    if team_context:
        team_str = "### YOUR TEAM'S ACTUAL STATS (THE ABSOLUTE TRUTH)\n"
        for p in team_context.values():
            types = "/".join(p.get('Type', []))
            moves = ", ".join([m['name'] for m in p.get('Moves', [])])
            evs = ", ".join([f"{k}:{v}" for k, v in p.get('EVs', {}).items()])
            team_str += f"- {p['Pokemon']} | TYPE: {types} | ITEM: {p.get('Item')} | ABILITY: {p.get('Ability')} | NATURE: {p.get('Nature')} | EVS: {evs} | MOVES: {moves}\n"

    # 3. Inject Pre-calculated Math (Weakness Map)
    weak_str = ""
    if team_weakness:
        weak_str = "### TEAM-WIDE VULNERABILITIES (CALCULATED BY ENGINE)\n"
        for t, counts in team_weakness.items():
            if counts['weak'] > 0:
                weak_str += f"- {t.capitalize()}: {counts['weak']} members of your team are WEAK to this.\n"

    # 4. Construct the "Ground Truth" System Prompt
    system_content = f"""
    You are a competitive Pokemon coach. 
    
    CRITICAL RULES:
    1. NO QUESTIONS: Do not ask the user for information. You have all the data you need in the sections below. 
    2. ANALYZE AND ADVISE: Look at the 'TEAM-WIDE VULNERABILITIES'. If even 1 mon is weak to a threat's STAB, mention it.
    3. THE DATA IS THE TRUTH: Use the 'YOUR TEAM'S ACTUAL STATS' for types and moves.
    4. SMOGON KNOWLEDGE: Use the 'SMOGON STRATEGY DATABASE' to understand the opponent.

    {team_str}
    
    {weak_str}

    {rag_context}
    """
    
    # 5. Stream Response
    stream = client.chat.completions.create(
        model="llama3.2:3b-instruct-q4_K_M",
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_query}
        ],
        stream=True,
        temperature=0.1
    )
    
    return stream

def get_suggestions(team):
    load_dotenv()
    
    # Load topPoke.json locally to avoid global state issues on import
    try:
        with open(config.JSON_DIR / "topPoke.json", "r") as f:
            topPoke = json.load(f)
    except FileNotFoundError:
        topPoke = {}

    max_retries = 5
    attempt = 0
    
    # Prepare Clean Data with Stats
    clean_team = []
    for p in team.values():
        clean_team.append({
            "Pokemon": p["Pokemon"],
            "Item": p["Item"],
            "Ability": p["Ability"],
            "Moves": [m["name"] for m in p["Moves"]],
            "EVs": p["EVs"],
            "Nature": p["Nature"],
            "Base Stats": p.get("Base Stats", {}), # Crucial for context
            "Real Speed": p.get("Speed", 0),       # Crucial for context
            "Roles": p.get("Roles", [])
        })

    while attempt < max_retries:
        # Use the OpenAI client to connect to a local Ollama instance
        # Docker support: check env var, default to localhost
        base_url = os.getenv('OLLAMA_HOST', 'http://localhost:11434') + '/v1'
        client = OpenAI(base_url=base_url, api_key='ollama')
        attempt += 1
        
        try:
            # Prepare meta list (top 60 for context)
            meta_list = list(topPoke.keys())[:60]
            
            completion = client.chat.completions.create(
                model="llama3.2:3b-instruct-q4_K_M",
                messages=[{
                    "role": "user",
                    "content": f"""
                    You are a competitive Pokemon expert. Analyze this team deeply.
                    
                    Return a JSON object with this EXACT structure:
                    {{
                        "team_analysis": ["Detailed point about team synergy", "Point about major weakness"],
                        "pokemon_specific": {{
                            "PokemonName1": "Specific advice (e.g., change item, move, or EVs)",
                            "PokemonName2": "Specific advice"
                        }},
                        "threats": [
                            {{
                                "pokemon": "ThreatName", 
                                "explanation": "Why it beats this team",
                                "counter_play": "How to handle it"
                            }}
                        ]
                    }}

                    Meta Context: {meta_list}
                    Team Data (with Stats): {json.dumps(clean_team, indent=2)}
                    """
                }],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=4000,
                stream=False,
            )
            
            result_text = completion.choices[0].message.content
            result_json = json.loads(result_text)
            
            return result_json

        except (json.JSONDecodeError, AttributeError, openai.APIError) as e:
            print(f"An error occurred on attempt {attempt}: {e}")
            continue
    
    return None

def get_team_guide(team):
    load_dotenv()
    
    # Reuse the clean team logic
    clean_team = []
    for p in team.values():
        clean_team.append({
            "Pokemon": p["Pokemon"],
            "Item": p["Item"],
            "Ability": p["Ability"],
            "Moves": [m["name"] for m in p["Moves"]],
            "EVs": p["EVs"],
            "Nature": p["Nature"],
            "Base Stats": p.get("Base Stats", {}),
            "Real Speed": p.get("Speed", 0),
            "Roles": p.get("Roles", [])
        })

    max_retries = 3
    attempt = 0
    
    while attempt < max_retries:
        base_url = os.getenv('OLLAMA_HOST', 'http://localhost:11434') + '/v1'
        client = OpenAI(base_url=base_url, api_key='ollama')
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
                "win_condition": "One or two sentences explaining the primary goal (e.g., 'Wear down counters with hazards to sweep with Kingambit').",
                "lead_options": [
                    {{
                        "pokemon": "Name",
                        "scenario": "When to lead with this (e.g., 'Lead vs Hyper Offense to set screens')."
                    }}
                ],
                "key_combos": [
                    {{
                        "name": "Combo Name (e.g. Volt-Turn)",
                        "description": "Explain how two specific pokemon work together."
                    }}
                ],
                "tera_strategy": "Who is the best Tera Captain and when to use it?"
            }}
            """

            completion = client.chat.completions.create(
                model="llama3.2:3b-instruct-q4_K_M",
                messages=[{"role": "user", "content": prompt_content}],
                response_format={"type": "json_object"},
                temperature=0.4, # Higher temp for more creative writing
                max_tokens=2000,
                stream=False,
            )
            
            result_text = completion.choices[0].message.content
            result_json = json.loads(result_text)
            
            return result_json

        except (json.JSONDecodeError, AttributeError, openai.APIError) as e:
            print(f"Guide generation error on attempt {attempt}: {e}")
            continue
    
    return None

