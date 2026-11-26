"""Oak voicing a retrieved passage: framing lines, the quoted sentences, and the chat answer they make."""
import unittest
from unittest import mock

from metamatch.agents import coach, retell

PASSAGE = ("Kingambit is a potent late game cleaner with Swords Dance and Sucker Punch. It fears burns from Will-O-Wisp. "
           "Low Kick hits opposing Kingambit hard. Leftovers keeps it healthy over a long game.")
HIT = {"text": "Pokemon: Kingambit | Section: Set Swords Dance | Format: SV OU analysis\n" + PASSAGE,
       "metadata": {"pokemon": "Kingambit", "species": "Kingambit", "section": "Set Swords Dance",
                    "source": "smogon_analysis", "format": "gen9ou", "game": "sv", "type": "set"},
       "distance": 0.3}


class TestQuotes(unittest.TestCase):
    def test_best_sentences_keep_the_passage_order_and_match_the_question(self):
        got = retell.best_sentences("does kingambit fear burns", PASSAGE, k=2)
        self.assertIn("It fears burns from Will-O-Wisp.", got)
        self.assertEqual(got, [s for s in retell.SENTENCE.split(PASSAGE) if s in got])

    def test_no_shared_words_falls_back_to_the_first_sentences(self):
        self.assertEqual(retell.best_sentences("zzz qqq", PASSAGE, k=1), [PASSAGE.split(". ")[0] + "."])

    def test_quote_is_the_passage_words_only(self):
        quote = retell.quoted("how do I use Kingambit", HIT)
        for sentence in retell.SENTENCE.split(quote):
            self.assertIn(sentence, PASSAGE)


class TestFrames(unittest.TestCase):
    def test_template_names_the_set(self):
        self.assertEqual(retell.template(HIT["metadata"]), "Ah, Kingambit! Here's how players run its Swords Dance set:")

    def test_template_avoids_the_last_line_used(self):
        first = retell.template(HIT["metadata"])
        self.assertNotEqual(retell.template(HIT["metadata"], recent=[first]), first)

    def test_concept_template_uses_its_title(self):
        meta = {"pokemon": "Concept", "type": "concept", "title": "Entry Hazards", "source": "concepts"}
        self.assertIn("entry hazards", retell.template(meta))

    def test_frame_check_rejects_facts_and_other_pokemon(self):
        meta = HIT["metadata"]
        self.assertIsNone(retell.check_frame("Ah, Kingambit! Here's how the experts run it:", meta))
        self.assertIn("another Pokemon", retell.check_frame("Kingambit beats Great Tusk:", meta))
        self.assertIn("move", retell.check_frame("Kingambit loves Sucker Punch:", meta))
        self.assertEqual(retell.check_frame("Kingambit has 135 Attack:", meta), "a number")

    def test_frame_uses_the_template_unless_the_model_is_asked_for(self):
        with mock.patch("metamatch.agents.client.ollama_available", return_value=True), \
                mock.patch("metamatch.agents.client.chat") as chat:
            line, by = retell.frame("how do I use Kingambit", HIT["metadata"], use_model=False)
        self.assertEqual(by, "template")
        chat.assert_not_called()

    def test_a_model_line_that_fails_the_check_falls_back(self):
        with mock.patch("metamatch.agents.client.ollama_available", return_value=True), \
                mock.patch("metamatch.agents.client.chat", return_value="Kingambit outspeeds Great Tusk:"):
            line, by = retell.frame("how do I use Kingambit", HIT["metadata"], use_model=True)
        self.assertEqual(by, "template")


class TestChatAnswer(unittest.TestCase):
    def test_open_question_gets_oaks_line_the_quote_and_the_source(self):
        with mock.patch.object(coach, "references", return_value=[HIT]), \
                mock.patch.object(coach, "ollama_available", return_value=False):
            text = coach.CoachAgent().packet_text("how do I use Kingambit", {}, coach.Briefing())
        self.assertIn("Ah, Kingambit!", text)
        self.assertIn("> ", text)
        self.assertIn("smogon.com/dex/sv/pokemon/kingambit/ou", text)
        self.assertNotIn("can't", text.split("\n")[0])

    def test_nothing_worth_reading_keeps_the_honest_fallback(self):
        with mock.patch.object(coach, "references", return_value=[]):
            text = coach.CoachAgent().packet_text("what is the meaning of life", {}, coach.Briefing())
        self.assertTrue(text.startswith("*"))


if __name__ == "__main__":
    unittest.main()
