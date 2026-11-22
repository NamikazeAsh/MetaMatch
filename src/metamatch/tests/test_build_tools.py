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

    def test_beat_questions_get_checks_voiced_by_oak(self):
        plan = plan_query("how do I beat Kingambit?", self.team)
        self.assertEqual((plan.intent, plan.asks_how), ("checks", True))

    def test_archetype_questions_stay_open(self):
        # Archetypes with a ladder roster get an engine answer; ones without stay open
        self.assertEqual(plan_query("how do I beat stall?", self.team).intent, "archetype")
        self.assertEqual(plan_query("how do I beat hyper offense?", self.team).intent, "open")

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

    def test_a_target_speed_is_priced_in_evs_then_nature(self):
        from metamatch.engine.speed_board import price, price_text
        curve = {"unit": "EVs", "current": 0, "free": 4, "item": "", "own": [(0, 170), (4, 171), (8, 172)],
                 "fast": ("Jolly", [(0, 187), (4, 188)])}
        text = lambda target: price_text(curve, price(curve, target))
        self.assertEqual(text(170), "Your current spread")
        self.assertEqual(text(171), "+4 Spe EVs")
        self.assertEqual(text(172), "+8 Spe EVs, 4 taken from other stats")
        self.assertEqual(text(188), "Needs a Jolly nature and 4 Spe EVs")
        self.assertIn("Choice Scarf", text(300))
        self.assertNotIn("Choice Scarf", price_text(dict(curve, item="Choice Scarf"), None))
        self.assertEqual(price_text(dict(curve, current=8), price(curve, 171)), "4 fewer Spe EVs than you run would still do it")

    def test_spread_labels_read_like_a_paste(self):
        from metamatch.engine.sets import spread_label
        self.assertEqual(spread_label("Impish:248/0/228/0/0/32", "gen9ou"), "Impish 248 HP / 228 Def / 32 Spe")
        self.assertEqual(spread_label("Jolly:2/32/0/0/0/32", "gen9championsou"), "Jolly 2 HP / 32 Atk / 32 Spe SP")

    def test_each_speed_lists_the_spreads_that_make_it(self):
        from metamatch.engine.sets import speed_distribution, speed_spreads
        groups = speed_spreads("Corviknight", "gen9ou")
        if not groups:
            self.skipTest("No OU usage stats downloaded")
        for spe, share in speed_distribution("Corviknight", "gen9ou"):
            self.assertAlmostEqual(share, sum(s for _, s in groups[spe]))


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


class TestMegaPastes(unittest.TestCase):
    def test_mega_named_paste_reads_like_the_stone_holder(self):
        from metamatch.engine.guide import _mega
        for header in ("Gengar @ Gengarite", "Gengar-Mega @ Gengarite"):
            team, _ = readTeam(header + "\nAbility: Cursed Body\nTimid Nature\n- Shadow Ball", "gen9championsou")
            p = next(iter(team.values()))
            self.assertEqual((p["Pokemon"], p.get("Forme"), p.get("Mega Ability")), ("Gengar", "Gengar-Mega", "Shadow Tag"),
                             header)
            self.assertEqual([m["forme"] for m in _mega(team, "gen9championsou")], ["Gengar-Mega"], header)


class TestMegaOutsideChampions(unittest.TestCase):
    def test_smogon_sources_use_the_apps_format_ids(self):
        from metamatch import config
        from metamatch.rag.cards import FORMAT_SOURCE
        self.assertTrue(set(FORMAT_SOURCE) <= set(config.FORMATS), set(FORMAT_SOURCE) - set(config.FORMATS))

    def test_each_format_gets_only_the_gimmick_it_allows(self):
        from metamatch import config
        # National Dex runs Terastal Clause and allows Megas; SV OU and UU have Tera and no Megas
        self.assertEqual([f for f in config.FORMATS if config.has_megas(f)], ["gen9natdex", "gen9championsou", "gen9championsuu"])
        self.assertEqual([f for f in config.FORMATS if config.has_tera(f)], ["gen9ou", "gen9uu"])

    def test_national_dex_megas_get_their_card(self):
        from metamatch.engine.guide import _mega
        team, _ = readTeam("Charizard @ Charizardite Y\nAbility: Blaze\nTimid Nature\n- Flamethrower\n- Solar Beam",
                           "gen9natdex")
        self.assertEqual([m["forme"] for m in _mega(team, "gen9natdex")], ["Charizard-Mega-Y"])


