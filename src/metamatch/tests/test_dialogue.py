"""Chat follow ups, planner misreads and Brock's fact check (no LLM needed)."""
import unittest

from metamatch.agents import client
from metamatch.agents.auditor import verify as brock_verify
from metamatch.agents.manager import AgentManager, BUILDER_RE, STRATEGY_RE
from metamatch.engine import calc, dialogue
from metamatch.engine.names import find_pokemon
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


def _team():
    team, _ = readTeam(TEAM, "gen9ou")
    return team


def _ask(conversation, team):
    """Resolves each message in turn, the way the chat tab does; returns the readings."""
    state, out = None, []
    for q in conversation:
        reading = dialogue.resolve(q, state, team)
        plan = plan_query(reading.text, team)
        state = dialogue.update(state, reading, plan, clarified=plan.intent == "clarify")
        out.append(reading)
    return out


class TestFollowUps(unittest.TestCase):
    def setUp(self):
        self.team = _team()

    def test_swap_opponent(self):
        r = _ask(["Does my Dragapult outspeed Iron Valiant?", "what about Roaring Moon?"], self.team)[-1]
        self.assertEqual(r.kind, "swap")
        self.assertEqual(r.text, "Does my Dragapult outspeed Roaring Moon?")

    def test_swap_member(self):
        r = _ask(["Does my Dragapult outspeed Iron Valiant?", "and gholdengo?"], self.team)[-1]
        self.assertEqual(r.text, "Does my Gholdengo outspeed Iron Valiant?")

    def test_swap_own_species_is_opposing(self):
        r = _ask(["How do I beat Raging Bolt?", "what about Kingambit"], self.team)[-1]
        self.assertEqual(r.text, "How do I beat opposing Kingambit?")
        self.assertEqual(plan_query(r.text, self.team).opponents, ["Kingambit"])

    def test_variant_puts_detail_on_opponent(self):
        r = _ask(["Does my Dragapult outspeed Iron Valiant?", "what if it's the scarf set?"], self.team)[-1]
        self.assertEqual(r.kind, "variant")
        self.assertEqual(r.text, "Does my Dragapult outspeed scarf Iron Valiant?")
        self.assertEqual(plan_query(r.text, self.team).opp_overrides.get("item"), "Choice Scarf")

    def test_variant_field_goes_last(self):
        r = _ask(["Does my Kingambit survive Great Tusk's Headlong Rush?", "what if it's in sand"], self.team)[-1]
        self.assertEqual(r.text, "Does my Kingambit survive Great Tusk's Headlong Rush in sand?")

    def test_pronoun_is_last_opponent(self):
        r = _ask(["What is the most common item on Iron Valiant?", "does it outspeed my Dragapult?"], self.team)[-1]
        self.assertEqual(r.text, "does Iron Valiant outspeed my Dragapult?")

    def test_expletive_it_left_alone(self):
        r = _ask(["What is the most common item on Iron Valiant?", "is it worth running Tera Steel on Gholdengo?"],
                 self.team)[-1]
        self.assertEqual(r.kind, "new")

    def test_clarify_reply(self):
        readings = _ask(["Does my Gholdengo outspeed it?", "Iron Valiant"], self.team)
        self.assertEqual(readings[-1].text, "Does my Gholdengo outspeed Iron Valiant?")

    def test_why_reuses_verdict(self):
        state = dialogue.DialogueState(query="Does my Dragapult outspeed Iron Valiant?", verdict="V")
        r = dialogue.resolve("why?", state, self.team)
        self.assertEqual((r.kind, r.why_of), ("why", "V"))

    def test_new_question_untouched(self):
        r = _ask(["Does my Dragapult outspeed Iron Valiant?", "How do I beat stall?"], self.team)[-1]
        self.assertEqual(r.text, "How do I beat stall?")

    def test_setup_goes_last_and_drops_on_member_swap(self):
        readings = _ask(["Does my Kingambit OHKO Great Tusk?", "what about after a swords dance?", "and dragapult?"],
                        self.team)
        self.assertEqual(readings[1].text, "Does my Kingambit OHKO Great Tusk after a swords dance?")
        self.assertEqual(readings[2].text, "Does my Dragapult OHKO Great Tusk?")

    def test_tera_detail_lands_on_opponent(self):
        r = _ask(["who checks dragonite on my team", "what if it teras normal and uses extreme speed"], self.team)[-1]
        plan = plan_query(r.text, self.team)
        self.assertEqual((plan.opp_overrides.get("tera"), plan.user_overrides.get("tera")), ("Normal", None))

    def test_why_not_option(self):
        r = _ask(["what item should my kingambit use", "why not black glasses?"], self.team)[-1]
        self.assertEqual(r.text, "Is Black Glasses common on Kingambit?")

    def test_replace_carries_member(self):
        r = _ask(["Is my Gholdengo set good?", "ok what should I replace then"], self.team)[-1]
        self.assertIn("my Gholdengo", r.text)


