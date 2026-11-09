"""Ability lines (engine/abilities.py): measured by switching the ability off, triggers told to the calc, rules
from Showdown's text otherwise."""
import sys
import unittest
from pathlib import Path

from metamatch.engine import calc
from metamatch.team import readTeam, detectRole

KINGAMBIT = """Kingambit @ Leftovers
Ability: Supreme Overlord
EVs: 112 HP / 252 Atk / 144 Spe
Adamant Nature
- Swords Dance
- Kowtow Cleave
- Sucker Punch
- Iron Head"""
URSALUNA = """Ursaluna @ {item}
Ability: Guts
EVs: 252 HP / 252 Atk / 4 SpD
Brave Nature
- Facade
- Headlong Rush
- Fire Punch
- Protect"""
AZUMARILL = """Azumarill @ Choice Band
Ability: Huge Power
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Liquidation
- Play Rough
- Aqua Jet
- Knock Off"""
DRAGONITE = """Dragonite @ Heavy-Duty Boots
Ability: Multiscale
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Dragon Dance
- Extreme Speed
- Earthquake
- Roost"""
VALIANT = """Iron Valiant @ Booster Energy
Ability: Quark Drive
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Shadow Ball
- Psyshock
- Calm Mind"""
HEATRAN = """Heatran @ Leftovers
Ability: Flash Fire
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Magma Storm
- Earth Power
- Stealth Rock
- Protect"""
SHOWDOWN_TS = '''export const AbilitiesText = {
\tmultiscale: {
\t\tname: "Multiscale",
\t\tshortDesc: "If this Pokemon is at full HP, damage taken from attacks is halved.",
\t\tgen4: {
\t\t\tshortDesc: "Old text.",
\t\t},
\t},
};
'''


def team(*sets, fmt="gen9ou"):
    t, _ = readTeam("\n\n".join(sets), fmt)
    detectRole(t)
    return t


class TestAbilityText(unittest.TestCase):
    def test_showdown_text_keeps_the_current_generation_line(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
        from build_ability_text import parse
        self.assertEqual(parse(SHOWDOWN_TS),
                         {"Multiscale": "If this Pokemon is at full HP, damage taken from attacks is halved."})


class TestAbilityRules(unittest.TestCase):
    def test_entry_abilities_are_lead_jobs(self):
        from metamatch.engine.abilities import ability_lines
        lando = "\n".join(["Landorus-Therian @ Rocky Helmet", "Ability: Intimidate", "EVs: 252 HP / 240 Def / 16 Spe",
                           "Impish Nature", "- Stealth Rock", "- Earthquake", "- U-turn", "- Taunt"])
        line = ability_lines(team(lando), "gen9ou")["Landorus-Therian"]
        self.assertTrue(line.lead and not line.measured)
        self.assertIn("Intimidate", line.text)

    def test_prankster_names_dark_immunity_only_for_moves_aimed_at_the_foe(self):
        from metamatch.engine.abilities import ability_lines
        snarl = "\n".join(["Grimmsnarl @ Light Clay", "Ability: Prankster", "EVs: 252 HP / 252 SpD", "Careful Nature",
                           "- Reflect", "- Light Screen", "- Spirit Break", "- {last}"])
        aimed = ability_lines(team(snarl.format(last="Parting Shot")), "gen9ou")["Grimmsnarl"].text
        self.assertIn("Parting Shot fails on Dark types", aimed)
        screens = ability_lines(team(snarl.format(last="Foul Play")), "gen9ou")["Grimmsnarl"].text
        self.assertNotIn("Dark", screens)


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestMeasuredAbilities(unittest.TestCase):
    def test_situations_and_always_on_boosts_are_measured(self):
        from metamatch.engine.abilities import ability_lines
        lines = ability_lines(team(KINGAMBIT, URSALUNA.format(item="Flame Orb"), AZUMARILL), "gen9ou")
        self.assertTrue(lines["Kingambit"].text.startswith("With 3 teammates down, Supreme Overlord lets"))
        self.assertTrue(lines["Ursaluna"].text.startswith("Once Flame Orb burns it, Guts lets"))
        self.assertIn("without it", lines["Azumarill"].text)
        self.assertTrue(all(l.measured and l.gain > 0 for l in lines.values()))

    def test_switching_an_ability_off_measures_defense_and_speed(self):
        from metamatch.engine.abilities import ability_lines
        lines = ability_lines(team(DRAGONITE, VALIANT), "gen9ou")
        self.assertRegex(lines["Dragonite"].text, r"^Multiscale lets it survive any single hit from \d+ .* \d+ without it$")
        self.assertTrue(lines["Iron Valiant"].text.startswith("With Booster Energy, Quark Drive"))

    def test_an_immunity_that_never_changes_a_ko_is_stated_as_a_rule(self):
        from metamatch.engine.abilities import ability_lines
        line = ability_lines(team(HEATRAN), "gen9ou")["Heatran"]
        self.assertTrue(line.measured or line.text == "Flash Fire makes it immune to Fire moves")

    def test_guts_without_an_orb_says_nothing(self):
        from metamatch.engine.abilities import ability_lines
        self.assertEqual(ability_lines(team(URSALUNA.format(item="Leftovers")), "gen9ou"), {})

    def test_win_condition_card_carries_the_line_before_its_matchups(self):
        from metamatch.engine.guide import team_guide
        g = team_guide(team(KINGAMBIT), "gen9ou")
        self.assertEqual(g.win["name"], "Kingambit")
        at = next(i for i, pt in enumerate(g.win["points"]) if "Supreme Overlord" in pt)
        self.assertTrue(g.win["points"][at + 1].startswith("Beats "))
        self.assertIn("Supreme Overlord", g.win["text"])


if __name__ == "__main__":
    unittest.main()
