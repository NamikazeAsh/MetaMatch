"""Team building tools: Threat Board and the "what checks X" answer."""
import unittest

from metamatch.engine import calc
from metamatch.engine.planner import plan_query
from metamatch.engine.solvers import Verdict, solve
from metamatch.agents.grounded import verify
from metamatch.team import readTeam

TEAM = """Gholdengo @ Choice Scarf
Ability: Good as Gold
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Trick
- Focus Blast

Great Tusk @ Booster Energy
Ability: Protosynthesis
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Headlong Rush
- Ice Spinner
- Rapid Spin
- Knock Off

Kingambit @ Black Glasses
Ability: Supreme Overlord
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Swords Dance
- Kowtow Cleave
- Sucker Punch
- Iron Head"""


class TestChecksIntent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM, "gen9ou")

    def test_phrasings_route_to_checks(self):
        for q in ["what checks Kyurem on my team?", "who on my team counters Zamazenta", "answers to raging bolt?"]:
            self.assertEqual(plan_query(q, self.team).intent, "checks", q)

    def test_strategy_questions_stay_open(self):
        self.assertEqual(plan_query("how do I beat Kingambit?", self.team).intent, "open")

    def test_verifier_rejects_a_loser_called_an_answer(self):
        v = Verdict("checks", "Gholdengo", "Gholdengo beats Kyurem one on one.", [], other="Kyurem",
                    losers=["Great Tusk"], members=["Gholdengo", "Great Tusk", "Kingambit"])
        self.assertIsNotNone(verify("Great Tusk is your best answer to Kyurem.", v))
        self.assertIsNone(verify("Gholdengo handles Kyurem, while Great Tusk is OHKO'd by Ice Beam.", v))


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestThreatBoard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.team, _ = readTeam(TEAM, "gen9ou")

    def test_board_rows_cover_every_member(self):
        from metamatch.engine.threat_board import coverage, threat_board
        rows = threat_board(self.team, n=4)
        self.assertTrue(rows)
        members = {p["Pokemon"] for p in self.team.values()}
        for r in rows:
            self.assertNotIn(r.name, members)
            self.assertEqual(set(r.cells), members)
            self.assertTrue(set(r.answers).isdisjoint(r.losses))
        answered, total, share = coverage(rows)
        self.assertEqual(total, len(rows))
        self.assertTrue(0 <= share <= 1)

    def test_checks_answer_lists_answers_and_losses(self):
        v = solve(plan_query("what checks Kyurem on my team?", self.team))
        self.assertEqual(v.intent, "checks")
        self.assertIn("Kyurem", v.statement)
        for name in v.losers:
            self.assertNotIn(name, v.answer)


class TestSpeedBoard(unittest.TestCase):
    def test_ivs_are_parsed_and_lower_speed(self):
        team, _ = readTeam("Hatterene @ Life Orb\nAbility: Magic Bounce\nEVs: 252 HP / 252 SpA\nQuiet Nature\n"
                           "IVs: 0 Atk / 0 Spe\n- Psychic", "gen9ou")
        p = next(iter(team.values()))
        self.assertEqual(p["IVs"], {"Atk": 0, "Spe": 0})
        self.assertEqual(p["Speed"], 56)   # base 29, 0 IV, 0 EV, Quiet: floor(63 * 0.9)

    def test_outspeed_share_mixes_in_scarf(self):
        from metamatch.engine.speed_board import MetaSpeed, outspeed_share
        m = MetaSpeed("X", 10.0, [(300, 0.8), (250, 0.2)], scarf_share=0.5)
        self.assertAlmostEqual(outspeed_share(301, m), 0.5)     # beats every unscarfed set, no scarfed one
        self.assertAlmostEqual(outspeed_share(460, m), 1.0)
        self.assertAlmostEqual(outspeed_share(260, m), 0.1)     # only the unscarfed 250s


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestCompleter(unittest.TestCase):
    def test_lift_separates_real_pairs_from_popular_ones(self):
        from metamatch.auditor import load_chaos_data
        from metamatch.engine.completer import lift
        data = load_chaos_data("gen9ou")
        self.assertIsNone(lift(data, "Kingambit", "NotAPokemon"))
        value = lift(data, "Kingambit", "Great Tusk")
        self.assertTrue(value is None or value > 0)

    def test_candidates_skip_the_team_and_fill_holes(self):
        from metamatch.engine.completer import complete
        team, _ = readTeam(TEAM, "gen9ou")
        picks, redundant, board = complete(team, "gen9ou", n_threats=6, top_n=4)
        names = {p["Pokemon"] for p in team.values()}
        self.assertTrue(picks)
        for c in picks + redundant:
            self.assertNotIn(c.name, names)
            self.assertTrue(0 <= c.gain <= 1)
        for c in redundant:
            self.assertEqual(c.gain, 0)


