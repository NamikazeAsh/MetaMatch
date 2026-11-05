import unittest

from metamatch import meta_pulse as mp

USAGE_TXT = """ Total battles: 1000
 + ---- + ------------------ + --------- + ------ + ------- + ------ + ------- +
 | Rank | Pokemon            | Usage %   | Raw    | %       | Real   | %       |
 + ---- + ------------------ + --------- + ------ + ------- + ------ + ------- +
 | 1    | Great Tusk         | 30.09623% | 340473 | 28.319% | 270722 | 28.051% |
 | 2    | Ogerpon-Wellspring | 19.44396% | 170001 | 14.140% | 136474 | 14.141% |
"""


def _history():
    """Two months: A stays #1, B rises past C, D drops, E is new to the top."""
    prev = [["A", 30.0], ["C", 20.0], ["D", 15.0], ["B", 10.0]] + [[f"X{i}", 2.0] for i in range(30)] + [["E", 1.0]]
    now = [["A", 31.0], ["B", 22.0], ["C", 19.0], ["E", 9.0], ["D", 4.0]] + [[f"X{i}", 2.0] for i in range(30)]
    return {"gen9ou": {"2026-09": prev, "2026-10": now}}


class TestMetaPulse(unittest.TestCase):
    def test_parse_usage_text(self):
        self.assertEqual(mp.parse_usage_text(USAGE_TXT), [("Great Tusk", 30.096), ("Ogerpon-Wellspring", 19.444)])

    def test_card_rules(self):
        cards = mp.pulse("gen9ou", n=6, history=_history(), month="2026-10", with_sets=False)
        kinds = {c["name"]: c["kind"] for c in cards}
        self.assertEqual(cards[0]["name"], "A")
        self.assertEqual(kinds["A"], "top")
        self.assertEqual(kinds["B"], "riser")
        self.assertEqual(kinds["D"], "faller")
        self.assertEqual(kinds["E"], "newcomer")
        self.assertEqual(len({c["name"] for c in cards}), len(cards))  # no duplicates
        b = next(c for c in cards if c["name"] == "B")
        self.assertEqual((b["rank"], b["prev_rank"], b["delta"]), (2, 4, 12.0))
        self.assertEqual(b["headline"], "Gains 12.0 points of usage")  # only 2 ranks, so the points read better
        self.assertEqual(next(c for c in cards if c["name"] == "A")["headline"], "Holds onto the #1 spot")

    def test_single_month_has_no_deltas(self):
        history = {"gen9ou": {"2026-10": _history()["gen9ou"]["2026-10"]}}
        cards = mp.pulse("gen9ou", n=3, history=history, month="2026-10", with_sets=False)
        self.assertEqual([c["kind"] for c in cards], ["top", "staple", "staple"])
        self.assertTrue(all(c["delta"] is None for c in cards))

    def test_unknown_format_is_empty(self):
        self.assertEqual(mp.pulse("gen9uu", history=_history(), month="2026-10", with_sets=False), [])

    def test_small_movers_never_headline(self):
        # X0 jumps from 2% to 2.9%: a big relative move but under the usage floor
        history = _history()
        history["gen9ou"]["2026-10"][5] = ["X0", 2.9]
        cards = mp.pulse("gen9ou", n=6, history=history, month="2026-10", with_sets=False)
        self.assertNotIn("X0", [c["name"] for c in cards if c["kind"] == "riser"])

    def test_sprite_urls_use_showdown_ids(self):
        forme, base = mp.sprite_urls("Ogerpon-Wellspring")
        self.assertTrue(forme.endswith("/ogerpon-wellspring.png"))
        self.assertTrue(base.endswith("/ogerpon.png"))
        self.assertTrue(mp.sprite_urls("Chi-Yu")[0].endswith("/chiyu.png"))
        self.assertTrue(mp.sprite_urls("Urshifu-Rapid-Strike")[0].endswith("/urshifu-rapidstrike.png"))

    def test_month_label(self):
        self.assertEqual(mp.month_label("2026-10"), "October 2026")


class TestMagazine(unittest.TestCase):
    def test_leaderboard_rank_changes(self):
        rows = mp.leaderboard("gen9ou", n=4, history=_history(), month="2026-10")
        self.assertEqual([r["name"] for r in rows], ["A", "B", "C", "E"])
        self.assertEqual([r["prev_rank"] for r in rows], [1, 4, 2, 35])  # E was ranked 35th last month

    def test_featured_prefers_top10_riser(self):
        cards = mp.pulse("gen9ou", n=6, history=_history(), month="2026-10", with_sets=False)
        self.assertEqual(cards[mp.featured_index(cards)]["name"], "B")
        only_top = [c for c in cards if c["kind"] != "riser"]
        self.assertEqual(only_top[mp.featured_index(only_top)]["kind"], "top")


if __name__ == "__main__":
    unittest.main()
