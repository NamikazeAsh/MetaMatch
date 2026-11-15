"""Engine correctness fixes from the 2026 11 15 restructure: self dropping moves over turns, half HP moves,
Choice and Assault Vest sets, Speed ties, and Speed answers with a stated opponent item."""
import unittest

from metamatch.engine import calc, mechanics
from metamatch.engine.briefing import _race, _reason
from metamatch.engine.dex import get_dex
from metamatch.engine.planner import plan_query
from metamatch.engine.sets import likely_set
from metamatch.engine.solvers import solve
from metamatch.team import readTeam

TEAM = """Gholdengo @ Choice Scarf
Ability: Good as Gold
Tera Type: Steel
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Trick
- Focus Blast"""


class TestSelfDrops(unittest.TestCase):
    def test_dex_marks_self_dropping_moves(self):
        dex = get_dex("sv")
        self.assertEqual(dex.move("Draco Meteor").get("selfDrop"), 2)
        self.assertEqual(dex.move("Make It Rain").get("selfDrop"), 1)
        self.assertFalse(dex.move("Close Combat").get("selfDrop"))

    @unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
    def test_later_uses_hit_weaker(self):
        att = {"name": "Dragapult", "nature": "Timid", "evs": {"spa": 252, "spe": 252}}
        dfn = {"name": "Corviknight", "nature": "Impish", "evs": {"hp": 252, "def": 168, "spd": 88}}
        r = calc.calculate({"game": "sv", "attacker": att, "defender": dfn, "move": "Draco Meteor"})
        naive = mechanics.hits_to_ko(r, att, dfn, "Draco Meteor")
        counted = mechanics.hits_to_ko(r, att, dfn, "Draco Meteor", game="sv")
        self.assertGreater(counted, naive)


class TestHalfHpMoves(unittest.TestCase):
    def test_half_hp_never_kos_alone_but_opens(self):
        half = {"range": [100, 100], "percent": [50.0, 50.0], "half_hp": True, "defender_stats": {"hp": 200}}
        hit = {"range": [60, 70], "percent": [30.0, 35.0], "defender_stats": {"hp": 200}}
        self.assertIsNone(mechanics.hits_to_ko(half, {}, {}, "Ruination"))
        self.assertIsNone(_race([("Ruination", half)], {}, {}, None))
        # Ruination then 60 damage hits: 100 left, so 1 + 2 = 3, against 4 hits of the plain attack alone
        self.assertEqual(_race([("Ruination", half), ("Earthquake", hit)], {}, {}, None), 3)

    @unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
    def test_ruination_shows_as_chip(self):
        from metamatch.engine.threat_board import threat_row
        team, _ = readTeam("Dragonite @ Heavy-Duty Boots\nAbility: Multiscale\nEVs: 252 Atk / 4 SpD / 252 Spe\n"
                           "Adamant Nature\n- Dragon Dance\n- Earthquake\n- Extreme Speed\n- Roost", "gen9ou")
        row = threat_row(team, "Ting-Lu", "gen9ou")
        if row and "Ruination" in [m for m, _ in likely_set("Ting-Lu", "gen9ou")["moves"]]:
            self.assertIn("Ruination", row.cells["Dragonite"].reason)


class TestSets(unittest.TestCase):
    def test_choice_and_vest_sets_have_no_locked_status_moves(self):
        dex = get_dex("sv")
        for name in ["Dragapult", "Kyurem", "Gholdengo"]:
            s = likely_set(name, "gen9ou")
            if not s:
                continue
            item = (s["item"] or "").replace(" ", "").lower()
            status = [m for m, _ in s["moves"] if (dex.move(m) or {}).get("category") == "Status"]
            if item in ("choicespecs", "choiceband", "choicescarf"):
                self.assertTrue(set(status) <= {"Trick", "Switcheroo"}, (name, status))
            if item == "assaultvest":
                self.assertEqual(status, [], name)


class TestSpeed(unittest.TestCase):
    def test_tie_share_and_wording(self):
        self.assertAlmostEqual(mechanics.scarf_adjusted_tie(439, [(439, 1.0)], 0.0), 1.0)
        x = {"outspeeds": 0.0, "ties": 1.0, "to_ko": 2, "to_be_koed": 2, "dealt": None, "taken": None}
        self.assertTrue(_reason(x).startswith("speed tie"))

    @unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
    def test_stated_scarf_drops_ladder_share(self):
        team, _ = readTeam(TEAM, "gen9ou")
        v = solve(plan_query("Does my Gholdengo outspeed a Choice Scarf Dragapult?", team))
        self.assertFalse(any("Across all" in f for f in v.facts))
        self.assertTrue(any("stated Choice Scarf" in f for f in v.facts))


if __name__ == "__main__":
    unittest.main()
