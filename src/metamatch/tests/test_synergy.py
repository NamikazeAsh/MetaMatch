"""Team engines (engine/synergy.py): cores found by rule, measured with the calc, and no false alarms."""
import unittest

from metamatch.engine import calc
from metamatch.team import readTeam, detectRole

TORKOAL = """Torkoal @ Heat Rock
Ability: Drought
EVs: 248 HP / 252 Def / 8 SpD
Bold Nature
- Lava Plume
- Rapid Spin
- Stealth Rock
- Will-O-Wisp"""
VENUSAUR = """Venusaur @ Life Orb
Ability: Chlorophyll
EVs: 4 Def / 252 SpA / 252 Spe
Timid Nature
- Growth
- Giga Drain
- Weather Ball
- Sludge Bomb"""
ALOMOMOLA = """Alomomola @ Assault Vest
Ability: Regenerator
EVs: 20 HP / 236 Def / 252 SpD
Sassy Nature
- Flip Turn
- Scald
- Mirror Coat
- Body Slam"""


def team(*sets):
    t, _ = readTeam("\n\n".join(sets), "gen9ou")
    detectRole(t)
    return t


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestTeamEngines(unittest.TestCase):
    def test_sun_core_is_measured_and_its_drawbacks_named(self):
        from metamatch.engine.synergy import team_engines
        sun = next(e for e in team_engines(team(TORKOAL, VENUSAUR, ALOMOMOLA), "gen9ou") if e.key == "sun")
        self.assertTrue(sun.complete and sun.always_on)
        self.assertEqual([s["name"] for s in sun.setters], ["Torkoal"])
        venusaur = next(u for u in sun.users if u.name == "Venusaur")
        before, after, share_before, share_after = venusaur.speed
        self.assertEqual(after, 2 * before)                   # Chlorophyll doubles Speed
        self.assertGreater(share_after, share_before)
        self.assertGreater(venusaur.damage[2], venusaur.damage[1])   # Weather Ball turns Fire and hits harder in sun
        self.assertTrue(any("Scald is halved" in d for d in sun.drawbacks))

    def test_half_built_core_names_setters_players_pair_it_with(self):
        from metamatch.engine.synergy import describe, team_engines
        engines = team_engines(team(VENUSAUR, ALOMOMOLA), "gen9ou")
        sun = next(e for e in engines if e.key == "sun")
        self.assertFalse(sun.setters)
        self.assertIn("nothing on the team sets it", describe(sun))
        self.assertTrue({"Torkoal", "Ninetales"} & set(sun.partners))

    def test_incidental_users_and_setters_raise_no_alarm(self):
        from metamatch.engine.synergy import team_engines
        slowking = "Slowking-Galar @ Heavy-Duty Boots\nAbility: Regenerator\nEVs: 252 HP / 4 Def / 252 SpD\nSassy Nature\n" \
                   "- Chilly Reception\n- Future Sight\n- Sludge Bomb\n- Slack Off"
        wake = "Walking Wake @ Booster Energy\nAbility: Protosynthesis\nEVs: 252 SpA / 4 SpD / 252 Spe\nTimid Nature\n" \
               "- Hydro Steam\n- Draco Meteor\n- Flamethrower\n- Flip Turn"
        hands = "Iron Hands @ Assault Vest\nAbility: Quark Drive\nEVs: 252 HP / 252 Atk\nAdamant Nature\n" \
                "- Drain Punch\n- Ice Punch\n- Wild Charge\n- Fake Out"
        # Chilly Reception pivots without a snow core; Hydro Steam and Quark Drive work fine without sun or terrain
        self.assertEqual(team_engines(team(slowking, wake, hands), "gen9ou", measure=False), [])

    def test_weather_ball_belongs_to_the_weather_its_set_points_at(self):
        from metamatch.engine.synergy import team_engines
        tyranitar = "Tyranitar @ Leftovers\nAbility: Sand Stream\nEVs: 252 HP / 4 Atk / 252 SpD\nCareful Nature\n" \
                    "- Stone Edge\n- Knock Off\n- Stealth Rock\n- Thunder Wave"
        kingdra = "Kingdra @ Choice Specs\nAbility: Swift Swim\nEVs: 252 SpA / 4 SpD / 252 Spe\nModest Nature\n" \
                  "- Weather Ball\n- Draco Meteor\n- Hurricane\n- Flip Turn"
        engines = team_engines(team(tyranitar, kingdra), "gen9ou", measure=False)
        sand = next((e for e in engines if e.key == "sand"), None)
        self.assertTrue(sand is None or "Kingdra" not in [u.name for u in sand.users])
        rain = next(e for e in engines if e.key == "rain")       # Swift Swim with no rain setter: half built
        self.assertFalse(rain.setters)

    def test_trick_room_finds_the_slow_hitters(self):
        from metamatch.engine.synergy import team_engines
        hatterene = "Hatterene @ Mental Herb\nAbility: Magic Bounce\nEVs: 252 HP / 252 SpA\nQuiet Nature\nIVs: 0 Spe\n" \
                    "- Trick Room\n- Psychic\n- Dazzling Gleam\n- Mystical Fire"
        ursaluna = "Ursaluna @ Flame Orb\nAbility: Guts\nEVs: 252 HP / 252 Atk\nBrave Nature\nIVs: 0 Spe\n" \
                   "- Facade\n- Headlong Rush\n- Fire Punch\n- Protect"
        tr = next(e for e in team_engines(team(hatterene, ursaluna), "gen9ou") if e.key == "trick_room")
        self.assertIn("Ursaluna", [u.name for u in tr.users])
        self.assertTrue(all(u.speed[3] > u.speed[2] for u in tr.users))   # moves first against more under Trick Room


if __name__ == "__main__":
    unittest.main()
