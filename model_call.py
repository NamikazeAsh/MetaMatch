from groq import Groq
import os
from dotenv import load_dotenv
import json

from pprint import pprint

load_dotenv()

with open("jsons/team.json", "r") as f:
    team = json.load(f)
with open("jsons/topPoke.json", "r") as f:
    topPoke = json.load(f)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

completion = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=
    [{"role": "user", 
    "content":f"""
    Summarize this Pokémon team, give improvement suggestions, mention which meta-mons are a threat to my team.
    Sentence ends with newline inside list.
    
    Output ONLY JSON: keys = (synergy, suggestions)
    synergy: which pokemon synergize well with team. FORMAT: List-String 
    suggestions: improvements to be made in team. FORMAT: List-String
    Poke team: {team}
    """}],
    temperature=0.2,
    max_completion_tokens=4000,
    reasoning_effort="low",
    stream=False,
    seed=305
)

result_text = completion.choices[0].message.content

try:
    result_json = json.loads(result_text)
except json.JSONDecodeError:
    print("Failed to parse JSON.")
else:
    if 'synergy' in result_json and 'suggestions' in result_json:
        pprint(result_json)
    else:
        print("Keys missing.")
        pprint(result_json)
