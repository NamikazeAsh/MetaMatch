"""Teams like yours and real game precedents, on a small synthetic ladder corpus (no network, no replays)."""
import unittest
from unittest import mock

from metamatch.engine import precedents, team_neighbors as tn

A = ["Great Tusk", "Gholdengo", "Kingambit", "Dragapult", "Ogerpon-Wellspring", "Zapdos"]
CORPUS = {"formats": {"gen9ou": [
    {"id": "gen9ou-1", "side": "p1", "rating": 1700, "time": 300, "lead": "Great Tusk",
     "team": ["Great Tusk", "Gholdengo", "Kingambit", "Dragapult", "Ogerpon-Wellspring", "Slowking-Galar"],
     "kos": [[12, "Great Tusk", "Kingambit"], [20, "Gholdengo", "Iron Valiant"]]},
    {"id": "gen9ou-2", "side": "p2", "rating": 1550, "time": 200, "lead": "Toxapex",
     "team": ["Toxapex", "Gliscor", "Blissey", "Corviknight", "Clefable", "Dondozo"], "kos": []},
    {"id": "gen9ou-3", "side": "p1", "rating": 1800, "time": 100, "lead": "Kingambit",
     "team": ["Kingambit", "Gholdengo", "Great Tusk", "Iron Valiant", "Landorus-Therian", "Rotom-Wash"],
     "kos": [[7, "Kingambit", "Iron Valiant"], [11, "Landorus-Therian", "Samurott-Hisui"]]},
    # The same six as gen9ou-1 from another game: one team, two games
    {"id": "gen9ou-4", "side": "p2", "rating": 1650, "time": 50, "lead": "Dragapult",
     "team": ["Slowking-Galar", "Ogerpon-Wellspring", "Dragapult", "Kingambit", "Gholdengo", "Great Tusk"], "kos": []},
]}}


