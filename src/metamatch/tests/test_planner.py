"""Planner and solver checks on natural chat phrasing (not the MetaBench templates)."""
import unittest

from metamatch.agents.grounded import verify
from metamatch.engine import calc
from metamatch.engine.planner import plan_query
from metamatch.engine.solvers import Verdict, solve
from metamatch.team import readTeam

SV_TEAM = """Great Tusk @ Booster Energy
Ability: Protosynthesis
Tera Type: Steel
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Headlong Rush
- Ice Spinner
- Knock Off
- Rapid Spin

Gholdengo @ Leftovers
Ability: Good as Gold
Tera Type: Fairy
EVs: 252 HP / 252 SpA / 4 Spe
Modest Nature
- Make It Rain
- Shadow Ball
- Nasty Plot
- Recover"""

CHAMPIONS_TEAM = """Garchomp @ Garchompite Z
Ability: Rough Skin
EVs: 2 HP / 32 SpA / 32 Spe
Timid Nature
- Draco Meteor
- Flamethrower
- Earth Power
- Stealth Rock

Kingambit @ Black Glasses
Ability: Supreme Overlord
EVs: 32 HP / 32 Atk / 2 Def
Adamant Nature
- Sucker Punch
- Kowtow Cleave
- Iron Head
- Swords Dance"""


class TestPlannerIntents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sv, _ = readTeam(SV_TEAM, "gen9ou")
        cls.ch, _ = readTeam(CHAMPIONS_TEAM, "gen9championsou")

    def plan(self, query, team=None):
        return plan_query(query, self.sv if team is None else team)

    def test_speed(self):
        p = self.plan("Is Great Tusk faster than Dragapult?")
        self.assertEqual((p.intent, p.user["Pokemon"], p.opponent), ("speed", "Great Tusk", "Dragapult"))

    def test_survive_flips_attacker(self):
        p = self.plan("can gholdengo survive a kingambit sucker punch")
        self.assertEqual((p.intent, p.user["Pokemon"], p.opponent, p.move), ("ko", "Gholdengo", "Kingambit", "Sucker Punch"))
        self.assertTrue(p.survive)
        self.assertEqual(p.attacker, "opponent")

    def test_move_owner_becomes_user(self):
        p = self.plan("how much damage does Knock Off do to Dragapult?")
        self.assertEqual((p.intent, p.user["Pokemon"], p.move, p.attacker), ("damage", "Great Tusk", "Knock Off", "user"))

    def test_2hko(self):
        p = self.plan("Does Great Tusk 2HKO Kingambit with Headlong Rush?")
        self.assertEqual((p.intent, p.ko_hits, p.move), ("ko", 2, "Headlong Rush"))

    def test_type(self):
        p = self.plan("is gholdengo weak to fire?")
        self.assertEqual((p.intent, p.user["Pokemon"], p.atk_type), ("type", "Gholdengo", "Fire"))

    def test_type_about_opponent(self):
        p = self.plan("Is Dragapult immune to Normal moves?")
        self.assertEqual((p.intent, p.opponent, p.atk_type), ("type", "Dragapult", "Normal"))
        self.assertFalse(p.user_named)

    def test_usage_and_stat(self):
        self.assertEqual(self.plan("What's the most common item on Kingambit?").usage_field, "item")
        p = self.plan("what is Gholdengo's speed stat")
        self.assertEqual((p.intent, p.stat), ("stat", "spe"))

    def test_open_questions_stay_open(self):
        for q in ["How do I beat stall?", "What's a good lead for this team?", "Is Dragapult faster than Kingambit?"]:
            self.assertEqual(self.plan(q).intent, "open", q)

    def test_mega_named_by_base_species(self):
        p = self.plan("Is my Garchomp immune to Ground attacks?", self.ch)
        self.assertEqual((p.intent, p.user["Forme"], p.atk_type), ("type", "Garchomp-Mega-Z", "Ground"))


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestSolvers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sv, _ = readTeam(SV_TEAM, "gen9ou")
        cls.ch, _ = readTeam(CHAMPIONS_TEAM, "gen9championsou")

    def test_survive(self):
        v = solve(plan_query("Can Gholdengo survive a Kingambit Sucker Punch?", self.sv))
        # Kingambit's most common set does 71.4-84.6% to this Gholdengo
        self.assertEqual(v.answer, "yes")
        self.assertIn("Gholdengo survives", v.statement)

    def test_mega_levitate_immunity(self):
        v = solve(plan_query("Is my Garchomp immune to Ground attacks?", self.ch))
        self.assertEqual(v.answer, "immune")
        self.assertIn("Levitate", v.statement)

    def test_type_chart(self):
        self.assertEqual(solve(plan_query("is gholdengo weak to fire?", self.sv)).answer, "weak")
        self.assertEqual(solve(plan_query("Is Dragapult immune to Normal moves?", self.sv)).answer, "immune")

    def test_speed_and_stat(self):
        self.assertEqual(solve(plan_query("Is Great Tusk faster than Dragapult?", self.sv)).answer, "no")
        self.assertEqual(solve(plan_query("what is Great Tusk's speed stat", self.sv)).answer, "300")

    def test_usage(self):
        v = solve(plan_query("What's the most common item on Kingambit?", self.sv))
        self.assertEqual(v.persona, "builder")
        self.assertTrue(v.answer)


