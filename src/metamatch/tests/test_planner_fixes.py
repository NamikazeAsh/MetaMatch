"""Planner regression tests: who attacks, whose set details are whose, and name matching. Written from the bug
reports, not from benchmark questions."""
import unittest

from metamatch.agents.grounded import verify
from metamatch.engine import calc
from metamatch.engine.names import find_pokemon
from metamatch.engine.planner import _usage_field, plan_query
from metamatch.engine.solvers import solve
from metamatch.team import readTeam
from metamatch.tests.test_planner import SV_TEAM


class TestAttackerAndSubject(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sv, _ = readTeam(SV_TEAM, "gen9ou")

    def plan(self, q):
        return plan_query(q, self.sv)

    def test_opponent_subject_attacks_without_move(self):
        self.assertEqual(self.plan("Does Dragapult OHKO Gholdengo?").attacker, "opponent")
        self.assertEqual(self.plan("Does Kingambit OHKO my Gholdengo?").attacker, "opponent")
        self.assertEqual(self.plan("Does Gholdengo OHKO Kingambit?").attacker, "user")

    def test_survive_without_move_attacks_the_subject(self):
        p = self.plan("Can Gholdengo survive Kingambit?")
        self.assertEqual((p.attacker, p.survive, p.subject), ("opponent", True, "user"))
        self.assertEqual(self.plan("Can Kingambit survive Headlong Rush?").attacker, "user")

    def test_subject_skips_lead_in_and_pronouns(self):
        self.assertEqual(self.plan("Does Dragapult outspeed my Great Tusk?").subject, "opponent")
        self.assertEqual(self.plan("Against Dragapult, is my Great Tusk faster?").subject, "user")
        self.assertEqual(self.plan("Dragapult is on its usual set. Does my Great Tusk outspeed it?").subject, "user")
        self.assertEqual(self.plan("my Great Tusk vs a Dragapult, do I outspeed it?").subject, "user")

    def test_nickname_possessive(self):
        p = self.plan("how much damage does Gambit's Knock Off do to Great Tusk?")
        self.assertEqual((p.attacker, p.opponent, p.move), ("opponent", "Kingambit", "Knock Off"))
        self.assertEqual(self.plan("how much damage does Tusk's Knock Off do to Kingambit?").attacker, "user")


class TestSetScoping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sv, _ = readTeam(SV_TEAM, "gen9ou")

    def test_user_details_stay_off_opponent(self):
        p = plan_query("Does my Jolly 252 Atk Great Tusk OHKO Kingambit with Headlong Rush?", self.sv)
        self.assertEqual(p.opp_overrides, {})
        p = plan_query("Does my Great Tusk @ Choice Band OHKO Kingambit with Headlong Rush?", self.sv)
        self.assertNotIn("item", p.opp_overrides)

    def test_opponent_details_still_apply(self):
        p = plan_query("Does Great Tusk OHKO Impish 252 HP / 252 Def Kingambit with Headlong Rush?", self.sv)
        self.assertEqual(p.opp_overrides, {"nature": "Impish", "evs": {"hp": 252, "def": 252}})
        p = plan_query("Assuming 252 HP / 4 Def, does Great Tusk OHKO Kingambit with Headlong Rush?", self.sv)
        self.assertEqual(p.opp_overrides, {"evs": {"hp": 252, "def": 4}})

    def test_item_mid_sentence_and_usage_words(self):
        p = plan_query("Does Kingambit @ Leftovers survive Great Tusk's Headlong Rush?", self.sv)
        self.assertEqual(p.opp_overrides.get("item"), "Leftovers")
        self.assertEqual(_usage_field("What's the most common item on Terapagos?"), "item")
        self.assertEqual(_usage_field("what tera type does it run"), "tera")


class TestNames(unittest.TestCase):
    def test_english_words_are_not_nicknames(self):
        for q in ["that team is gross", "I hate moth balls", "crown my king", "drill into it"]:
            self.assertEqual(find_pokemon(q), [], q)

    def test_nicknames_in_a_pokemon_slot_still_work(self):
        self.assertEqual(find_pokemon("does my rillaboom outspeed moth"), ["Rillaboom", "Iron Moth"])
        self.assertEqual(find_pokemon("Can Tusk OHKO Gross?"), ["Great Tusk", "Metagross"])
        self.assertEqual(find_pokemon("does pult outspeed gambit"), ["Dragapult", "Kingambit"])
        self.assertEqual(find_pokemon("corv vs pex"), ["Corviknight", "Toxapex"])

    def test_regional_and_appliance_formes(self):
        cases = {"Alolan Ninetales": "Ninetales-Alola", "Hisuian Zoroark": "Zoroark-Hisui",
                 "Galarian Moltres": "Moltres-Galar", "Rotom W": "Rotom-Wash", "Wash Rotom": "Rotom-Wash",
                 "Black Kyurem": "Kyurem-Black", "Hearthflame Ogerpon": "Ogerpon-Hearthflame",
                 "single strike urshifu": "Urshifu"}
        for q, want in cases.items():
            self.assertEqual(find_pokemon(q), [want], q)

    def test_one_letter_forms_skip_english(self):
        self.assertEqual(find_pokemon("Is Ninetales a good pick"), ["Ninetales"])


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestPerspectiveSolvers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sv, _ = readTeam(SV_TEAM, "gen9ou")

    def test_speed_answers_the_question_asked(self):
        # Dragapult's usual Timid spread is faster than this Jolly Great Tusk
        self.assertEqual(solve(plan_query("Does Dragapult outspeed my Great Tusk?", self.sv)).answer, "yes")
        self.assertEqual(solve(plan_query("Does my Great Tusk outspeed Dragapult?", self.sv)).answer, "no")
        self.assertEqual(solve(plan_query("Is my Great Tusk slower than Dragapult?", self.sv)).answer, "yes")

    def test_speed_verifier_follows_perspective(self):
        v = solve(plan_query("Does Dragapult outspeed my Great Tusk?", self.sv))
        self.assertIsNone(verify("Dragapult outspeeds Great Tusk, so it moves first.", v))
        slower = solve(plan_query("Is my Great Tusk slower than Dragapult?", self.sv))
        self.assertIsNone(verify("Great Tusk is slower than Dragapult here.", slower))

    def test_ko_and_survive_without_move(self):
        v = solve(plan_query("Does Kingambit OHKO my Gholdengo?", self.sv))
        self.assertTrue(v.statement.startswith("Kingambit's"))
        v = solve(plan_query("Can Gholdengo survive Kingambit?", self.sv))
        self.assertIn("Gholdengo survives", v.statement)


if __name__ == "__main__":
    unittest.main()
