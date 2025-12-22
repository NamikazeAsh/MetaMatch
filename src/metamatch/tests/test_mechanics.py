import unittest
from unittest.mock import patch
from ..team import readTeam

# Mock API response to avoid hitting PokeAPI during tests
def mock_fetch_pokemon_data(name):
    # Minimal data structure required for readTeam to proceed
    base_data = {
        'types': [],
        'stats': {'speed': 100},
        'sprite': 'mock_url',
        'abilities': []
    }
    
    n = name.lower()
    
    # --- Existing Mocks ---
    if n == 'rotom-wash': base_data['types'] = ['Electric', 'Water']
    elif n == 'heatran': base_data['types'] = ['Fire', 'Steel']
    elif n == 'scizor': base_data['types'] = ['Bug', 'Steel']
    elif n == 'toxicroak': base_data['types'] = ['Poison', 'Fighting']
    elif n == 'swampert': base_data['types'] = ['Water', 'Ground']
    elif n == 'thundurus': base_data['types'] = ['Electric', 'Flying']
    
    # --- New Mocks for Expanded Tests ---
    elif n == 'azumarill': base_data['types'] = ['Water', 'Fairy']
    elif n == 'electivire': base_data['types'] = ['Electric']
    elif n == 'vaporeon': base_data['types'] = ['Water']
    elif n == 'gastrodon': base_data['types'] = ['Water', 'Ground']
    elif n == 'orthworm': base_data['types'] = ['Steel']
    elif n == 'dachsbun': base_data['types'] = ['Fairy']
    elif n == 'gyarados': base_data['types'] = ['Water', 'Flying']
    elif n == 'ferrothorn': base_data['types'] = ['Grass', 'Steel']
    elif n == 'garchomp': base_data['types'] = ['Dragon', 'Ground']
    elif n == 'sableye': base_data['types'] = ['Dark', 'Ghost']
    elif n == 'kingambit': base_data['types'] = ['Dark', 'Steel']
    elif n == 'torterra': base_data['types'] = ['Grass', 'Ground']
    elif n == 'goodra': base_data['types'] = ['Dragon']
    elif n == 'raichu': base_data['types'] = ['Electric']
    elif n == 'shedinja': base_data['types'] = ['Bug', 'Ghost'] # Edge case
        
    return base_data

