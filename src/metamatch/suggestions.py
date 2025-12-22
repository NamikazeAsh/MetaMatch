from openai import OpenAI
import os
from dotenv import load_dotenv
import json
from pprint import pprint
import re
import openai
from . import config

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

