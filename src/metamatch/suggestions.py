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
    
    while attempt < max_retries:
        # Use the OpenAI client to connect to a local Ollama instance
        client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
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
                    Team Data: {team}
                    """
                }],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=1500,
                stream=False,
            )
            
            result_text = completion.choices[0].message.content
            result_json = json.loads(result_text)
            
            return result_json

        except (json.JSONDecodeError, AttributeError, openai.APIError) as e:
            print(f"An error occurred on attempt {attempt}: {e}")
            continue
    
    return None