class TestMechanics(unittest.TestCase):
    
    @patch('src.metamatch.team.fetch_pokemon_data', side_effect=mock_fetch_pokemon_data)
    @patch('src.metamatch.team.get_move_metadata', return_value={'category': 'Status', 'type': 'Normal'})
    def test_ability_immunities(self, mock_move, mock_fetch):
        """
        Test ability-based immunities supported by team.py logic.
        """
        # Batch 1: Ability Immunities
        raw_team = """
Rotom-Wash @ Leftovers
Ability: Levitate
EVs: 252 HP
- Hydro Pump

Heatran @ Leftovers
Ability: Flash Fire
EVs: 252 HP
- Magma Storm

Swampert @ Leftovers
Ability: Damp
EVs: 252 HP
- Earthquake

Thundurus @ Life Orb
Ability: Volt Absorb
EVs: 252 SpA
- Thunderbolt

Azumarill @ Sitrus Berry
Ability: Sap Sipper
EVs: 252 HP
- Play Rough

Raichu @ Focus Sash
Ability: Lightning Rod
EVs: 252 Spe
- Volt Switch

Gastrodon @ Leftovers
Ability: Storm Drain
EVs: 252 HP
- Earth Power

Orthworm @ Sitrus Berry
Ability: Earth Eater
EVs: 252 Def
- Shed Tail

Dachsbun @ Leftovers
Ability: Well-Baked Body
EVs: 252 Def
- Body Press
"""
        team, _ = readTeam(raw_team)
        
        # 1. Rotom-Wash (Levitate) -> Ground Immune
        self.assertEqual(team[0]['Damage From'].get('ground'), 0.0)
        # 2. Heatran (Flash Fire) -> Fire Immune
        self.assertEqual(team[1]['Damage From'].get('fire'), 0.0)
        # 3. Swampert (Ground Type) -> Electric Immune
        self.assertEqual(team[2]['Damage From'].get('electric'), 0.0)
        # 4. Thundurus (Volt Absorb) -> Electric Immune
        self.assertEqual(team[3]['Damage From'].get('electric'), 0.0)
        # 5. Azumarill (Sap Sipper) -> Grass Immune
        self.assertEqual(team[4]['Damage From'].get('grass'), 0.0)
        # 6. Raichu (Lightning Rod) -> Electric Immune
        self.assertEqual(team[5]['Damage From'].get('electric'), 0.0)
        # 7. Gastrodon (Storm Drain) -> Water Immune
        self.assertEqual(team[6]['Damage From'].get('water'), 0.0)
        # 8. Orthworm (Earth Eater) -> Ground Immune
        self.assertEqual(team[7]['Damage From'].get('ground'), 0.0)
        # 9. Dachsbun (Well-Baked Body) -> Fire Immune
        self.assertEqual(team[8]['Damage From'].get('fire'), 0.0)

    @patch('src.metamatch.team.fetch_pokemon_data', side_effect=mock_fetch_pokemon_data)
    @patch('src.metamatch.team.get_move_metadata', return_value={'category': 'Status', 'type': 'Normal'})
    def test_item_immunities(self, mock_move, mock_fetch):
        raw_team = """
Heatran @ Air Balloon
Ability: Flash Fire
EVs: 252 HP
- Magma Storm
"""
        team, _ = readTeam(raw_team)
        # 10. Air Balloon -> Ground Immune
        self.assertEqual(team[0]['Damage From'].get('ground'), 0.0)

    @patch('src.metamatch.team.fetch_pokemon_data', side_effect=mock_fetch_pokemon_data)
    @patch('src.metamatch.team.get_move_metadata', return_value={'category': 'Status', 'type': 'Normal'})
    def test_type_chart_extremes(self, mock_move, mock_fetch):
        """
        Test 4x weaknesses and Natural Type Immunities.
        """
        raw_team = """
Scizor @ Band
Ability: Technician
EVs: 252 Atk
- Bullet Punch

Toxicroak @ Life Orb
Ability: Dry Skin
EVs: 252 Atk
- Close Combat

Gyarados @ Heavy-Duty Boots
Ability: Intimidate
EVs: 252 Atk
- Waterfall

Ferrothorn @ Leftovers
Ability: Iron Barbs
EVs: 252 HP
- Spikes

Garchomp @ Rocky Helmet
Ability: Rough Skin
EVs: 252 Spe
- Earthquake

Sableye @ Leftovers
Ability: Prankster
EVs: 252 HP
- Recover

Kingambit @ Black Glasses
Ability: Supreme Overlord
EVs: 252 Atk
- Kowtow Cleave

Torterra @ Leftovers
Ability: Overgrow
EVs: 252 Atk
- Wood Hammer
"""
        team, _ = readTeam(raw_team)
        
        # 11. Scizor (Bug/Steel) vs Fire -> 4x Weak
        self.assertEqual(team[0]['Damage From'].get('fire'), 4.0)
        
        # 12. Toxicroak (Dry Skin) vs Water -> Immune
        self.assertEqual(team[1]['Damage From'].get('water'), 0.0)
        
        # 13. Gyarados (Water/Flying) vs Electric -> 4x Weak
        self.assertEqual(team[2]['Damage From'].get('electric'), 4.0)
        # 14. Gyarados (Water/Flying) vs Ground -> Immune (Flying)
        self.assertEqual(team[2]['Damage From'].get('ground'), 0.0)
        
        # 15. Ferrothorn (Grass/Steel) vs Fire -> 4x Weak
        self.assertEqual(team[3]['Damage From'].get('fire'), 4.0)
        # 16. Ferrothorn (Grass/Steel) vs Poison -> Immune (Steel)
        self.assertEqual(team[3]['Damage From'].get('poison'), 0.0)
        
        # 17. Garchomp (Dragon/Ground) vs Ice -> 4x Weak
        self.assertEqual(team[4]['Damage From'].get('ice'), 4.0)
        # 18. Garchomp (Dragon/Ground) vs Electric -> Immune (Ground)
        self.assertEqual(team[4]['Damage From'].get('electric'), 0.0)
        
        # 19. Sableye (Dark/Ghost) vs Normal -> Immune (Ghost)
        self.assertEqual(team[5]['Damage From'].get('normal'), 0.0)
        # 20. Sableye (Dark/Ghost) vs Fighting -> Immune (Ghost)
        self.assertEqual(team[5]['Damage From'].get('fighting'), 0.0)
        # 21. Sableye (Dark/Ghost) vs Psychic -> Immune (Dark)
        self.assertEqual(team[5]['Damage From'].get('psychic'), 0.0)
        
        # 22. Kingambit (Dark/Steel) vs Fighting -> 4x Weak
        self.assertEqual(team[6]['Damage From'].get('fighting'), 4.0)
        # 23. Kingambit (Dark/Steel) vs Psychic -> Immune (Dark)
        self.assertEqual(team[6]['Damage From'].get('psychic'), 0.0)
        # 24. Kingambit (Dark/Steel) vs Poison -> Immune (Steel)
        self.assertEqual(team[6]['Damage From'].get('poison'), 0.0)
        
        # 25. Torterra (Grass/Ground) vs Electric -> Immune (Ground)
        self.assertEqual(team[7]['Damage From'].get('electric'), 0.0)
        # 26. Torterra (Grass/Ground) vs Ice -> 4x Weak
        self.assertEqual(team[7]['Damage From'].get('ice'), 4.0)

