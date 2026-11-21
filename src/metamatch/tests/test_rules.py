"""Rules questions answered from Pokemon Showdown's text and flags, and the checks on voiced engine answers.
The questions are the chat agent audit's: Clemont or Oak got each of them wrong."""
import sys
import unittest
from pathlib import Path

from metamatch.agents import claims
from metamatch.agents.grounded import verify_voice
from metamatch.engine.planner import plan_query
from metamatch.engine.solvers import Verdict, solve
from metamatch.team import readTeam
from metamatch.tests.test_team_type import SALT, SUN, ask

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import build_rules_text  # noqa: E402


class TestRulesAnswers(unittest.TestCase):
    def test_flag_rules_settle_yes_or_no(self):
        for query, paste, answer in [("Does Mold Breaker ignore Levitate?", SUN, "yes"),
                                     ("Does Magic Bounce reflect Stealth Rock?", SALT, "yes"),
                                     ("Does Sharpness boost Razor Shell?", SALT, "yes"),
                                     ("Does Sharpness boost Knock Off?", SALT, "no"),
                                     ("Does Purifying Salt halve Ghost damage?", SALT, "yes"),
                                     ("Does Torkoal's sun boost Dragapult's Flamethrower damage?", SUN, "yes"),
                                     ("Does rain weaken Fire moves?", SUN, "yes"),
                                     ("Does Technician boost Bullet Punch?", SUN, "yes")]:
            plan, v = ask(query, paste)
            self.assertEqual(plan.intent, "rules", query)
            self.assertEqual(v.answer, answer, query)

    def test_rule_text_and_who_on_the_team_it_applies_to(self):
        _, v = ask("How does Multiscale work?", SALT)
        self.assertIn("damage taken from attacks is halved", v.statement)
        self.assertIn("Your Dragonite has Multiscale.", v.facts)
        _, sharp = ask("What does Sharpness boost?", SALT)
        self.assertTrue(any("boosts Ceaseless Edge and Razor Shell (slicing moves)" in f for f in sharp.facts), sharp.facts)
        _, booster = ask("What does Booster Energy do for Great Tusk?", SALT.replace("Heavy-Duty Boots", "Booster Energy"))
        self.assertTrue(any("Protosynthesis" in f for f in booster.facts), booster.facts)

    def test_weather_dependent_moves(self):
        _, v = ask("What happens to Weather Ball in sun?", SUN)
        self.assertEqual(v.statement, "In sun, Weather Ball becomes a Fire type move with 100 power.")

    def test_advice_and_usage_questions_are_not_rules(self):
        for query in ["Is Life Orb the best item on Venusaur?", "When should I Dragon Dance with Dragonite?",
                      "How do I win with this sun team?", "Is Choice Band standard on Samurott-Hisui?"]:
            self.assertNotEqual(ask(query, SUN)[0].intent, "rules", query)


class TestVoiceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(SUN, "gen9ou")
        cls.water = solve(plan_query("Which of my Pokemon resist Water?", cls.team))

    def test_wrong_group_rejected(self):
        self.assertIsNotNone(claims.group_clash("Torkoal and Venusaur resist Water.", self.water))
        self.assertIsNotNone(claims.group_clash("Alomomola is weak to Water, so keep it away.", self.water))

    def test_right_groups_accepted(self):
        for text in ["Venusaur, Dragapult and Alomomola all resist Water, while Torkoal is weak to it.",
                     "Alomomola is your best switch in, and Torkoal isn't one to resist it.",
                     "Keep Torkoal away from Water attacks; Dragapult takes them well."]:
            self.assertIsNone(claims.group_clash(text, self.water), text)

    def test_immune_counts_as_resisting(self):
        team, _ = readTeam(SALT, "gen9ou")
        v = solve(plan_query("Which of my Pokemon resist Fighting?", team))
        self.assertIsNone(claims.group_clash("Gholdengo resists Fighting completely, it's immune.", v))

    def test_yes_or_no_must_not_flip(self):
        yes = Verdict("rules", "yes", "Yes. Mold Breaker ignores Levitate, which is one of the Abilities it bypasses.")
        self.assertIsNotNone(claims.yes_no_clash("No, Mold Breaker doesn't get through Levitate.", yes))
        self.assertIsNone(claims.yes_no_clash("Yes! Mold Breaker goes right through Levitate.", yes))
        self.assertIsNone(claims.yes_no_clash("Mold Breaker ignores Levitate, so Ground moves land.", yes))
        no = Verdict("rules", "no", "No. Sharpness does not affect Knock Off, because Knock Off is not a slicing move.")
        self.assertIsNotNone(claims.yes_no_clash("Sharpness boosts Knock Off nicely.", no))
        self.assertIsNone(claims.yes_no_clash("Sharpness won't help Knock Off, since it isn't a slicing move.", no))

    def test_voice_must_say_the_result_and_add_nobody(self):
        self.assertIsNotNone(verify_voice("Venusaur, Dragapult and Alomomola resist Water, like Toxapex does.", self.water, self.team))
        self.assertIsNotNone(verify_voice("Venusaur and Dragapult resist Water.", self.water, self.team))
        self.assertIsNone(verify_voice("Venusaur, Dragapult and Alomomola resist Water, so lean on Alomomola.", self.water, self.team))


