"""The saved sample teams behind "Try a sample team": each one parses into six known, legal Pokemon."""
import json
import unittest

from metamatch import config
from metamatch.engine.team_check import check
from metamatch.team import readTeam

FILE = config.JSON_DIR / "sample_teams.json"


class TestSampleTeams(unittest.TestCase):
    def test_every_sample_is_a_full_legal_team(self):
        samples = json.loads(FILE.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(samples), 5)
        self.assertEqual(len({s["source"] for s in samples}), len(samples))
        for s in samples:
            self.assertIn(s["format"], config.FORMATS, s["title"])
            team, _ = readTeam(s["team"], s["format"])
            self.assertEqual(len(team), 6, s["title"])
            self.assertTrue(all(p.get("Type") for p in team.values()), s["title"])
            self.assertEqual([m for level, m in check(team, s["format"]) if level == "fix"], [], s["title"])


if __name__ == "__main__":
    unittest.main()
