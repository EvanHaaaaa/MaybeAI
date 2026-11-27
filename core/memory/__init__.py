from typing import Dict, Any, List, Optional
from core.memory.embedding import EmbeddingEngine
from core.memory.database import MemoryDatabase
from core.memory.markdown_sync import MarkdownBrainSync
from core.memory.retriever import MemoryRetriever, MemoryRecallResult
from core.memory.extractor import MemoryExtractor

class EpisodicMemoryStore:
    """
    Unified Second Brain & Long-Term Episodic Memory Subsystem.
    Orchestrates SQLite storage, FTS5 BM25 search, dense vector retrieval,
    Andrej Karpathy Markdown journals, and event ingestion.
    """

    def __init__(
        self,
        db_path: str = "data/memory.db",
        markdown_dir: str = "data/second_brain",
        embedding_provider: str = "auto",
        embedder: Optional[EmbeddingEngine] = None,
        vector_scan_limit: int = 2000,
    ):
        self.embedder = embedder if embedder is not None else EmbeddingEngine(provider=embedding_provider)
        self.db = MemoryDatabase(
            db_path=db_path,
            embedding_provider=embedding_provider,
            embedder=self.embedder,
            vector_scan_limit=vector_scan_limit,
        )
        self.sync = MarkdownBrainSync(base_dir=markdown_dir)
        self.retriever = MemoryRetriever(db=self.db)
        self.extractor = MemoryExtractor(db=self.db, markdown_sync=self.sync)

    def recall(
        self,
        query: str,
        current_user: str = "Chat",
        game_context: str = "",
        top_k: int = 3
    ) -> MemoryRecallResult:
        return self.retriever.recall(
            query=query,
            current_user=current_user,
            game_context=game_context,
            top_k=top_k
        )

    def record_episode(
        self,
        title: str,
        content: str,
        episode_type: str = "general",
        user: str = "Chat",
        emotional_tag: str = "neutral",
        importance_score: float = 0.5,
        game_context: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        return self.extractor.record_episode(
            title=title,
            content=content,
            episode_type=episode_type,
            user=user,
            emotional_tag=emotional_tag,
            importance_score=importance_score,
            game_context=game_context,
            metadata=metadata
        )

    def extract_from_chat(self, user: str, text: str, is_donation: bool = False, donation_amount: str = ""):
        self.extractor.extract_from_chat(
            user=user,
            text=text,
            is_donation=is_donation,
            donation_amount=donation_amount
        )

    def on_minecraft_gift(self, player: str, item: str):
        self.extractor.on_minecraft_gift(player, item)

    def on_minecraft_attack(self, player: str):
        self.extractor.on_minecraft_attack(player)

    def on_minecraft_guard_incident(self, player: str, mob: str):
        self.extractor.on_minecraft_guard_incident(player, mob)

    def on_minecraft_joined(self, player: str):
        self.extractor.on_minecraft_joined(player)

    def on_chess_game_ended(self, player: str, eve_won: bool, player_won: bool, result: str, moves_count: int, elo: int):
        self.extractor.on_chess_game_ended(player, eve_won, player_won, result, moves_count, elo)

    def on_chess_queen_capture(self, player: str, eve_captured_player_queen: bool, san: str):
        self.extractor.on_chess_queen_capture(player, eve_captured_player_queen, san)

    def search_memories(self, query: str, top_k: int = 10, user: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.db.hybrid_search(query_str=query, top_k=top_k, user=user)

    def get_stats(self) -> Dict[str, Any]:
        return self.db.get_stats()

    def get_latest_journal(self) -> str:
        return self.sync.get_latest_journal_markdown()

    def fulfill_promise(self, promise_id: int) -> bool:
        """Marks a promise fulfilled in SQLite and syncs promises.md."""
        updated = self.db.fulfill_promise(promise_id)
        if updated:
            self.sync.sync_promises_from_db(self.db)
        return updated

    def sync_promises(self) -> None:
        """Bidirectionally reconciles promises.md with SQLite promises_challenges."""
        self.sync.sync_promises_from_db(self.db)

__all__ = [
    "EpisodicMemoryStore",
    "MemoryDatabase",
    "EmbeddingEngine",
    "MarkdownBrainSync",
    "MemoryRetriever",
    "MemoryRecallResult",
    "MemoryExtractor"
]