class TestSmogonHighlight(unittest.TestCase):
    def test_names_are_marked_once_lightly_and_the_words_kept(self):
        import re
        from metamatch.tabs.tab_coach_guide import _rich
        text = ("Mega Charizard Y's Fire-type Weather Ball and Drought pressure Landorus-T, while Black Sludge "
                "Galarian Slowking uses Future Sight. Return to form with Rest. Landorus-T and Mega Mewtwo X fear it.")
        html = _rich(text, {"Fire": {"color": "#f42"}}, set(), "Charizard")
        marks = re.findall(r'class="cg-(\w+)"[^>]*>([^<]+)<', html)
        # Not the card's own Pokemon, not abilities or items (Black Sludge isn't the move Sludge), each name once
        self.assertEqual(marks, [("mv", "Weather Ball"), ("pk", "Landorus-T"), ("pk", "Galarian Slowking"),
                                 ("mv", "Future Sight"), ("mv", "Rest"), ("pk", "Mega Mewtwo X")])
        self.assertIn('--t:#f42">Weather Ball', html)                 # the type the text gives, not the dex's Normal
        self.assertEqual(re.sub(r"<[^>]+>", "", html).replace("&#x27;", "'"), text)

    def test_the_subject_is_matched_as_a_whole_word(self):
        from metamatch.tabs.tab_coach_guide import _rich
        self.assertIn('cg-pk">Mewtwo', _rich("Mewtwo walls it.", {}, set(), "Mew"))


class TestMegaAnalysis(unittest.TestCase):
    def test_smogon_section_is_about_this_mega(self):
        from metamatch.rag.cards import mega_analysis
        y = mega_analysis("Charizard", "Charizard-Mega-Y", ["Heat Wave", "Solar Beam"], "gen9championsou")
        if y is None:
            self.skipTest("No Champions analyses cached and the mirror is unreachable")
        label, preview, rest = y
        self.assertEqual(label, "The play")
        self.assertIn("Mega Charizard Y", preview + " ".join(rest))
        x = mega_analysis("Charizard", "Charizard-Mega-X", ["Dragon Dance", "Flare Blitz"], "gen9championsou")
        self.assertNotEqual(x[1], preview)                             # X and Y have their own sets
        self.assertIsNone(mega_analysis("Lopunny", "Lopunny-Mega", [], "gen9ou"))   # only the format's own analysis


class TestGuideCombos(unittest.TestCase):
    def test_immunity_is_said_apart_from_resistance(self):
        from metamatch.engine.guide import _takes
        # Corviknight takes Ground for Tyranitar as an immunity, a free switch into Earthquake
        self.assertEqual(_takes(["Grass", "Ground", "Bug"], ["Flying", "Steel"]),
                         "is immune to Ground and resists Grass and Bug")
        self.assertEqual(_takes(["Fire"], ["Rock", "Dark"]), "resists Fire")


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


def _n(taken_hi, to_be_koed=None, to_ko=None, outspeeds=0.0, prio_move=None, taken_move="Earthquake"):
    return {"taken_hi": taken_hi, "taken_move": taken_move, "to_be_koed": to_be_koed, "to_ko": to_ko,
            "outspeeds": outspeeds, "prio_move": prio_move}


class TestBoardNumbers(unittest.TestCase):
    def test_cell_numbers_keep_what_the_guide_reads(self):
        from metamatch.engine.threat_board import cell_numbers
        hits = [("Earthquake", {"percent": [40.1, 47.3]}), ("Ice Spinner", {"percent": [20.0, 24.0]})]
        x = {"taken": hits[0], "taken_all": hits, "to_be_koed": 3, "to_ko": 2, "outspeeds": 0.8,
             "priority": (1, "Sucker Punch")}
        self.assertEqual(cell_numbers(x), {**_n(47.3, 3, 2, 0.8, "Sucker Punch"),
                                           "hits": [["Earthquake", 40.1, 47.3, "Physical"], ["Ice Spinner", 20.0, 24.0, "Physical"]]})
        self.assertIsNone(cell_numbers(None))
        self.assertEqual(cell_numbers({"taken": None, "outspeeds": 0.2, "priority": (0, None)})["taken_hi"], 0.0)

    def test_one_switch_in_rule(self):
        from metamatch.engine.threat_board import safe_switch
        self.assertTrue(safe_switch(_n(49.9, 2)))
        self.assertFalse(safe_switch(_n(50.0, 2)))
        self.assertTrue(safe_switch(_n(68.0, 3)))       # survives a second hit
        self.assertFalse(safe_switch(None))


