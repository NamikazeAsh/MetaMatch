from groq import Groq
import os
from dotenv import load_dotenv
import json
from pprint import pprint

with open("jsons/team.json", "r") as f:
    team = json.load(f)
with open("jsons/topPoke.json", "r") as f:
    topPoke = json.load(f)

def get_suggestions(team):
    load_dotenv()
    
    max_retries = 5
    attempt = 0
    
    while attempt < max_retries:
        client = Groq(api_key=os.environ.get('GROQ_API_KEY'))
        attempt += 1
        
        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{
                "role": "user",
                "content": f"""
                Summarize this Pokémon team, give improvement suggestions, mention which meta-mons are a threat to my team. 
                Respond in points, each point starts in a new line.
                
                Output ONLY JSON: keys = (synergy, suggestions)
                synergy: list of short strings (each string <= 50 words)
                suggestions: list of short strings (each string <= 50 words)
                Poke team: {team}
                """
            }],
            temperature=0.2,
            max_completion_tokens=4000,
            reasoning_effort="low",
            stream=False,
        )
        
        result_text = completion.choices[0].message.content
        
        try:
            result_json = json.loads(result_text)
            if 'synergy' in result_json and 'suggestions' in result_json:
                return result_json
        except json.JSONDecodeError:
            continue
    
    return None

