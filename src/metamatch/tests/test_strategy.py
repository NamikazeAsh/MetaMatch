"""Oak's grounding: one on one verdicts, the engine briefing and the advice verifier."""
import unittest

from metamatch.agents.coach import verify
from metamatch.engine import calc
from metamatch.engine.briefing import Briefing, Matchup, _verdict, strategy_briefing, team_weaknesses
from metamatch.team import readTeam, detectRole

TEAM = """Dragapult @ Choice Specs
Ability: Infiltrator
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Draco Meteor
- Shadow Ball
- Flamethrower
- U-turn

Corviknight @ Rocky Helmet
Ability: Pressure
Tera Type: Dragon
EVs: 248 HP / 252 Def / 8 SpD
Impish Nature
- Brave Bird
- Body Press
- Iron Defense
- Roost

Garchomp @ Loaded Dice
Ability: Rough Skin
Tera Type: Fire
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Swords Dance
- Scale Shot
- Earthquake
- Fire Fang"""


def _x(name, to_ko, to_be_koed, outspeeds=1.0):
    return {"name": name, "outspeeds": outspeeds, "to_ko": to_ko, "to_be_koed": to_be_koed,
            "dealt": None, "taken": ("Sucker Punch", {"percent": [104.1, 123]}) if to_be_koed == 1 else None}


class TestVerdicts(unittest.TestCase):
    def test_fewer_hits_wins(self):
        self.assertEqual(_verdict(_x("A", 2, 3, outspeeds=0)), "win")

    def test_speed_breaks_even_trades(self):
        self.assertEqual(_verdict(_x("A", 2, 2, outspeeds=1)), "win")
        self.assertEqual(_verdict(_x("A", 2, 2, outspeeds=0)), "lose")

    def test_getting_ohkoed_loses_even_when_faster(self):
        self.assertEqual(_verdict(_x("A", 2, 1, outspeeds=1)), "lose")

    def test_no_damage_either_way_is_even(self):
        self.assertEqual(_verdict(_x("A", None, None)), "even")

    def test_summary_names_ohkos(self):
        m = Matchup("Kingambit", wins=[_x("Corviknight", 2, 5)], losses=[_x("Dragapult", 2, 1)])
        self.assertEqual(m.summary(), "answers: Corviknight; loses: Dragapult (OHKO'd by Sucker Punch)")


class TestBriefing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM)
        detectRole(cls.team)

    def test_shared_weaknesses(self):
        weak = team_weaknesses(self.team)
        self.assertTrue(any(w.startswith("Dragon:") for w in weak), weak)
        self.assertTrue(any(w.startswith("Ice:") for w in weak), weak)

    def test_empty_team(self):
        self.assertEqual(strategy_briefing({}).facts, "")

    @unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
    def test_named_opponent_verdicts(self):
        b = strategy_briefing(self.team, ["Kingambit"])
        m = b.matchups[0]
        self.assertEqual(m.opponent, "Kingambit")
        self.assertIn("Corviknight", [x["name"] for x in m.wins])
        self.assertIn("Dragapult", [x["name"] for x in m.losses])
        self.assertIn("**Vs Kingambit**", b.summary)
        self.assertIn("Best answers to Kingambit", b.facts)


class TestCoachVerifier(unittest.TestCase):
    CONTEXT = ("### USER TEAM\n- Dragapult | Moves: Draco Meteor\n- Corviknight | Moves: Body Press\n"
               "Best answers to Kingambit: Corviknight (Body Press 69.4-82.3% (2HKO))\n"
               "Loses to Kingambit: Dragapult (takes Sucker Punch 104.1-123% (OHKO))")

    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM)
        m = Matchup("Kingambit", wins=[_x("Corviknight", 2, 5)], losses=[_x("Dragapult", 2, 1)])
        cls.one = Briefing(facts="", summary="", matchups=[m])

    def test_grounded_advice_passes(self):
        advice = "Bring Corviknight in on Kingambit and use Body Press, which does 69.4-82.3%. Keep Dragapult away from it."
        self.assertIsNone(verify(advice, self.CONTEXT, self.one, self.team))

    def test_invented_numbers(self):
        self.assertIn("numbers", verify("Body Press does 90% to Kingambit.", self.CONTEXT, self.one, self.team))

    def test_invented_pokemon(self):
        self.assertIn("Latios", verify("A Calm Mind Latios would beat it.", self.CONTEXT, self.one, self.team))

    def test_recommending_a_loser(self):
        reason = verify("Dragapult is a great answer to Kingambit.", self.CONTEXT, self.one, self.team)
        self.assertIn("loses to Kingambit", reason)

    def test_single_matchup_needs_no_name(self):
        reason = verify("Your best option is Dragapult.", self.CONTEXT, self.one, self.team)
        self.assertIn("loses to Kingambit", reason)

    def test_cautions_about_a_loser_pass(self):
        self.assertIsNone(verify("Avoid using Dragapult against Kingambit.", self.CONTEXT, self.one, self.team))

    def test_wrong_move_owner(self):
        reason = verify("Corviknight can use Swords Dance to set up.", self.CONTEXT, Briefing(), self.team)
        self.assertIn("only Garchomp runs", reason)


if __name__ == "__main__":
    unittest.main()
