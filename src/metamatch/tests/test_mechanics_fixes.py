"""
Regression tests for the shared mechanics fixes: final Speed with items, survival effects (Sturdy, Focus Sash,
Disguise), KO counts from raw rolls, priority in one on one verdicts, and item immunities. Each case comes from
the engine audit's reproduction, through the real planner, solvers and damage calc.
"""
import unittest

from metamatch.engine import calc, mechanics
from metamatch.engine.briefing import _verdict
from metamatch.engine.planner import plan_query
from metamatch.engine.solvers import solve
from metamatch.team import readTeam

SCARF_TUSK = """Great Tusk @ Choice Scarf
Ability: Protosynthesis
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Headlong Rush
- Knock Off"""

BAND_TUSK = """Great Tusk @ Choice Band
Ability: Protosynthesis
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Headlong Rush
- Knock Off"""

HAMMER = """Rillaboom @ Choice Band
Ability: Grassy Surge
EVs: 252 Atk / 4 SpD / 252 Spe
Adamant Nature
- Wood Hammer
- Grassy Glide"""

needs_calc = unittest.skipUnless(calc.available(), "needs Node and @smogon/calc")


def ask(team_text, question):
    team, _ = readTeam(team_text, "gen9ou")
    return solve(plan_query(question, team))


@needs_calc
class TestFinalSpeed(unittest.TestCase):
    def test_user_scarf_counts(self):
        v = ask(SCARF_TUSK, "Does my Great Tusk outspeed Dragapult?")
        self.assertEqual(v.answer, "yes")  # 300 x 1.5 = 450 beats 421
        self.assertIn("450", v.statement)

    def test_ignore_items_compares_bare_stats(self):
        v = ask(SCARF_TUSK, "Ignoring items, does my Great Tusk outspeed Dragapult?")
        self.assertEqual(v.answer, "no")  # 300 vs 421

    def test_opponent_scarf_only_when_stated(self):
        plain = ask(BAND_TUSK, "Does my Great Tusk outspeed Iron Valiant?")
        scarfed = ask(BAND_TUSK, "Does my Great Tusk outspeed Iron Valiant @ Choice Scarf?")
        self.assertIn("@ Choice Scarf", scarfed.statement)
        self.assertNotIn("@ Choice Scarf", plain.statement)

    def test_scarf_share_mixes_in(self):
        speeds = [(400, 1.0)]
        self.assertEqual(mechanics.scarf_adjusted_share(450, speeds, 0.0), 1.0)
        self.assertAlmostEqual(mechanics.scarf_adjusted_share(450, speeds, 0.4), 0.6)


@needs_calc
class TestSurvivalEffects(unittest.TestCase):
    def test_sturdy_survives_a_full_hp_hit(self):
        v = ask(BAND_TUSK, "Does my Great Tusk's Headlong Rush OHKO Magnezone @ Leftovers with Sturdy?")
        self.assertEqual(v.answer, "no")
        self.assertIn("Sturdy", v.statement)

    def test_focus_sash_survives(self):
        v = ask(BAND_TUSK, "Does my Great Tusk's Headlong Rush OHKO Glimmora @ Focus Sash?")
        self.assertEqual(v.answer, "no")

    def test_disguise_takes_the_first_hit(self):
        v = ask(HAMMER, "Does my Rillaboom's Wood Hammer OHKO Mimikyu?")
        self.assertEqual(v.answer, "no")

    def test_breakers_bypass_sturdy_but_not_sash(self):
        result = {"range": [150.0, 180.0], "percent": [150.0, 180.0], "desc": "", "ko": "guaranteed OHKO",
                  "defender_hp": 100}
        sturdy = {"name": "Magnezone", "ability": "Sturdy"}
        sash = {"name": "Glimmora", "item": "Focus Sash"}
        self.assertIsNone(mechanics.survival_effect(result, {"name": "Excadrill", "ability": "Mold Breaker"}, sturdy, "Earthquake"))
        self.assertEqual(mechanics.survival_effect(result, {"name": "Excadrill", "ability": "Mold Breaker"}, sash, "Earthquake"), "Focus Sash")


class TestPriorityVerdicts(unittest.TestCase):
    def race(self, **kw):
        x = {"to_ko": 1, "to_be_koed": 1, "outspeeds": 0.0, "priority": (0, None), "opp_priority": (0, None)}
        x.update(kw)
        return _verdict(x)

    def test_slower_side_with_a_priority_finisher_wins(self):
        self.assertEqual(self.race(priority=(1, "Sucker Punch")), "win")

    def test_opponent_priority_beats_speed(self):
        self.assertEqual(self.race(outspeeds=1.0, opp_priority=(2, "Extreme Speed")), "lose")

    def test_faster_side_wins_an_even_race(self):
        self.assertEqual(self.race(outspeeds=1.0), "win")


@needs_calc
class TestItemImmunity(unittest.TestCase):
    def test_air_balloon_is_credited_to_the_item(self):
        v = ask(BAND_TUSK, "Is Heatran @ Air Balloon immune to Ground?")
        self.assertEqual(v.answer, "immune")
        self.assertIn("Air Balloon", v.statement)


if __name__ == "__main__":
    unittest.main()
