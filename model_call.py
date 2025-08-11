# claude_call.py
import json
import re
from huggingface_hub import InferenceClient

client = InferenceClient()

MODEL = "Qwen/Qwen2.5-7B-Instruct-1M"

SYSTEM_PROMPT = """
You are a Pokemon competitive team analyzer. You MUST respond with this EXACT JSON structure:

{
    "team_analysis": {
        "major_weaknesses": [
            {
                "type": "",
                "vulnerable_pokemon": [pokemon in my team vulnerable to the type],
                "severity": "Critical|High|Medium|Low",
                "description": ""
            }
        ],
        "structural_weaknesses": [
            {
                "issue": "",
                "description": ""
            }
        ]
    },
    "threatening_pokemon": [
        {
            "name": "string",
            "threat_level": "Critical|High|Medium|Low",
            "reasons": ["array of strings"],
            "threatened_pokemon": ["array of strings"]
        }
    ],
    "recommendations": ["array of strings"]
}

Never deviate from this structure. Always include all fields.
"""

def _extract_json(text):
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return text[start:end]
    except ValueError:
        # fallback: try regex for smallest json-like block
        m = re.search(r"\{(?:[^{}]|(?R))*\}", text, flags=re.DOTALL)
        if m:
            return m.group(0)
        raise

def validate_structure(obj):
    required_top = {"team_analysis", "threatening_pokemon", "recommendations"}
    if not isinstance(obj, dict):
        return False, "output is not a JSON object"
    missing = required_top - obj.keys()
    if missing:
        return False, f"missing top-level fields: {missing}"
    return True, None

def analyze_team(team_data, meta_pokemon):
    team_json = json.dumps(team_data)
    meta_json = json.dumps(meta_pokemon)

    user_prompt = f"""
    Analyze my Pokemon team against the meta pokemon I've provided, they're updated Smogon metas.

    Team Data: {team_json}
    Meta Pokemon: {meta_json}

    Focus on type coverage, role synergy, and meta threats.
    """

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]

    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=1500,
        temperature=0.1
    )

    try:
        text = resp.choices[0].message["content"]
    except Exception:
        text = str(resp)

    try:
        json_text = _extract_json(text)
        parsed = json.loads(json_text)
    except Exception as e:
        print("Failed to parse JSON from model output. Raw output below:\n")
        print(text)
        print("\nParse error:", e)
        return None

    ok, reason = validate_structure(parsed)
    if not ok:
        print("Model returned JSON but failed validation:", reason)
        print("Returned JSON:", json.dumps(parsed, indent=2))
        return None

    return parsed

if __name__ == "__main__":
    with open("jsons/topPoke.json", "r", encoding="utf-8") as f:
        topPoke = json.load(f)
    with open("jsons/team.json", "r", encoding="utf-8") as f:
        team = json.load(f)

    out = analyze_team(team, topPoke)
    print(json.dumps(out, indent=2))