class TestQuickMatch(unittest.TestCase):
    def test_core_partners_skip_the_core_and_rank_by_score(self):
        from metamatch.engine.completer import core_partners
        out = core_partners(["Kingambit", "Great Tusk"], "gen9ou", n=10)
        self.assertTrue(out)
        names = [r["name"] for r in out]
        self.assertNotIn("Kingambit", names)
        self.assertNotIn("Great Tusk", names)
        scores = [r["score"] for r in out]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for r in out:
            self.assertTrue(0 < r["share"] <= 1)

    def test_unknown_core_gives_nothing(self):
        from metamatch.engine.completer import core_partners
        self.assertEqual(core_partners(["NotAPokemon"], "gen9ou"), [])


@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestSpreadLab(unittest.TestCase):
    def test_first_ok_finds_the_smallest_passing_value(self):
        from metamatch.engine.spread_lab import _first_ok
        values = list(range(0, 253, 4))
        self.assertEqual(values[_first_ok(values, lambda v: v >= 100)], 100)
        self.assertIsNone(_first_ok(values, lambda v: v > 999))

    def test_champions_result_fits_the_budget_and_passes_its_recheck(self):
        from metamatch.engine.sets import likely_set
        from metamatch.engine.spread_lab import Benchmark, Lab
        s = likely_set("Garchomp", "gen9championsou")
        base = {"name": s["name"], "item": s["item"], "ability": s["ability"]}
        r = Lab(base, [Benchmark("outspeed", "Samurott-Hisui"), Benchmark("ko", "Kingambit", "Earthquake", 2)],
                "gen9championsou").run()
        self.assertTrue(r.ok, r.problem)
        self.assertLessEqual(r.used, 66)
        self.assertTrue(all(v <= 32 for v in r.evs.values()))
        self.assertTrue(all(ok for _, ok, _ in r.checks))

    def test_impossible_benchmarks_are_reported_not_fatal(self):
        from metamatch.engine.sets import likely_set
        from metamatch.engine.spread_lab import Benchmark, Lab
        g = likely_set("Gholdengo", "gen9ou")
        base = {"name": g["name"], "item": "Leftovers", "ability": g["ability"]}
        r = Lab(base, [Benchmark("outspeed", "Dragapult"), Benchmark("survive", "Kingambit", "Sucker Punch")], "gen9ou").run()
        self.assertTrue(r.ok)
        failed = [label for label, ok, _ in r.checks if not ok]
        self.assertEqual(len(failed), 1)
        self.assertIn("Dragapult", failed[0])


class TestMatchupPreview(unittest.TestCase):
    def test_names_get_ladder_sets_and_pastes_are_used_as_written(self):
        from metamatch.engine.preview import opponent_sets
        sets, unknown = opponent_sets("Kingambit, Raging Bolt, zzzmon", "gen9ou")
        self.assertEqual([s["name"] for s in sets], ["Kingambit", "Raging Bolt"])
        sets, _ = opponent_sets("Kingambit @ Leftovers\nAbility: Defiant\nEVs: 252 HP / 252 Atk\nAdamant Nature\n- Iron Head",
                                "gen9ou")
        self.assertEqual((sets[0]["item"], sets[0]["ability"], sets[0]["stated"]), ("Leftovers", "Defiant", True))

    def test_bring_three_uses_the_worst_case(self):
        from types import SimpleNamespace as NS
        from metamatch.engine.preview import bring_three
        win = NS(verdict="win")
        rows = [NS(name=t, cells={m: win for m in ms}) for t, ms in
                [("A", ["x"]), ("B", ["x"]), ("C", ["y"]), ("D", ["z"])]]
        best = bring_three(rows, ["x", "y", "z", "w"])[0]
        self.assertEqual(set(best[0]), {"x", "y", "z"})
        self.assertEqual(best[1], 3)


class TestTeamCheck(unittest.TestCase):
    def test_legal_team_passes(self):
        from metamatch.engine.team_check import check
        team, _ = readTeam(TEAM, "gen9ou")
        levels = [level for level, _ in check(team, "gen9ou")]
        self.assertNotIn("fix", levels)
        self.assertIn("ok", levels)

    def test_problems_are_explained(self):
        from metamatch.engine.team_check import check
        bad = TEAM.replace("252 HP / 252 Atk / 4 SpD", "252 HP / 252 Atk / 252 SpD").replace("- Iron Head", "- Iron Head\n- Swords Dance")
        team, _ = readTeam(bad + "\n\n" + TEAM.split("\n\n")[0], "gen9ou")
        text = " ".join(msg for level, msg in check(team, "gen9ou") if level == "fix")
        self.assertIn("756 EVs", text)
        self.assertIn("Swords Dance twice", text)
        self.assertIn("Species Clause", text)

    def test_spread_conversion_round_trips_the_usual_numbers(self):
        from metamatch.engine.team_check import convert_paste, ev_to_sp
        self.assertEqual((ev_to_sp(252), ev_to_sp(4), ev_to_sp(0)), (32, 1, 0))
        out = convert_paste("X @ Y\nTera Type: Fire\nEVs: 252 Atk / 4 SpD / 252 Spe\nJolly Nature", to_champions=True)
        self.assertIn("EVs: 32 Atk / 1 SpD / 32 Spe", out)
        self.assertNotIn("Tera Type", out)

    def test_pdf_report_carries_the_sets_checks_and_board(self):
        from io import BytesIO
        from metamatch.engine.team_check import check, report_pdf
        team, _ = readTeam(TEAM, "gen9ou")
        board = [{"name": "Great Tusk", "usage": 30.1, "answers": []}, {"name": "Raging Bolt", "usage": 20.4, "answers": ["Kingambit"]}]
        pdf = report_pdf(team, "gen9ou", check(team, "gen9ou"), board, "October 2026")
        self.assertTrue(pdf.startswith(b"%PDF"))
        try:
            from pypdf import PdfReader   # dev only: reading the text back
        except ImportError:
            return
        reader = PdfReader(BytesIO(pdf))
        text = " ".join(page.extract_text() for page in reader.pages)
        self.assertEqual(len(reader.pages), 1)
        for said in ("Kingambit @", "Kowtow Cleave", "Legal for OU", "Nobody on the team", "October 2026"):
            self.assertIn(said, text)



