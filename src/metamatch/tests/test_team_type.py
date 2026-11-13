"""Team wide type questions ("which of my Pokemon resist Water") answered from the type chart, not the model.
The cases are the chat agent audit's: the mechanics agent got each of them wrong."""
import unittest

from metamatch.engine import calc
from metamatch.engine.briefing import team_weaknesses
from metamatch.engine.planner import plan_query
from metamatch.engine.solvers import solve
from metamatch.team import readTeam

SUN = """Torkoal @ Heat Rock
Ability: Drought
- Lava Plume
- Rapid Spin

Venusaur @ Life Orb
Ability: Chlorophyll
- Giga Drain
- Weather Ball

Garchomp @ Loaded Dice
Ability: Rough Skin
- Scale Shot
- Earthquake

Dragapult @ Choice Specs
Ability: Infiltrator
- Draco Meteor
- Shadow Ball

Corviknight @ Rocky Helmet
Ability: Pressure
- Brave Bird
- Body Press

Alomomola @ Assault Vest
Ability: Regenerator
- Flip Turn
- Scald"""

SALT = """Hatterene @ Rocky Helmet
Ability: Magic Bounce
- Psychic Noise
- Draining Kiss

Dragonite @ Leftovers
Ability: Multiscale
- Extreme Speed
- Earthquake

Great Tusk @ Heavy-Duty Boots
Ability: Protosynthesis
- Headlong Rush
- Close Combat

Garganacl @ Leftovers
Ability: Purifying Salt
- Salt Cure
- Recover

Samurott-Hisui @ Choice Band
Ability: Sharpness
- Ceaseless Edge
- Razor Shell

Gholdengo @ Choice Scarf
Ability: Good as Gold
- Make It Rain
- Shadow Ball"""


def ask(query, paste):
    team, _ = readTeam(paste, "gen9ou")
    plan = plan_query(query, team)
    return plan, solve(plan)


class TestTeamTypeAnswers(unittest.TestCase):
    def test_resist_list_is_exact(self):
        plan, v = ask("Which of my Pokemon resist Water?", SUN)
        self.assertEqual(plan.intent, "team_type")
        self.assertEqual(set(v.answer.split(", ")), {"Venusaur", "Dragapult", "Alomomola"})
        self.assertIn("Torkoal (2x) is weak to it", v.facts[0])

    def test_immunity_counts_as_resisting(self):
        _, v = ask("Which of my Pokemon resist Fighting?", SALT)
        self.assertEqual(set(v.answer.split(", ")), {"Gholdengo", "Hatterene", "Dragonite"})
        self.assertIn("Gholdengo (0x) is immune", v.facts[0])

    def test_weak_immune_and_neutral_asks(self):
        _, weak = ask("Which members of my team are weak to Ground?", SALT)
        self.assertEqual(set(weak.answer.split(", ")), {"Garganacl", "Gholdengo"})
        _, neutral = ask("Which of my Pokemon take neutral damage from Fairy?", SUN)
        self.assertEqual(neutral.answer, "Alomomola")

    def test_damage_scaling_ability_is_counted(self):
        team, _ = readTeam(SALT, "gen9ou")
        salt = next(p for p in team.values() if p["Pokemon"] == "Garganacl")
        self.assertEqual(salt["Damage From"]["ghost"], 0.5)
        _, v = ask("Does anything on my team resist Ghost?", SALT)
        self.assertIn("Garganacl (0.5x via Purifying Salt)", v.facts[0])

    def test_opponent_attacks_and_shared_weaknesses(self):
        _, v = ask("Who on my team resists Gholdengo's moves?", SUN)
        self.assertTrue(any(f.startswith("Make It Rain (Steel)") for f in v.facts), v.facts)
        team, _ = readTeam(SUN, "gen9ou")
        _, summary = ask("What types is my team weak to?", SUN)
        self.assertEqual(summary.answer, ", ".join(w.split(":")[0] for w in team_weaknesses(team)))

    def test_other_questions_keep_their_intent(self):
        self.assertEqual(ask("How do I fix my team's Fire weakness?", SUN)[0].intent, "open")
        self.assertEqual(ask("Does my Corviknight resist Ground?", SUN)[0].intent, "type")


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestScalesMatchTheCalc(unittest.TestCase):
    def test_ability_scales_agree_with_the_damage_calc(self):
        from metamatch.team import ABILITY_SCALES
        probes = {"fire": "Flamethrower", "ice": "Ice Beam", "ghost": "Shadow Ball"}
        for ability, scales in ABILITY_SCALES.items():
            for t, factor in scales.items():
                base = {"game": "sv", "attacker": {"name": "Mew"}, "move": probes[t]}
                with_it = calc.calculate({**base, "defender": {"name": "Mew", "ability": ability.title()}})
                without = calc.calculate({**base, "defender": {"name": "Mew", "ability": "Run Away"}})
                ratio = with_it["range"][1] / without["range"][1]
                self.assertAlmostEqual(ratio, factor, delta=0.05, msg=f"{ability} vs {t}")


if __name__ == "__main__":
    unittest.main()
