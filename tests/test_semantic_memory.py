import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

try:
    import tests  # noqa: F401  # Ensure tests/__init__.py sets MAYBEAI_LLM_PROVIDER=mock
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

from core.memory.embedding import EmbeddingEngine
from core.memory.database import MemoryDatabase
from core.memory.retriever import MemoryRetriever


class _FakeEmbedResp:
    def __init__(self, status: int, json_data: dict):
        self.status = status
        self._json_data = json_data

    async def json(self):
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEmbedSession:
    def __init__(self, response: _FakeEmbedResp, captured: dict):
        self._response = response
        self._captured = captured

    def post(self, url, headers=None, json=None):
        self._captured["url"] = url
        self._captured["headers"] = headers or {}
        self._captured["json"] = json
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestSemanticEmbeddingEngine(unittest.IsolatedAsyncioTestCase):
    def test_auto_provider_skips_cloud_in_mock_mode(self):
        with patch.dict(
            os.environ,
            {
                "MAYBEAI_LLM_PROVIDER": "mock",
                "MAYBEAI_EMBEDDING_PROVIDER": "",
                "GEMINI_API_KEY": "fake-gem-key",
                "OPENAI_API_KEY": "fake-oai-key",
            },
            clear=False,
        ), patch.object(EmbeddingEngine, "_try_init_local", return_value=False):
            eng = EmbeddingEngine(provider="auto")
            self.assertEqual(eng.active_backend, "hash")

    def test_explicit_provider_selection_and_missing_key_fallback(self):
        with patch.object(EmbeddingEngine, "_try_init_local", return_value=False):
            with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
                eng_no_key = EmbeddingEngine(provider="gemini")
                self.assertEqual(eng_no_key.active_backend, "hash")

            with patch.dict(os.environ, {"GEMINI_API_KEY": "test-gem"}, clear=False):
                eng_gem = EmbeddingEngine(provider="gemini")
                self.assertEqual(eng_gem.active_backend, "gemini")

            with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
                eng_no_oai = EmbeddingEngine(provider="openai")
                self.assertEqual(eng_no_oai.active_backend, "hash")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
                eng_oai = EmbeddingEngine(provider="openai")
                self.assertEqual(eng_oai.active_backend, "openai")

            eng_local_fallback = EmbeddingEngine(provider="local")
            self.assertEqual(eng_local_fallback.active_backend, "hash")

    def test_lru_cache_hits_misses_eviction_and_set_provider_clears(self):
        eng = EmbeddingEngine(dimension=128, provider="hash", cache_size=16)
        v1 = eng.encode("Eve likes chess and minecraft")
        v2 = eng.encode("Eve likes chess and minecraft")
        self.assertTrue(np.allclose(v1, v2))

        st = eng.get_status()
        self.assertEqual(st["active_backend"], "hash")
        self.assertEqual(st["cache_misses"], 1)
        self.assertEqual(st["cache_hits"], 1)
        self.assertEqual(st["cache_entries"], 1)

        # Fill past cache_size=16 to trigger LRU eviction
        for i in range(20):
            eng.encode(f"unique sentence number {i}")
        self.assertEqual(eng.get_status()["cache_entries"], 16)

        # Switching provider clears cache
        eng.set_provider("hash")
        self.assertEqual(eng.get_status()["cache_entries"], 0)
        self.assertEqual(eng.get_status()["cache_hits"], 0)

    async def test_mocked_gemini_and_openai_aencode(self):
        # Gemini text-embedding-004
        gem_captured = {}
        gem_vec = [0.1] * 16
        gem_resp = _FakeEmbedResp(200, {"embedding": {"values": gem_vec}})

        with patch.dict(os.environ, {"GEMINI_API_KEY": "gem-emb-key"}, clear=False), \
             patch("aiohttp.ClientSession", side_effect=lambda *a, **kw: _FakeEmbedSession(gem_resp, gem_captured)):
            eng = EmbeddingEngine(provider="gemini")
            out = await eng.aencode("Minecraft diamond gift")

        self.assertEqual(out.shape, (16,))
        self.assertAlmostEqual(float(np.linalg.norm(out)), 1.0, places=4)
        self.assertEqual(gem_captured["headers"].get("x-goog-api-key"), "gem-emb-key")
        self.assertIn("text-embedding-004:embedContent", gem_captured["url"])

        # OpenAI text-embedding-3-small
        oai_captured = {}
        oai_vec = [0.2] * 32
        oai_resp = _FakeEmbedResp(200, {"data": [{"embedding": oai_vec}]})

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-emb-key"}, clear=False), \
             patch("aiohttp.ClientSession", side_effect=lambda *a, **kw: _FakeEmbedSession(oai_resp, oai_captured)):
            eng2 = EmbeddingEngine(provider="openai")
            out2 = await eng2.aencode("Chess queen blunder")

        self.assertEqual(out2.shape, (32,))
        self.assertAlmostEqual(float(np.linalg.norm(out2)), 1.0, places=4)
        self.assertEqual(oai_captured["headers"].get("Authorization"), "Bearer sk-emb-key")

    def test_cosine_similarity_dimension_mismatch_returns_zero(self):
        eng = EmbeddingEngine(provider="hash")
        v128 = np.ones(128, dtype=np.float32)
        v384 = np.ones(384, dtype=np.float32)
        self.assertEqual(eng.cosine_similarity(v128, v384), 0.0)
        self.assertEqual(eng.cosine_similarity(None, v128), 0.0)
        self.assertEqual(eng.cosine_similarity(np.zeros(128, dtype=np.float32), v128), 0.0)


