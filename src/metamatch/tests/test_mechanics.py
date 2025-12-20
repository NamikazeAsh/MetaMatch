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
    
    if name.lower() == 'rotom-wash':
        base_data['types'] = ['Electric', 'Water']
    elif name.lower() == 'heatran':
        base_data['types'] = ['Fire', 'Steel']
    elif name.lower() == 'scizor':
        base_data['types'] = ['Bug', 'Steel']
    elif name.lower() == 'toxicroak':
        base_data['types'] = ['Poison', 'Fighting']
    elif name.lower() == 'swampert':
        base_data['types'] = ['Water', 'Ground']
    elif name.lower() == 'thundurus':
        base_data['types'] = ['Electric', 'Flying']
    elif name.lower() == 'azumarill':
        base_data['types'] = ['Water', 'Fairy']
        
    return base_data

class TestMechanics(unittest.TestCase):
    
    @patch('src.metamatch.team.fetch_pokemon_data', side_effect=mock_fetch_pokemon_data)
    @patch('src.metamatch.team.get_move_metadata', return_value={'category': 'Status', 'type': 'Normal'})
    def test_ability_immunities(self, mock_move, mock_fetch):
        """
        Test that abilities like Levitate and Flash Fire grant correct immunities.
        """
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
"""
        team, _ = readTeam(raw_team)
        
        # 1. Rotom-Wash (Electric/Water) vs Ground
        # Normally 2x (Electric is weak), but Levitate -> 0.0
        rotom = team[0]
        self.assertEqual(rotom['Pokemon'], 'Rotom-Wash')
        self.assertEqual(rotom['Damage From'].get('ground'), 0.0, "Rotom-Wash should be immune to Ground due to Levitate")

        # 2. Heatran (Fire/Steel) vs Fire
        # Normally Neutral (Fire resists Fire, Steel weak to Fire -> 1.0), but Flash Fire -> 0.0
        heatran = team[1]
        self.assertEqual(heatran['Pokemon'], 'Heatran')
        self.assertEqual(heatran['Damage From'].get('fire'), 0.0, "Heatran should be immune to Fire due to Flash Fire")

        # 3. Swampert (Water/Ground) vs Electric
        # Water is weak (2x), Ground is Immune (0x) -> Total 0x
        swampert = team[2]
        self.assertEqual(swampert['Pokemon'], 'Swampert')
        self.assertEqual(swampert['Damage From'].get('electric'), 0.0, "Swampert should be immune to Electric due to Ground typing")

        # 4. Thundurus (Electric/Flying) vs Electric
        # Flying resists (0.5), Electric resists (0.5) -> 0.25 normally.
        # But Volt Absorb -> 0.0
        thundurus = team[3]
        self.assertEqual(thundurus['Pokemon'], 'Thundurus')
        self.assertEqual(thundurus['Damage From'].get('electric'), 0.0, "Thundurus should be immune to Electric due to Volt Absorb")

    @patch('src.metamatch.team.fetch_pokemon_data', side_effect=mock_fetch_pokemon_data)
    @patch('src.metamatch.team.get_move_metadata', return_value={'category': 'Status', 'type': 'Normal'})
    def test_item_immunities(self, mock_move, mock_fetch):
        """
        Test that items like Air Balloon override natural weaknesses.
        """
        raw_team = """
Heatran @ Air Balloon
Ability: Flash Fire
EVs: 252 HP
- Magma Storm
"""
        team, _ = readTeam(raw_team)
        
        # Heatran (Fire/Steel) is normally 4x weak to Ground.
        # Air Balloon -> 0.0
        heatran = team[0]
        self.assertEqual(heatran['Pokemon'], 'Heatran')
        self.assertEqual(heatran['Damage From'].get('ground'), 0.0, "Air Balloon Heatran should be immune to Ground")

    @patch('src.metamatch.team.fetch_pokemon_data', side_effect=mock_fetch_pokemon_data)
    @patch('src.metamatch.team.get_move_metadata', return_value={'category': 'Status', 'type': 'Normal'})
    def test_calc_complexity(self, mock_move, mock_fetch):
        """
        Test 4x weaknesses and complex dual-type logic.
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
"""
        team, _ = readTeam(raw_team)
        
        # 1. Scizor (Bug/Steel) vs Fire
        # Bug weak (2x) * Steel weak (2x) -> 4x
        scizor = team[0]
        self.assertEqual(scizor['Pokemon'], 'Scizor')
        self.assertEqual(scizor['Damage From'].get('fire'), 4.0, "Scizor should take 4x damage from Fire")

        # 2. Toxicroak (Poison/Fighting) vs Water
        # Neutral normally. Dry Skin -> 0.0 (Immune/Heals)
        toxicroak = team[1]
        self.assertEqual(toxicroak['Pokemon'], 'Toxicroak')
        self.assertEqual(toxicroak['Damage From'].get('water'), 0.0, "Dry Skin Toxicroak should be immune to Water")

if __name__ == '__main__':
    unittest.main()
