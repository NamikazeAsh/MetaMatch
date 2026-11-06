"""Team building tools: Threat Board and the "what checks X" answer."""
import unittest

from metamatch.engine import calc
from metamatch.engine.planner import plan_query
from metamatch.engine.solvers import Verdict, solve
from metamatch.agents.grounded import verify
from metamatch.team import readTeam

TEAM = """Gholdengo @ Choice Scarf
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
- Rapid Spin
- Knock Off

Kingambit @ Black Glasses
Ability: Supreme Overlord
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Swords Dance
- Kowtow Cleave
- Sucker Punch
- Iron Head"""


class TestChecksIntent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM, "gen9ou")

    def test_phrasings_route_to_checks(self):
        for q in ["what checks Kyurem on my team?", "who on my team counters Zamazenta", "answers to raging bolt?"]:
            self.assertEqual(plan_query(q, self.team).intent, "checks", q)

    def test_strategy_questions_stay_open(self):
        self.assertEqual(plan_query("how do I beat Kingambit?", self.team).intent, "open")

    def test_verifier_rejects_a_loser_called_an_answer(self):
        v = Verdict("checks", "Gholdengo", "Gholdengo beats Kyurem one on one.", [], other="Kyurem",
                    losers=["Great Tusk"], members=["Gholdengo", "Great Tusk", "Kingambit"])
        self.assertIsNotNone(verify("Great Tusk is your best answer to Kyurem.", v))
        self.assertIsNone(verify("Gholdengo handles Kyurem, while Great Tusk is OHKO'd by Ice Beam.", v))


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestThreatBoard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM, "gen9ou")

    def test_board_rows_cover_every_member(self):
        from metamatch.engine.threat_board import coverage, threat_board
        rows = threat_board(self.team, n=4)
        self.assertTrue(rows)
        members = {p["Pokemon"] for p in self.team.values()}
        for r in rows:
            self.assertNotIn(r.name, members)
            self.assertEqual(set(r.cells), members)
            self.assertTrue(set(r.answers).isdisjoint(r.losses))
        answered, total, share = coverage(rows)
        self.assertEqual(total, len(rows))
        self.assertTrue(0 <= share <= 1)

    def test_checks_answer_lists_answers_and_losses(self):
        v = solve(plan_query("what checks Kyurem on my team?", self.team))
        self.assertEqual(v.intent, "checks")
        self.assertIn("Kyurem", v.statement)
        for name in v.losers:
            self.assertNotIn(name, v.answer)


class TestSpeedBoard(unittest.TestCase):
    def test_ivs_are_parsed_and_lower_speed(self):
        team, _ = readTeam("Hatterene @ Life Orb\nAbility: Magic Bounce\nEVs: 252 HP / 252 SpA\nQuiet Nature\n"
                           "IVs: 0 Atk / 0 Spe\n- Psychic", "gen9ou")
        p = next(iter(team.values()))
        self.assertEqual(p["IVs"], {"Atk": 0, "Spe": 0})
        self.assertEqual(p["Speed"], 56)   # base 29, 0 IV, 0 EV, Quiet: floor(63 * 0.9)

    def test_outspeed_share_mixes_in_scarf(self):
        from metamatch.engine.speed_board import MetaSpeed, outspeed_share
        m = MetaSpeed("X", 10.0, [(300, 0.8), (250, 0.2)], scarf_share=0.5)
        self.assertAlmostEqual(outspeed_share(301, m), 0.5)     # beats every unscarfed set, no scarfed one
        self.assertAlmostEqual(outspeed_share(460, m), 1.0)
        self.assertAlmostEqual(outspeed_share(260, m), 0.1)     # only the unscarfed 250s


if __name__ == "__main__":
    unittest.main()
