"""Building a team from a few names: reading the names, and filling the open slots under Species Clause."""
import unittest

from metamatch.auditor import load_chaos_data
from metamatch.engine import team_fill
from metamatch.recommender import is_mega

PASTE = """Gholdengo @ Choice Scarf
Ability: Good as Gold
- Make It Rain
- Shadow Ball"""


class TestLooksLikeNames(unittest.TestCase):
    def test_names_and_free_text(self):
        self.assertTrue(team_fill.looks_like_names("gholdengo, great tusk, kingambit"))
        self.assertTrue(team_fill.looks_like_names("a team with dragapult and ting lu"))
        self.assertTrue(team_fill.looks_like_names("Gholdengo"))

    def test_pastes_links_and_nothing(self):
        self.assertFalse(team_fill.looks_like_names(PASTE))
        self.assertFalse(team_fill.looks_like_names("Gholdengo @ Choice Scarf"))
        self.assertFalse(team_fill.looks_like_names("https://pokepast.es/abc123"))
        self.assertFalse(team_fill.looks_like_names("   "))
        self.assertFalse(team_fill.looks_like_names("hello there"))


@unittest.skipUnless(load_chaos_data("gen9ou") and load_chaos_data("gen9natdex"), "needs this month's stats")
class TestParseNames(unittest.TestCase):
    def test_reads_names_as_the_format_lists_them(self):
        names, unknown = team_fill.parse_names("gholdengo, great tusk, kingambit", "gen9ou")
        self.assertEqual(names, ["Gholdengo", "Great Tusk", "Kingambit"])
        self.assertEqual(unknown, [])

    def test_species_clause_keeps_the_first(self):
        names, _ = team_fill.parse_names("rotom wash, rotom heat, gholdengo", "gen9ou")
        self.assertEqual(len([n for n in names if n.startswith("Rotom")]), 1)

    def test_one_mega(self):
        names, _ = team_fill.parse_names("mega lop, mega metagross, kingambit", "gen9natdex")
        self.assertLessEqual(sum(is_mega(n) for n in names), 1)
        self.assertIn("Kingambit", names)

    def test_a_pokemon_the_format_has_no_record_of(self):
        names, unknown = team_fill.parse_names("gholdengo, mega lop", "gen9ou")
        self.assertEqual(names, ["Gholdengo"])
        self.assertEqual(unknown, ["Lopunny-Mega"])


@unittest.skipUnless(load_chaos_data("gen9ou"), "needs this month's stats")
class TestFill(unittest.TestCase):
    def check(self, team, core, fmt):
        self.assertEqual(len(team), 6)
        self.assertEqual(team[:len(core)], core)
        self.assertEqual(len({team_fill.species(n, fmt) for n in team}), 6)
        self.assertLessEqual(sum(is_mega(n) for n in team), 1)

    def test_every_method_makes_a_legal_six(self):
        core = ["Gholdengo", "Great Tusk"]
        for method in team_fill.METHODS:
            team, filled = team_fill.fill(core, "gen9ou", method=method)
            self.check(team, core, "gen9ou")
            self.assertEqual(filled, team[2:])

    def test_veto_keeps_out_picks_without_a_set(self):
        first, _ = team_fill.fill(["Gholdengo"], "gen9ou")
        team, filled = team_fill.fill(["Gholdengo"], "gen9ou", has_set=lambda n: n != first[1])
        self.check(team, ["Gholdengo"], "gen9ou")
        self.assertNotIn(first[1], filled)

    def test_a_full_team_is_left_alone(self):
        six = ["Gholdengo", "Great Tusk", "Kingambit", "Dragapult", "Ting-Lu", "Iron Valiant"]
        self.assertEqual(team_fill.fill(six, "gen9ou"), (six, []))


if __name__ == "__main__":
    unittest.main()
