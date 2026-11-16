"""The broken down team score: parts add up, a deliberately weak team scores below a sound one, notes are honest."""
import unittest

from metamatch.engine import calc
from metamatch.engine.team_score import WEIGHTS, score_team
from metamatch.team import readTeam

SOUND = """Gholdengo @ Choice Scarf
Ability: Good as Gold
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Trick
- Focus Blast

Great Tusk @ Booster Energy
Ability: Protosynthesis
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Headlong Rush
- Ice Spinner
- Knock Off
- Rapid Spin

Kingambit @ Leftovers
Ability: Supreme Overlord
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Swords Dance
- Kowtow Cleave
- Sucker Punch
- Iron Head

Dragapult @ Heavy-Duty Boots
Ability: Infiltrator
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Draco Meteor
- Shadow Ball
- U-turn
- Will-O-Wisp

Corviknight @ Leftovers
Ability: Pressure
EVs: 252 HP / 168 Def / 88 SpD
Impish Nature
- Body Press
- Brave Bird
- Roost
- Defog

Ting-Lu @ Leftovers
Ability: Vessel of Ruin
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Stealth Rock
- Ruination
- Earthquake
- Whirlwind"""

WEAK = "\n\n".join(f"{n} @ Choice Band\nAbility: {a}\nEVs: 252 Atk / 4 SpD / 252 Spe\nJolly Nature\n- {m}" for n, a, m in
                   [("Raichu", "Static", "Thunder Punch"), ("Persian", "Technician", "Fake Out"), ("Spidops", "Insomnia", "Lunge"),
                    ("Oinkologne", "Thick Fat", "Body Slam"), ("Dudunsparce", "Serene Grace", "Body Slam"),
                    ("Lokix", "Tinted Lens", "First Impression")])


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestTeamScore(unittest.TestCase):
    def test_parts_add_up_and_weak_team_scores_lower(self):
        sound = score_team(readTeam(SOUND, "gen9ou")[0], "gen9ou")
        weak = score_team(readTeam(WEAK, "gen9ou")[0], "gen9ou")
        self.assertAlmostEqual(sound.total, round(sum(p.points for p in sound.parts), 1), places=1)
        self.assertEqual({p.key for p in sound.parts}, set(WEIGHTS))
        self.assertGreater(sound.total, weak.total + 20)
        self.assertTrue(all(p.evidence for p in sound.parts))
        self.assertTrue(any("does not predict" in n for n in sound.notes))


if __name__ == "__main__":
    unittest.main()