@unittest.skipUnless(calc.available(), "Node or @smogon/calc not installed")
class TestEngineGuide(unittest.TestCase):
    def test_guide_names_only_the_team_and_moves_it_runs(self):
        import re
        from metamatch.engine.dex import dex_for_format
        from metamatch.engine.guide import team_guide
        team, _ = readTeam(TEAM.replace("Jolly Nature", "Tera Type: Ground\nJolly Nature", 1), "gen9ou")
        g = team_guide(team, "gen9ou")
        moves = {p["Pokemon"]: {m["name"] for m in p["Moves"]} for p in team.values()}
        self.assertTrue(set(g.named_members()) <= set(moves))
        dex = dex_for_format("gen9ou")
        for card in [g.win] + g.leads:
            said = {m for m in dex.move_data if len(m) > 4 and re.search(rf"\b{re.escape(m)}\b", " ".join(card["points"]))}
            self.assertTrue(said <= moves[card["name"]], (card["name"], said))
        tusk = next(x for x in g.tera if x["name"] == "Great Tusk")
        self.assertTrue({"Flying", "Psychic", "Fairy"} <= set(tusk["removed"]))   # pure Ground after Tera
        self.assertIn("2x STAB", tusk["note"])                                     # Headlong Rush


class TestGuideLeads(unittest.TestCase):
    def test_ladder_lead_rate_nudges_and_is_shown_but_unknown_stays_neutral(self):
        from metamatch.engine.guide import Member, _leads
        mk = lambda name, **kw: Member(**dict(dict(name=name, beats=[], loses=[], speed=100, outspeeds=0.5, setup=[],
                                                    priority=[], hazards=[], removal=[], pivots=[], attacks=[],
                                                    types=[], weak=[]), **kw))
        members = [mk("Rare"), mk("Popular"), mk("Shy"), mk("Setter", hazards=["Stealth Rock"])]
        rates = {"Popular": (0.6, True), "Shy": (0.02, False), "Rare": (None, False)}
        leads = _leads(members, 12, None, rates=rates)
        self.assertEqual([l["name"] for l in leads], ["Popular", "Setter"])
        self.assertIn("Leads 60% of the ladder games it's in", leads[0]["points"])
        self.assertEqual([l["name"] for l in _leads(members[:1] + members[2:3], 12, None, rates=rates)], ["Rare", "Shy"])


class TestAudit(unittest.TestCase):
    def test_roles_coverage_and_rare_moves_read_plainly(self):
        from metamatch.suggestions import get_suggestions
        from metamatch.team import detectRole
        team, _ = readTeam(TEAM.replace("- Iron Head", "- Toxic"), "gen9ou")
        detectRole(team)
        out = get_suggestions(team)
        cards = {c["label"]: c for c in out["team_analysis"]}
        self.assertTrue(cards["Hazard removal"]["ok"])
        self.assertIn("Great Tusk", cards["Hazard removal"]["text"])
        self.assertFalse(cards["Hazard setter"]["ok"])
        rare = " ".join(out["pokemon_specific"]["Kingambit"])
        self.assertIn("Toxic is on only", rare)
        self.assertNotIn("Kowtow Cleave", rare)      # never suggests a move the set already runs
        self.assertEqual(out["pokemon_specific"]["Gholdengo"], [])


class TestMatchupMatrices(unittest.TestCase):
    def test_weak_spots_and_coverage_gaps_are_flagged(self):
        from metamatch.tabs.tab_matrix import defense, defense_summary, offense, offense_summary
        team, _ = readTeam(TEAM, "gen9ou")
        d = defense_summary(defense(team))
        weak, res, imm, flag = d["Ground"]                 # Gholdengo and Kingambit weak, nobody takes it well
        self.assertEqual(set(weak), {"Gholdengo", "Kingambit"})
        self.assertTrue(flag)
        self.assertIn("Great Tusk", d["Electric"][2])      # Ground types are immune to Electric
        self.assertFalse(d["Electric"][3])
        o = offense_summary(offense(team))
        self.assertIn("Great Tusk", o["Steel"])            # Headlong Rush
        self.assertEqual(o["Water"], [])


if __name__ == "__main__":
    unittest.main()