class TestWatchAnswers(unittest.TestCase):
    def test_switch_in_takes_the_least_and_says_when_none_is_safe(self):
        from metamatch.engine.guide import _switch_in
        a = _switch_in({"Slowbro": _n(34, 3, taken_move="Crunch"), "Weavile": _n(90, 1)})
        self.assertEqual((a["member"], a["safe"]), ("Slowbro", True))
        self.assertIn("at most 34% from Crunch", a["text"])
        b = _switch_in({"Hatterene": _n(77, 2), "Weavile": _n(120, 1)})
        self.assertEqual((b["member"], b["safe"]), ("Hatterene", False))
        self.assertTrue(b["text"].startswith("No safe switch in"))
        self.assertIn("survives a second hit", _switch_in({"Moltres": _n(68, 3, taken_move="Draco Meteor")})["text"])

    def test_revenge_tiers(self):
        from metamatch.engine.guide import _revenge
        fast = {"Weavile": _n(90, 1, to_ko=1, outspeeds=0.9), "Kingambit": _n(30, 4, to_ko=1, prio_move="Sucker Punch")}
        self.assertIn("outspeeds it and knocks it out in one hit", _revenge(fast)["text"])
        prio = {"Kingambit": _n(30, 4, to_ko=1, outspeeds=0.1, prio_move="Sucker Punch")}
        self.assertEqual(_revenge(prio)["text"], "Kingambit's Sucker Punch knocks it out in one hit")
        two = {"Darkrai": _n(60, 2, to_ko=2, outspeeds=0.7)}
        self.assertTrue(_revenge(two)["text"].startswith("Wear it down first: Darkrai"))
        self.assertIsNone(_revenge({"Slowbro": _n(30, 4, to_ko=3, outspeeds=0.1)}))


class TestHazardPlan(unittest.TestCase):
    PASTE = """Charizard @ Charizardite Y
Ability: Blaze
- Flamethrower

Volcarona @ Heavy-Duty Boots
Ability: Flame Body
- Quiver Dance

Clefable @ Leftovers
Ability: Magic Guard
- Moonblast

Rotom-Wash @ Leftovers
Ability: Levitate
- Hydro Pump

Hatterene @ Leftovers
Ability: Magic Bounce
- Psyshock

Excadrill @ Air Balloon
Ability: Mold Breaker
- Rapid Spin
- Stealth Rock"""

    def setUp(self):
        from metamatch.engine.hazards import hazard_plan
        team, _ = readTeam(self.PASTE, "gen9natdex")
        self.h = hazard_plan(team, "gen9natdex")
        self.m = {m["name"]: m for m in self.h["members"]}

    def test_stealth_rock_and_spikes_per_member(self):
        self.assertEqual(self.m["Charizard"]["rocks"], 50.0)
        self.assertEqual(self.m["Volcarona"]["rocks"], 0.0)                      # Heavy-Duty Boots
        self.assertEqual(self.m["Clefable"]["protected"], "Magic Guard")
        self.assertEqual(self.m["Clefable"]["spikes1"], 0.0)
        for name in ("Charizard", "Rotom-Wash", "Excadrill"):                  # Flying, Levitate, Air Balloon
            self.assertFalse(self.m[name]["grounded"], name)
        self.assertEqual(self.m["Hatterene"]["spikes3"], 25.0)

    def test_team_side_and_verdict(self):
        self.assertEqual(self.h["bounce"], ["Hatterene"])
        self.assertEqual(self.h["boots"], ["Volcarona"])
        self.assertEqual([r["name"] for r in self.h["removers"]], ["Excadrill"])
        self.assertEqual([x["name"] for x in self.h["setters"]], ["Excadrill"])
        self.assertIn("half of Charizard's HP", self.h["verdict"])
        self.assertIn("Keep Excadrill healthy", self.h["verdict"])

    def test_never_suggests_boots_for_a_mega(self):
        from metamatch.engine.hazards import _verdict
        said = _verdict([{"name": "Charizard", "rocks": 50.0, "spikes1": 0.0, "mega": True}], [], [])
        self.assertNotIn("Boots", said)


