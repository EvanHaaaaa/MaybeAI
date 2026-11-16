import sqlite3
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from core.memory.embedding import EmbeddingEngine

class MemoryDatabase:
    """
    SQLite-backed Episodic & Long-Term Memory Store for Eve Maybe.
    Features:
    - ACID persistent storage in data/memory.db
    - SQLite FTS5 Full-Text Search with BM25 ranking
    - 128-dimensional Dense Vector Cosine Similarity Search
    - User Profiles, Viewer Dossiers, and Promises/Challenges tracking
    """

    def __init__(self, db_path: str = "data/memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = EmbeddingEngine()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path), timeout=10.0)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self):
        with self._get_connection() as con:
            cur = con.cursor()

            # 1. Episodic Memories Table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS episodic_memories (
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
            """)

            # 2. SQLite FTS5 Full-Text Search Virtual Table
            cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_memories USING fts5(
                title,
                content,
                user,
                episode_type,
                content='episodic_memories',
                content_rowid='id'
            );
            """)

            # Triggers to keep FTS5 synchronized
            cur.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_memories_ai AFTER INSERT ON episodic_memories BEGIN
                INSERT INTO fts_memories(rowid, title, content, user, episode_type)
                VALUES (new.id, new.title, new.content, new.user, new.episode_type);
            END;
            """)
            cur.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_memories_ad AFTER DELETE ON episodic_memories BEGIN
                INSERT INTO fts_memories(fts_memories, rowid, title, content, user, episode_type)
                VALUES('delete', old.id, old.title, old.content, old.user, old.episode_type);
            END;
            """)
            cur.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_memories_au AFTER UPDATE ON episodic_memories BEGIN
                INSERT INTO fts_memories(fts_memories, rowid, title, content, user, episode_type)
                VALUES('delete', old.id, old.title, old.content, old.user, old.episode_type);
                INSERT INTO fts_memories(rowid, title, content, user, episode_type)
                VALUES (new.id, new.title, new.content, new.user, new.episode_type);
            END;
            """)

            # 3. Viewer & User Profiles Table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                username TEXT PRIMARY KEY,
                first_seen REAL,
                last_seen REAL,
                interaction_count INTEGER DEFAULT 0,
                tags_json TEXT DEFAULT '[]',
                preferences_json TEXT DEFAULT '{}',
                games_played_json TEXT DEFAULT '{}',
                win_loss_json TEXT DEFAULT '{}',
                stories_json TEXT DEFAULT '[]',
                total_donations TEXT DEFAULT '',
                notes_json TEXT DEFAULT '[]'
            );
            """)

            # 4. Promises and Challenges Table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS promises_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                text TEXT,
                type TEXT DEFAULT 'promise',
                status TEXT DEFAULT 'pending',
                created_at REAL,
                fulfilled_at REAL,
                context TEXT DEFAULT ''
            );
            """)
            con.commit()

    def add_episodic_memory(
        self,
        title: str,
        content: str,
        episode_type: str = "general",
        user: str = "Chat",
        emotional_tag: str = "neutral",
        importance_score: float = 0.5,
        game_context: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[np.ndarray] = None
    ) -> int:
        """Stores a new episodic memory with dense vector embedding."""
        now = time.time()
        date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        meta_json = json.dumps(metadata or {})

        if embedding is None:
            full_text = f"{title} {content} {user} {episode_type} {game_context}"
            embedding = self.embedder.encode(full_text)

        blob = self.embedder.serialize(embedding)

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
            INSERT INTO episodic_memories (
                timestamp, date_str, episode_type, user, title, content,
                emotional_tag, importance_score, game_context, embedding, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now, date_str, episode_type, user, title, content,
                emotional_tag, importance_score, game_context, blob, meta_json
            ))
            memory_id = cur.lastrowid
            con.commit()
            return memory_id

    def get_memory(self, memory_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM episodic_memories WHERE id = ?", (memory_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_memory(row)

    def get_recent_memories(
        self,
        limit: int = 20,
        episode_type: Optional[str] = None,
        user: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM episodic_memories"
        params = []
        conditions = []

        if episode_type:
            conditions.append("episode_type = ?")
            params.append(episode_type)
        if user:
            conditions.append("user = ?")
            params.append(user)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            return [self._row_to_memory(r) for r in rows]

    def vector_search(
        self,
        query_vec: np.ndarray,
        top_k: int = 5,
        user: Optional[str] = None,
        min_score: float = 0.15
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Dense vector search over episodic memories using cosine similarity."""
        memories = self.get_recent_memories(limit=300, user=user)
        results = []

        for mem in memories:
            vec = mem.get("_embedding_vec")
            if vec is None:
                continue
            sim = self.embedder.cosine_similarity(query_vec, vec)
            if sim >= min_score:
                results.append((mem, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def fts_search(
        self,
        query_str: str,
        top_k: int = 5,
        user: Optional[str] = None
    ) -> List[Tuple[Dict[str, Any], float]]:
        """SQLite FTS5 full-text keyword search with BM25 scoring."""
        clean_query = "".join(c for c in query_str if c.isalnum() or c.isspace()).strip()
        if not clean_query:
            return []

        tokens = clean_query.split()
        match_query = " OR ".join(f'"{t}"' for t in tokens if len(t) > 1)
        if not match_query:
            return []

        with self._get_connection() as con:
            cur = con.cursor()
            try:
                sql = """
                SELECT e.*, rank AS fts_rank
                FROM fts_memories f
                JOIN episodic_memories e ON f.rowid = e.id
                WHERE fts_memories MATCH ?
                """
                params = [match_query]
                if user:
                    sql += " AND e.user = ?"
                    params.append(user)

                sql += " ORDER BY rank LIMIT ?"
                params.append(top_k)

                cur.execute(sql, params)
                rows = cur.fetchall()
                # In FTS5, rank is negative (lower = better match)
                results = []
                for r in rows:
                    mem = self._row_to_memory(r)
                    rank_score = max(0.1, 1.0 / (1.0 + abs(float(r["fts_rank"]))))
                    results.append((mem, rank_score))
                return results
            except Exception:
                return []

    def hybrid_search(
        self,
        query_str: str,
        query_vec: Optional[np.ndarray] = None,
        top_k: int = 5,
        user: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        State-of-the-art hybrid search combining:
        - Dense vector semantic similarity (50%)
        - FTS5 BM25 keyword matching (30%)
        - Importance score (10%)
        - Recency time-decay (10%)
        """
        if query_vec is None:
            query_vec = self.embedder.encode(query_str)

        vec_matches = {mem["id"]: (mem, score) for mem, score in self.vector_search(query_vec, top_k=top_k * 2, user=user)}
        fts_matches = {m["id"]: score for m, score in self.fts_search(query_str, top_k=top_k * 2, user=user)}

        combined_scores: Dict[int, Tuple[Dict[str, Any], float]] = {}
        now = time.time()

        for mid, (mem, v_score) in vec_matches.items():
            f_score = fts_matches.get(mid, 0.0)
            importance = mem.get("importance_score", 0.5)

            # Recency factor: 1.0 today, decays gently over 30 days
            age_days = (now - mem.get("timestamp", now)) / 86400.0
            recency = max(0.2, 1.0 / (1.0 + (age_days * 0.05)))

            score = (0.50 * v_score) + (0.30 * f_score) + (0.10 * importance) + (0.10 * recency)
            combined_scores[mid] = (mem, score)

        # Include FTS matches that vector might have missed
        if fts_matches:
            with self._get_connection() as con:
                cur = con.cursor()
                for mid, f_score in fts_matches.items():
                    if mid not in combined_scores:
                        cur.execute("SELECT * FROM episodic_memories WHERE id = ?", (mid,))
                        r = cur.fetchone()
                        if r:
                            mem = self._row_to_memory(r)
                            importance = mem.get("importance_score", 0.5)
                            age_days = (now - mem.get("timestamp", now)) / 86400.0
                            recency = max(0.2, 1.0 / (1.0 + (age_days * 0.05)))
                            score = (0.30 * f_score) + (0.10 * importance) + (0.10 * recency)
                            combined_scores[mid] = (mem, score)

        ranked = sorted(combined_scores.values(), key=lambda x: x[1], reverse=True)
        return [mem for mem, _ in ranked[:top_k]]

    def _row_to_memory(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        blob = d.pop("embedding", None)
        if blob:
            d["_embedding_vec"] = self.embedder.deserialize(blob)
        if "metadata_json" in d and d["metadata_json"]:
            try:
                d["metadata"] = json.loads(d["metadata_json"])
            except Exception:
                d["metadata"] = {}
        return d

    # --- User Profile & Viewer Dossier Operations ---

    def get_or_create_user(self, username: str) -> Dict[str, Any]:
        clean_user = username.strip() or "Chatter"
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT * FROM user_profiles WHERE username = ?", (clean_user,))
            row = cur.fetchone()
            if row:
                return self._row_to_user(row)

            now = time.time()
            cur.execute("""
            INSERT INTO user_profiles (
                username, first_seen, last_seen, interaction_count,
                tags_json, preferences_json, games_played_json, win_loss_json,
                stories_json, total_donations, notes_json
            ) VALUES (?, ?, ?, 1, '["new"]', '{}', '{}', '{}', '[]', '', '[]')
            """, (clean_user, now, now))
            con.commit()

            cur.execute("SELECT * FROM user_profiles WHERE username = ?", (clean_user,))
            return self._row_to_user(cur.fetchone())

    def update_user_interaction(self, username: str, text: str = ""):
        profile = self.get_or_create_user(username)
        count = profile["interaction_count"] + 1
        tags = set(profile["tags"])
        if count >= 5:
            tags.add("regular")
        if count >= 15:
            tags.add("superfan")

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
            UPDATE user_profiles
            SET interaction_count = ?, last_seen = ?, tags_json = ?
            WHERE username = ?
            """, (count, time.time(), json.dumps(list(tags)), profile["username"]))
            con.commit()

    def add_user_preference(self, username: str, key: str, value: str):
        profile = self.get_or_create_user(username)
        prefs = profile["preferences"]
        prefs.setdefault(key, [])
        if value not in prefs[key]:
            prefs[key].append(value)

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("UPDATE user_profiles SET preferences_json = ? WHERE username = ?", (json.dumps(prefs), username))
            con.commit()

    def record_user_game(self, username: str, game: str, outcome: str):
        profile = self.get_or_create_user(username)
        games = profile["games_played"]
        win_loss = profile["win_loss"]

        games[game] = games.get(game, 0) + 1
        win_loss[f"{game}_{outcome}"] = win_loss.get(f"{game}_{outcome}", 0) + 1

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
            UPDATE user_profiles
            SET games_played_json = ?, win_loss_json = ?
            WHERE username = ?
            """, (json.dumps(games), json.dumps(win_loss), username))
            con.commit()

    def add_user_story(self, username: str, story: str):
        profile = self.get_or_create_user(username)
        stories = profile["stories"]
        if story not in stories:
            stories.append(story)
            if len(stories) > 10:
                stories = stories[-10:]
            with self._get_connection() as con:
                cur = con.cursor()
                cur.execute("UPDATE user_profiles SET stories_json = ? WHERE username = ?", (json.dumps(stories), username))
                con.commit()

    def add_user_note(self, username: str, note: str):
        profile = self.get_or_create_user(username)
        notes = profile["notes"]
        if note not in notes:
            notes.append(note)
            with self._get_connection() as con:
                cur = con.cursor()
                cur.execute("UPDATE user_profiles SET notes_json = ? WHERE username = ?", (json.dumps(notes), username))
                con.commit()

    def record_donation(self, username: str, amount_str: str):
        profile = self.get_or_create_user(username)
        tags = set(profile["tags"])
        tags.add("donor")

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
            UPDATE user_profiles
            SET total_donations = ?, tags_json = ?
            WHERE username = ?
            """, (f"{profile['total_donations']} {amount_str}".strip(), json.dumps(list(tags)), username))
            con.commit()

    def _row_to_user(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        d["tags"] = json.loads(d.get("tags_json") or "[]")
        d["preferences"] = json.loads(d.get("preferences_json") or "{}")
        d["games_played"] = json.loads(d.get("games_played_json") or "{}")
        d["win_loss"] = json.loads(d.get("win_loss_json") or "{}")
        d["stories"] = json.loads(d.get("stories_json") or "[]")
        d["notes"] = json.loads(d.get("notes_json") or "[]")
        return d

    # --- Promises & Challenges ---

    def add_promise_or_challenge(
        self,
        user: str,
        text: str,
        ptype: str = "promise",
        context: str = ""
    ) -> int:
        now = time.time()
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
            INSERT INTO promises_challenges (user, text, type, status, created_at, context)
            VALUES (?, ?, ?, 'pending', ?, ?)
            """, (user, text, ptype, now, context))
            pid = cur.lastrowid
            con.commit()
            return pid

    def get_pending_promises(self, user: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM promises_challenges WHERE status = 'pending'"
        params = []
        if user:
            query += " AND user = ?"
            params.append(user)
        query += " ORDER BY created_at DESC"

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]

    def fulfill_promise(self, promise_id: int):
        now = time.time()
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("UPDATE promises_challenges SET status = 'fulfilled', fulfilled_at = ? WHERE id = ?", (now, promise_id))
            con.commit()

    # --- Database Statistics ---

    def get_stats(self) -> Dict[str, Any]:
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM episodic_memories")
            mem_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM user_profiles")
            user_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM promises_challenges WHERE status = 'pending'")
            pending_promises = cur.fetchone()[0]

            return {
                "total_memories": mem_count,
                "known_users": user_count,
                "pending_promises": pending_promises
            }
