"""RAG chunking, scoping and filtering. No embedding model or network needed."""
import unittest

from metamatch.agents.coach import _relevant, _source_label
from metamatch.rag import chunking, store
from metamatch.rag.scraper import analysis_chunks

LONG = " ".join(f"Sentence number {i} explains how this Pokemon plays into common threats." for i in range(40))


class TestChunking(unittest.TestCase):
    def test_chunks_respect_size_and_sentence_boundaries(self):
        parts = chunking.split_paragraphs([LONG])
        self.assertGreater(len(parts), 1)
        for p in parts:
            self.assertLessEqual(len(p), chunking.MAX_CHARS + chunking.TAIL_SLACK)
            self.assertTrue(p.endswith("."), p[-30:])

    def test_short_tail_joins_previous_chunk_when_there_is_room(self):
        para = " ".join(["This sentence is filler about a defensive pivot."] * 8)  # about 400 characters
        self.assertEqual(len(chunking.split_paragraphs([para, "Tiny tail."])), 1)
        # No text is ever dropped
        parts = chunking.split_paragraphs([LONG, "Tiny tail."])
        self.assertTrue(parts[-1].endswith("Tiny tail."))

    def test_analysis_chunks_have_headers_and_no_empty_bodies(self):
        data = {"Kingambit": {"overview": "", "sets": {"Swords Dance": {"description": f"<p>{LONG}</p>"},
                                                       "Empty": {"description": ""}},
                              "comments": "<p>Other options include Iron Head for Fairy types, which is a fine choice "
                                          "when the team lacks a Steel move and needs to hit Fairy types hard.</p>"}}
        chunks = analysis_chunks(data, "gen9uu")
        self.assertTrue(chunks)
        for c in chunks:
            self.assertTrue(c["text"].startswith("Pokemon: Kingambit | Section: "))
            self.assertTrue(chunking.body(c["text"]).strip())
            self.assertEqual((c["metadata"]["format"], c["metadata"]["game"]), ("gen9uu", "sv"))
        self.assertNotIn("Set Empty", {c["metadata"]["section"] for c in chunks})


class TestScoping(unittest.TestCase):
    def test_format_falls_back_to_ou_only_without_own_analyses(self):
        metas = [{"format": "gen9ou"}, {"format": "gen9uu"}, {"format": "any"}]
        self.assertEqual(store._formats_for("gen9uu", metas), {"gen9uu", "any"})
        self.assertEqual(store._formats_for("gen9natdex", metas), {"gen9natdex", "any", "gen9ou"})
        self.assertEqual(store._formats_for("gen9championsou", metas), {"gen9championsou", "any"})

    def test_relevance_matches_megas_and_concepts(self):
        mega = {"metadata": {"pokemon": "Absol-Mega", "type": "community_guide"}}
        self.assertTrue(_relevant(mega, {"Absol"}))
        self.assertFalse(_relevant(mega, {"Garchomp"}))
        self.assertTrue(_relevant({"metadata": {"pokemon": "Concept", "type": "concept"}}, set()))

    def test_source_labels(self):
        self.assertEqual(_source_label({"pokemon": "Kingambit", "section": "Set Swords Dance", "source": "smogon_analysis"}),
                         "Kingambit, Set Swords Dance (Smogon analysis)")
        self.assertEqual(_source_label({"pokemon": "Concept", "section": "Pivoting and Momentum", "source": "concepts"}),
                         "Pivoting and Momentum (concept note)")

    def test_bm25_prefers_exact_terms(self):
        docs = ["Pokemon: A | Section: x | Format: y\nKnock Off removes items from walls.",
                "Pokemon: B | Section: x | Format: y\nThis Pokemon sets up with Swords Dance."]
        store._corpus.cache_clear()
        real = store.get_collection
        store.get_collection = lambda: type("C", (), {"get": lambda self, include: {
            "ids": ["a", "b"], "documents": docs, "metadatas": [{}, {}]}})()
        try:
            corpus = store._corpus(-1)
            scores = store._bm25("who runs knock off", [0, 1], corpus)
            self.assertEqual(max(scores, key=scores.get), 0)
        finally:
            store.get_collection = real
            store._corpus.cache_clear()


