import sys
import os
import json
import time

# Add src to path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, 'src')
sys.path.append(src_path)

from metamatch.team import readTeam, detectRole, addComments
from metamatch.suggestions import get_chat_response

# 1. Define the Team
team_raw = """
Ogerpon-Cornerstone @ Cornerstone Mask
Ability: Sturdy
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Power Whip
- Ivy Cudgel
- Knock Off
- Swords Dance

Hatterene @ Assault Vest
Ability: Magic Bounce
EVs: 252 HP / 52 SpA / 144 SpD / 60 Spe
Modest Nature
- Draining Kiss
- Psychic Noise
- Mystical Fire
- Nuzzle

Pecharunt @ Heavy-Duty Boots
Ability: Poison Puppeteer
EVs: 252 HP / 184 Def / 44 SpD / 28 Spe
Bold Nature
- Malignant Chain
- Shadow Ball
- Parting Shot
- Recover

Landorus-Therian @ Rocky Helmet
Ability: Intimidate
EVs: 252 HP / 144 Def / 112 Spe
Jolly Nature
- Stealth Rock
- Earthquake
- U-turn
- Taunt

Kingambit @ Leftovers
Ability: Supreme Overlord
EVs: 252 Atk / 4 SpD / 252 Spe
Adamant Nature
- Kowtow Cleave
- Low Kick
- Sucker Punch
- Swords Dance

Latios @ Choice Specs
Ability: Levitate
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Draco Meteor
- Psyshock
- Aura Sphere
- Trick
"""

# 2. Process Team
team, team_weakness = readTeam(team_raw)
detectRole(team)
addComments(team)

# 3. Define 10 Targeted Questions
questions = [
    "Who is my best switch-in for a Choice Band Great Tusk?",
    "Can my Pecharunt wall a Great Tusk successfully?",
    "Is Kingambit a safe switch-in for a Fighting move from Great Tusk?",
    "Is my Latios faster than a standard Gholdengo?",
    "Can Hatterene survive a Steel-type 'Make It Rain' from Gholdengo?",
    "Should I switch Landorus-T into a Zamazenta using Body Press?",
    "How many members of my team are weak to Fire-type attacks?",
    "What is the strategic role of my Pecharunt in this team?",
    "I'm facing Meowscarada. Should I lead with Pecharunt or Landorus-T?",
    "Can Ogerpon-Cornerstone break through a Dondozo?"
]

output_file = "rag_final_results.txt"

print(f"Running 10 final tests with Battle Engine...")

with open(output_file, "w", encoding="utf-8") as f:
    for i, q in enumerate(questions):
        print(f"Test {i+1}/10: {q}")
        f.write(f"Q{i+1}: {q}\n")
        f.write("-" * 20 + "\n")
        try:
            stream = get_chat_response(q, team, team_weakness)
            full_response = ""
            for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                full_response += content
            f.write(full_response.strip() + "\n")
        except Exception as e:
            f.write(f"ERROR: {str(e)}\n")
        f.write("\n" + "="*60 + "\n\n")

print("Final tests complete.")