class TestVoiceTrim(unittest.TestCase):
    """Real voiced answers from the probes: the claim in the later sentence was wrong each time."""
    def test_later_sentences_only_stay_when_they_claim_nothing(self):
        from metamatch.agents.grounded import _trim_voice
        self.assertEqual(_trim_voice("Garganacl and Gholdengo are weak to Ground. Garganacl is weak to Ground because "
                                     "it's a dual Ice/Ground type."), "Garganacl and Gholdengo are weak to Ground.")
        self.assertEqual(_trim_voice("Multiscale halves the damage taken from attacks if your Dragonite is at full HP. "
                                     "It's a pretty straightforward mechanic, really."),
                         "Multiscale halves the damage taken from attacks if your Dragonite is at full HP. "
                         "It's a pretty straightforward mechanic, really.")
        self.assertEqual(_trim_voice("Yes. Mold Breaker ignores Levitate. So Ground moves hit for 100 damage."),
                         "Yes. Mold Breaker ignores Levitate.")
        self.assertEqual(_trim_voice("Corviknight is immune to Ground attacks. I think the battle engine's already "
                                     "figured out the details."), "Corviknight is immune to Ground attacks.")


class TestExampleGaps(unittest.TestCase):
    """Two gaps found while writing example answers."""
    TEAM = ("Kingambit @ Black Glasses\nAbility: Supreme Overlord\n- Swords Dance\n- Kowtow Cleave\n\n"
            "Great Tusk @ Booster Energy\nAbility: Protosynthesis\n- Headlong Rush\n- Ice Spinner")

    def test_unmarked_team_species_is_the_opponents_copy(self):
        plan, _ = ask("Does Kingambit OHKO my Great Tusk after a Swords Dance?", self.TEAM)
        self.assertEqual((plan.intent, plan.user["Pokemon"], plan.opponents), ("ko", "Great Tusk", ["Kingambit"]))
        self.assertEqual(plan.opp_overrides.get("boosts"), {"atk": 2})

    def test_zero_damage_reads_as_an_immunity(self):
        _, v = ask("How much damage does Weather Ball do to Heatran in sun?", SUN)
        self.assertEqual(v.statement, "Venusaur's Weather Ball does no damage to Heatran, whose Flash Fire makes it immune.")


class TestBuildRulesText(unittest.TestCase):
    def test_parses_text_flags_and_breakable(self):
        texts = {
            "data/text/abilities.ts": '\tlevitate: {\n\t\tname: "Levitate",\n\t\tshortDesc: "Immune to Ground.",\n\t},\n',
            "data/text/items.ts": '\tleftovers: {\n\t\tname: "Leftovers",\n\t\tshortDesc: "Heals 1/16.",\n\t},\n',
            "data/text/moves.ts": ('\trazorshell: {\n\t\tname: "Razor Shell",\n\t\tdesc: "Long text.",\n\t\tshortDesc: "Short.",\n'
                                   '\t\tgen8: {\n\t\t\tdesc: "Old text.",\n\t\t},\n\t},\n'),
            "data/moves.ts": ('\trazorshell: {\n\t\tbasePower: 75,\n\t\tname: "Razor Shell",\n\t\ttype: "Water",\n'
                              '\t\tcategory: "Physical",\n\t\tflags: { contact: 1, protect: 1, slicing: 1 },\n\t},\n'),
            "data/abilities.ts": '\tlevitate: {\n\t\tflags: { breakable: 1 },\n\t\tname: "Levitate",\n\t},\n',
        }
        data = build_rules_text.build(texts)
        self.assertTrue(data["abilities"]["Levitate"]["breakable"])
        move = data["moves"]["Razor Shell"]
        self.assertEqual((move["short"], move["desc"], move["basePower"]), ("Short.", "Long text.", 75))
        self.assertEqual(move["flags"], ["contact", "slicing"])
        self.assertEqual(data["items"]["Leftovers"]["short"], "Heals 1/16.")

    def test_reads_priority_pivots_and_hazards(self):
        # Each move needs a text entry (its name) and a data entry (its fields)
        moves = {"uturn": ("U-turn", '\t\tpriority: 0,\n\t\tselfSwitch: true,\n\t\ttarget: "normal",\n'),
                 "aquajet": ("Aqua Jet", '\t\tpriority: 1,\n\t\ttarget: "normal",\n'),
                 "spikes": ("Spikes", "\t\tsideCondition: 'spikes',\n\t\ttarget: \"foeSide\",\n"),
                 "reflect": ("Reflect", "\t\tsideCondition: 'reflect',\n\t\ttarget: \"allySide\",\n")}
        texts = {"data/text/abilities.ts": "", "data/text/items.ts": "", "data/abilities.ts": "",
                 "data/text/moves.ts": "".join(f'\t{k}: {{\n\t\tname: "{n}",\n\t\tshortDesc: "x",\n\t}},\n'
                                               for k, (n, _) in moves.items()),
                 "data/moves.ts": "".join(f'\t{k}: {{\n\t\tname: "{n}",\n{body}\t}},\n' for k, (n, body) in moves.items())}
        m = build_rules_text.build(texts)["moves"]
        self.assertTrue(m["U-turn"]["switches"])
        self.assertNotIn("priority", m["U-turn"])                  # 0 isn't stored
        self.assertEqual(m["Aqua Jet"]["priority"], 1)
        self.assertTrue(m["Spikes"]["hazard"])
        self.assertNotIn("hazard", m["Reflect"])                   # a side condition on your own side isn't a hazard


if __name__ == "__main__":
    unittest.main()