class TestYourSix(unittest.TestCase):
    def test_safe_into_and_get_out_against(self):
        from metamatch.engine.guide import _six
        team = {"0": {"Pokemon": "Slowbro", "Roles": ["Wall", "Pivot", "Cleric"]}}
        cell = lambda verdict, n: {"Slowbro": {"verdict": verdict, "n": n}}
        rows = [{"name": "Great Tusk", "cells": cell("win", _n(30, 4, taken_move="Headlong Rush"))},
                {"name": "Kingambit", "cells": cell("lose", _n(70, 2, outspeeds=0.0, taken_move="Kowtow Cleave"))},
                {"name": "Alomomola", "cells": cell("lose", _n(20, 6, outspeeds=0.3))},      # a slow loss: no reason to leave
                {"name": "Kyurem", "cells": cell("even", _n(45, 3))},
                {"name": "Gholdengo", "cells": cell("lose", _n(110, 1, outspeeds=0.9, taken_move="Make It Rain"))}]
        m = _six(team, rows)[0]
        self.assertEqual(m["jobs"], ["Pivot", "Wall"])                         # the banner's job order
        self.assertEqual([x["name"] for x in m["safe"]], ["Great Tusk", "Kyurem"])
        self.assertEqual([x["name"] for x in m["out"]], ["Gholdengo", "Kingambit"])   # one hit knockouts first
        self.assertIn("a one hit knockout", m["out"][0]["tip"])
        self.assertEqual(m["safe"][0]["tip"], "takes at most 30% from Headlong Rush")


class TestOneFix(unittest.TestCase):
    def _setup(self, hazards=None, answers_tusk=()):
        from metamatch.engine.guide import Guide
        names = ["Kingambit", "Hatterene", "Pelipper", "Charizard", "Weavile", "Clefable"]
        team = {str(i): {"Pokemon": n} for i, n in enumerate(names)}
        team["3"]["Forme"] = "Charizard-Mega-Y"
        g = Guide("gen9ou", 3)
        g.win = {"name": "Kingambit"}
        g.hazards = hazards or {"setters": [{"name": "Weavile"}], "removers": [], "bounce": ["Hatterene"]}
        cells = {n: {"verdict": "even", "n": _n(70, 2)} for n in names}
        rows = [{"name": "Great Tusk", "usage": 30.0, "answers": list(answers_tusk), "losses": [], "cells": cells},
                {"name": "Gholdengo", "usage": 25.0, "answers": ["Pelipper", "Weavile"], "losses": ["Clefable"], "cells": cells},
                {"name": "Kyurem", "usage": 20.0, "answers": ["Clefable", "Kingambit"], "losses": [], "cells": cells}]
        return team, rows, g

    def test_never_swaps_a_protected_member(self):
        from metamatch.engine.guide import fix_target
        team, rows, g = self._setup()
        t = fix_target(team, rows, g)
        self.assertEqual(t["hole"]["name"], "Great Tusk")
        # Kingambit wins, Charizard is the Mega, Weavile the only setter, Hatterene the only hazard control
        self.assertNotIn(t["swap"], {"Kingambit", "Charizard", "Weavile", "Hatterene"})

    def test_swaps_the_member_doing_least(self):
        from metamatch.engine.guide import fix_target
        team, rows, g = self._setup()
        # Pelipper and Clefable each beat one; Clefable also loses one, so it goes
        self.assertEqual(fix_target(team, rows, g)["swap"], "Clefable")

    def test_the_holes_one_answer_stays_and_no_hole_means_no_card(self):
        from metamatch.engine.guide import fix_target
        team, rows, g = self._setup(answers_tusk=["Clefable"])
        self.assertEqual(fix_target(team, rows, g)["swap"], "Pelipper")
        for r in rows:
            r["answers"] = ["Pelipper", "Clefable"]
        self.assertIsNone(fix_target(team, rows, g))

    def test_pick_prefers_one_that_beats_the_hole(self):
        from metamatch.engine.guide import fix_pick
        picks = [{"name": "Ogerpon", "covers": ["Kyurem"]}, {"name": "Iron Valiant", "covers": ["Great Tusk"]}]
        self.assertEqual(fix_pick(picks, "Great Tusk")["name"], "Iron Valiant")
        self.assertEqual(fix_pick(picks, "Zamazenta")["name"], "Ogerpon")
        self.assertIsNone(fix_pick([{"name": "Gholdengo", "covers": []}], "Great Tusk"))


