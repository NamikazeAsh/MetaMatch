import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# recommender imports `metamatch.config`, so the src dir must be importable too
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ..team import readTeam, addComments, looks_like_champions
from ..utils import calculate_speed, sp_to_ev
from .. import config


def mock_fetch_pokemon_data(name):
    return {'types': ['Dragon', 'Ground'], 'stats': {'speed': 100}, 'sprite': 'mock_url', 'abilities': []}


CHAMPIONS_TEAM = """
Garchomp @ Life Orb
Ability: Rough Skin
EVs: 2 HP / 32 Atk / 32 Spe
Jolly Nature
- Earthquake
- Dragon Claw
- Swords Dance
- Protect
"""

SV_TEAM = """
Garchomp @ Life Orb
Ability: Rough Skin
Tera Type: Steel
EVs: 4 HP / 252 Atk / 252 Spe
Jolly Nature
- Earthquake
- Dragon Claw
- Swords Dance
- Protect
"""


class TestChampionsMechanics(unittest.TestCase):

    def test_speed_formula(self):
        # SV Lv100: base 100, 252 EVs, +Spe -> 328
        self.assertEqual(calculate_speed(100, ev=252, nature_mod=1.1), 328)
        # Champions Lv50: floor((100 + 32 + 20) * 1.1) = 167
        self.assertEqual(calculate_speed(100, ev=32, nature_mod=1.1, game="champions"), 167)
        # Champions, no investment, neutral nature: 100 + 0 + 20
        self.assertEqual(calculate_speed(100, ev=0, game="champions"), 120)

    def test_sp_to_ev(self):
        self.assertEqual(sp_to_ev(0), 0)
        self.assertEqual(sp_to_ev(2), 16)
        self.assertEqual(sp_to_ev(32), 252)

    def test_detect_champions_export(self):
        self.assertTrue(looks_like_champions(CHAMPIONS_TEAM))
        self.assertFalse(looks_like_champions(SV_TEAM))

    @patch('src.metamatch.team.fetch_pokemon_data', side_effect=mock_fetch_pokemon_data)
    @patch('src.metamatch.team.get_move_metadata', return_value={'category': 'Status', 'type': 'Normal'})
    def test_parse_champions_team(self, mock_move, mock_fetch):
        team, _ = readTeam(CHAMPIONS_TEAM, "gen9championsou")
        p = team[0]
        self.assertEqual(p['Format'], "gen9championsou")
        self.assertEqual(p['SP'], {'HP': 2, 'Atk': 32, 'Spe': 32})
        self.assertEqual(p['EVs'], {'HP': 16, 'Atk': 252, 'Spe': 252})
        self.assertEqual(p['Speed'], 167)

    @patch('src.metamatch.team.fetch_pokemon_data', side_effect=mock_fetch_pokemon_data)
    @patch('src.metamatch.team.get_move_metadata', return_value={'category': 'Status', 'type': 'Normal'})
    def test_champions_validation(self, mock_move, mock_fetch):
        # 66 SP and no Tera is a complete Champions set
        team, _ = readTeam(CHAMPIONS_TEAM, "gen9championsou")
        addComments(team)
        self.assertEqual(team[0]['Comments'], [])

        # Over budget and over the per stat cap
        bad = CHAMPIONS_TEAM.replace("EVs: 2 HP / 32 Atk / 32 Spe", "EVs: 40 Atk / 32 Spe")
        team, _ = readTeam(bad, "gen9championsou")
        addComments(team)
        self.assertIn("Over 66 stat points", team[0]['Comments'])
        self.assertIn("Stat above 32 points", team[0]['Comments'])

        # The same set read as SV gets the old EV and Tera warnings
        team, _ = readTeam(CHAMPIONS_TEAM, "gen9ou")
        addComments(team)
        self.assertIn("Missing EV values", team[0]['Comments'])
        self.assertIn("Has improper tera type", team[0]['Comments'])

    def test_team_format_defaults_to_ou(self):
        # Teams saved before Champions support have no Format key
        self.assertEqual(config.team_format({0: {'Pokemon': 'Garchomp'}}), "gen9ou")
        self.assertEqual(config.team_format({0: {'Format': 'gen9championsuu'}}), "gen9championsuu")

    def test_recommender_champions_format(self):
        from metamatch import recommender
        chaos = {"data": {
            "Garchomp": {"Teammates": {"Corviknight": 50.0, "Samurott-Hisui": 20.0}, "Abilities": {"Rough Skin": 1}, "Moves": {}},
            "Corviknight": {"Abilities": {"Pressure": 1}, "Moves": {"uturn": 1}},
        }}
        with tempfile.TemporaryDirectory() as d:
            Path(d, "gen9championsou-1760.json").write_text(json.dumps(chaos), encoding="utf-8")
            with patch.object(recommender.config, "STATS_DIR", Path(d)):
                recs = recommender.get_recommendations(["Garchomp"], format_id="gen9championsou")
                # SV OU file is absent in the temp dir, so nothing comes back for it
                self.assertEqual(recommender.get_recommendations(["Garchomp"], format_id="gen9ou"), [])
        self.assertEqual(recs[0][0], "Corviknight")


