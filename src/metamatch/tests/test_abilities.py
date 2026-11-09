"""Ability lines (engine/abilities.py): measured where the calc can, rules from Showdown's text otherwise."""
import unittest

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


def team(*sets, fmt="gen9ou"):
    t, _ = readTeam("\n\n".join(sets), fmt)
    detectRole(t)
    return t


class TestAbilityRules(unittest.TestCase):
    def test_entry_abilities_are_lead_jobs(self):
        from metamatch.engine.abilities import ability_lines
        lando = "Landorus-Therian @ Rocky Helmet\nAbility: Intimidate\nEVs: 252 HP / 240 Def / 16 Spe\nImpish Nature\n" \
                "- Stealth Rock\n- Earthquake\n- U-turn\n- Taunt"
        line = ability_lines(team(lando), "gen9ou")["Landorus-Therian"]
        self.assertTrue(line.lead and not line.measured)
        self.assertIn("Intimidate", line.text)

    def test_prankster_names_dark_immunity_only_for_moves_aimed_at_the_foe(self):
        from metamatch.engine.abilities import ability_lines
        snarl = "Grimmsnarl @ Light Clay\nAbility: Prankster\nEVs: 252 HP / 252 SpD\nCareful Nature\n" \
                "- Reflect\n- Light Screen\n- Spirit Break\n- {last}"
        screens = ability_lines(team(snarl.format(last="Parting Shot")), "gen9ou")["Grimmsnarl"].text
        self.assertIn("Parting Shot fails on Dark types", screens)
        only_screens = ability_lines(team(snarl.format(last="Foul Play")), "gen9ou")["Grimmsnarl"].text
        self.assertNotIn("Dark", only_screens)


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestMeasuredAbilities(unittest.TestCase):
    def test_situations_and_always_on_boosts_are_measured(self):
        from metamatch.engine.abilities import ability_lines
        lines = ability_lines(team(KINGAMBIT, URSALUNA.format(item="Flame Orb"), AZUMARILL), "gen9ou")
        self.assertTrue(lines["Kingambit"].text.startswith("With 3 teammates down, Supreme Overlord lets"))
        self.assertTrue(lines["Ursaluna"].text.startswith("Once Flame Orb burns it, Guts lets"))
        self.assertIn("without it", lines["Azumarill"].text)
        self.assertTrue(all(l.measured and l.gain > 0 for l in lines.values()))

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
