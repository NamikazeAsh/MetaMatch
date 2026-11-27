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

    def test_compare_reads_tera_types_lowercase_abilities_and_two_pokemon(self):
        p = plan_query("tera fairy or tera steel for my gholdengo", self.team)
        self.assertEqual((p.intent, p.options), ("compare", [("tera", "Fairy"), ("tera", "Steel")]))
        p = plan_query("gholdengo good as gold or something else, which one", self.team, force="compare")
        self.assertIn(("ability", "Good as Gold"), p.options)
        p = plan_query("tusk or gambit for this slot", self.team, force="compare")
        self.assertEqual(p.options, [("pokemon", "Great Tusk"), ("pokemon", "Kingambit")])

    def test_tera_compare_names_a_pick_with_both_counts(self):
        from metamatch.engine import calc
        from metamatch.engine.solvers import solve
        if not calc.available():
            self.skipTest("no damage calculator")
        v = solve(plan_query("tera fairy or tera steel for my gholdengo", self.team))
        self.assertIn("Tera Fairy", v.statement)
        self.assertIn("Tera Steel", v.statement)

    def test_game_plan_names_the_playstyle_and_phases(self):
        from metamatch.engine import calc
        from metamatch.engine.solvers import solve
        if not calc.available():
            self.skipTest("no damage calculator")
        v = solve(plan_query("walk me through my game plan", self.team))
        self.assertTrue(v.statement.startswith("This plays as "))
        self.assertIn("Early on, lead with your", v.statement)

    def test_learn_questions_read_the_move_after_the_verb(self):
        from metamatch.engine.solvers import solve
        p = plan_query("can you give gholdengo shell smash", self.team)
        self.assertEqual((p.intent, p.move), ("learn", "Shell Smash"))
        v = solve(p)
        if v:   # learnset data present
            self.assertTrue(v.statement.startswith("No: Gholdengo can't learn Shell Smash"))
        self.assertNotEqual(plan_query("does tusk get knocked out by iron valiant moonblast", self.team).intent, "learn")
        self.assertNotEqual(plan_query("does gambit run sucker punch usually", self.team).intent, "learn")

    def test_other_game_questions_decline(self):
        from metamatch.agents.manager import decline_for
        self.assertIsNotNone(decline_for("how do i evolve eevee into sylveon", "gen9ou"))
        self.assertIsNone(decline_for("can i catch iron valiant on the switch", "gen9ou"))

    def test_fit_question_judges_the_named_candidate(self):
        p = plan_query("Can I use Charizard on my team", self.team)
        self.assertEqual((p.intent, p.options), ("teammate", [("pokemon", "Charizard")]))
        self.assertEqual(plan_query("how do i beat charizard", self.team).intent, "checks")

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

    def test_unsure_but_answerable_is_answered_with_the_other_readings_under_it(self):
        from unittest import mock
        from metamatch.agents import manager
        from metamatch.agents.grounded import FACTS_MARK
        guess = {"kind": "threats", "confidence": 0.3, "sure": False,
                 "top": [("threats", 0.3), ("win", 0.2), ("lead", 0.1)]}
        with mock.patch.object(manager, "_classify", lambda text, team: guess):
            m = manager.AgentManager()
            turn = m.prepare("hmm what could run through me", self.team)
            self.assertEqual(turn.verdict.intent, "threats")
            self.assertIn("What's my win condition?", turn.meta["also"])
            spoken = "".join(m.respond(turn, self.team)).partition(FACTS_MARK)[0]
            self.assertIn(manager.ALSO, spoken)

    def test_an_item_word_doesnt_send_a_damage_question_to_the_set_listing(self):
        from metamatch.agents.manager import AgentManager
        turn = AgentManager().prepare("rough % for specs draco into assault vest raging bolt?", self.team)
        self.assertNotEqual(turn.route, "builder")

    def test_damage_chip_names_the_member_carrying_the_move_and_the_stated_item(self):
        from metamatch.agents.manager import unsure_options
        team, _ = readTeam(TEAM + "\n\nDragapult @ Choice Specs\nAbility: Infiltrator\nEVs: 252 SpA / 4 SpD / 252 Spe\n"
                           "Timid Nature\n- Draco Meteor\n- Shadow Ball\n- Flamethrower\n- U-turn", "gen9ou")
        plan = plan_query("rough % for specs draco into assault vest raging bolt?", team)
        self.assertEqual((plan.user_overrides.get("item"), plan.opp_overrides.get("item")),
                         ("Choice Specs", "Assault Vest"))
        self.assertIn("How much damage does my Dragapult's Draco Meteor do to Assault Vest Raging Bolt?",
                      unsure_options(["damage"], plan, team))

    def test_greetings_are_smalltalk(self):
        from metamatch.agents.manager import SMALLTALK_RE
        for q in ("sup hows it goin", "what's up", "hey, how's it going?"):
            self.assertTrue(SMALLTALK_RE.match(q), q)

    def test_usage_field_reads_named_abilities_and_teammate_words(self):
        from metamatch.engine.planner import _usage_field
        self.assertEqual(_usage_field("do zapdos on the ladder mostly have static"), "ability")
        self.assertEqual(_usage_field("who do people usually bring alongside kingambit"), "teammates")
        self.assertEqual(_usage_field("what item do people use with great tusk"), "item")
        self.assertEqual(_usage_field("is great tusk still top 10 or did it fall"), "rank")
        self.assertEqual(_usage_field("how common is kingambit right now"), "rank")

    def test_meta_trends_reads_the_ladder_history(self):
        from metamatch.agents.manager import meta_trends
        text = meta_trends("gen9ou")
        self.assertTrue(text.startswith("Here's what's moving") or "don't have" in text)


if __name__ == "__main__":
    unittest.main()
