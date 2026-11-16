"""The packet voice: parsing the model's two lines, the opener and why checks, the repairs, and fallbacks. No LLM."""
import unittest

from metamatch.agents import voice
from metamatch.engine.packet import Fact, Packet

FACTS = [Fact("damage", "The opposing Raging Bolt's Thunderbolt does 38 to 44% of your Slowking-Galar's HP, knocking it "
                        "out in 3 hits.", role="why")]
PACKET = Packet("who can switch into raging bolt", "switchins", answer="Your Slowking-Galar takes the opposing Raging "
                                                                       "Bolt's attacks best.")


class TestParse(unittest.TestCase):
    def test_labelled_and_bare_lines(self):
        self.assertEqual(voice.parse("OPENER: Ah!\nWHY: Because."), {"opener": "Ah!", "why": "Because."})
        self.assertEqual(voice.parse("Ah, splendid!\nYour Kingambit wins."), {"opener": "Ah, splendid!", "why": "Your Kingambit wins."})


class TestOpener(unittest.TestCase):
    def test_tone_only(self):
        self.assertIsNone(voice.check_opener("Ah, a classic problem!"))
        self.assertIsNone(voice.check_opener("Science has the answer!"))

    def test_claims_rejected(self):
        for line in ["Your Kingambit is a beast!", "Rain teams are tough!", "That's a great team you have there!",
                     "Great news, you outspeed it!", "Ah, 3 of them!"]:
            self.assertIsNotNone(voice.check_opener(line), line)

    def test_repetition_rejected(self):
        self.assertIsNotNone(voice.check_opener("Ah, a classic problem!", ["Ah, a classic problem!"]))

    def test_every_bank_line_passes(self):
        for persona in voice.PERSONAS.values():
            for line in persona["bank"]:
                self.assertIsNone(voice.check_opener(line), line)


class TestWhy(unittest.TestCase):
    def test_restatement_passes(self):
        why = "The opposing Raging Bolt's Thunderbolt only does 38 to 44% of your Slowking-Galar's HP."
        self.assertIsNone(voice.check_why(why, FACTS, PACKET))

    def test_invented_reason_rejected(self):
        why = "Your Slowking-Galar has great special bulk and Regenerator to heal it up."
        self.assertIsNotNone(voice.check_why(why, FACTS, PACKET))

    def test_invented_number_rejected(self):
        why = "The opposing Raging Bolt's Thunderbolt does 60% of your Slowking-Galar's HP."
        self.assertIn("numbers", voice.check_why(why, FACTS, PACKET))

    def test_repairs(self):
        fixed = voice.repair_why("F1: Thunderbolt does 38 to 44% of Slowking-Galar's HP.", FACTS, ["Slowking-Galar"])
        self.assertEqual(fixed, "Thunderbolt does 38 to 44% of your Slowking-Galar's HP.")


class TestOffline(unittest.TestCase):
    def test_fallbacks_without_the_model(self):
        original = voice.ollama_available
        voice.ollama_available = lambda *a, **k: False
        try:
            p = Packet("q", "switchins", persona="strategy", answer="A.")
            p.add(Fact("damage", FACTS[0].text), why=True)
            opener, why, report = voice.speak(p)
            self.assertIn(opener, voice.PERSONAS["strategy"]["bank"])
            self.assertEqual(why, FACTS[0].text)
            self.assertEqual(report["opener"], "stock")
        finally:
            voice.ollama_available = original


if __name__ == "__main__":
    unittest.main()