class TestTeamNeighbors(unittest.TestCase):
    def setUp(self):
        for f in (tn._corpus_file, tn.corpus, tn._idf, tn.embedding):
            f.cache_clear()
        self.patches = [mock.patch.object(tn, "_corpus_file", lambda: CORPUS),
                        mock.patch.object(tn, "embedding", lambda format_id: {})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for f in (tn.corpus, tn._idf):
            f.cache_clear()

    def test_same_six_from_two_games_is_one_team(self):
        teams = tn.corpus("gen9ou")
        self.assertEqual(len(teams), 3)
        key = frozenset(CORPUS["formats"]["gen9ou"][0]["team"])
        self.assertEqual(len(teams[key]["records"]), 2)

    def test_identical_team_has_similarity_one(self):
        six = CORPUS["formats"]["gen9ou"][0]["team"]
        self.assertAlmostEqual(tn.similarity(frozenset(six), frozenset(six), "gen9ou"), 1.0)

    def test_closest_team_shares_the_most_and_unrelated_teams_are_left_out(self):
        near = tn.neighbors(A, "gen9ou")
        self.assertEqual(near[0]["replays"][0], "gen9ou-1")
        self.assertEqual(near[0]["extra"], ["Slowking-Galar"])
        self.assertNotIn("Toxapex", {n for r in near for n in r["team"]})

    def test_substitutions_read_what_neighbours_run_instead(self):
        near = tn.neighbors(A, "gen9ou")
        subs = tn.substitutions(A, near)
        self.assertEqual(subs["Zapdos"]["without"], len(near))
        self.assertIn("Slowking-Galar", dict(subs["Zapdos"]["instead"]))

    def test_reorder_lifts_what_close_teams_run(self):
        partners = [{"name": "Toxapex"}, {"name": "Slowking-Galar"}, {"name": "Corviknight"}]
        order = [p["name"] for p in tn.reorder(A[:5], "gen9ou", partners)]
        self.assertEqual(order[0], "Slowking-Galar")
        self.assertEqual(sorted(order), sorted(p["name"] for p in partners))

    def test_mega_compares_as_its_base(self):
        self.assertEqual(tn.base("Charizard-Mega-Y"), "Charizard")
        self.assertEqual(tn.base("Landorus-Therian"), "Landorus-Therian")


class TestPrecedents(unittest.TestCase):
    def setUp(self):
        for f in (tn._corpus_file, tn.corpus, tn._idf):
            f.cache_clear()
        self.patch = mock.patch.object(tn, "_corpus_file", lambda: CORPUS)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        for f in (tn.corpus, tn._idf):
            f.cache_clear()

    def test_precedent_is_a_shared_member_knocking_out_the_threat(self):
        p = precedents.precedent(A, "Iron Valiant", "gen9ou")
        self.assertEqual((p["by"], p["turn"]), ("Gholdengo", 20))
        self.assertGreaterEqual(p["shared"], tn.MIN_SHARED)

    def test_a_knockout_by_a_member_you_dont_run_does_not_count(self):
        # In gen9ou-3 only Landorus-Therian, which team A doesn't run, knocked out Samurott-Hisui
        p = precedents.precedent(A, "Samurott-Hisui", "gen9ou")
        self.assertIsNone(p)

    def test_a_knockout_by_a_board_answer_is_preferred(self):
        # Both Gholdengo (gen9ou-1) and Kingambit (gen9ou-3) knocked out Iron Valiant; Kingambit is the board's answer
        p = precedents.precedent(A, "Iron Valiant", "gen9ou", prefer=["Kingambit"])
        self.assertEqual(p["by"], "Kingambit")

    def test_line_names_no_winner(self):
        text = precedents.line(precedents.precedent(A, "Iron Valiant", "gen9ou")).lower()
        for word in ("won", "win", "lost", "loss", "beat the"):
            self.assertNotIn(word, text)


LOG = """|player|p1|Alice|
|player|p2|Bob|
|teamsize|p1|3
|teamsize|p2|3
|gametype|singles
|gen|9
|tier|[Gen 9] National Dex
|poke|p1|Charizard, M|
|poke|p1|Great Tusk|
|poke|p1|Gholdengo|
|poke|p2|Kingambit, M|
|poke|p2|Urshifu-*, M|
|poke|p2|Toxapex, F|
|start
|switch|p1a: Zard|Charizard, M|100/100
|switch|p2a: Gambit|Kingambit, M|100/100
|turn|1
|detailschange|p1a: Zard|Charizard-Mega-Y, M
|move|p1a: Zard|Heat Wave|p2a: Gambit
|-damage|p2a: Gambit|0 fnt
|faint|p2a: Gambit
|
|switch|p2a: Fish|Urshifu-Rapid-Strike, M|100/100
|turn|2
"""


class TestLadderRecords(unittest.TestCase):
    def setUp(self):
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[3] / "scripts" / "fetch_ladder_teams.py"
        spec = importlib.util.spec_from_file_location("fetch_ladder_teams", path)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_record_holds_the_six_as_played_the_lead_and_knockouts(self):
        recs = {r["side"]: r for r in self.mod.records({"id": "gen9natdex-1", "log": LOG, "players": ["Alice", "Bob"],
                                                         "rating": 1600, "uploadtime": 10})}
        self.assertEqual(recs["p1"]["team"], ["Charizard-Mega-Y", "Great Tusk", "Gholdengo"])
        self.assertEqual(recs["p2"]["team"], ["Kingambit", "Urshifu-Rapid-Strike", "Toxapex"])
        self.assertEqual(recs["p1"]["lead"], "Charizard-Mega-Y")
        self.assertEqual(recs["p1"]["kos"], [[1, "Charizard-Mega-Y", "Kingambit"]])
        self.assertEqual(recs["p2"]["kos"], [])
        self.assertNotIn("Alice", str({k: v for k, v in recs["p1"].items() if k != "_player"}))

    def test_terastal_formes_fold_back(self):
        self.assertEqual(self.mod._name("Ogerpon-Wellspring-Tera"), "Ogerpon-Wellspring")
        self.assertEqual(self.mod._name("Terapagos-Stellar"), "Terapagos")


if __name__ == "__main__":
    unittest.main()
