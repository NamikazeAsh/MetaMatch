"""The answer packet: plain language helpers, lint, and every engine answer producing lint clean typed facts."""
import unittest

from metamatch.engine import calc
from metamatch.engine.compose import packet_for
from metamatch.engine.packet import Fact, hits, lint, pct, plainify, spread_words
from metamatch.engine.planner import plan_query
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
- Focus Blast

Great Tusk @ Booster Energy
Ability: Protosynthesis
Tera Type: Ground
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Headlong Rush
- Ice Spinner
- Knock Off
- Rapid Spin

Kingambit @ Leftovers
Ability: Supreme Overlord
Tera Type: Dark
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Swords Dance
- Kowtow Cleave
- Sucker Punch
- Iron Head

Dragapult @ Heavy-Duty Boots
Ability: Infiltrator
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Draco Meteor
- Shadow Ball
- U-turn
- Will-O-Wisp"""

QUESTIONS = ["Does my Dragapult outspeed Iron Valiant?", "Does my Great Tusk OHKO Iron Valiant with Headlong Rush?",
             "How much damage does Kingambit's Kowtow Cleave do to Gholdengo?", "Is my Gholdengo weak to Ground?",
             "What is Gholdengo's speed stat?", "What does Dragapult usually run?", "Is Loaded Dice common on Garchomp?",
             "What are the most common teammates of Kingambit?", "Which of my Pokemon resist Water?", "what am i weak to",
             "Does Mold Breaker ignore Levitate?", "How do I beat Zamazenta?", "Does my Kingambit beat Gholdengo?",
             "What is my win condition?", "what should i lead", "what are my biggest threats", "what's my game plan",
             "who should i tera", "who can switch into raging bolt", "why is dragapult on this team",
             "What's the most common spread for Great Tusk?"]


class TestHelpers(unittest.TestCase):
    def test_words(self):
        self.assertEqual(pct(97.4, 114.2), "97 to 114%")
        self.assertEqual(hits(2, 2), "in 2 hits")
        self.assertEqual(hits(4, 3), "in 3 or 4 hits")
        self.assertEqual(hits(1), "in one hit")
        self.assertIsNone(hits(None))
        self.assertEqual(plainify("lets Sucker Punch 2HKO 6"), "lets Sucker Punch knock out in two hits 6")
        self.assertIn("same type bonus", plainify("Headlong Rush goes from 1.5x to 2x STAB"))
        self.assertEqual(spread_words("Timid", {"spa": 252, "spe": 252}), "Timid nature with 252 Special Attack and 252 Speed EVs")

    def test_lint_catches_problems(self):
        self.assertTrue(lint(Fact("damage", "Kingambit OHKOs it."), ["Kingambit"]))
        self.assertFalse(lint(Fact("damage", "Your Kingambit knocks out the opposing Gholdengo in one hit."),
                              ["Kingambit", "Gholdengo"]))


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestAnswersAreClean(unittest.TestCase):
    def test_every_answer_has_a_plain_sentence_and_clean_facts(self):
        team, _ = readTeam(TEAM, "gen9ou")
        names = [p["Pokemon"] for p in team.values()]
        for q in QUESTIONS:
            plan = plan_query(q, team)
            v = solve(plan)
            self.assertIsNotNone(v, q)
            self.assertTrue(v.plain, q)
            self.assertTrue(v.typed, q)
            for f in v.typed:
                self.assertEqual(lint(f, names), [], (q, f.text))
            p = packet_for(q, plan, v)
            self.assertTrue(1 <= len(p.why) <= 2, q)
            self.assertTrue(p.answer, q)



class TestSmogonCards(unittest.TestCase):
    def test_card_chain_and_labels(self):
        from metamatch.rag.cards import _order, card, _note
        order = _order("gen9ou")
        self.assertEqual(order[0], "gen9ou")
        self.assertLess(order.index("gen9uu"), order.index("gen8ou"))
        self.assertNotIn("championsou", order[:6])
        c = card("Kingambit", "gen9ou")
        if c:   # needs the local cache (scripts/fetch_smogon_analyses.py)
            self.assertTrue(c[0].startswith("From the"))
        self.assertIn("Dynamax", _note("gen8ou", "Dynamax lets it hit hard", "gen9ou"))
        self.assertEqual(_note("gen9ou", "Dynamax", "gen9ou"), "")


if __name__ == "__main__":
    unittest.main()
