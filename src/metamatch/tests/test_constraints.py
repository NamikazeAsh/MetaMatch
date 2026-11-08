"""
Stated constraints (engine/constraints.py): set details and field conditions the question gives must
reach the solvers, credited to the right side, and nothing the question doesn't say may appear.
"""
import unittest

from metamatch.engine import calc
from metamatch.engine.planner import plan_query
from metamatch.engine.solvers import solve
from metamatch.team import readTeam

TEAM = """Great Tusk @ Booster Energy
Ability: Protosynthesis
Tera Type: Steel
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Headlong Rush
- Ice Spinner
- Knock Off
- Rapid Spin

Rillaboom @ Choice Scarf
Ability: Grassy Surge
EVs: 252 Atk / 4 SpD / 252 Spe
Adamant Nature
- Wood Hammer
- Grassy Glide
- U-turn
- Knock Off

Corviknight @ Leftovers
Ability: Pressure
Tera Type: Dragon
EVs: 252 HP / 168 Def / 88 SpD
Impish Nature
- Brave Bird
- U-turn
- Roost
- Defog"""


class TestExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM, "gen9ou")

    def plan(self, q):
        return plan_query(q, self.team)

    def test_conditional_spread_goes_to_the_opponent(self):
        p = self.plan("Is my Rillaboom faster than Iron Bundle if Iron Bundle is Timid with 252 Spe and no speed item?")
        self.assertEqual(p.opp_overrides.get("nature"), "Timid")
        self.assertEqual(p.opp_overrides.get("evs"), {"spe": 252})
        self.assertTrue(p.opp_overrides.get("no_speed_item"))
        self.assertEqual(p.user_overrides, {})
        self.assertFalse(p.raw_stats)

    def test_global_item_ignore_is_raw(self):
        self.assertTrue(self.plan("Ignoring items, is Great Tusk faster than Kingambit?").raw_stats)

    def test_full_set_in_brackets(self):
        p = self.plan("Does a Kingambit @ Black Glasses (Ability: Supreme Overlord, Adamant nature, 252 HP / 252 Atk, "
                      "moves: Kowtow Cleave, Sucker Punch, Iron Head, Swords Dance) OHKO my Corviknight? "
                      "Assume it uses its strongest listed move.")
        o = p.opp_overrides
        self.assertEqual((o["item"], o["ability"], o["nature"]), ("Black Glasses", "Supreme Overlord", "Adamant"))
        self.assertEqual(o["moves"], ["Kowtow Cleave", "Sucker Punch", "Iron Head", "Swords Dance"])
        self.assertIsNone(p.move)       # listed moves are not the asked move
        self.assertTrue(p.strongest)
        self.assertEqual((p.intent, p.attacker), ("ko", "opponent"))

    def test_casual_items_and_negations(self):
        p = self.plan("can my tusk tank a modest specs gholdengo shadow ball? no booster")
        self.assertEqual((p.intent, p.survive), ("ko", True))
        self.assertEqual((p.opp_overrides.get("item"), p.opp_overrides.get("nature")), ("Choice Specs", "Modest"))
        self.assertEqual(p.user_overrides.get("item"), "")

    def test_details_glued_to_my_mon_stay_mine(self):
        p = self.plan("Does my Adamant 252 Atk Rillaboom outspeed Gholdengo?")
        self.assertEqual(p.user_overrides.get("nature"), "Adamant")
        self.assertEqual(p.opp_overrides, {})

    def test_tera_screens_weather(self):
        p = self.plan("If my Corviknight Terastallizes into Fire, is it weak to Ground attacks?")
        self.assertEqual(p.user_overrides.get("tera"), "Fire")
        p = self.plan("Behind Reflect on my side, does Kingambit's Kowtow Cleave OHKO my Great Tusk?")
        self.assertEqual(p.screens, {"user": {"isReflect"}})
        self.assertEqual(p.move, "Kowtow Cleave")
        p = self.plan("In rain, does Great Tusk outspeed Barraskewda?")
        self.assertEqual(p.conditions, {"weather": "Rain"})

    def test_english_words_are_not_natures(self):
        p = self.plan("Be careful: does Corviknight's Brave Bird OHKO a bold Meowscarada?")
        self.assertNotIn("nature", p.opp_overrides)
        self.assertEqual(p.move, "Brave Bird")

    def test_stat_boost_wording_is_not_a_stat_question(self):
        self.assertEqual(self.plan("With no stat boosts, does Great Tusk OHKO Kingambit with Headlong Rush?").intent, "ko")

    def test_same_species_on_both_sides(self):
        p = self.plan("Does my Great Tusk's Headlong Rush OHKO an opposing Great Tusk?")
        self.assertEqual((p.intent, p.opponent, p.user["Pokemon"]), ("ko", "Great Tusk", "Great Tusk"))

    def test_stat_of_a_pokemon_off_the_team(self):
        p = self.plan("what's the speed stat of a max speed timid dragapult")
        self.assertEqual((p.intent, p.stat_target, p.opp_overrides.get("max")), ("stat", "opponent", ["spe"]))

    def test_conditions_count_only_where_they_matter(self):
        # Tailwind changes a speed answer, a burn doesn't, so the burn is reported as not counted
        p = self.plan("Under Tailwind, does my burned Great Tusk outspeed Dragapult?")
        self.assertEqual((p.counted, p.unhandled), (["Tailwind"], ["burned"]))
        self.assertEqual(self.plan("is my rillaboom faster than dragapult with sticky web up").unhandled, ["sticky web"])

    def test_conditions_go_to_the_right_side(self):
        sides = lambda q: [(c.kind, c.side) for c in self.plan(q).situation]
        self.assertEqual(sides("if Dragapult has tailwind does it outspeed my Rillaboom"), [("tailwind", "opponent")])
        self.assertEqual(sides("Does my Great Tusk outspeed a paralyzed Dragapult?"), [("status", "opponent")])
        self.assertEqual(sides("Does my Great Tusk OHKO Kingambit at 50% HP?"), [("hp", "opponent")])
        self.assertEqual(sides("Can my Corviknight Brave Bird OHKO Rillaboom with a crit?"), [("crit", None)])
        # Negated assumptions are what the engine already does
        self.assertEqual(self.plan("Assume no crits and no hazards: does Great Tusk OHKO Kingambit?").unhandled, [])

    def test_regional_letter_names(self):
        from metamatch.engine.names import find_pokemon
        self.assertEqual(find_pokemon("is h-arcanine faster than g-slowking"), ["Arcanine-Hisui", "Slowking-Galar"])


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestStatedAnswers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM, "gen9ou")

    def solve(self, q):
        return solve(plan_query(q, self.team))

    def test_stated_spread_and_own_scarf(self):
        # Adamant 252 Spe Rillaboom is 269, 403 with its Scarf: below a stated Timid 252 Bundle (408), above Modest (371)
        v = self.solve("Does my Rillaboom outspeed Iron Bundle if it runs Timid with 252 Spe and no speed item?")
        self.assertIn("stated spread", v.statement)
        self.assertEqual(v.answer, "no")
        v = self.solve("Does my Rillaboom outspeed Iron Bundle if it runs Modest with 252 Spe and no speed item?")
        self.assertEqual(v.answer, "yes")

    def test_tera_changes_the_type_answer(self):
        self.assertEqual(self.solve("If my Corviknight Terastallizes into Fire, is it weak to Ground attacks?").answer, "weak")
        self.assertEqual(self.solve("Is my Corviknight weak to Ground attacks?").answer, "immune")

    def test_status_moves_never_count_as_strongest(self):
        v = self.solve("Does a Gholdengo @ Choice Specs (Modest nature, 252 HP / 252 SpA, moves: Make It Rain, "
                       "Shadow Ball, Nasty Plot, Recover) OHKO my Great Tusk? Assume its strongest listed move.")
        self.assertNotIn("Nasty Plot", v.statement)
        self.assertNotIn("Recover", v.statement)

    def test_reflect_cuts_damage(self):
        plain = self.solve("How much damage does Kingambit's Kowtow Cleave do to my Great Tusk?")
        screened = self.solve("Behind Reflect on my side, how much damage does Kingambit's Kowtow Cleave do to my Great Tusk?")
        self.assertLess(float(screened.answer.split("-")[1].rstrip("%")), float(plain.answer.split("-")[1].rstrip("%")))

    def test_stat_off_the_team(self):
        v = self.solve("what's the speed stat of a max speed timid dragapult")
        self.assertEqual(v.answer, "421")


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestCountedConditions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM, "gen9ou")

    def solve(self, q):
        return solve(plan_query(q, self.team))

    def test_tailwind_and_trick_room_change_who_moves_first(self):
        v = self.solve("Under Tailwind, does my Corviknight outspeed Dragapult?")
        self.assertIn("340 Speed", v.statement)            # 170 doubled; still below Dragapult's 421
        self.assertNotIn("Leftovers", v.statement)
        self.assertEqual(v.answer, "no")
        v = self.solve("Under Trick Room does my Corviknight outspeed Kingambit?")
        self.assertEqual(v.answer, "no")                  # 170 Speed is the faster one, so it moves second
        self.assertIn("Trick Room", v.statement)

    def test_hp_crits_and_hazards_reach_the_calc(self):
        plain = self.solve("How much does my Corviknight's Brave Bird do to Rillaboom?")
        crit = self.solve("How much does my Corviknight's Brave Bird do to Rillaboom on a crit?")
        self.assertGreater(float(crit.answer.split("-")[0]), float(plain.answer.split("-")[0]) * 1.4)
        v = self.solve("Does my Great Tusk's Headlong Rush OHKO Kingambit at 50% HP? Assume no boosts.")
        self.assertEqual(v.answer, "yes")                 # 83-98% of max HP is more than the 50% it has left
        # Stealth Rock breaks Focus Sash, so the Sash no longer saves Glimmora
        self.assertEqual(self.solve("Can a Focus Sash Glimmora survive my Great Tusk's Headlong Rush after Stealth Rock?").answer, "no")

    def test_booster_energy_is_active_unless_told_otherwise(self):
        on = self.solve("Does my Great Tusk's Headlong Rush OHKO Kingambit?")
        off = self.solve("Does my Great Tusk's Headlong Rush OHKO Kingambit? Assume no boosts.")
        self.assertEqual((on.answer, off.answer), ("yes", "no"))


if __name__ == "__main__":
    unittest.main()
