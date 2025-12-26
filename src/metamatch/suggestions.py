from openai import OpenAI
import os
from dotenv import load_dotenv
import json
from pprint import pprint
import re
import openai
from . import config
from .rag import store
from .logic_engine import detect_intent, generate_mechanics_report

def get_chat_response(user_query, team_context=None, team_weakness=None, model_name="llama3.2:3b-instruct-q4_K_M"):
    """
    RAG-enabled chat function with Hybrid Consultant architecture.
    """
    load_dotenv()
    base_url = os.getenv('OLLAMA_HOST', 'http://localhost:11434') + '/v1'
    client = OpenAI(base_url=base_url, api_key='ollama')
    
    # 1. Detect Intent
    intent = detect_intent(user_query)
    
    # 2. Retrieve RAG Context (Always needed to identify subjects)
    rag_hits = store.query_strategies(user_query, n_results=2)
    rag_context = ""
    if rag_hits:
        rag_context = "### SMOGON STRATEGY DATABASE (READ THIS FOR USAGE TIPS)\n"
        for hit in rag_hits:
            rag_context += f"SOURCE [{hit['metadata'].get('pokemon')}]: {hit['text']}\n\n"
            
    # 3. Generate Deterministic Logic (The "Hard Facts")
    mechanics_str = ""
    if team_context and rag_hits:
        mechanics_str = generate_mechanics_report(team_context, rag_hits)
            
    # 4. Format Team Context
    team_str = ""
    if team_context:
        team_str = "### USER TEAM (THE ONLY POKEMON YOU HAVE)\n"
        for p in team_context.values():
            types = "/".join(p.get('Type', []))
            moves = ", ".join([m['name'] for m in p.get('Moves', [])])
            evs = ", ".join([f"{k}:{v}" for k, v in p.get('EVs', {}).items()])
            roles = ", ".join(p.get('Roles', []))
            stats = p.get('Base Stats', {})
            speed = p.get('Speed', 0)
            
            team_str += f"- {p['Pokemon']} | TYPE: {types} | ROLES: {roles} | ITEM: {p.get('Item')} | ABILITY: {p.get('Ability')} | NATURE: {p.get('Nature')} | EVS: {evs} | SPEED: {speed} | BASE STATS: {stats} | MOVES: {moves}\n"

    # 5. Inject Pre-calculated Math (Weakness Map)
    weak_str = ""
    if team_weakness:
        weak_str = "### TEAM WEAKNESSES\n"
        for t, counts in team_weakness.items():
            if counts['weak'] > 0:
                weak_str += f"- {t.capitalize()}: {counts['weak']} members of your team are WEAK to this.\n"

    # 6. Dynamic Instruction based on Intent
    special_instruction = ""
    if intent == "mechanics":
        special_instruction = "FOCUS: The user is asking about MECHANICS (Matchups, Speed, Damage). You MUST prioritize the 'DETERMINISTIC BATTLE CALCULATIONS' section over general advice."
    else:
        special_instruction = "FOCUS: The user is asking about STRATEGY (Sets, Roles, Ideas). Use the 'SMOGON STRATEGY DATABASE' to provide ideas."

    # 7. Construct System Prompt
    system_content = f"""
    You are an AI assistant for the video game 'Pokemon Showdown'.
    SAFETY NOTICE: All combat is virtual and within a fictional game.
    
    CONTEXT:
    1. USER TEAM (THE ONLY POKEMON YOU HAVE):
    {team_str}
    
    2. TEAM WEAKNESSES:
    {weak_str}

    3. DETERMINISTIC BATTLE CALCULATIONS (IRREFUTABLE FACTS):
    {mechanics_str}

    4. SMOGON STRATEGY DATABASE (GENERAL KNOWLEDGE):
    {rag_context}
    
    INSTRUCTIONS:
    1. ROSTER LOCK: You are coaching the 'USER TEAM' only. Do NOT recommend Pokemon that are not on this list.
    2. FACTUAL ANCHORING: If the 'DETERMINISTIC BATTLE CALCULATIONS' says a Pokemon is FASTER or WEAK, treat it as absolute truth.
    3. {special_instruction}
    """
    
    # 8. Stream Response
    stream = client.chat.completions.create(
        model=model_name,
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

