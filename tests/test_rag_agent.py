"""Unit tests for the RAG agent (Stage 9 phase 1-3).

Only pure logic is exercised here: chunking, embeddings, cosine, exams
profiles, retrieval ordering and bands, and index persistence shape.
Network-dependent paths (Gemini embed, live feeds) are verified live
separately; the keyword embedder is the offline baseline.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import ai_engine.rag_agent as rag  # noqa: E402

ITEM = {
    'title': 'RBI holds repo rate, flags inflation risk',
    'summary': 'The central bank kept the policy rate unchanged and '
               'highlighted inflation management for scheduled banks.',
    'source': 'The Hindu',
    'published': '2026-11-04',
    'url': 'https://example.com/rbi',
}


class TestKeywordEmbedding(unittest.TestCase):
    def test_deterministic_and_normalized(self):
        a = rag.keyword_embedding('rbi monetary policy framework')
        b = rag.keyword_embedding('rbi monetary policy framework')
        self.assertEqual(a, b)
        self.assertAlmostEqual(sum(v * v for v in a), 1.0, places=9)

    def test_related_text_scores_higher_than_unrelated(self):
        probe = rag.keyword_embedding('rbi repo rate monetary policy')
        related = rag.keyword_embedding('RBI kept the repo rate unchanged')
        unrelated = rag.keyword_embedding('cricket world cup final match')
        self.assertGreater(rag.cosine(probe, related), rag.cosine(probe, unrelated))

    def test_empty_text_is_zero_vector(self):
        self.assertEqual(rag.keyword_embedding(''), rag.keyword_embedding(''))


class TestChunking(unittest.TestCase):
    def test_chunk_item_combines_title_and_summary(self):
        chunk = rag.chunk_item(ITEM)
        self.assertIn(ITEM['title'], chunk)
        self.assertIn('scheduled banks', chunk)

    def test_chunk_item_empty(self):
        self.assertEqual(rag.chunk_item({}), '')


class TestIndexLifecycle(unittest.TestCase):
    def test_build_and_retrieve_roundtrip_keyword(self):
        items = [ITEM, dict(ITEM, title='Cricket final', url='u2')]
        index = rag.build_index(items, embedder_name='keyword')
        self.assertEqual(index['embedder'], 'keyword')
        self.assertEqual(len(index['entries']), 2)

        result = rag.retrieve_for_exam(index, 'Banking', top_k=2)
        self.assertEqual(result['exam'], 'Banking')
        # The RBI item must outrank the cricket item for Banking.
        self.assertEqual(result['items'][0]['url'], ITEM['url'])
        self.assertIn('monetary policy', result['items'][0]['topics'][0])
        self.assertIn(result['items'][0]['band'], ('strong', 'moderate', 'weak'))

    def test_unknown_exam_raises(self):
        index = rag.build_index([ITEM], embedder_name='keyword')
        with self.assertRaises(ValueError):
            rag.retrieve_for_exam(index, 'Rugby')

    def test_index_persistence_roundtrip(self):
        index = rag.build_index([ITEM], embedder_name='keyword')
        original_path = rag.INDEX_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                rag.INDEX_PATH = str(Path(tmp) / 'idx.json')
                rag.save_index(index)
                reloaded = rag.load_index()
                self.assertIsNotNone(reloaded)
                self.assertEqual(reloaded['embedder'], 'keyword')
                self.assertEqual(
                    len(reloaded['entries']),
                    len(index['entries']),
                )
        finally:
            rag.INDEX_PATH = original_path

    def test_load_index_missing_file(self):
        original_path = rag.INDEX_PATH
        try:
            rag.INDEX_PATH = str(Path(tempfile.gettempdir()) / 'no-such-idx.json')
            self.assertIsNone(rag.load_index())
        finally:
            rag.INDEX_PATH = original_path


class TestExamProfiles(unittest.TestCase):
    def test_every_taxonomized_exam_has_profile(self):
        for exam in rag.EXAM_TOPICS:
            with self.subTest(exam=exam):
                profile = rag.exam_profile(exam, rag.keyword_embedding)
                vector, phrases = profile
                self.assertEqual(len(phrases), len(rag.EXAM_TOPICS[exam]))
                self.assertAlmostEqual(sum(v * v for v in vector), 1.0, places=9)

    def test_unknown_exam_no_profile(self):
        self.assertIsNone(rag.exam_profile('Rugby', rag.keyword_embedding))


class TestBands(unittest.TestCase):
    def test_band_ordering(self):
        self.assertEqual(rag.match_band(0.99, 'keyword'), 'strong')
        self.assertEqual(rag.match_band(0.15, 'keyword'), 'moderate')
        self.assertEqual(rag.match_band(0.0, 'keyword'), 'weak')


class TestRelatedForArticle(unittest.TestCase):
    def test_related_prefers_matching_items(self):
        items = [ITEM, dict(ITEM, title='Cricket final', url='u2')]
        index = rag.build_index(items, embedder_name='keyword')
        related = rag.related_for_article(
            index, 'The RBI decided to keep the repo rate unchanged.', 'Banking',
        )
        self.assertEqual(related[0]['url'], ITEM['url'])
        self.assertIn('similarity', related[0])


if __name__ == '__main__':
    unittest.main()