class TestSharedMoveLists(unittest.TestCase):
    def test_lists_read_from_showdown_data(self):
        from metamatch.engine import moves
        self.assertEqual(moves.HAZARDS, ("Stealth Rock", "Spikes", "Toxic Spikes", "Sticky Web"))
        self.assertTrue({"U-turn", "Volt Switch", "Flip Turn", "Shed Tail", "Chilly Reception"} <= set(moves.PIVOTS))
        self.assertNotIn("Revival Blessing", moves.PIVOTS)
        self.assertTrue({"Thunderclap", "Jet Punch", "Water Shuriken", "Sucker Punch", "Extreme Speed"} <= moves.PRIORITY)
        self.assertFalse({"Fake Out", "Feint", "Bide"} & moves.PRIORITY)
        self.assertIn("Mortal Spin", moves.REMOVAL)

    def test_priority_through_an_ability(self):
        from metamatch.engine.moves import is_priority
        self.assertTrue(is_priority("Grassy Glide", ["Grassy Surge"]))
        self.assertFalse(is_priority("Grassy Glide", ["Overgrow", None]))
        self.assertFalse(is_priority("Thunderbolt", ["Protosynthesis", None]))   # None (no Mega ability) matches nothing

    def test_roles_use_the_shared_lists(self):
        from metamatch.team import detectRole
        from metamatch.recommender import ROLE_FILL_MOVES
        paste = ("Raging Bolt @ Booster Energy\nAbility: Protosynthesis\n- Thunderclap\n- Draco Meteor\n\n"
                 "Barraskewda @ Choice Band\nAbility: Swift Swim\n- Liquidation\n- Flip Turn\n\n"
                 "Glimmora @ Focus Sash\nAbility: Toxic Debris\n- Mortal Spin\n- Power Gem")
        team, _ = readTeam(paste, "gen9ou")
        detectRole(team)
        roles = {p["Pokemon"]: p["Roles"] for p in team.values()}
        self.assertIn("Priority User", roles["Raging Bolt"])
        self.assertIn("Pivot", roles["Barraskewda"])
        self.assertIn("Hazard Remover", roles["Glimmora"])
        self.assertIn("mortalspin", ROLE_FILL_MOVES["Hazard Remover"])
        self.assertIn("chillyreception", ROLE_FILL_MOVES["Pivot"])


