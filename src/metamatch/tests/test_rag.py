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


if __name__ == "__main__":
    unittest.main()
