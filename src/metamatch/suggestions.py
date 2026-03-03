import streamlit as st
from openai import OpenAI
import os
from dotenv import load_dotenv
import json
from pprint import pprint
import re
import openai
from . import config

def get_client():
    """
    Returns a configured OpenAI-compatible client.
    Prioritizes Hugging Face Inference API if HF_TOKEN is present.
    """
    # 1. Try Hugging Face (Free Inference API)
    hf_token = st.secrets.get("HF_TOKEN") or os.getenv("HF_TOKEN")
    if hf_token:
        # Using Hugging Face as an OpenAI-compatible provider
        return OpenAI(
            base_url="https://api-inference.huggingface.co/v1/",
            api_key=hf_token
        ), "mistralai/Mistral-7B-Instruct-v0.2"

    # 2. Try OpenAI (Paid)
    openai_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if openai_key:
        return OpenAI(api_key=openai_key), "gpt-3.5-turbo"

    # 3. Fallback to Local Ollama
    base_url = os.getenv('OLLAMA_HOST', 'http://localhost:11434') + '/v1'
    return OpenAI(base_url=base_url, api_key='ollama'), "llama3.2:3b-instruct-q4_K_M"

def get_chat_response(user_query, team_context=None, team_weakness=None, model_name=None):
    """
    RAG-enabled chat function using Multi-Agent Architecture.
    Delegates to AgentManager for routing and specialized execution.
    """
    # Lazy import to avoid circular dependency
    from .agents.manager import AgentManager
    manager = AgentManager()
    
    # Delegate to the autonomous agent system
    stream = manager.get_response(user_query, team_context, team_weakness)
    
    return stream

def get_suggestions(team):
    load_dotenv()
    
    # Load topPoke.json locally to avoid global state issues on import
    try:
        with open(config.JSON_DIR / "topPoke.json", "r") as f:
            topPoke = json.load(f)
    except FileNotFoundError:
        topPoke = {}

    max_retries = 3
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

    client, model = get_client()

    while attempt < max_retries:
        attempt += 1
        
        try:
            # Prepare meta list (top 60 for context)
            meta_list = list(topPoke.keys())[:60]
            
            completion = client.chat.completions.create(
                model=model,
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
                # Response format only supported by some models, adding safety
                response_format={"type": "json_object"} if "gpt" in model else None,
                temperature=0.2,
                max_tokens=4000,
                stream=False,
            )
            
            result_text = completion.choices[0].message.content
            
            # If not a JSON object model, try to extract JSON from text
            if "{" in result_text and "}" in result_text:
                json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
                if json_match:
                    result_text = json_match.group()

            result_json = json.loads(result_text)
            return result_json

        except Exception as e:
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
                "tera_strategy": "Who is the best Tera Captain?"
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
            
            # JSON Extraction safety
            if "{" in result_text and "}" in result_text:
                json_match = re.search(r"\{.*\}", result_text, re.DOTALL)
                if json_match:
                    result_text = json_match.group()

            result_json = json.loads(result_text)
            return result_json

        except Exception as e:
            print(f"Guide generation error on attempt {attempt}: {e}")
            continue
    
    return None