class TestYourWalls(unittest.TestCase):
    def test_recovery_and_status_lists(self):
        from metamatch.engine.moves import RECOVERY, STATUS_MOVES, category
        self.assertEqual((RECOVERY["Slack Off"], RECOVERY["Roost"], RECOVERY["Shore Up"]), (0.5, 0.5, 0.5))
        self.assertIsNone(RECOVERY["Strength Sap"])
        self.assertEqual(STATUS_MOVES["Will-O-Wisp"], ("brn", 100))
        self.assertEqual(STATUS_MOVES["Scald"], ("brn", 30))
        self.assertEqual(STATUS_MOVES["Toxic"], ("tox", 100))
        self.assertEqual(category("Make It Rain"), "Special")

    def test_recovery_lines(self):
        from metamatch.engine.defense import recovery
        p = {"Pokemon": "Slowbro", "Ability": "Regenerator", "Item": "Leftovers", "Type": ["Water", "Psychic"],
             "Moves": [{"name": "Scald"}, {"name": "Slack Off"}]}
        r = recovery(p)
        self.assertEqual((r["move"], r["heal"], r["regenerator"], r["passive"]), ("Slack Off", 0.5, True, True))
        self.assertEqual(r["lines"], ["Slack Off heals 50%", "Regenerator heals 33% when it switches out",
                                      "Leftovers heals 6% a turn"])
        rest = recovery({"Pokemon": "Dondozo", "Moves": [{"name": "Rest"}], "Item": "Black Sludge", "Type": ["Water"]})
        self.assertIsNone(rest["heal"])                                      # asleep: no healing through a hit
        self.assertFalse(rest["passive"])                                    # Black Sludge hurts a non Poison type

    def test_walls_pivots_and_breaks(self):
        from metamatch.engine.defense import classify
        slack = {"heal": 0.5, "regenerator": True}
        regen = {"heal": None, "regenerator": True}
        self.assertEqual(classify(_n(34, 3), slack), "walls")
        self.assertEqual(classify(_n(52, 3), slack), "pivots")            # survives a second hit
        self.assertEqual(classify(_n(87, 2), slack), "breaks")
        self.assertEqual(classify(_n(30, 4), regen), "walls")             # Regenerator heals more than it took
        self.assertEqual(classify(_n(40, 3), regen), "pivots")
        self.assertIsNone(classify(_n(70, 3, taken_move="x") | {"to_be_koed": None, "taken_hi": 70}, regen))

    def test_bulk_counts_assault_vest_and_eviolite(self):
        from unittest import mock
        from metamatch.engine import defense
        stats = {"hp": 300, "atk": 100, "def": 200, "spa": 100, "spd": 200, "spe": 100}
        with mock.patch("metamatch.engine.solvers._stats", return_value=stats):
            av = defense.bulk({"Pokemon": "Goodra", "Item": "Assault Vest", "Moves": [{"name": "Draco Meteor"}]}, "sv")
            ev = defense.bulk({"Pokemon": "Chansey", "Item": "Eviolite", "Moves": [{"name": "Seismic Toss"}]}, "sv")
        self.assertEqual((av["physical"], av["special"], av["lean"]), (60000, 90000.0, "special"))
        self.assertEqual((ev["physical"], ev["special"], ev["lean"]), (90000.0, 90000.0, None))

    def test_who_status_cant_touch(self):
        from metamatch.engine.defense import HELPED_BY, _immune
        self.assertTrue(_immune("brn", ["Fire", "Ghost"], "Flash Fire"))
        self.assertTrue(_immune("psn", ["Steel", "Ghost"], "Good as Gold"))
        self.assertTrue(_immune("brn", ["Water"], "Water Veil"))
        self.assertFalse(_immune("brn", ["Ground", "Fighting"], "Protosynthesis"))
        self.assertIn("Guts", HELPED_BY["brn"])

    def test_summary_names_the_open_side(self):
        from metamatch.engine.defense import _summary
        def row(name, cat, takers):
            cells = {m: {"n": {**_n(30 if m in takers else 70, 3 if m in takers else 2), "hits": [["Hit", 1, 70, cat]]}}
                     for m in ("Slowbro", "Weavile")}
            return {"name": name, "cells": cells}
        cards = [{"name": "Slowbro"}]
        rows = [row("Great Tusk", "Physical", ["Slowbro"]), row("Gholdengo", "Special", []), row("Raging Bolt", "Special", [])]
        self.assertEqual(_summary({}, rows, cards), "Slowbro takes the physical hits, but nothing on your team safely "
                                                    "takes special ones from Gholdengo and Raging Bolt.")
        self.assertIsNone(_summary({}, rows[:2], cards))                   # one open threat isn't a pattern

    def test_a_burn_halves_physical_hits(self):
        from metamatch.engine.dex import dex_for_format
        from metamatch.engine.sets import likely_set
        from metamatch.logic_engine import best_hits
        team, _ = readTeam("Slowbro @ Leftovers\nAbility: Regenerator\nEVs: 252 HP / 252 Def / 4 SpD\nBold Nature\n"
                           "- Scald\n- Slack Off", "gen9ou")
        p, s = list(team.values())[0], likely_set("Great Tusk", "gen9ou")
        plain = best_hits(p, s, "sv", dex_for_format("gen9ou"), n=4) if s else None
        if not plain:
            self.skipTest("No damage calc or usage data")
        burned = best_hits(p, dict(s, status="brn"), "sv", dex_for_format("gen9ou"), n=4)
        self.assertAlmostEqual(burned[1][0][1]["percent"][1], plain[1][0][1]["percent"][1] / 2, delta=1.5)


