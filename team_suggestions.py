import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def call_gpt4(prompt, system_prompt=None, temperature=0, model="gpt-3.5-turbo"):
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content

with open("jsons/team.json") as f:
    team_data = json.load(f)

prompt = f"Suggest threats to a Pokémon team based on this JSON data:\n{json.dumps(team_data, indent=2)}"
response = call_gpt4(prompt)
print(response)