GUIDE_HTML = """<html><body><main>
<p>Pokemon · Field Notes</p>
<h1>Mega Absol High-Risk Sweeper Lines</h1>
<h2>Role Overview</h2>
<p>Mega Absol is a fragile physical sweeper with Magic Bounce. It punishes passive teams.</p>
<p>Tip</p>
<h3>Team Support</h3>
<p>Pair it with Kingambit to punish Intimidate. Redirection support helps if playing in Doubles formats.</p>
<p>milotic</p>
<h2>Claims Behind Mega Absol's Sweeper Lines</h2>
<p>Hatterene's Magic Bounce reflects hazards, which is off topic here.</p>
</main></body></html>"""


class TestChampionsRag(unittest.TestCase):

    def test_parse_guide_splits_doubles_and_stops_at_claims(self):
        from ..rag import pokechamp
        g = pokechamp.parse_guide(GUIDE_HTML)
        self.assertEqual(g["title"], "Mega Absol High-Risk Sweeper Lines")
        self.assertEqual([s["heading"] for s in g["sections"]], ["Role Overview", "Team Support"])
        support = g["sections"][1]
        self.assertEqual(support["singles"], ["Pair it with Kingambit to punish Intimidate."])
        self.assertEqual(len(support["doubles"]), 1)
        # Labels, slug cards and the off topic claims section are dropped
        all_text = " ".join(t for s in g["sections"] for t in s["singles"] + s["doubles"])
        self.assertNotIn("Hatterene", all_text)
        self.assertNotIn("milotic", all_text)

    def test_guide_subject(self):
        from ..rag import pokechamp
        species = ["Absol", "Charizard", "Garchomp", "Samurott-Hisui"]
        self.assertEqual(pokechamp.guide_subject("Mega Absol Sweeper Lines", species), "Absol-Mega")
        self.assertEqual(pokechamp.guide_subject("Mega Charizard X Dragon Dance", species), "Charizard-Mega-X")
        self.assertEqual(pokechamp.guide_subject("Samurott-Hisui Ceaseless Edge", species), "Samurott-Hisui")
        self.assertEqual(pokechamp.guide_subject("Trick Room Teams", species), "General")

    def test_usage_card_helpers(self):
        from ..rag import usage_cards
        self.assertEqual(usage_cards._fmt_spread("Jolly:2/32/0/0/0/32"), "Jolly 2 HP / 32 Atk / 32 Spe")
        # Moves are a share of the Pokemon's weight, not of all move slots
        self.assertEqual(usage_cards._top({"earthquake": 90, "spikes": 30}, total=100, names={"earthquake": "Earthquake"}),
                         [("Earthquake", 90.0), ("spikes", 30.0)])


if __name__ == '__main__':
    unittest.main()
