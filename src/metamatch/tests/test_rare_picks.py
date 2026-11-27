"""Rare picks (Sceptile in National Dex): the all ratings stats fill in Pokemon the top ladder rarely brings, so
Quick Match and Spread Lab can offer them with a real set."""
import unittest
from unittest import mock

from metamatch import auditor
from metamatch.engine import sets

HIGH = {"Great Tusk": {"usage": 0.3, "Abilities": {"protosynthesis": 900}},
        "Sceptile": {"usage": 0.0002, "Abilities": {"overgrow": 1}}}
LOW = {"Great Tusk": {"usage": 0.25, "Abilities": {"protosynthesis": 9000}},
       "Sceptile": {"usage": 0.004, "Abilities": {"unburden": 300, "overgrow": 100},
                    "Items": {"lifeorb": 80, "focussash": 50}, "Moves": {"leafblade": 350, "dragonpulse": 300},
                    "Spreads": {"Jolly:0/252/0/0/4/252": 120}, "Tera Types": {}, "Teammates": {"Greninja": 60}},
       "Pidgey": {"usage": 0.00001, "Abilities": {"keeneye": 3}}}


class TestAllRatings(unittest.TestCase):
    def test_trim_keeps_only_rare_picks_with_enough_sets(self):
        rare = auditor.trim_all_ratings(LOW, HIGH)
        self.assertEqual(set(rare), {"Sceptile"})   # Great Tusk is in the main file, Pidgey has 3 sets
        self.assertTrue(rare["Sceptile"]["all_ratings"])
        self.assertEqual(list(rare["Sceptile"]["Items"]), ["lifeorb", "focussash"])

    def test_roster_lists_rare_picks_after_the_main_stats(self):
        rare = auditor.trim_all_ratings(LOW, HIGH)
        with mock.patch.object(auditor, "load_chaos_data", lambda f: HIGH), \
                mock.patch.object(auditor, "load_all_ratings", lambda f: rare):
            self.assertEqual(auditor.format_roster("gen9natdex"), ["Great Tusk", "Sceptile"])

    def test_set_lookup_falls_back_to_all_ratings(self):
        rare = auditor.trim_all_ratings(LOW, HIGH)
        main = {"Great Tusk": HIGH["Great Tusk"]}
        with mock.patch.object(sets, "load_chaos_data", lambda f: main), \
                mock.patch.object(sets, "load_all_ratings", lambda f: rare):
            key, entry = sets.chaos_entry("Sceptile", "gen9natdex")
            self.assertEqual((key, entry["all_ratings"]), ("Sceptile", True))
            self.assertEqual(sets.chaos_entry("Sceptile", "gen9natdex", rare=False), (None, None))


if __name__ == "__main__":
    unittest.main()
