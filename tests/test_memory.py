import os
import shutil
import tempfile
import unittest
from pathlib import Path
import numpy as np

from core.memory.embedding import EmbeddingEngine
from core.memory.database import MemoryDatabase
from core.memory.markdown_sync import MarkdownBrainSync
from core.memory.extractor import MemoryExtractor
from core.memory.retriever import MemoryRetriever
from core.memory import EpisodicMemoryStore
from core.conversation.engine import ConversationEngine

class TestEmbeddingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = EmbeddingEngine(dimension=128)

    def test_encode_and_shape(self):
        vec = self.engine.encode("Steve gave Eve a Diamond in Minecraft")
        self.assertEqual(vec.shape, (128,))
        self.assertEqual(vec.dtype, np.float32)
        # Vector should be L2-normalized
        self.assertAlmostEqual(float(np.linalg.norm(vec)), 1.0, places=4)

    def test_semantic_similarity(self):
        v1 = self.engine.encode("Steve gave Eve a diamond in Minecraft")
        v2 = self.engine.encode("Steve handed a diamond to Eve")
        v3 = self.engine.encode("Completely unrelated topic about cooking pizza")

        sim_12 = self.engine.cosine_similarity(v1, v2)
        sim_13 = self.engine.cosine_similarity(v1, v3)

        self.assertGreater(sim_12, sim_13)
        self.assertGreater(sim_12, 0.4)

    def test_serialization(self):
        vec = self.engine.encode("test vector text")
        blob = self.engine.serialize(vec)
        restored = self.engine.deserialize(blob)
        self.assertTrue(np.allclose(vec, restored))


class TestEmbeddingSessionPooling(unittest.IsolatedAsyncioTestCase):
    async def test_shared_session_reuse_and_aclose(self):
        engine = EmbeddingEngine(dimension=128, provider="hash")
        s1 = await engine._get_session()
        s2 = await engine._get_session()
        self.assertIs(s1, s2)
        self.assertFalse(s1.closed)

        await engine.aclose()
        self.assertTrue(s1.closed)
        self.assertIsNone(engine._session)

        s3 = await engine._get_session()
        self.assertIsNot(s3, s1)
        await engine.close()
        self.assertTrue(s3.closed)


class TestMemoryDatabaseAndSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = str(Path(self.temp_dir) / "test_memory.db")
        self.brain_dir = str(Path(self.temp_dir) / "test_brain")
        self.db = MemoryDatabase(db_path=self.db_path)
        self.sync = MarkdownBrainSync(base_dir=self.brain_dir)
        self.extractor = MemoryExtractor(db=self.db, markdown_sync=self.sync)
        self.retriever = MemoryRetriever(db=self.db)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_episodic_memory_creation_and_search(self):
        mem_id = self.extractor.record_episode(
            title="Steve Memberi Diamond",
            content="Steve memberikan 1 diamond di goa Minecraft saat kami sedang menambang.",
            episode_type="minecraft_gift",
            user="Steve",
            emotional_tag="happy",
            importance_score=0.9,
            game_context="Minecraft Survival"
        )
        self.assertIsInstance(mem_id, int)

        # FTS5 keyword search
        fts_res = self.db.fts_search("diamond")
        self.assertGreaterEqual(len(fts_res), 1)
        self.assertEqual(fts_res[0][0]["user"], "Steve")

        # Hybrid search
        hybrid_res = self.db.hybrid_search("siapa yang ngasih diamond di goa")
        self.assertGreaterEqual(len(hybrid_res), 1)
        self.assertEqual(hybrid_res[0]["user"], "Steve")

        # Check Markdown sync files
        journal_files = list((Path(self.brain_dir) / "journals").glob("*.md"))
        self.assertGreaterEqual(len(journal_files), 1)
        journal_content = journal_files[0].read_text(encoding="utf-8")
        self.assertIn("Steve Memberi Diamond", journal_content)

        user_dossier = Path(self.brain_dir) / "users" / "Steve.md"
        self.assertTrue(user_dossier.exists())
        self.assertIn("Steve Memberi Diamond", user_dossier.read_text(encoding="utf-8"))

    def test_user_profiles_and_preferences(self):
        # Record chat preference
        self.extractor.extract_from_chat("Sultan", "aku suka banget martabak manis keju!")
        profile = self.db.get_or_create_user("Sultan")
        self.assertEqual(profile["username"], "Sultan")
        self.assertIn("martabak manis keju", profile["preferences"].get("likes", []))

        # Record chess game outcome
        self.extractor.on_chess_game_ended(
            player="Evan",
            eve_won=True,
            player_won=False,
            result="checkmate",
            moves_count=14,
            elo=1400
        )
        evan_prof = self.db.get_or_create_user("Evan")
        self.assertEqual(evan_prof["games_played"].get("chess"), 1)
        self.assertEqual(evan_prof["win_loss"].get("chess_loss"), 1)

    def test_promises_and_challenges(self):
        # Extract promise from chat
        self.extractor.extract_from_chat("Viewer42", "aku janji besok bakal bawain martabak buat Eve!")
        promises = self.db.get_pending_promises(user="Viewer42")
        self.assertEqual(len(promises), 1)
        self.assertIn("martabak", promises[0]["text"])

        # Check markdown promises board
        prom_file = Path(self.brain_dir) / "promises.md"
        self.assertIn("Viewer42", prom_file.read_text(encoding="utf-8"))

    def test_memory_recall_prompt_generation(self):
        # Ingest memory
        self.extractor.on_minecraft_gift("Steve", "Diamond")
        recall = self.retriever.recall(query="Eve kamu ingat aku?", current_user="Steve")
        self.assertIsNotNone(recall.user_profile)
        self.assertGreaterEqual(len(recall.episodes), 1)

        prompt_text = recall.to_prompt_text("Steve")
        self.assertIn("EVE'S SECOND BRAIN & EPISODIC MEMORY RECALL", prompt_text)
        self.assertIn("Diamond", prompt_text)
        self.assertIn("Eh, kamu yang kemarin ngasih aku diamond, kan?", prompt_text)


class TestConversationEpisodicIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        character = {
            "name": "Eve Maybe",
            "nickname": "Eve",
            "creator": "Creator",
            "bio": "Autonomous AI VTuber"
        }
        self.conv = ConversationEngine(character=character)
        # Point to temp memory db
        self.conv.episodic_memory = EpisodicMemoryStore(
            db_path=str(Path(self.temp_dir) / "test_memory.db"),
            markdown_dir=str(Path(self.temp_dir) / "test_brain")
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_recall_callback_in_mock_response(self):
        # 1. Steve gives Eve a Diamond in Minecraft
        self.conv.episodic_memory.on_minecraft_gift("Steve", "Diamond")

        # 2. Later, Steve chats asking if Eve remembers him
        response = self.conv.generate_mock_response(
            user_name="Steve",
            message="Eve, kamu masih ingat aku gak?",
            game_context="Minecraft Survival"
        )
        # Should drop the iconic callback!
        self.assertIn("diamond", response.lower())
        self.assertTrue("kamu yang kemarin ngasih aku" in response.lower() or "steve" in response.lower())

    def test_chess_blunder_callback(self):
        # Record chess game where Evan lost Queen
        self.conv.episodic_memory.on_chess_game_ended(
            player="Evan",
            eve_won=True,
            player_won=False,
            result="checkmate_white_wins",
            moves_count=16,
            elo=1400
        )
        response = self.conv.generate_mock_response(
            user_name="Evan",
            message="Halo Eve! Kamu inget kemarin?",
            game_context="Casual Chat"
        )
        self.assertTrue("catur" in response.lower() or "ratu" in response.lower() or "evan" in response.lower())

if __name__ == "__main__":
    unittest.main()
