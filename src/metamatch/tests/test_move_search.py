"""Move Search: learnsets from Showdown's data, and the tiered search over a format's Pokemon."""
import importlib.util
import unittest
from pathlib import Path

from metamatch.engine import move_search
from metamatch.engine.learnsets import learns
from metamatch.strategy_data import ensure_strategy_data

ROOT = Path(__file__).resolve().parents[3]


def _build_module():
    spec = importlib.util.spec_from_file_location("build_learnsets", ROOT / "scripts" / "build_learnsets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LEARNSETS = ("export const Learnsets = {\n"
             "\tdewott: {\n\t\tlearnset: {\n\t\t\tswordsdance: [\"9M\", \"8M\"],\n\t\t\taquajet: [\"7E\"],\n\t\t},\n"
             "\t\teventData: [\n\t\t\t{generation: 5, level: 10, moves: [\"tackle\"]},\n\t\t],\n\t},\n"
             "\tsamurott: {\n\t\tlearnset: {\n\t\t\tmegahorn: [\"9L1\"],\n\t\t\tpursuit: [\"4L1\"],\n\t\t},\n\t},\n"
             "};\n")
CHAMPIONS = ("export const Learnsets = {\n"
             "\tsamurott: {\n\t\tlearnset: {\n\t\t\tsurf: [\"9M\"],\n\t\t},\n\t},\n"
             "\tfloette: {\n\t\tinherit: true,\n\t\tlearnset: {\n\t\t\tmoonblast: [\"9M\"],\n\t\t},\n\t},\n"
             "};\n")
POKEDEX = ("export const Pokedex = {\n"
           "\tsamurott: {\n\t\tnum: 503,\n\t\tname: \"Samurott\",\n\t\tprevo: \"Dewott\",\n\t},\n"
           "\trotomwash: {\n\t\tname: \"Rotom-Wash\",\n\t\tbaseSpecies: \"Rotom\",\n\t\tchangesFrom: \"Rotom\",\n\t},\n"
           "};\n")


class TestBuildLearnsets(unittest.TestCase):
    def setUp(self):
        self.data = _build_module().build({"data/learnsets.ts": LEARNSETS, "data/mods/champions/learnsets.ts": CHAMPIONS,
                                           "data/pokedex.ts": POKEDEX})

    def test_gen9_and_past_sources_split(self):
        self.assertEqual(self.data["sv"]["dewott"], "swordsdance")
        self.assertEqual(self.data["past"]["dewott"], "aquajet")
        self.assertEqual(self.data["sv"]["samurott"], "megahorn")
        self.assertEqual(self.data["past"]["samurott"], "pursuit")

    def test_event_moves_are_not_read_as_learnset(self):
        self.assertNotIn("tackle", self.data["sv"]["dewott"] + self.data["past"]["dewott"])

    def test_champions_and_dex_links(self):
        self.assertEqual(self.data["champions"]["samurott"], "surf")
        self.assertEqual(self.data["dex"]["samurott"], {"prevo": "dewott"})
        self.assertEqual(self.data["dex"]["rotomwash"], {"baseSpecies": "rotom", "changesFrom": "rotom"})


class TestLearns(unittest.TestCase):
    def test_evolution_learns_its_pre_evolutions_moves(self):
        from metamatch.engine.learnsets import _tables
        own = _tables()["sv"]["dragonite"]
        line = learns("Dragonair", "gen9ou")
        self.assertTrue(line - own, "Dragonair should teach a move Dragonite's own entry lacks")
        self.assertTrue(line <= learns("Dragonite", "gen9ou"))

    def test_forme_learns_its_base_forms_moves(self):
        moves = learns("Rotom-Wash", "gen9ou")
        self.assertIn("hydropump", moves)
        self.assertIn("voltswitch", moves)

    def test_mega_uses_its_base_species(self):
        self.assertEqual(learns("Charizard-Mega-Y", "gen9natdex"), learns("Charizard", "gen9natdex"))

    def test_national_dex_adds_past_generation_moves(self):
        self.assertIn("pursuit", learns("Tyranitar", "gen9natdex"))
        self.assertNotIn("pursuit", learns("Tyranitar", "gen9ou"))


class TestMoveSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.strat = ensure_strategy_data()

    def test_together_is_the_lower_bound(self):
        self.assertAlmostEqual(move_search.together([0.9, 0.8]), 0.7)
        self.assertEqual(move_search.together([0.5, 0.4]), 0.0)
        self.assertAlmostEqual(move_search.together([0.3]), 0.3)

    def test_options_are_proper_move_names(self):
        options = move_search.move_options("gen9ou")
        self.assertIn("Stealth Rock", options)
        self.assertFalse([m for m in options if m == m.lower()], "raw ids leaked into the picker")

    def test_smogon_sets_come_from_this_format_only(self):
        for r in move_search.search(["Scald"], "gen9ou", self.strat):
            for s in r["sets"]:
                self.assertTrue(s.endswith("(OU)"), s)

    def test_tiers_are_ordered_then_sorted_by_usage(self):
        results = move_search.search(["Stealth Rock", "U-turn"], "gen9ou", self.strat)
        order = [move_search.TIERS.index(r["tier"]) if r["tier"] in move_search.TIERS else 3 for r in results]
        self.assertEqual(order, sorted(order))
        for tier in move_search.TIERS:
            usage = [r["usage"] for r in results if r["tier"] == tier]
            self.assertEqual(usage, sorted(usage, reverse=True))

    def test_every_full_match_runs_or_learns_every_move(self):
        from metamatch.engine.dex import to_id
        for r in move_search.search(["Stealth Rock", "U-turn"], "gen9ou", self.strat):
            if r["tier"] == "ladder":
                self.assertTrue(all(v >= move_search.MIN_SHARE for v in r["shares"].values()))
            if r["tier"] == "learn":
                self.assertTrue({"stealthrock", "uturn"} <= learns(r["name"], "gen9ou"))
            if r["tier"] == "near":
                self.assertIn(r["missing"], ("Stealth Rock", "U-turn"))
                self.assertLess(r["shares"][r["missing"]], move_search.MIN_SHARE)
                self.assertEqual(r["learns_missing"], to_id(r["missing"]) in learns(r["name"], "gen9ou"))

    def test_champions_has_no_smogon_tier(self):
        results = move_search.search(["Earthquake"], "gen9championsou", self.strat)
        self.assertTrue(results)
        self.assertFalse([r for r in results if r["tier"] == "smogon"])

    def test_move_info_reads_showdown_data(self):
        info = move_search.move_info("Scald")
        self.assertEqual((info["type"], info["category"], info["power"]), ("Water", "Special", 80))
        self.assertIn("burn", info["short"])


if __name__ == "__main__":
    unittest.main()