class TestPlannerReads(unittest.TestCase):
    def setUp(self):
        self.team = _team()

    def test_beat_own_species_is_opponent(self):
        plan = plan_query("How do I beat Kingambit?", self.team)
        self.assertEqual(plan.opponents, ["Kingambit"])
        self.assertIsNone(plan.user)

    def test_teammates_is_not_an_item(self):
        plan = plan_query("What are the most common teammates of Kingambit?", self.team)
        self.assertEqual((plan.intent, plan.usage_field), ("usage", "teammates"))
        v = solve(plan)
        self.assertIn("teammate", v.statement)

    def test_named_option_share(self):
        plan = plan_query("Is Sucker Punch common on Kingambit?", self.team)
        self.assertEqual((plan.intent, plan.usage_field, plan.usage_option), ("usage", "move", "Sucker Punch"))
        self.assertIn("Sucker Punch is on", solve(plan).statement)

    def test_spread_to_survive_is_not_a_yes_no(self):
        plan = plan_query("What spread lets Gholdengo survive Great Tusk's Headlong Rush?", self.team)
        self.assertEqual(plan.intent, "open")

    @unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
    def test_evs_to_outspeed(self):
        plan = plan_query("What EVs does my Kingambit need to outspeed Great Tusk?", self.team)
        self.assertEqual(plan.intent, "speed_spread")
        v = solve(plan)
        self.assertEqual(v.persona, "builder")
        self.assertIn("Great Tusk", v.statement)

    def test_team_strategy_intents(self):
        cases = {"What is my win condition?": "win", "what should i lead": "lead", "what are my biggest threats": "threats",
                 "what's my game plan": "gameplan", "is my team good": "gameplan", "How do I beat stall?": "open",
                 "What should I lead against rain?": "open"}
        for q, intent in cases.items():
            self.assertEqual(plan_query(q, self.team).intent, intent, q)

    def test_usual_set_is_the_whole_set(self):
        for q in ["What does Great Tusk usually run?", "kingambit sets?"]:
            plan = plan_query(q, self.team)
            self.assertEqual((plan.intent, plan.usage_field), ("usage", "set"), q)
            self.assertIn(" with ", solve(plan).statement)

    def test_one_member_matchup(self):
        plan = plan_query("Does my Kingambit beat Gholdengo?", self.team)
        self.assertEqual(plan.intent, "matchup")

    def test_tera_plan(self):
        self.assertEqual(plan_query("who should i tera", self.team).intent, "tera")

    def test_complaint_about_own_species_is_opponent(self):
        plan = plan_query("gambit keeps sweeping me", self.team)
        self.assertEqual((plan.intent, plan.opponents, plan.asks_how), ("checks", ["Kingambit"], True))

    @unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
    def test_team_answers_are_verdicts(self):
        for q in ["What is my win condition?", "what should i lead", "what's my game plan"]:
            v = solve(plan_query(q, self.team))
            self.assertIsNotNone(v, q)
            self.assertEqual(v.persona, "strategy")

    @unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
    def test_checks_use_stated_set(self):
        plan = plan_query("how do I beat a Choice Scarf Iron Valiant?", self.team)
        self.assertEqual(plan.opp_overrides.get("item"), "Choice Scarf")
        self.assertIn("details the question states", " ".join(solve(plan).facts))

    def test_complaints_are_beat_questions(self):
        for q in ["zamazenta is destroying me", "how to deal w lando", "ogerpon wellspring counters?",
                  "gliscor walls my whole team", "best way to handle pult", "who on my team switches into tusk"]:
            self.assertEqual(plan_query(q, self.team).intent, "checks", q)

    def test_archetype_advice_is_not_a_rules_lookup(self):
        self.assertEqual(plan_query("what do i do against sun teams", self.team).intent, "open")
        self.assertEqual(plan_query("what does sun do", self.team).intent, "rules")

    def test_typo_with_short_first_word(self):
        self.assertEqual(find_pokemon("how do i beat iron valient"), ["Iron Valiant"])
        self.assertEqual(find_pokemon("does iron head hit hard"), [])


