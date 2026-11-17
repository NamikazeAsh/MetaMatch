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
             "What's the most common spread for Great Tusk?", "What is weak in my dragapult",
             "what does my kingambit resist", "how to use weather team", "how do i build a rain team"]


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


class TestMemberTypeProfile(unittest.TestCase):
    def test_one_member_without_a_type_gets_its_whole_profile(self):
        team, _ = readTeam(TEAM, "gen9ou")
        for q, ask, answer in [("What is weak in my dragapult", "weak", "Ice, Ghost, Dragon, Dark, Fairy"),
                               ("what are my kingambit's weaknesses", "weak", "Fire, Fighting, Ground"),
                               ("what does my kingambit resist", "resist", None),
                               ("what is my great tusk immune to", "immune", "Electric")]:
            plan = plan_query(q, team)
            self.assertEqual((plan.intent, plan.atk_type, plan.team_ask), ("type", None, ask), q)
            v = solve(plan)
            if answer:
                self.assertEqual(v.answer, answer, q)
        # Advice about a weakness is still a strategy question
        self.assertNotEqual(plan_query("how do I cover my dragapult's weaknesses", team).intent, "type")


class TestSuggestions(unittest.TestCase):
    def test_every_chip_and_help_example_reaches_an_engine_answer(self):
        from metamatch.agents.suggest import marker, split, suggestions
        from metamatch.tabs.tab_chat import help_cards
        team, _ = readTeam(TEAM, "gen9ou")
        for q in ["how do i cover dragapult's weaknesses", "how do I play hyper offense", "when should i be aggressive",
                  "how do i make my kingambit better"]:
            chips = suggestions(q, plan_query(q, team), team)
            self.assertTrue(chips, q)
            for c in chips:
                self.assertNotIn(plan_query(c, team).intent, ("open", "clarify"), c)
            self.assertEqual(split("Answer." + marker(chips)), ("Answer.", chips))
        for _, _, _, _, questions in help_cards(team):
            for q in questions:
                self.assertNotIn(plan_query(q, team).intent, ("open", "clarify"), q)


SAND = """Tyranitar @ Smooth Rock
Ability: Sand Stream
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Stealth Rock
- Knock Off
- Stone Edge
- Ice Beam

Excadrill @ Air Balloon
Ability: Sand Rush
EVs: 252 Atk / 4 SpD / 252 Spe
Adamant Nature
- Earthquake
- Iron Head
- Rock Slide
- Rapid Spin"""


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestOwnWeatherSpeed(unittest.TestCase):
    def test_sand_rush_speed_is_given_when_the_team_sets_sand(self):
        from metamatch.engine.solvers import own_field
        team, _ = readTeam(SAND, "gen9ou")
        self.assertEqual(own_field(team, "Excadrill")[:2], ("Tyranitar", "sand"))
        v = solve(plan_query("Does my Excadrill outspeed Iron Valiant?", team))
        self.assertIn("With your Tyranitar's sand up, your Excadrill has", v.plain)
        # A stated weather is the question's own condition, so no second number is added
        v = solve(plan_query("Does my Excadrill outspeed Iron Valiant in rain?", team))
        self.assertNotIn("sand up", v.plain)
        tiers = solve(plan_query("Walk me through my speed tiers", team))
        self.assertEqual(tiers.answer, "Excadrill")


class TestTeamWeather(unittest.TestCase):
    def test_using_weather_is_about_the_team_and_facing_it_is_an_archetype(self):
        team, _ = readTeam(TEAM, "gen9ou")
        plan = plan_query("how to use weather team", team)
        self.assertEqual((plan.intent, plan.archetype), ("weather", None))
        self.assertEqual(plan_query("how do i build a rain team", team).archetype, "rain")
        self.assertNotEqual(plan_query("how do I play against rain", team).intent, "weather")
        v = solve(plan)
        self.assertEqual(v.answer, "no")
        self.assertIn("runs no weather", v.statement)


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