class TestFixFit(unittest.TestCase):
    def test_pairing_line(self):
        from metamatch.engine.guide import fix_fit
        often = fix_fit({}, {"name": "Missingno", "pairs": [("Pelipper", 0.12, 57.5)]}, "gen9ou")
        self.assertEqual(often["pairing"], "Players run it on 12% of teams with Pelipper, 58x more often than usual")
        self.assertEqual(fix_fit({}, {"name": "Missingno", "pairs": [("Weavile", 0.05, 1.2)]}, "gen9ou")["pairing"],
                         "Players sometimes run it with Weavile")
        self.assertIsNone(fix_fit({}, {"name": "Missingno", "pairs": [("Weavile", 0.01, 0.9)]}, "gen9ou")["pairing"])

    def test_the_pick_joins_the_teams_sun(self):
        from metamatch.engine import calc
        from metamatch.engine.guide import fix_fit
        if not calc.available():
            self.skipTest("No damage calc")
        rest, _ = readTeam("Charizard @ Charizardite Y\nAbility: Blaze\nTimid Nature\nEVs: 252 SpA / 252 Spe\n"
                           "- Flamethrower\n- Solar Beam", "gen9natdex")
        fit = fix_fit(rest, {"name": "Raging Bolt", "pairs": []}, "gen9natdex")
        self.assertTrue(any("Charizard's sun" in line for line in fit["cores"]), fit)


class TestTeraKeepsAbilityImmunities(unittest.TestCase):
    def test_levitate_air_balloon_and_thick_fat_survive_tera(self):
        from metamatch.engine.guide import team_guide
        team, _ = readTeam("Gholdengo @ Air Balloon\nAbility: Good as Gold\nTera Type: Electric\n- Make It Rain\n- Thunderbolt\n\n"
                           "Rotom-Wash @ Leftovers\nAbility: Levitate\nTera Type: Steel\n- Hydro Pump\n- Volt Switch\n\n"
                           "Snorlax @ Leftovers\nAbility: Thick Fat\nTera Type: Grass\n- Body Slam\n- Curse", "gen9ou")
        after = {x["name"]: x["after"] for x in team_guide(team, "gen9ou", rows=[]).tera}
        self.assertEqual(after["Gholdengo"], [])                          # Tera Electric, but the balloon still floats
        self.assertNotIn("Ground", after["Rotom-Wash"])                   # Levitate outlasts the Steel typing
        self.assertFalse({"Fire", "Ice"} & set(after["Snorlax"]))         # Thick Fat still halves them


class TestSpeedShareCountsScarf(unittest.TestCase):
    def test_a_scarf_minority_lowers_the_ladder_share(self):
        import re
        from metamatch.engine import calc
        from metamatch.engine.sets import likely_set
        if not calc.available() or not likely_set("Dragapult", "gen9championsou"):
            self.skipTest("No damage calc or Champions data")
        from metamatch.agents import AgentManager
        team, w = readTeam("Garchomp @ Choice Scarf\nAbility: Rough Skin\nLevel: 50\nEVs: 2 HP / 32 Atk / 32 Spe\nJolly Nature\n"
                           "- Earthquake\n- Dragon Claw", "gen9championsou")
        out = "".join(AgentManager().get_response("Does my Garchomp outspeed Dragapult?", team, w))
        share = int(re.search(r"Garchomp outspeeds (\d+)%", out).group(1))
        scarf = likely_set("Dragapult", "gen9championsou")["scarf_share"]
        self.assertLess(share, 100)                                   # Scarf Dragapult outspeeds Scarf Garchomp
        self.assertAlmostEqual(share / 100, 1 - scarf, delta=0.02)
        self.assertIn("carry Choice Scarf", out)


if __name__ == "__main__":
    unittest.main()
