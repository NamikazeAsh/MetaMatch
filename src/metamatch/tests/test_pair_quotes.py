"""Smogon matchup quotes: the sentence about two Pokemon facing each other, never a teammate or third party one."""
import unittest
from unittest.mock import patch

from metamatch.rag import pair_quotes as pq

ANALYSES = {
    "Corviknight": {"sets": {"Defensive": {"description": (
        "<p>Corviknight is a reliable answer to Kingambit thanks to Body Press. "
        "Corviknight pairs well with Great Tusk, which spins hazards. "
        "Great Tusk checks Kingambit, letting Corviknight stay healthy.</p>")}}},
    "Dragapult": {"sets": {"Boots Pivot": {"description": (
        "<p>Corviknight checks Kingambit and has slow pivoting with U-turn, letting Dragapult come in safely. "
        "Dragapult is vulnerable to Kingambit's Sucker Punch.</p>")}}},
    "Kyurem": {"sets": {"Choice Specs": {"description": (
        "<p>Kyurem is often accompanied by Zamazenta, which switches into Pokemon that check Kyurem.</p>")}}},
}


class TestPairQuotes(unittest.TestCase):
    def setUp(self):
        pq._index.cache_clear()
        pq._names.cache_clear()
        self.patch = patch.object(pq, "_load", lambda key: ANALYSES)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        pq._index.cache_clear()
        pq._names.cache_clear()

    def test_the_sentence_about_the_pair(self):
        heading, sentence = pq.quote("Corviknight", "Kingambit", "gen9ou", prefer="Corviknight")
        self.assertIn("reliable answer to Kingambit", sentence)
        self.assertIn("Corviknight's SV OU analysis (Defensive set)", heading)

    def test_a_third_pokemon_doing_the_check_is_not_about_the_pair(self):
        # "Corviknight checks Kingambit ... letting Dragapult" is about Corviknight, not Dragapult
        _, sentence = pq.quote("Dragapult", "Kingambit", "gen9ou", prefer="Dragapult")
        self.assertIn("vulnerable to Kingambit", sentence)

    def test_teammate_sentences_are_never_quoted(self):
        self.assertIsNone(pq.quote("Kyurem", "Zamazenta", "gen9ou"))
        self.assertIsNone(pq.quote("Corviknight", "Great Tusk", "gen9ou"))

    def test_quotes_for_members_in_order(self):
        cards = pq.quotes_for(["Dragapult", "Corviknight", "Kyurem"], "Kingambit", "gen9ou", limit=2)
        self.assertEqual([c[0].split(" and ")[0] for c in cards], ["Smogon on Dragapult", "Smogon on Corviknight"])
        self.assertTrue(all(c[2] == "" for c in cards))

    def test_unknown_format_has_no_quotes(self):
        self.assertIsNone(pq.quote("Corviknight", "Kingambit", "gen9doublesou"))


if __name__ == "__main__":
    unittest.main()
