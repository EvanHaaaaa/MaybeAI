import sqlite3
import json
import time
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from core.memory.embedding import EmbeddingEngine


def _has_hnswlib() -> bool:
    try:
        import hnswlib  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


def _has_sqlite_vec() -> bool:
    try:
        import sqlite_vec  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


class MemoryDatabase:
    """
    SQLite-backed Episodic & Long-Term Memory Store for Eve Maybe.
    Features:
    - ACID persistent storage in data/memory.db with PRAGMA user_version schema migrations
    - SQLite FTS5 Full-Text Search with BM25 ranking
    - Indexed ANN Vector Search (hnswlib / sqlite-vec / vectorized NumPy) with linear fallback
    - Semantic Facts store with provenance & creator-verification protection
    - User Profiles, Viewer Dossiers, and Promises/Challenges tracking
    """

    SCHEMA_VERSION = 2
    VALID_ANN_BACKENDS = ("auto", "hnsw", "numpy", "linear")

    def __init__(
        self,
        db_path: str = "data/memory.db",
        embedding_provider: str = "auto",
        embedder: Optional[EmbeddingEngine] = None,
        vector_scan_limit: int = 2000,
        ann_backend: str = "auto",
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder if embedder is not None else EmbeddingEngine(provider=embedding_provider)
        self.vector_scan_limit = max(1, int(vector_scan_limit))

        requested_ann = (ann_backend or "auto").lower().strip()
        if requested_ann not in self.VALID_ANN_BACKENDS:
            requested_ann = "auto"
        self.requested_ann_backend = requested_ann
        self.active_ann_backend = self._resolve_ann_backend(requested_ann)

        # In-memory ANN partition cache keyed by embedding dimension
        self._ann_lock = threading.RLock()
        self._ann_partitions: Dict[int, Dict[str, Any]] = {}

        self._init_db()

    @staticmethod
    def _resolve_ann_backend(requested: str) -> str:
        if requested == "linear":
            return "linear"
        if requested == "numpy":
            return "numpy"
        if requested == "hnsw":
            return "hnsw" if _has_hnswlib() else "numpy"
        # "auto": prefer hnswlib -> sqlite_vec -> vectorized numpy
        if _has_hnswlib():
            return "hnsw"
        if _has_sqlite_vec():
            return "sqlite_vec"
        return "numpy"

    def get_schema_version(self) -> int:
        with self._get_connection() as con:
            row = con.execute("PRAGMA user_version").fetchone()
            return int(row[0]) if row else 0

    def _get_connection(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path), timeout=10.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
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
                decay_weight REAL DEFAULT 1.0,
                game_context TEXT DEFAULT '',
                embedding BLOB,
                embedding_dim INTEGER DEFAULT 0,
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

            # 5. Semantic Facts Table (H4-02 hierarchical consolidation)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS semantic_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                fact_key TEXT NOT NULL,
                fact_text TEXT NOT NULL,
                category TEXT DEFAULT 'fact',
                importance_score REAL DEFAULT 0.6,
                decay_weight REAL DEFAULT 1.0,
                confidence REAL DEFAULT 0.7,
                is_creator INTEGER DEFAULT 0,
                verified INTEGER DEFAULT 0,
                source_episode_ids TEXT DEFAULT '[]',
                created_at REAL,
                updated_at REAL,
                last_accessed REAL,
                UNIQUE(user, fact_key)
            );
            """)

            # Schema versioning & migrations via PRAGMA user_version
            ver_row = cur.execute("PRAGMA user_version").fetchone()
            current_ver = int(ver_row[0]) if ver_row else 0
            if current_ver < self.SCHEMA_VERSION:
                existing_cols = {
                    r[1] for r in cur.execute("PRAGMA table_info(episodic_memories)").fetchall()
                }
                if "embedding_dim" not in existing_cols:
                    cur.execute("ALTER TABLE episodic_memories ADD COLUMN embedding_dim INTEGER DEFAULT 0")
                if "decay_weight" not in existing_cols:
                    cur.execute("ALTER TABLE episodic_memories ADD COLUMN decay_weight REAL DEFAULT 1.0")
                # Ensure FTS5 external-content index is synchronized before any UPDATE triggers fire
                cur.execute("INSERT INTO fts_memories(fts_memories) VALUES('rebuild')")
                # Backfill embedding_dim for legacy rows (float32 = 4 bytes per dim)
                cur.execute(
                    "UPDATE episodic_memories SET embedding_dim = LENGTH(embedding) / 4 "
                    "WHERE embedding IS NOT NULL AND (embedding_dim IS NULL OR embedding_dim = 0)"
                )
                cur.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")

            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_dim_user "
                "ON episodic_memories(embedding_dim, user, timestamp DESC)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_semantic_facts_user "
                "ON semantic_facts(user, importance_score DESC)"
            )
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

        vec_arr = np.asarray(embedding, dtype=np.float32).reshape(-1)
        emb_dim = int(vec_arr.size)
        blob = self.embedder.serialize(vec_arr)

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute("""
            INSERT INTO episodic_memories (
                timestamp, date_str, episode_type, user, title, content,
                emotional_tag, importance_score, decay_weight, game_context,
                embedding, embedding_dim, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?, ?)
            """, (
                now, date_str, episode_type, user, title, content,
                emotional_tag, importance_score, game_context, blob, emb_dim, meta_json
            ))
            memory_id = cur.lastrowid
            con.commit()

        self._append_to_ann_partition(memory_id, user, vec_arr)
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

    def _memory_embedding_text(self, mem: Dict[str, Any]) -> str:
        return (
            f"{mem.get('title', '')} {mem.get('content', '')} "
            f"{mem.get('user', '')} {mem.get('episode_type', '')} {mem.get('game_context', '')}"
        ).strip()

    def _update_memory_embedding(self, memory_id: int, vec: np.ndarray) -> None:
        try:
            vec_arr = np.asarray(vec, dtype=np.float32).reshape(-1)
            emb_dim = int(vec_arr.size)
            blob = self.embedder.serialize(vec_arr)
            with self._get_connection() as con:
                con.execute(
                    "UPDATE episodic_memories SET embedding = ?, embedding_dim = ? WHERE id = ?",
                    (blob, emb_dim, memory_id),
                )
                con.commit()
            self._invalidate_ann_partitions()
        except Exception:
            pass

    def _invalidate_ann_partitions(self) -> None:
        with self._ann_lock:
            self._ann_partitions.clear()

    def _append_to_ann_partition(self, memory_id: Optional[int], user: str, vec: np.ndarray) -> None:
        if memory_id is None or vec.size == 0 or self.active_ann_backend == "linear":
            return
        dim = int(vec.size)
        norm = float(np.linalg.norm(vec))
        if norm <= 1e-6:
            return
        normed = (vec / norm).astype(np.float32, copy=False)
        with self._ann_lock:
            part = self._ann_partitions.get(dim)
            if part is not None:
                part["pending"].append((int(memory_id), user or "", normed))

    def _get_ann_partition(self, dim: int) -> Optional[Dict[str, Any]]:
        with self._ann_lock:
            part = self._ann_partitions.get(dim)
            if part is None:
                with self._get_connection() as con:
                    rows = con.execute(
                        "SELECT id, user, embedding FROM episodic_memories "
                        "WHERE embedding IS NOT NULL AND embedding_dim = ? ORDER BY id ASC",
                        (dim,),
                    ).fetchall()
                if not rows:
                    part = {
                        "ids": np.empty((0,), dtype=np.int64),
                        "users": np.empty((0,), dtype=object),
                        "matrix": np.empty((0, dim), dtype=np.float32),
                        "pending": [],
                        "hnsw": None,
                    }
                else:
                    ids_list: List[int] = []
                    users_list: List[str] = []
                    vecs_list: List[np.ndarray] = []
                    for r in rows:
                        vec = np.frombuffer(r["embedding"], dtype=np.float32)
                        if vec.size != dim:
                            continue
                        norm = float(np.linalg.norm(vec))
                        if norm <= 1e-6:
                            continue
                        ids_list.append(int(r["id"]))
                        users_list.append(r["user"] or "")
                        vecs_list.append(vec / norm)
                    if vecs_list:
                        matrix = np.vstack(vecs_list).astype(np.float32, copy=False)
                        ids_arr = np.asarray(ids_list, dtype=np.int64)
                        users_arr = np.asarray(users_list, dtype=object)
                    else:
                        matrix = np.empty((0, dim), dtype=np.float32)
                        ids_arr = np.empty((0,), dtype=np.int64)
                        users_arr = np.empty((0,), dtype=object)
                    part = {
                        "ids": ids_arr,
                        "users": users_arr,
                        "matrix": matrix,
                        "pending": [],
                        "hnsw": None,
                    }
                    if self.active_ann_backend == "hnsw" and matrix.shape[0] > 0:
                        part["hnsw"] = self._build_hnsw_index(dim, ids_arr, matrix)
                self._ann_partitions[dim] = part
            elif part["pending"]:
                pending = part["pending"]
                part["pending"] = []
                new_ids = np.asarray([p[0] for p in pending], dtype=np.int64)
                new_users = np.asarray([p[1] for p in pending], dtype=object)
                new_vecs = np.vstack([p[2] for p in pending]).astype(np.float32, copy=False)
                if part["matrix"].shape[0] == 0:
                    part["ids"] = new_ids
                    part["users"] = new_users
                    part["matrix"] = new_vecs
                else:
                    part["ids"] = np.concatenate([part["ids"], new_ids])
                    part["users"] = np.concatenate([part["users"], new_users])
                    part["matrix"] = np.vstack([part["matrix"], new_vecs])
                if self.active_ann_backend == "hnsw" and part["matrix"].shape[0] > 0:
                    part["hnsw"] = self._build_hnsw_index(dim, part["ids"], part["matrix"])
            return part

    @staticmethod
    def _build_hnsw_index(dim: int, ids: np.ndarray, matrix: np.ndarray) -> Any:
        try:
            import hnswlib  # type: ignore

            idx = hnswlib.Index(space="cosine", dim=dim)
            idx.init_index(max_elements=max(len(ids), 16), ef_construction=100, M=16)
            idx.add_items(matrix, ids)
            idx.set_ef(50)
            return idx
        except Exception:
            return None

    def _fetch_memories_by_ids(self, ordered_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        if not ordered_ids:
            return {}
        placeholders = ",".join("?" for _ in ordered_ids)
        with self._get_connection() as con:
            rows = con.execute(
                f"SELECT * FROM episodic_memories WHERE id IN ({placeholders})",
                ordered_ids,
            ).fetchall()
        return {int(r["id"]): self._row_to_memory(r) for r in rows}

    def _reencode_eligible_mismatched(self, target_shape: Tuple[int, ...], user: Optional[str]) -> None:
        target_dim = int(target_shape[0])
        sql = (
            "SELECT id, title, content, user, episode_type, game_context, embedding, embedding_dim "
            "FROM episodic_memories WHERE embedding IS NOT NULL AND embedding_dim != ?"
        )
        params: List[Any] = [target_dim]
        if user:
            sql += " AND user = ?"
            params.append(user)
        with self._get_connection() as con:
            rows = con.execute(sql, params).fetchall()
        for r in rows:
            existing_dim = int(r["embedding_dim"] or 0)
            if existing_dim > self.embedder.DIMENSION and self.embedder.active_backend == "hash":
                continue
            existing_vec = self.embedder.deserialize(r["embedding"]) if r["embedding"] else None
            mem_stub = dict(r)
            try:
                reencoded = self.embedder.encode(self._memory_embedding_text(mem_stub))
                if self._can_persist_reencoded_embedding(existing_vec, reencoded, target_shape):
                    self._update_memory_embedding(int(r["id"]), reencoded)
            except Exception:
                continue

    async def _areencode_eligible_mismatched(self, target_shape: Tuple[int, ...], user: Optional[str]) -> None:
        target_dim = int(target_shape[0])
        sql = (
            "SELECT id, title, content, user, episode_type, game_context, embedding, embedding_dim "
            "FROM episodic_memories WHERE embedding IS NOT NULL AND embedding_dim != ?"
        )
        params: List[Any] = [target_dim]
        if user:
            sql += " AND user = ?"
            params.append(user)
        with self._get_connection() as con:
            rows = con.execute(sql, params).fetchall()
        for r in rows:
            existing_dim = int(r["embedding_dim"] or 0)
            if existing_dim > self.embedder.DIMENSION and self.embedder.active_backend == "hash":
                continue
            existing_vec = self.embedder.deserialize(r["embedding"]) if r["embedding"] else None
            mem_stub = dict(r)
            try:
                reencoded = await self.embedder.aencode(self._memory_embedding_text(mem_stub))
                if self._can_persist_reencoded_embedding(existing_vec, reencoded, target_shape):
                    self._update_memory_embedding(int(r["id"]), reencoded)
            except Exception:
                continue

    def _ann_search_partition(
        self,
        q_vec: np.ndarray,
        top_k: int,
        user: Optional[str],
        min_score: float,
    ) -> List[Tuple[Dict[str, Any], float]]:
        norm = float(np.linalg.norm(q_vec))
        if norm <= 1e-6:
            return []
        q_norm = (q_vec / norm).astype(np.float32, copy=False)
        dim = int(q_norm.size)

        part = self._get_ann_partition(dim)
        if part is None or part["matrix"].shape[0] == 0:
            return []

        ids = part["ids"]
        matrix = part["matrix"]
        hnsw_idx = part.get("hnsw")

        if user is None and hnsw_idx is not None:
            k = min(max(1, top_k), int(ids.shape[0]))
            labels, distances = hnsw_idx.knn_query(q_norm, k=k)
            scored: List[Tuple[int, float]] = []
            for mid, dist in zip(labels[0], distances[0]):
                sim = float(1.0 - dist)
                if sim >= min_score:
                    scored.append((int(mid), sim))
            scored.sort(key=lambda x: x[1], reverse=True)
        else:
            if user is not None:
                mask = part["users"] == user
                if not np.any(mask):
                    return []
                sub_ids = ids[mask]
                sub_matrix = matrix[mask]
            else:
                sub_ids = ids
                sub_matrix = matrix

            scores = sub_matrix @ q_norm
            n_items = int(scores.shape[0])
            if n_items == 0:
                return []

            if n_items > top_k:
                top_idx = np.argpartition(scores, -top_k)[-top_k:]
                top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]
            else:
                top_idx = np.argsort(scores)[::-1]

            scored = [
                (int(sub_ids[i]), float(scores[i]))
                for i in top_idx
                if float(scores[i]) >= min_score
            ]

        if not scored:
            return []

        fetched = self._fetch_memories_by_ids([mid for mid, _ in scored])
        return [(fetched[mid], sim) for mid, sim in scored if mid in fetched][:top_k]

    def _can_persist_reencoded_embedding(
        self,
        existing_vec: Optional[np.ndarray],
        new_vec: Optional[np.ndarray],
        expected_shape: Tuple[int, ...],
    ) -> bool:
        """Guards against overwriting valid cloud/local embeddings with hash fallbacks."""
        if new_vec is None or getattr(new_vec, "shape", None) != expected_shape:
            return False
        if existing_vec is not None:
            existing_dim = getattr(existing_vec, "shape", (0,))[0]
            # Preserve valid higher-dim cloud/local embeddings when currently in hash fallback mode
            if existing_dim > self.embedder.DIMENSION and (
                self.embedder.active_backend == "hash"
                or getattr(self.embedder, "last_encode_was_fallback", False)
                or new_vec.shape[0] == self.embedder.DIMENSION
            ):
                return False
        return True

    def vector_search(
        self,
        query_vec: np.ndarray,
        top_k: int = 5,
        user: Optional[str] = None,
        min_score: float = 0.15,
        reencode_mismatched: bool = True,
        scan_limit: Optional[int] = None,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Dense vector search over episodic memories using cosine similarity.
        Gracefully handles mismatched vector dimensions (e.g., legacy 128-d blobs
        vs new 384-d/768-d embeddings) without overwriting valid cloud embeddings
        with hash fallbacks.
        """
        if query_vec is None:
            return []
        q_vec = np.asarray(query_vec, dtype=np.float32).reshape(-1)
        if q_vec.size == 0:
            return []

        if self.active_ann_backend != "linear":
            if reencode_mismatched:
                self._reencode_eligible_mismatched(q_vec.shape, user)
            return self._ann_search_partition(q_vec, top_k=top_k, user=user, min_score=min_score)

        effective_limit = max(1, int(scan_limit)) if scan_limit is not None else self.vector_scan_limit
        memories = self.get_recent_memories(limit=effective_limit, user=user)
        results = []

        for mem in memories:
            vec = mem.get("_embedding_vec")
            if vec is None or getattr(vec, "shape", None) != q_vec.shape:
                if reencode_mismatched and mem.get("id") is not None:
                    if (
                        vec is not None
                        and getattr(vec, "shape", (0,))[0] > self.embedder.DIMENSION
                        and self.embedder.active_backend == "hash"
                    ):
                        continue
                    try:
                        reencoded = self.embedder.encode(self._memory_embedding_text(mem))
                        if self._can_persist_reencoded_embedding(vec, reencoded, q_vec.shape):
                            vec = reencoded
                            mem["_embedding_vec"] = vec
                            self._update_memory_embedding(mem["id"], vec)
                        else:
                            continue
                    except Exception:
                        continue
                else:
                    continue

            sim = self.embedder.cosine_similarity(q_vec, vec)
            if sim >= min_score:
                results.append((mem, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    async def avector_search(
        self,
        query_vec: np.ndarray,
        top_k: int = 5,
        user: Optional[str] = None,
        min_score: float = 0.15,
        reencode_mismatched: bool = True,
        scan_limit: Optional[int] = None,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Async dense vector search using aencode for mismatched legacy embeddings."""
        if query_vec is None:
            return []
        q_vec = np.asarray(query_vec, dtype=np.float32).reshape(-1)
        if q_vec.size == 0:
            return []

        if self.active_ann_backend != "linear":
            if reencode_mismatched:
                await self._areencode_eligible_mismatched(q_vec.shape, user)
            return self._ann_search_partition(q_vec, top_k=top_k, user=user, min_score=min_score)

        effective_limit = max(1, int(scan_limit)) if scan_limit is not None else self.vector_scan_limit
        memories = self.get_recent_memories(limit=effective_limit, user=user)
        results = []

        for mem in memories:
            vec = mem.get("_embedding_vec")
            if vec is None or getattr(vec, "shape", None) != q_vec.shape:
                if reencode_mismatched and mem.get("id") is not None:
                    if (
                        vec is not None
                        and getattr(vec, "shape", (0,))[0] > self.embedder.DIMENSION
                        and self.embedder.active_backend == "hash"
                    ):
                        continue
                    try:
                        reencoded = await self.embedder.aencode(self._memory_embedding_text(mem))
                        if self._can_persist_reencoded_embedding(vec, reencoded, q_vec.shape):
                            vec = reencoded
                            mem["_embedding_vec"] = vec
                            self._update_memory_embedding(mem["id"], vec)
                        else:
                            continue
                    except Exception:
                        continue
                else:
                    continue

            sim = self.embedder.cosine_similarity(q_vec, vec)
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

    async def ahybrid_search(
        self,
        query_str: str,
        query_vec: Optional[np.ndarray] = None,
        top_k: int = 5,
        user: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Async hybrid search using aencode for non-blocking semantic retrieval."""
        if query_vec is None:
            query_vec = await self.embedder.aencode(query_str)

        vec_matches = {
            mem["id"]: (mem, score)
            for mem, score in await self.avector_search(query_vec, top_k=top_k * 2, user=user)
        }
        fts_matches = {m["id"]: score for m, score in self.fts_search(query_str, top_k=top_k * 2, user=user)}

        combined_scores: Dict[int, Tuple[Dict[str, Any], float]] = {}
        now = time.time()

        for mid, (mem, v_score) in vec_matches.items():
            f_score = fts_matches.get(mid, 0.0)
            importance = mem.get("importance_score", 0.5)
            age_days = (now - mem.get("timestamp", now)) / 86400.0
            recency = max(0.2, 1.0 / (1.0 + (age_days * 0.05)))
            score = (0.50 * v_score) + (0.30 * f_score) + (0.10 * importance) + (0.10 * recency)
            combined_scores[mid] = (mem, score)

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

    def get_promises(
        self,
        status: Optional[str] = None,
        user: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM promises_challenges"
        conditions = []
        params: List[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if user:
            conditions.append("user = ?")
            params.append(user)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(max(1, int(limit)))

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]

    def fulfill_promise(self, promise_id: int) -> bool:
        now = time.time()
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute(
                "UPDATE promises_challenges SET status = 'fulfilled', fulfilled_at = ? WHERE id = ?",
                (now, promise_id),
            )
            con.commit()
            return cur.rowcount > 0

    def update_promise_status(self, promise_id: int, status: str) -> bool:
        clean_status = (status or "pending").strip().lower()
        now = time.time()
        with self._get_connection() as con:
            cur = con.cursor()
            if clean_status in ("fulfilled", "archived"):
                cur.execute(
                    "UPDATE promises_challenges SET status = ?, fulfilled_at = COALESCE(fulfilled_at, ?) WHERE id = ?",
                    (clean_status, now, promise_id),
                )
            else:
                cur.execute(
                    "UPDATE promises_challenges SET status = ? WHERE id = ?",
                    (clean_status, promise_id),
                )
            con.commit()
            return cur.rowcount > 0

    def archive_old_promises(self, older_than_days: float = 30.0) -> int:
        cutoff = time.time() - (max(0.0, float(older_than_days)) * 86400.0)
        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute(
                "UPDATE promises_challenges SET status = 'archived' WHERE status = 'fulfilled' AND fulfilled_at IS NOT NULL AND fulfilled_at < ?",
                (cutoff,),
            )
            con.commit()
            return int(cur.rowcount or 0)

    # --- Semantic Facts & Decay (H4-02) ---

    def upsert_semantic_fact(
        self,
        user: str,
        fact_key: str,
        fact_text: str,
        category: str = "fact",
        importance_score: float = 0.6,
        confidence: float = 0.7,
        is_creator: bool = False,
        verified: bool = False,
        source_episode_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Inserts or updates a deduplicated semantic fact with source_episode_ids provenance.
        Creator-verified facts (is_creator=1 or verified=1) are never overwritten by
        automated consolidation unless explicitly overridden with is_creator/verified=True.
        """
        now = time.time()
        clean_user = (user or "Chat").strip() or "Chat"
        clean_key = fact_key.strip().lower()[:120]
        new_ep_ids = sorted({int(eid) for eid in (source_episode_ids or []) if eid is not None})

        with self._get_connection() as con:
            cur = con.cursor()
            cur.execute(
                "SELECT * FROM semantic_facts WHERE user = ? AND fact_key = ?",
                (clean_user, clean_key),
            )
            existing = cur.fetchone()
            if existing is not None:
                is_protected = bool(existing["is_creator"]) or bool(existing["verified"])
                if is_protected and not (is_creator or verified):
                    return {
                        "id": int(existing["id"]),
                        "updated": False,
                        "skipped_verified": True,
                    }

                try:
                    prev_ids = json.loads(existing["source_episode_ids"] or "[]")
                except Exception:
                    prev_ids = []
                merged_ids = sorted({int(x) for x in prev_ids} | set(new_ep_ids))
                merged_importance = max(float(existing["importance_score"] or 0.5), float(importance_score))
                merged_conf = max(float(existing["confidence"] or 0.5), float(confidence))

                cur.execute(
                    """
                    UPDATE semantic_facts
                    SET fact_text = ?, category = ?, importance_score = ?,
                        confidence = ?, is_creator = ?, verified = ?,
                        source_episode_ids = ?, updated_at = ?, decay_weight = 1.0
                    WHERE id = ?
                    """,
                    (
                        fact_text.strip(),
                        category,
                        merged_importance,
                        merged_conf,
                        1 if (is_creator or existing["is_creator"]) else 0,
                        1 if (verified or existing["verified"]) else 0,
                        json.dumps(merged_ids),
                        now,
                        int(existing["id"]),
                    ),
                )
                con.commit()
                return {
                    "id": int(existing["id"]),
                    "updated": True,
                    "skipped_verified": False,
                }

            cur.execute(
                """
                INSERT INTO semantic_facts (
                    user, fact_key, fact_text, category, importance_score,
                    decay_weight, confidence, is_creator, verified,
                    source_episode_ids, created_at, updated_at, last_accessed
                ) VALUES (?, ?, ?, ?, ?, 1.0, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_user,
                    clean_key,
                    fact_text.strip(),
                    category,
                    float(importance_score),
                    float(confidence),
                    1 if is_creator else 0,
                    1 if verified else 0,
                    json.dumps(new_ep_ids),
                    now,
                    now,
                    now,
                ),
            )
            fact_id = int(cur.lastrowid)
            con.commit()
            return {"id": fact_id, "updated": False, "skipped_verified": False}

    def get_semantic_facts(
        self,
        user: Optional[str] = None,
        min_importance: float = 0.0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM semantic_facts"
        conditions: List[str] = []
        params: List[Any] = []
        if user:
            conditions.append("user = ?")
            params.append(user)
        if min_importance > 0.0:
            conditions.append("(importance_score * decay_weight) >= ?")
            params.append(float(min_importance))
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY is_creator DESC, verified DESC, (importance_score * decay_weight) DESC, updated_at DESC LIMIT ?"
        params.append(max(1, int(limit)))

        with self._get_connection() as con:
            rows = con.execute(query, params).fetchall()
        results: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["is_creator"] = bool(d.get("is_creator"))
            d["verified"] = bool(d.get("verified"))
            try:
                d["source_episode_ids"] = json.loads(d.get("source_episode_ids") or "[]")
            except Exception:
                d["source_episode_ids"] = []
            results.append(d)
        return results

    def apply_memory_decay(
        self,
        half_life_days: float = 30.0,
        min_decay: float = 0.05,
    ) -> Dict[str, int]:
        """Applies exponential time-decay weights to episodic memories and non-verified semantic facts."""
        now = time.time()
        hl = max(1.0, float(half_life_days))
        floor = max(0.01, min(1.0, float(min_decay)))
        ep_updated = 0
        fact_updated = 0

        with self._get_connection() as con:
            cur = con.cursor()
            ep_rows = cur.execute("SELECT id, timestamp FROM episodic_memories").fetchall()
            for r in ep_rows:
                age_days = max(0.0, (now - float(r["timestamp"] or now)) / 86400.0)
                decay = max(floor, min(1.0, 0.5 ** (age_days / hl)))
                cur.execute("UPDATE episodic_memories SET decay_weight = ? WHERE id = ?", (decay, int(r["id"])))
                ep_updated += 1

            fact_rows = cur.execute(
                "SELECT id, updated_at FROM semantic_facts WHERE is_creator = 0 AND verified = 0"
            ).fetchall()
            for r in fact_rows:
                age_days = max(0.0, (now - float(r["updated_at"] or now)) / 86400.0)
                decay = max(floor, min(1.0, 0.5 ** (age_days / hl)))
                cur.execute("UPDATE semantic_facts SET decay_weight = ? WHERE id = ?", (decay, int(r["id"])))
                fact_updated += 1

            con.commit()

        return {"episodic_updated": ep_updated, "semantic_updated": fact_updated}

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

            cur.execute("SELECT COUNT(*) FROM semantic_facts")
            semantic_fact_count = cur.fetchone()[0]

            ver_row = cur.execute("PRAGMA user_version").fetchone()
            schema_ver = int(ver_row[0]) if ver_row else 0

            return {
                "total_memories": mem_count,
                "known_users": user_count,
                "pending_promises": pending_promises,
                "semantic_facts": semantic_fact_count,
                "embedding_provider": self.embedder.active_backend,
                "embedding_dimension": self.embedder.dimension,
                "ann_backend": self.active_ann_backend,
                "schema_version": schema_ver,
            }
