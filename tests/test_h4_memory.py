import asyncio
import json
import shutil
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from core.memory import EpisodicMemoryStore, MemoryConsolidator, MemoryDatabase, MarkdownBrainSync


class TestH4ANNVectorMemory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = str(Path(self.temp_dir) / "ann_test.db")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_schema_version_pragma_and_legacy_migration(self):
        # Create a legacy v0 database without embedding_dim or semantic_facts
        legacy_path = str(Path(self.temp_dir) / "legacy.db")
        with sqlite3.connect(legacy_path) as con:
            con.execute(
                """
                CREATE TABLE episodic_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    date_str TEXT,
                    episode_type TEXT,
                    user TEXT,
                    title TEXT,
                    content TEXT,
                    emotional_tag TEXT DEFAULT 'neutral',
                    importance_score REAL DEFAULT 0.5,
                    game_context TEXT DEFAULT '',
                    embedding BLOB,
                    metadata_json TEXT DEFAULT '{}'
                );
                """
            )
            vec = np.ones(128, dtype=np.float32)
            con.execute(
                "INSERT INTO episodic_memories (timestamp, title, content, embedding) VALUES (?, ?, ?, ?)",
                (time.time(), "Legacy", "Old memory", vec.tobytes()),
            )
            con.commit()

        db = MemoryDatabase(db_path=legacy_path, embedding_provider="hash")
        self.assertEqual(db.get_schema_version(), MemoryDatabase.SCHEMA_VERSION)
        stats = db.get_stats()
        self.assertEqual(stats["schema_version"], MemoryDatabase.SCHEMA_VERSION)
        self.assertIn(stats["ann_backend"], ("numpy", "hnsw", "sqlite_vec"))

        with db._get_connection() as con:
            row = con.execute("SELECT embedding_dim FROM episodic_memories WHERE title = 'Legacy'").fetchone()
            self.assertEqual(int(row[0]), 128)

    def test_ann_searches_beyond_2000_rows_while_linear_respects_limit(self):
        db = MemoryDatabase(
            db_path=self.db_path,
            embedding_provider="hash",
            vector_scan_limit=100,
            ann_backend="numpy",
        )
        rng = np.random.default_rng(42)
        vecs = rng.normal(size=(300, 128)).astype(np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)

        # Insert target row first (oldest), then 299 newer distractor rows
        target_vec = np.zeros(128, dtype=np.float32)
        target_vec[0] = 1.0
        target_id = db.add_episodic_memory(
            title="Ancient Diamond",
            content="Oldest memory beyond linear scan limit",
            user="Steve",
            embedding=target_vec,
        )
        for i in range(299):
            db.add_episodic_memory(
                title=f"Noise {i}",
                content=f"Distractor {i}",
                user="Chat",
                embedding=vecs[i],
            )

        # NumPy ANN finds the oldest row even though vector_scan_limit=100
        ann_hits = db.vector_search(target_vec, top_k=3, min_score=0.5, reencode_mismatched=False)
        self.assertTrue(any(m["id"] == target_id for m, _ in ann_hits))

        # Linear fallback respects vector_scan_limit=100 and misses the oldest row
        db_linear = MemoryDatabase(
            db_path=self.db_path,
            embedding_provider="hash",
            vector_scan_limit=100,
            ann_backend="linear",
        )
        lin_hits = db_linear.vector_search(target_vec, top_k=3, min_score=0.5, reencode_mismatched=False)
        self.assertFalse(any(m["id"] == target_id for m, _ in lin_hits))

    def test_50k_ann_query_under_20ms_p95(self):
        db = MemoryDatabase(
            db_path=self.db_path,
            embedding_provider="hash",
            ann_backend="numpy",
        )
        n_rows = 50000
        dim = 128
        rng = np.random.default_rng(123)
        mat = rng.normal(size=(n_rows, dim)).astype(np.float32)
        mat /= np.linalg.norm(mat, axis=1, keepdims=True)
        now = time.time()

        # Bulk-insert 50,000 synthetic rows directly for benchmark setup speed
        rows = [
            (
                now - (n_rows - i),
                "2026-11-27 00:00:00",
                "general",
                "Chat" if i % 2 == 0 else "Evan",
                f"Synthetic {i}",
                f"Content {i}",
                "neutral",
                0.5,
                1.0,
                "",
                mat[i].tobytes(),
                dim,
                "{}",
            )
            for i in range(n_rows)
        ]
        with db._get_connection() as con:
            con.executemany(
                """
                INSERT INTO episodic_memories (
                    timestamp, date_str, episode_type, user, title, content,
                    emotional_tag, importance_score, decay_weight, game_context,
                    embedding, embedding_dim, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            con.commit()

        # Warm up partition cache once (index build), then measure 25 queries
        q = mat[12345].copy()
        warm = db.vector_search(q, top_k=5, min_score=0.1, reencode_mismatched=False)
        self.assertEqual(warm[0][0]["title"], "Synthetic 12345")

        latencies_ms = []
        for idx in range(25):
            qv = mat[(idx * 997) % n_rows]
            t0 = time.perf_counter()
            hits = db.vector_search(qv, top_k=5, min_score=0.1, reencode_mismatched=False)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            latencies_ms.append(dt_ms)
            self.assertGreaterEqual(len(hits), 1)

        p95 = float(np.percentile(latencies_ms, 95))
        self.assertLess(p95, 20.0, f"50k ANN p95 latency too high: {p95:.2f} ms")


class TestH4ConsolidationAndPromises(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = str(Path(self.temp_dir) / "consolidate.db")
        self.brain_dir = str(Path(self.temp_dir) / "brain")
        self.store = EpisodicMemoryStore(
            db_path=self.db_path,
            markdown_dir=self.brain_dir,
            embedding_provider="hash",
            ann_backend="numpy",
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_consolidation_provenance_dedup_and_creator_protection(self):
        # Creator-verified fact must never be overwritten by consolidation or decayed
        self.store.db.upsert_semantic_fact(
            user="Evan",
            fact_key="preference:martabak_manis_keju",
            fact_text="Creator-verified: Evan loves Martabak Manis Keju",
            category="preference",
            importance_score=0.95,
            confidence=1.0,
            is_creator=True,
            verified=True,
            source_episode_ids=[],
        )

        # Duplicate episodes for Sultan + Evan
        ep1 = self.store.record_episode(
            title="Chat Preference",
            content="aku suka matcha latte dingin",
            episode_type="chat",
            user="Sultan",
            importance_score=0.6,
        )
        ep2 = self.store.record_episode(
            title="Chat Preference Again",
            content="aku suka banget matcha latte dingin",
            episode_type="chat",
            user="Sultan",
            importance_score=0.7,
        )
        ep3 = self.store.record_episode(
            title="Evan Preference",
            content="aku suka martabak manis keju",
            episode_type="chat",
            user="Evan",
            importance_score=0.5,
        )

        summary = await self.store.aconsolidate(limit=500)
        self.assertEqual(summary["episodes_processed"], 3)
        self.assertGreaterEqual(summary["verified_skipped"], 1)

        sultan_facts = self.store.db.get_semantic_facts(user="Sultan")
        matcha_facts = [f for f in sultan_facts if "matcha latte dingin" in f["fact_text"].lower()]
        self.assertEqual(len(matcha_facts), 1)
        self.assertEqual(set(matcha_facts[0]["source_episode_ids"]), {ep1, ep2})

        evan_facts = self.store.db.get_semantic_facts(user="Evan")
        martabak = [f for f in evan_facts if f["fact_key"] == "preference:martabak_manis_keju"][0]
        self.assertEqual(martabak["fact_text"], "Creator-verified: Evan loves Martabak Manis Keju")
        self.assertTrue(martabak["is_creator"])
        self.assertEqual(martabak["decay_weight"], 1.0)
        self.assertNotEqual(ep3, 0)

    async def test_async_llm_distill_callback(self):
        ep_id = self.store.record_episode(
            title="Minecraft Boss",
            content="Steve and Eve defeated the Ender Dragon together.",
            episode_type="minecraft_event",
            user="Steve",
            importance_score=0.9,
        )

        async def mock_llm_distill(user, episodes):
            return [
                {
                    "fact_key": "achievement:ender_dragon",
                    "fact_text": f"{user} helped Eve defeat the Ender Dragon",
                    "category": "relationship",
                    "importance_score": 0.9,
                    "confidence": 0.95,
                    "source_episode_ids": [e["id"] for e in episodes],
                }
            ]

        consolidator = MemoryConsolidator(
            db=self.store.db,
            markdown_sync=self.store.sync,
            llm_distill_fn=mock_llm_distill,
        )
        res = await consolidator.consolidate_async(limit=100, sync_promises=False)
        self.assertEqual(res["facts_created"], 1)
        facts = self.store.db.get_semantic_facts(user="Steve")
        self.assertEqual(facts[0]["source_episode_ids"], [ep_id])
        self.assertIn("Ender Dragon", facts[0]["fact_text"])

    def test_promises_bidirectional_roundtrip(self):
        pid = self.store.db.add_promise_or_challenge("Viewer1", "Main chess bareng", ptype="promise")
        self.store.sync_promises()

        promises_file = Path(self.brain_dir) / "promises.md"
        md_text = promises_file.read_text(encoding="utf-8")
        self.assertIn("Main chess bareng", md_text)

        # Simulate manual edit in promises.md: mark pid fulfilled & add a new row without numeric ID
        edited = md_text.replace(f"| {pid} | Viewer1 | promise | pending |", f"| {pid} | Viewer1 | promise | fulfilled |")
        edited += "| new | Viewer2 | challenge | pending | 2026-11-27 | Speedrun Nether |\n"
        promises_file.write_text(edited, encoding="utf-8")

        sync_stats = self.store.sync.sync_promises_bidirectional(self.store.db)
        self.assertEqual(sync_stats["updated_in_db"], 1)
        self.assertEqual(sync_stats["imported_from_md"], 1)

        db_rows = self.store.db.get_promises(limit=50)
        by_user = {r["user"]: r for r in db_rows}
        self.assertEqual(by_user["Viewer1"]["status"], "fulfilled")
        self.assertEqual(by_user["Viewer2"]["text"], "Speedrun Nether")


if __name__ == "__main__":
    unittest.main()
