import unittest
from unittest.mock import patch

from metamatch.engine import calc
from metamatch.engine.dex import get_dex, to_id
from metamatch.engine.sets import likely_set, speed_distribution
from metamatch.logic_engine import analyze_matchup
from metamatch.team import readTeam

CHAOS = {"Kingambit": {
    "usage": 0.34,
    "Abilities": {"supremeoverlord": 90.0, "defiant": 10.0},
    "Spreads": {"Adamant:248/252/8/0/0/0": 60.0, "Jolly:0/252/0/0/4/252": 40.0},
    "Items": {"leftovers": 70.0, "blackglasses": 30.0},
    "Moves": {"suckerpunch": 99.0, "swordsdance": 95.0, "ironhead": 90.0, "lowkick": 60.0, "kowtowcleave": 50.0},
    "Tera Types": {"bug": 40.0, "nothing": 0.0},
}}


class TestDex(unittest.TestCase):
    def test_lookup_is_name_insensitive(self):
        dex = get_dex("sv")
        self.assertEqual(dex.species("landorus therian")["name"], "Landorus-Therian")
        self.assertEqual(dex.move_name("ceaselessedge"), "Ceaseless Edge")
        self.assertEqual(dex.item_name("heavydutyboots"), "Heavy-Duty Boots")
        self.assertEqual(to_id("Mr. Mime"), "mrmime")

    def test_mega_forme_from_stone(self):
        dex = get_dex("champions")
        self.assertEqual(dex.mega_forme("Garchomp", "Garchompite Z"), "Garchomp-Mega-Z")
        self.assertIsNone(dex.mega_forme("Garchomp", "Life Orb"))
        # A stone only works on its own species
        self.assertIsNone(dex.mega_forme("Dragonite", "Garchompite Z"))

    def test_champions_status_moves_have_category(self):
        self.assertEqual(get_dex("champions").move("Stealth Rock")["category"], "Status")


class TestLikelySet(unittest.TestCase):
    def setUp(self):
        patcher = patch("metamatch.engine.sets.load_chaos_data", return_value=CHAOS)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_picks_most_common_fields_with_display_names(self):
        s = likely_set("kingambit", "gen9ou")
        self.assertEqual((s["nature"], s["evs"]["hp"], s["evs"]["atk"]), ("Adamant", 248, 252))
        self.assertAlmostEqual(s["spread_share"], 0.6)
        self.assertEqual(s["item"], "Leftovers")
        self.assertEqual(s["ability"], "Supreme Overlord")
        self.assertEqual([m for m, _ in s["moves"]], ["Sucker Punch", "Swords Dance", "Iron Head", "Low Kick"])
        self.assertEqual(s["tera"][0], "Bug")

    def test_known_info_overrides_prior(self):
        s = likely_set("Kingambit", "gen9ou", known={"item": "Black Glasses", "moves": ["Kowtow Cleave"]})
        self.assertEqual(s["item"], "Black Glasses")
        self.assertEqual(s["moves"][0], ("Kowtow Cleave", 1.0))
        self.assertEqual(len(s["moves"]), 4)

    def test_speed_distribution(self):
        # Base 50: Adamant 0 Spe = 136, Jolly 252 Spe = 218
        self.assertEqual(speed_distribution("Kingambit", "gen9ou"), [(136, 0.6), (218, 0.4)])

    def test_unknown_pokemon(self):
        self.assertIsNone(likely_set("Pikachu", "gen9ou"))


class TestTeamFormes(unittest.TestCase):
    @patch("metamatch.team.get_move_metadata", return_value={"category": "Status", "type": "Normal"})
    def test_mega_stone_uses_mega_forme(self, _):
        team, _ = readTeam("Garchomp @ Garchompite Z\nAbility: Rough Skin\nEVs: 2 HP / 32 SpA / 32 Spe\nTimid Nature\n- Draco Meteor",
                           "gen9championsou")
        p = team[0]
        self.assertEqual(p["Pokemon"], "Garchomp")
        self.assertEqual(p["Forme"], "Garchomp-Mega-Z")
        self.assertEqual(p["Type"], ["Dragon"])
        self.assertEqual(p["Mega Ability"], "Levitate")
        self.assertEqual(p["Damage From"]["ground"], 0.0)
        # floor((151 + 32 + 20) * 1.1)
        self.assertEqual(p["Speed"], 223)
        self.assertEqual(p["Moves"][0]["category"], "Special")


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestCalc(unittest.TestCase):
    def test_known_calc(self):
        r = calc.calculate({
            "game": "sv",
            "attacker": {"name": "Great Tusk", "nature": "Jolly", "evs": {"atk": 252, "spe": 252}},
            "defender": {"name": "Dragapult", "nature": "Timid", "evs": {"spa": 252, "spe": 252}},
            "move": "Ice Spinner",
        })
        self.assertEqual(r["range"], [224, 264])
        self.assertEqual(r["ko"], "guaranteed 2HKO")

    def test_champions_level_50_stat_points(self):
        r = calc.calculate({
            "game": "champions",
            "attacker": {"name": "Garchomp-Mega-Z", "nature": "Timid", "evs": {"spa": 32, "spe": 32, "hp": 2}},
            "defender": {"name": "Kingambit", "nature": "Adamant", "evs": {"hp": 32, "atk": 32, "def": 2}},
            "move": "Earth Power",
        })
        self.assertEqual(r["attacker_stats"]["spe"], 223)
        self.assertGreater(r["percent"][0], 0)

    def test_bad_request_returns_none_and_server_survives(self):
        self.assertEqual(calc.calculate_many([
            {"game": "sv", "attacker": {"name": "Notamon"}, "defender": {"name": "Kingambit"}, "move": "Tackle"},
            {"game": "sv", "attacker": {"name": "Kingambit"}, "defender": {"name": "Kingambit"}, "move": "Notamove"},
        ]), [None, None])
        self.assertIsNotNone(calc.calculate(
            {"game": "sv", "attacker": {"name": "Kingambit"}, "defender": {"name": "Gholdengo"}, "move": "Sucker Punch"}))

    def test_matchup_reports_real_damage(self):
        user = {"Pokemon": "Great Tusk", "Format": "gen9ou", "Type": ["Ground", "Fighting"], "Speed": 300,
                "Ability": "Protosynthesis", "Item": "", "Nature": "Jolly", "EVs": {"Atk": 252, "Spe": 252},
                "Moves": [{"name": "Headlong Rush", "type": "Ground", "category": "Physical"}]}
        with patch("metamatch.engine.sets.load_chaos_data", return_value=CHAOS):
            facts = analyze_matchup(user, "Kingambit", likely_set("Kingambit", "gen9ou"))
        self.assertIn("outspeeds 100% of Kingambit sets", facts[0])
        self.assertTrue(any(f.startswith("DAMAGE DEALT: Headlong Rush does") for f in facts))
        self.assertTrue(any(f.startswith("DAMAGE TAKEN: Kingambit's") for f in facts))


if __name__ == "__main__":
    unittest.main()
