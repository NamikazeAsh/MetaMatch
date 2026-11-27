"""The learned question classifier (engine/intent.py) and how the chat uses it."""
import unittest

from metamatch.engine import intent
from metamatch.engine.planner import plan_query
from metamatch.team import readTeam

TEAM = """Great Tusk @ Booster Energy
Ability: Protosynthesis
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Headlong Rush
- Ice Spinner
- Knock Off
- Rapid Spin

Gholdengo @ Choice Scarf
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


class TestNormalize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM, "gen9ou")

    def test_names_moves_and_types_become_placeholders(self):
        norm = intent.normalize("does gambit survive a dragapult draco meteor", self.team)
        self.assertEqual(norm, "does my pokemon survive a their pokemon move")
        self.assertEqual(intent.normalize("is gholdengo weak to ground", self.team), "is my pokemon weak to type")

    def test_the_players_own_owner_word_is_kept(self):
        self.assertEqual(intent.normalize("does my tusk outspeed their kingambit", self.team),
                         "does my pokemon outspeed their pokemon")


@unittest.skipUnless(intent.available(), "no trained intent model")
class TestClassifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM, "gen9ou")

    def test_clear_questions_get_their_kind(self):
        for q, kind in (("whats rising on the ladder this month", "meta_trends"),
                        ("who will win worlds this year", "out_of_scope"),
                        ("how do i beat iron valiant", "checks"),
                        ("rate my team", "score")):
            got = intent.classify(q, self.team)
            self.assertEqual(got["kind"], kind, (q, got["top"]))

    def test_predictions_are_deterministic(self):
        a = intent.classify("specs or scarf on dragapult", self.team)
        b = intent.classify("specs or scarf on dragapult", self.team)
        self.assertEqual(a, b)

    def test_nonsense_is_not_sure(self):
        self.assertFalse(intent.classify("hmm what about that one thing", self.team)["sure"])


class TestForcedPlans(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM, "gen9ou")

    def test_forced_kind_fills_its_slots(self):
        p = plan_query("is there any way my tusk deals with their lando", self.team, force="matchup")
        self.assertEqual((p.intent, p.kind, p.user["Pokemon"], p.opponent), ("matchup", "matchup", "Great Tusk",
                                                                             "Landorus-Therian"))
        p = plan_query("rain teams scare me", self.team, force="archetype")
        self.assertEqual((p.intent, p.archetype), ("archetype", "rain"))

    def test_kinds_without_a_solver_stay_open(self):
        p = plan_query("whats rising this month", self.team, force="meta_trends")
        self.assertEqual((p.intent, p.kind), ("open", "meta_trends"))


class TestChatRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM, "gen9ou")

    def test_missing_opponent_asks_instead_of_guessing(self):
        from metamatch.agents.manager import AgentManager
        manager = AgentManager()
        turn = manager.prepare("x", self.team)
        plan = plan_query("does it outspeed", self.team)
        out = manager._classified("does it outspeed", turn.reading, plan, "speed", self.team, {})
        self.assertEqual(out.plan.intent, "clarify")

    def test_unsure_offers_questions_built_from_the_names(self):
        from metamatch.agents.manager import unsure_options
        plan = plan_query("what about iron valiant", self.team)
        options = unsure_options(["checks", "usage", "win"], plan, self.team)
        self.assertIn("How do I beat Iron Valiant?", options)
        self.assertIn("What's my win condition?", options)

    def test_meta_trends_reads_the_ladder_history(self):
        from metamatch.agents.manager import meta_trends
        text = meta_trends("gen9ou")
        self.assertTrue(text.startswith("Here's what's moving") or "don't have" in text)


if __name__ == "__main__":
    unittest.main()