class TestDimensionMismatchSafety(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_dir = Path(self._temp_dir_obj.name)
        self.db = MemoryDatabase(
            db_path=str(self.temp_dir / "semantic_test.db"),
            embedding_provider="hash",
        )
        self.retriever = MemoryRetriever(db=self.db)

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    async def test_vector_search_and_retriever_handle_mismatched_dimensions_safely(self):
        # Store a legacy 64-d vector alongside a normal 128-d vector
        legacy_vec = np.ones(64, dtype=np.float32)
        legacy_vec /= np.linalg.norm(legacy_vec)
        mid_legacy = self.db.add_episodic_memory(
            title="Legacy Diamond Memory",
            content="Steve gave Eve a shiny diamond in Minecraft cave",
            episode_type="minecraft_gift",
            user="Steve",
            embedding=legacy_vec,
        )

        # 1. Search with 384-d query vector when reencode_mismatched=False -> safely returns []
        q384 = np.ones(384, dtype=np.float32)
        q384 /= np.linalg.norm(q384)
        res_skip = self.db.vector_search(q384, top_k=5, reencode_mismatched=False)
        self.assertEqual(res_skip, [])

        # 2. Search with 128-d query vector when reencode_mismatched=True -> re-encodes legacy row to 128-d!
        q128 = self.db.embedder.encode("Steve diamond Minecraft cave")
        res_reencoded = self.db.vector_search(q128, top_k=5, reencode_mismatched=True)
        self.assertGreaterEqual(len(res_reencoded), 1)
        self.assertEqual(res_reencoded[0][0]["id"], mid_legacy)

        # Verify persisted vector in SQLite is now 128-d
        stored = self.db.get_memory(mid_legacy)
        self.assertEqual(stored["_embedding_vec"].shape, (128,))

        # 3. Insert another mismatched 768-d vector and verify async ahybrid_search & arecall never raise
        vec768 = np.ones(768, dtype=np.float32)
        vec768 /= np.linalg.norm(vec768)
        self.db.add_episodic_memory(
            title="High-Dim Memory",
            content="Evan played chess and blundered his queen",
            episode_type="chess",
            user="Evan",
            embedding=vec768,
        )

        async_hits = await self.db.ahybrid_search("chess queen Evan", top_k=3)
        self.assertGreaterEqual(len(async_hits), 1)

        recall = await self.retriever.arecall(query="chess queen", current_user="Evan", top_k=3)
        self.assertIsNotNone(recall.user_profile)
        self.assertGreaterEqual(len(recall.episodes), 1)


if __name__ == "__main__":
    unittest.main()