from ..team import detectRole

class TestRoles(unittest.TestCase):
    def test_weather_roles(self):
        """
        Test detection of Weather Setters and Abusers.
        """
        # Mock team dict structure expected by detectRole
        team = {
            0: {"Pokemon": "Pelipper", "Ability": "Drizzle", "Item": "Damp Rock", "Moves": ["Surf"], "EVs": {}, "Roles": []},
            1: {"Pokemon": "Barraskewda", "Ability": "Swift Swim", "Item": "Choice Band", "Moves": ["Liquidation"], "EVs": {}, "Roles": []},
            2: {"Pokemon": "Torkoal", "Ability": "Drought", "Item": "Heat Rock", "Moves": ["Lava Plume"], "EVs": {}, "Roles": []},
            3: {"Pokemon": "Walking Wake", "Ability": "Protosynthesis", "Item": "Choice Specs", "Moves": ["Hydro Steam"], "EVs": {}, "Roles": []}
        }
        
        detectRole(team)
        
        self.assertIn("Weather Setter", team[0]["Roles"])
        self.assertIn("Weather Abuser", team[1]["Roles"])
        self.assertIn("Weather Setter", team[2]["Roles"])
        self.assertIn("Weather Abuser", team[3]["Roles"])

    def test_sweeper_roles(self):
        """
        Test detection of Sweeper sub-types.
        """
        team = {
            0: {"Pokemon": "Garchomp", "Ability": "Rough Skin", "Item": "Life Orb", "Moves": ["Swords Dance"], "EVs": {"Atk": 252, "Spe": 252}, "Roles": []},
            1: {"Pokemon": "Iron Valiant", "Ability": "Quark Drive", "Item": "Booster Energy", "Moves": ["Calm Mind"], "EVs": {"SpA": 252, "Spe": 252}, "Roles": []}
        }
        
        detectRole(team)
        
        # Garchomp: Atk 252 + Spe 252 -> Physical Sweeper, Fast Sweeper
        self.assertIn("Physical Sweeper", team[0]["Roles"])
        self.assertIn("Fast Sweeper", team[0]["Roles"])
        self.assertIn("Setup Sweeper", team[0]["Roles"]) # Has Swords Dance
        
        # Iron Valiant: SpA 252 + Spe 252 -> Special Sweeper, Fast Sweeper
        self.assertIn("Special Sweeper", team[1]["Roles"])
        self.assertIn("Fast Sweeper", team[1]["Roles"])
        self.assertIn("Setup Sweeper", team[1]["Roles"]) # Has Calm Mind

    def test_utility_roles(self):
        """
        Test detection of Phazers (Forced Switcher) and Stallbreakers.
        """
        team = {
            0: {"Pokemon": "Dragonite", "Ability": "Multiscale", "Item": "Heavy-Duty Boots", "Moves": ["Dragon Tail"], "EVs": {}, "Roles": []},
            1: {"Pokemon": "Heatran", "Ability": "Flash Fire", "Item": "Leftovers", "Moves": ["Taunt", "Magma Storm"], "EVs": {"SpA": 252}, "Roles": []},
            2: {"Pokemon": "Garganacl", "Ability": "Purifying Salt", "Item": "Red Card", "Moves": ["Salt Cure"], "EVs": {}, "Roles": []}
        }
        
        detectRole(team)
        
        # Dragonite: Has Dragon Tail -> Forced Switcher
        self.assertIn("Forced Switcher", team[0]["Roles"])
        
        # Heatran: Has Taunt + SpA EVs -> Stallbreaker
        self.assertIn("Stallbreaker", team[1]["Roles"])
        
        # Garganacl: Has Red Card -> Forced Switcher
        self.assertIn("Forced Switcher", team[2]["Roles"])

if __name__ == '__main__':
    unittest.main()