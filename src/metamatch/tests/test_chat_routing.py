"""Fixes from the 2026 11 26 chat coverage audit: which questions reach which answer."""
import unittest

from metamatch.agents import coach
from metamatch.agents.manager import _is_building, decline_for
from metamatch.engine.names import find_pokemon
from metamatch.engine.planner import plan_query
from metamatch.team import readTeam

TEAM = """Gholdengo @ Choice Scarf
Ability: Good as Gold
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Trick
- Focus Blast

Kingambit @ Leftovers
Ability: Supreme Overlord
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Swords Dance
- Kowtow Cleave
- Sucker Punch
- Iron Head"""

ANALYSIS = {"metadata": {"source": "smogon_analysis", "pokemon": "Dragapult", "species": "Dragapult"}}


class TestPlannerRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM, "gen9ou")

    def test_how_fast_is_a_stat_question(self):
        p = plan_query("how fast is scarf gholdengo", self.team)
        self.assertEqual((p.intent, p.stat), ("stat", "spe"))

    def test_who_switches_into_a_type_is_a_team_type_question(self):
        p = plan_query("Who switches into a Ghost move safely?", self.team)
        self.assertEqual((p.intent, p.atk_type), ("team_type", "Ghost"))


class TestBrockOnlyForSets(unittest.TestCase):
    def test_set_questions_still_go_to_brock(self):
        self.assertTrue(_is_building("what item should gholdengo run"))
        self.assertTrue(_is_building("good partners for kingambit"))

    def test_a_move_named_speed_is_still_a_set_question(self):
        self.assertTrue(_is_building("Dragonite sets? tera normal extreme speed or something else"))

    def test_speed_typing_mechanics_and_in_battle_questions_do_not(self):
        for q in ("what does tera steel do for tusk defensively", "how does choice lock work if i tera",
                  "should i tera kingambit now or save it", "evs for gambit to survive great tusk"):
            self.assertFalse(_is_building(q), q)


class TestQuotesOnlyForHowToUse(unittest.TestCase):
    asked = {coach._species_key("Dragapult")}

    def test_how_to_use_quotes_the_analysis(self):
        self.assertTrue(coach._named_analysis(ANALYSIS, self.asked, "how do I use dragapult"))
        self.assertTrue(coach._named_analysis(ANALYSIS, self.asked, "what's dragapult's role on hyper offense"))

    def test_matchups_battle_moments_and_mechanics_do_not(self):
        for q in ("pult locked into draco, opp sends a fairy, now what", "what can i do vs dragapult",
                  "does infiltrator matter on dragapult"):
            self.assertFalse(coach._named_analysis(ANALYSIS, self.asked, q), q)


class TestDeclines(unittest.TestCase):
    def test_out_of_scope_questions_get_a_reason(self):
        for q in ("who will win worlds this year", "best great league team for pokemon go",
                  "can you give me a hacked set", "just play the game for me on showdown",
                  "what does my opponent's team look like before team preview",
                  "champions doubles: should lopunny fake out the left or right mon"):
            self.assertIsNotNone(decline_for(q, "gen9ou"), q)

    def test_ordinary_questions_are_not_declined(self):
        for q in ("how do i exploit their weakness", "is my kingambit set good", "what beats my team"):
            self.assertIsNone(decline_for(q, "gen9ou"), q)


class TestPronounClash(unittest.TestCase):
    def test_it_carries_the_member_into_the_next_clause(self):
        from types import SimpleNamespace
        from metamatch.agents.claims import group_clash
        verdict = SimpleNamespace(groups={"resist": ["Kingambit"], "weak": ["Gholdengo"], "neutral": [], "immune": []})
        self.assertIsNotNone(group_clash("Your Kingambit resists Ghost attacks because it is weak to them.", verdict))
        self.assertIsNone(group_clash("Your Kingambit resists Ghost attacks, so it switches in safely.", verdict))


class TestMegaNicknames(unittest.TestCase):
    def test_zard_y_is_the_mega(self):
        self.assertEqual(find_pokemon("does mega zard y heat wave ohko kingambit")[0], "Charizard-Mega-Y")
        self.assertEqual(find_pokemon("is zard good"), ["Charizard"])


if __name__ == "__main__":
    unittest.main()
