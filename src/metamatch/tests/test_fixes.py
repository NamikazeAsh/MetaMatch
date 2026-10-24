import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from metamatch import config, recommender, suggestions
from metamatch.logic_engine import find_pokemon_in_query
from metamatch.team import coverageCheck, damageRelations, readTeam
from metamatch.utils import extract_pokemon_names, parse_header


def mock_fetch_pokemon_data(name):
    return {'types': ['Steel', 'Ghost'], 'stats': {'speed': 84}, 'sprite': '', 'abilities': []}


def move(name, mtype, category='Physical'):
    return {'name': name, 'type': mtype, 'category': category}


class TestDamageRelations(unittest.TestCase):
    def test_dual_type_stab_takes_best_type_not_product(self):
        _, attack = damageRelations(['Ground', 'Flying'])
        # Ground is 0x into Flying but Flying STAB is neutral, so Flying is not an immunity
        self.assertNotIn('flying', attack)
        self.assertEqual(attack['electric'], 2.0)
        self.assertEqual(attack['grass'], 2.0)   # Ground 0.5x, Flying 2x
        self.assertEqual(attack['steel'], 2.0)   # Ground 2x, Flying 0.5x

    def test_incoming_still_multiplies(self):
        incoming, _ = damageRelations(['Ground', 'Flying'])
        self.assertEqual(incoming['ice'], 4.0)
        self.assertEqual(incoming['electric'], 0.0)


class TestCoverage(unittest.TestCase):
    def test_coverage_means_super_effective(self):
        team = {0: {'Moves': [move('Earthquake', 'Ground'), move('Swords Dance', 'Normal', 'Status')]}}
        cov = coverageCheck(team)
        for t in ['Fire', 'Electric', 'Poison', 'Rock', 'Steel']:
            self.assertTrue(cov[t], t)
        # Owning a Ground move does not cover Ground
        self.assertFalse(cov['Ground'])
        self.assertFalse(cov['Normal'])


class TestParsing(unittest.TestCase):
    def test_header_variants(self):
        self.assertEqual(parse_header('Toxapex'), ('Toxapex', ''))
        self.assertEqual(parse_header('Great Tusk @ Booster Energy'), ('Great Tusk', 'Booster Energy'))
        self.assertEqual(parse_header('Kingambit (F) @ Black Glasses'), ('Kingambit', 'Black Glasses'))
        self.assertEqual(parse_header('Bob (Rotom-Wash) (M) @ Leftovers'), ('Rotom-Wash', 'Leftovers'))

    @patch('metamatch.team.fetch_pokemon_data', side_effect=mock_fetch_pokemon_data)
    @patch('metamatch.team.get_move_metadata', return_value={'category': 'Status', 'type': 'Normal'})
    def test_itemless_pokemon_keeps_name(self, *_):
        team, _ = readTeam("Gholdengo\nAbility: Good as Gold\nEVs: 252 HP / 252 SpA / 4 Spe\nModest Nature\n- Nasty Plot")
        self.assertEqual(team[0]['Pokemon'], 'Gholdengo')
        self.assertEqual(team[0]['Item'], '')

    def test_extract_names_handles_itemless_and_crlf(self):
        raw = "Toxapex\r\nAbility: Regenerator\r\n\r\nBob (Great Tusk) (M) @ Leftovers\r\n- Rapid Spin"
        self.assertEqual(extract_pokemon_names(raw), ['Toxapex', 'Great Tusk'])


class TestQueryEntities(unittest.TestCase):
    def test_finds_all_named_pokemon_in_order(self):
        self.assertEqual(find_pokemon_in_query('Is Rotom-Wash faster than Great Tusk?'), ['Rotom-Wash', 'Great Tusk'])
        self.assertEqual(find_pokemon_in_query('does gholdengo beat iron hands'), ['Gholdengo', 'Iron Hands'])

    def test_longest_name_wins(self):
        self.assertNotIn('Rotom', find_pokemon_in_query('rotom wash vs toxapex'))

    def test_no_pokemon(self):
        self.assertEqual(find_pokemon_in_query('is it weak to ground'), [])


class TestThreats(unittest.TestCase):
    def test_usage_and_move_percentages(self):
        chaos = {"Kingambit": {
            "usage": 0.343, "Raw count": 10,
            "Abilities": {"Supreme Overlord": 100.0},
            "Moves": {"suckerpunch": 90.0, "kowtowcleave": 80.0, "ironhead": 70.0, "swordsdance": 160.0},
        }}
        team = {0: {'Pokemon': 'Toxapex', 'Damage From': {'dark': 2.0}, 'Damage To': {}},
                1: {'Pokemon': 'Clefable', 'Damage From': {'steel': 2.0}, 'Damage To': {}}}
        with tempfile.TemporaryDirectory() as d:
            Path(d, "topPoke.json").write_text(json.dumps({"Kingambit": ["Dark", "Steel"]}), encoding="utf-8")
            with patch('metamatch.auditor.load_chaos_data', return_value=chaos), \
                 patch.object(config, "JSON_DIR", Path(d)):
                threats = suggestions.compute_threats(team, "gen9ou")
        self.assertEqual(threats[0]['pokemon'], 'Kingambit')
        self.assertIn('34.3% of ladder teams', threats[0]['explanation'])
        self.assertIn('Sucker Punch (90%)', threats[0]['explanation'])

    def test_core_roles_skip_cleric(self):
        self.assertNotIn('Cleric', suggestions.CORE_ROLES)


class TestRecommender(unittest.TestCase):
    def _recs(self, names, items=None):
        chaos = {"Garchomp": {"Teammates": {"Garchomp-Mega-Z": 90.0, "Gengar-Mega": 60.0, "Corviknight": 50.0},
                              "Abilities": {"Rough Skin": 1}, "Moves": {}}}
        with patch('metamatch.recommender.load_chaos_data', return_value=chaos):
            return [r[0] for r in recommender.get_recommendations(names, format_id="gen9championsou", team_items=items)]

    def test_no_duplicate_species_via_mega_forme(self):
        self.assertNotIn('Garchomp-Mega-Z', self._recs(['Garchomp']))

    def test_mega_stone_blocks_second_mega(self):
        self.assertIn('Gengar-Mega', self._recs(['Garchomp'], ['Life Orb']))
        self.assertNotIn('Gengar-Mega', self._recs(['Garchomp'], ['Garchompite Z']))

    def test_mega_stone_detection(self):
        self.assertTrue(recommender.holds_mega_stone('Charizardite Y'))
        self.assertFalse(recommender.holds_mega_stone('Eviolite'))
        self.assertFalse(recommender.holds_mega_stone('Leftovers'))


if __name__ == '__main__':
    unittest.main()