class TestCorpusFixes(unittest.TestCase):
    def test_dangling_opener_joins_the_piece_before_it(self):
        pieces = ["Kingambit sets up with Swords Dance against passive foes.", "However, it fears burns."]
        self.assertEqual(chunking.join_dangling(pieces), [" ".join(pieces)])
        self.assertEqual(len(chunking.join_dangling(["Kingambit is strong.", "Gholdengo blocks hazard removal."])), 2)

    def test_dangling_join_never_exceeds_the_size_limit(self):
        big = "x" * chunking.MAX_CHARS
        self.assertEqual(len(chunking.join_dangling([big, "However, " + "y" * 300])), 2)

    def test_mega_set_is_filed_under_the_mega_from_its_stone(self):
        data = {"Charizard": {"sets": {"Drought Wallbreaker": {"description": "<p>Fires off Solar Beam in its own sun, breaking through the bulkiest walls.</p>"},
                                       "Setup Sweeper": {"description": "<p>Dragon Dance boosts it into a fast physical sweeper late in the game.</p>"}}}}
        strat = {"Charizard": {"sets": {"Drought Wallbreaker (NatDex)": {"item": "Charizardite Y"},
                                        "Setup Sweeper (NatDex)": {"item": "Charizardite X"}}}}
        by_set = {c["metadata"]["set_name"]: c["metadata"] for c in analysis_chunks(data, "gen9natdex", strat)}
        self.assertEqual(by_set["Drought Wallbreaker"]["pokemon"], "Charizard-Mega-Y")
        self.assertEqual(by_set["Setup Sweeper"]["pokemon"], "Charizard-Mega-X")
        self.assertEqual(by_set["Drought Wallbreaker"]["species"], "Charizard")

    def test_mega_set_is_found_from_its_text_without_item_data(self):
        data = {"Charizard": {"sets": {"Wallbreaker": {"description": "<p>Mega Charizard Y sets the sun on entry and fires off Solar Beam freely.</p>"}}}}
        meta = analysis_chunks(data, "gen9championsou")[0]["metadata"]
        self.assertEqual((meta["pokemon"], meta["game"], meta["format"]), ("Charizard-Mega-Y", "champions", "gen9championsou"))

    def test_formats_without_megas_keep_the_base_name(self):
        data = {"Charizard": {"sets": {"Sun": {"description": "<p>Mega Charizard Y is not legal here, so this set runs Heavy-Duty Boots.</p>"}}}}
        self.assertEqual(analysis_chunks(data, "gen9ou")[0]["metadata"]["pokemon"], "Charizard")

    def test_exact_duplicates_are_dropped(self):
        from metamatch.rag.build_index import dedupe
        chunks = [{"text": "same"}, {"text": "same "}, {"text": "other"}]
        self.assertEqual([c["text"] for c in dedupe(chunks)], ["same", "other"])

    def test_champions_uu_reads_champions_ou_analyses(self):
        formats = store._formats_for("gen9championsuu", [{"format": "gen9championsuu"}])
        self.assertIn("gen9championsou", formats)


class TestBenchmarkStats(unittest.TestCase):
    def setUp(self):
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[3] / "bench" / "rag" / "score.py"
        spec = importlib.util.spec_from_file_location("rag_score", path)
        self.score = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.score)

    def test_ndcg_rewards_relevant_hits_ranked_first(self):
        self.assertEqual(self.score.ndcg5([True, False, False]), 1.0)
        self.assertLess(self.score.ndcg5([False, True]), 1.0)
        self.assertEqual(self.score.ndcg5([False, False]), 0.0)

    def test_permutation_test_separates_real_and_no_difference(self):
        self.assertEqual(self.score.permutation_test([1, 0, 1], [1, 0, 1]), 1.0)
        self.assertLess(self.score.permutation_test([1] * 12, [0] * 12, rounds=2000), 0.01)


if __name__ == "__main__":
    unittest.main()
