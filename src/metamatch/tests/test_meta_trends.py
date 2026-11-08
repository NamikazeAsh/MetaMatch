"""MetaFlash trends: moveset parsing, set trends, top players' picks, rising cores and the saved team report."""
import unittest

from metamatch import meta_trends as mt

MOVESET_TXT = """ +----------------------------------------+
 | Great Tusk                             |
 +----------------------------------------+
 | Raw count: 1200                        |
 +----------------------------------------+
 | Items                                  |
 | Booster Energy 60.000%                 |
 | Rocky Helmet 30.000%                   |
 | Other 10.000%                          |
 +----------------------------------------+
 | Spreads                                |
 | Jolly:0/252/0/0/4/252 50.000%          |
 +----------------------------------------+
 | Teammates                              |
 | Kingambit 40.000%                      |
 +----------------------------------------+
 +----------------------------------------+
 | Kingambit                              |
 +----------------------------------------+
 | Raw count: 900                         |
 +----------------------------------------+
"""


def _entry(items=(), teammates=()):
    return {"abilities": [], "items": [list(x) for x in items], "moves": [], "tera": [], "teammates": [list(x) for x in teammates]}


class TestMetaTrends(unittest.TestCase):
    def test_moveset_parsing_keeps_named_options_in_order(self):
        out = mt.parse_moveset_text(MOVESET_TXT)
        self.assertEqual(list(out), ["Great Tusk", "Kingambit"])
        self.assertEqual(out["Great Tusk"]["items"], [["Booster Energy", 60.0], ["Rocky Helmet", 30.0]])   # no "Other"
        self.assertEqual(out["Great Tusk"]["teammates"], [["Kingambit", 40.0]])
        self.assertEqual(out["Great Tusk"]["raw"], 1200)
        self.assertEqual(list(mt.parse_moveset_text(MOVESET_TXT, top_n=1)), ["Great Tusk"])

    def test_set_trends_report_real_shifts_only(self):
        usage = {"gen9ou": {"2026-09": [["A", 30.0], ["B", 20.0]], "2026-10": [["A", 30.0], ["B", 20.0]]}}
        sets = {"gen9ou": {
            "2026-09": {"A": _entry([("Scarf", 38.0), ("Boots", 30.0)]), "B": _entry([("Orb", 50.0), ("Vest", 40.0)])},
            "2026-10": {"A": _entry([("Scarf", 45.0), ("Boots", 28.0)]), "B": _entry([("Orb", 52.0), ("Belt", 8.0)])},
        }}
        trends = mt.set_trends("gen9ou", "2026-10", history=sets, usage=usage)
        # Biggest change first: Vest left B's list (40% before, under the 8% shortest listed share now), then A's
        # Scarf moved 7 points. Orb's 2 points are too small, and Belt is newly listed but under 10%
        self.assertEqual([(t["name"], t["option"], t["delta"]) for t in trends], [("B", "Vest", -32.0), ("A", "Scarf", 7.0)])
        self.assertTrue(trends[0].get("gone"))

    def test_top_players_picks_and_rising_cores(self):
        usage = {"gen9ou": {"2026-09": [["A", 20.0], ["B", 20.0], ["C", 5.0]], "2026-10": [["A", 30.0], ["B", 10.0], ["C", 1.0]]}}
        wide = {"gen9ou": {"2026-10": [["A", 20.0], ["B", 12.0], ["C", 0.5]]}}
        favs = mt.ladder_favorites("gen9ou", "2026-10", wide=wide, usage=usage)
        self.assertEqual([r["name"] for r in favs], ["A"])          # B is used less at the top, C is under 2%
        sets = {"gen9ou": {"2026-09": {"A": _entry(teammates=[("B", 20.0)]), "B": _entry(teammates=[("A", 20.0)])},
                           "2026-10": {"A": _entry(teammates=[("B", 30.0)]), "B": _entry(teammates=[("A", 80.0)])}}}
        cores = mt.rising_cores("gen9ou", "2026-10", history=sets, usage=usage)
        self.assertEqual(cores[0]["pair"], ["A", "B"])
        self.assertEqual((cores[0]["share"], cores[0]["prev"]), (9.0, 4.0))   # 30% x 30% now, 20% x 20% before

    def test_team_report_flags_new_and_climbing_threats(self):
        usage = {"gen9ou": {"2026-09": [["X", 9.0]] * 0 + [[f"T{i}", 20.0 - i] for i in range(14)],
                            "2026-10": [["T13", 30.0]] + [[f"T{i}", 20.0 - i] for i in range(12)]}}
        rows = [{"name": "T13", "answers": [], "losses": ["M"]}, {"name": "T0", "answers": ["M"], "losses": []},
                {"name": "T5", "answers": ["M"], "losses": []}]
        report = mt.team_report({}, "gen9ou", "2026-10", rows=rows, usage=usage)
        self.assertEqual((report["answered"], report["total"]), (2, 3))
        self.assertEqual([t["name"] for t in report["new"]], ["T13"])      # #14 last month, #1 now
        self.assertEqual(report["new"][0]["answers"], [])


if __name__ == "__main__":
    unittest.main()