class TestVerifier(unittest.TestCase):
    verdict = Verdict("ko", "yes", "Kingambit's Sucker Punch does 71.4-84.6% to Gholdengo, so Gholdengo survives.",
                      ["Calc: 252+ Atk Kingambit Sucker Punch vs. 252 HP / 0 Def Gholdengo: 225-267 (71.4 - 84.6%)"])

    def test_grounded_text_passes(self):
        self.assertIsNone(verify("Sucker Punch only takes 71.4 to 84.6% of Gholdengo's HP, so it lives the hit.", self.verdict))

    def test_invented_number_rejected(self):
        self.assertIn("92", verify("Sucker Punch does 92%, so it barely lives.", self.verdict))

    def test_contradicting_answer_rejected(self):
        self.assertIsNotNone(verify("It dies.\nANSWER: no", self.verdict))


if __name__ == "__main__":
    unittest.main()


class TestNamesAndClarify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sv, _ = readTeam(SV_TEAM, "gen9ou")

    def test_nicknames_typos_and_megas(self):
        from metamatch.engine.names import find_pokemon
        self.assertEqual(find_pokemon("does my rillaboom outspeed cress"), ["Rillaboom", "Cresselia"])
        self.assertEqual(find_pokemon("can tusk ohko lando"), ["Great Tusk", "Landorus-Therian"])
        self.assertEqual(find_pokemon("ohko a full health excadril"), ["Excadrill"])
        self.assertEqual(find_pokemon("is mega garchomp z faster"), ["Garchomp-Mega-Z"])
        # Item words must not fuzzy match Pokemon ("helmet" vs Shelmet)
        self.assertEqual(find_pokemon("giga impact on corv @ rocky helmet"), ["Corviknight"])

    def test_unknown_opponent_asks_instead_of_answering(self):
        p = plan_query("is great tusk faster than zzzmon on its most common spread", self.sv)
        self.assertEqual(p.intent, "clarify")

    def test_mega_display_name(self):
        from metamatch.engine.solvers import display_name
        self.assertEqual(display_name("Garchomp-Mega-Z"), "Mega Garchomp Z")
        self.assertEqual(display_name("Staraptor-Mega"), "Mega Staraptor")
        self.assertEqual(display_name("Kingambit"), "Kingambit")


class TestContradictions(unittest.TestCase):
    def test_speed(self):
        v = Verdict("speed", "no", "Mega Staraptor (178 Speed) is slower than Dragapult (213 Speed).", [],
                    subject="Mega Staraptor", other="Dragapult")
        self.assertIsNotNone(verify("Once it Mega Evolves, it outspeeds a Dragapult on its usual spread.", v))
        self.assertIsNone(verify("Dragapult outspeeds it, so Staraptor moves second.", v))

    def test_ko(self):
        v = Verdict("ko", "sometimes", "Dragon Tail does 84.8-101.8% to Dragapult, so it OHKOs only on some rolls.", [])
        self.assertIsNotNone(verify("It is a guaranteed OHKO.", v))
        survive = Verdict("ko", "yes", "Sucker Punch does 71.4-84.6% to Gholdengo, so Gholdengo survives.", [], survive=True)
        self.assertIsNotNone(verify("Gholdengo does not survive the hit.", survive))
        self.assertIsNone(verify("Gholdengo lives comfortably at 71.4-84.6%.", survive))