class TestRouting(unittest.TestCase):
    def test_builder_words(self):
        for q in ["Is Life Orb the best item on Venusaur?", "What should I replace Alomomola with?",
                  "Specs or Life Orb on Dragapult?", "What spread lets Corviknight survive Thunderclap?"]:
            self.assertTrue(BUILDER_RE.search(q) and not STRATEGY_RE.search(q), q)

    def test_strategy_stays(self):
        for q in ["How do I beat stall?", "What should I lead with?", "How do I use Kingambit against rain?"]:
            self.assertTrue(STRATEGY_RE.search(q), q)

    def test_prepare_routes_items_to_brock(self):
        turn = AgentManager().prepare("Should my Dragapult run Choice Specs instead?", _team())
        self.assertEqual(turn.route, "builder")

    def test_set_up_is_not_a_set_question(self):
        self.assertFalse(BUILDER_RE.search("how do i set up with dragonite safely"))

    def test_small_talk(self):
        turn = AgentManager().prepare("thanks!", _team())
        self.assertEqual(turn.route, "smalltalk")
        self.assertNotIn("Kingambit", "".join(AgentManager().respond(turn, _team())))


class TestRetrievalQuery(unittest.TestCase):
    def test_canonical_names(self):
        from metamatch.rag.store import canonical
        self.assertEqual(canonical("gambit keeps sweeping me"), "Kingambit keeps sweeping me")
        self.assertEqual(canonical("how do i beat iron valient"), "how do i beat Iron Valiant")

    def test_no_retrieval_for_small_talk_and_engine_questions(self):
        from metamatch.agents.coach import NO_RETRIEVAL
        for q in ["thanks!", "what is my team weak to", "rate my team", "is my team good?"]:
            self.assertTrue(NO_RETRIEVAL.search(q), q)
        self.assertFalse(NO_RETRIEVAL.search("is my team good against stall"))


class TestBrockCheck(unittest.TestCase):
    FACTS = ["Your Dragapult (Dragon/Ghost) runs Heavy-Duty Boots, Infiltrator, Tera Ghost, moves Draco Meteor, U-turn.",
             "Ladder sets of Dragapult (yours is above), items: Choice Specs 50%, Heavy-Duty Boots 24%."]

    def test_grounded_answer_passes(self):
        self.assertIsNone(brock_verify("Half of ladder Dragapult run Choice Specs (50%), so it is a fine pick.", self.FACTS))

    def test_invented_item_rejected(self):
        self.assertIn("Life Orb", brock_verify("Life Orb would hit harder than Choice Specs.", self.FACTS))

    def test_invented_number_rejected(self):
        self.assertIn("62", brock_verify("About 62% of players run Choice Specs.", self.FACTS))

    def test_invented_pokemon_rejected(self):
        self.assertIn("Gyarados", brock_verify("Gyarados would pair well with Dragapult.", self.FACTS))


class TestBoosterSpeed(unittest.TestCase):
    def test_booster_lands_on_speed_only_when_speed_is_best(self):
        from metamatch.engine.sets import speed_is_best_stat
        valiant = {"atk": 130, "def": 90, "spa": 120, "spd": 60, "spe": 116}
        self.assertTrue(speed_is_best_stat(valiant, "Timid", {"spa": 252, "spd": 4, "spe": 252}, "sv"))
        moon = {"atk": 139, "def": 71, "spa": 55, "spd": 101, "spe": 119}
        self.assertFalse(speed_is_best_stat(moon, "Jolly", {"atk": 252, "spd": 4, "spe": 252}, "sv"))

    def test_share_mixes_booster_like_scarf(self):
        from metamatch.engine.mechanics import scarf_adjusted_share
        self.assertAlmostEqual(scarf_adjusted_share(400, [(364, 1.0)], 0.0, 0.7), 0.3)


class TestContextFit(unittest.TestCase):
    def test_drops_oldest_turns_only(self):
        msgs = [{"role": "system", "content": "s"}] + [{"role": "user", "content": "x" * 3000} for _ in range(6)] + \
               [{"role": "user", "content": "question"}]
        fitted = client.fit(msgs, max_tokens=300, num_ctx=4096)
        self.assertEqual(fitted[0]["content"], "s")
        self.assertEqual(fitted[-1]["content"], "question")
        self.assertLessEqual(client.estimate_tokens(fitted) + 300, 4096)


if __name__ == "__main__":
    unittest.main()
