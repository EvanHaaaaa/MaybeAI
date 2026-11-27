import asyncio
import inspect
import re
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from core.memory.database import MemoryDatabase
from core.memory.markdown_sync import MarkdownBrainSync


DistillCallback = Callable[
    [str, List[Dict[str, Any]]],
    Any,  # List[Dict[str, Any]] or Awaitable[List[Dict[str, Any]]]
]


class MemoryConsolidator:
    """
    H4-02 Hierarchical Memory Consolidation & Decay Pipeline.

    Clusters episodic memories per user/topic, distills deduplicated semantic facts
    and preferences (via an optional async/sync LLM callback with deterministic
    heuristic fallback), preserves `source_episode_ids` provenance, applies
    time-decay weights without overwriting creator-verified facts, and runs
    bidirectional `promises.md` synchronization.
    """

    _PREF_PATTERNS = (
        re.compile(r"\b(?:aku\s+suka(?:\s+banget)?|i\s+(?:really\s+)?love|i\s+like)\s+([^.,!?\n]{2,50})", re.I),
        re.compile(r"\b(?:favorit(?:e)?(?:\s+ku)?|favorite)\s*(?:is|adalah|:)?\s*([^.,!?\n]{2,50})", re.I),
    )

    def __init__(
        self,
        db: MemoryDatabase,
        markdown_sync: Optional[MarkdownBrainSync] = None,
        llm_distill_fn: Optional[DistillCallback] = None,
    ):
        self.db = db
        self.markdown_sync = markdown_sync
        self.llm_distill_fn = llm_distill_fn

    @staticmethod
    def _normalize_key(category: str, text: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
        return f"{category}:{slug[:80]}"

    def cluster_episodes(
        self,
        episodes: List[Dict[str, Any]],
    ) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
        """Groups episodic rows into (user, episode_type) clusters."""
        clusters: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for ep in episodes:
            user = (ep.get("user") or "Chat").strip() or "Chat"
            ep_type = (ep.get("episode_type") or "general").strip() or "general"
            clusters[(user, ep_type)].append(ep)
        return dict(clusters)

    def _heuristic_distill(
        self,
        user: str,
        episodes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Deterministic heuristic distillation when no LLM callback is configured."""
        grouped: Dict[str, Dict[str, Any]] = {}

        def _add(category: str, fact_key: str, fact_text: str, importance: float, confidence: float, ep_id: Optional[int]):
            if fact_key not in grouped:
                grouped[fact_key] = {
                    "fact_key": fact_key,
                    "fact_text": fact_text,
                    "category": category,
                    "importance_score": importance,
                    "confidence": confidence,
                    "source_episode_ids": [],
                }
            entry = grouped[fact_key]
            entry["importance_score"] = max(entry["importance_score"], importance)
            entry["confidence"] = max(entry["confidence"], confidence)
            if ep_id is not None and ep_id not in entry["source_episode_ids"]:
                entry["source_episode_ids"].append(int(ep_id))

        for ep in episodes:
            ep_id = ep.get("id")
            title = str(ep.get("title") or "").strip()
            content = str(ep.get("content") or "").strip()
            ep_type = str(ep.get("episode_type") or "general").strip().lower()
            importance = float(ep.get("importance_score") or 0.5)
            combined = f"{title}. {content}".strip()

            # 1. Preference extraction
            matched_pref = False
            for pat in self._PREF_PATTERNS:
                for m in pat.finditer(combined):
                    item = m.group(1).strip(" .,:;!?\"'")
                    if len(item) >= 2:
                        matched_pref = True
                        fkey = self._normalize_key("preference", item)
                        _add(
                            "preference",
                            fkey,
                            f"{user} likes {item}",
                            max(0.65, importance),
                            0.8,
                            ep_id,
                        )

            # 2. Event / domain-specific distillation
            if ep_type in ("minecraft_gift", "chess", "minecraft_attack", "donation", "promise"):
                summary = title or content[:100]
                fkey = self._normalize_key(ep_type, summary)
                _add(
                    ep_type,
                    fkey,
                    f"{user}: {summary}" if user.lower() not in summary.lower() else summary,
                    max(0.6, importance),
                    0.75,
                    ep_id,
                )
            elif not matched_pref and (importance >= 0.65 or len(episodes) >= 3):
                summary = title or content[:100]
                if summary:
                    fkey = self._normalize_key("fact", summary)
                    _add("fact", fkey, summary, importance, 0.65, ep_id)

        return list(grouped.values())

    async def _distill_cluster(
        self,
        user: str,
        episodes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if self.llm_distill_fn is not None:
            try:
                res = self.llm_distill_fn(user, episodes)
                if inspect.isawaitable(res):
                    res = await res
                if isinstance(res, list) and res:
                    normalized: List[Dict[str, Any]] = []
                    default_ids = [int(e["id"]) for e in episodes if e.get("id") is not None]
                    for item in res:
                        if not isinstance(item, dict) or not item.get("fact_text"):
                            continue
                        cat = str(item.get("category") or "fact")
                        ftext = str(item["fact_text"]).strip()
                        fkey = str(item.get("fact_key") or self._normalize_key(cat, ftext))
                        ep_ids = item.get("source_episode_ids") or default_ids
                        normalized.append({
                            "fact_key": fkey,
                            "fact_text": ftext,
                            "category": cat,
                            "importance_score": float(item.get("importance_score", 0.7)),
                            "confidence": float(item.get("confidence", 0.8)),
                            "source_episode_ids": [int(x) for x in ep_ids if x is not None],
                        })
                    if normalized:
                        return normalized
            except Exception:
                pass
        return self._heuristic_distill(user, episodes)

    async def consolidate_async(
        self,
        limit: int = 500,
        user: Optional[str] = None,
        half_life_days: float = 30.0,
        sync_promises: bool = True,
    ) -> Dict[str, Any]:
        """Runs full hierarchical consolidation, decay, and optional bidirectional promises sync."""
        episodes = self.db.get_recent_memories(limit=max(1, int(limit)), user=user)
        clusters = self.cluster_episodes(episodes)

        # Group by user across episode types so cross-type facts deduplicate per user
        user_episodes: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for (u, _ep_type), eps in clusters.items():
            user_episodes[u].extend(eps)

        facts_created = 0
        facts_updated = 0
        verified_skipped = 0

        for u, eps in user_episodes.items():
            distilled = await self._distill_cluster(u, eps)
            for fact in distilled:
                res = self.db.upsert_semantic_fact(
                    user=u,
                    fact_key=fact["fact_key"],
                    fact_text=fact["fact_text"],
                    category=fact.get("category", "fact"),
                    importance_score=float(fact.get("importance_score", 0.6)),
                    confidence=float(fact.get("confidence", 0.7)),
                    source_episode_ids=fact.get("source_episode_ids", []),
                )
                if res.get("skipped_verified"):
                    verified_skipped += 1
                elif res.get("updated"):
                    facts_updated += 1
                else:
                    facts_created += 1

        decay_stats = self.db.apply_memory_decay(half_life_days=half_life_days)

        promise_sync_stats: Dict[str, int] = {}
        if sync_promises and self.markdown_sync is not None:
            promise_sync_stats = self.markdown_sync.sync_promises_bidirectional(self.db)

        return {
            "episodes_processed": len(episodes),
            "clusters": len(clusters),
            "facts_created": facts_created,
            "facts_updated": facts_updated,
            "verified_skipped": verified_skipped,
            "decay": decay_stats,
            "promises_sync": promise_sync_stats,
        }

    def consolidate(
        self,
        limit: int = 500,
        user: Optional[str] = None,
        half_life_days: float = 30.0,
        sync_promises: bool = True,
    ) -> Dict[str, Any]:
        """Synchronous wrapper for `consolidate_async`."""
        try:
            asyncio.get_running_loop()
            # If called from inside a running loop, run heuristic sync path directly
            episodes = self.db.get_recent_memories(limit=max(1, int(limit)), user=user)
            clusters = self.cluster_episodes(episodes)
            user_episodes: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for (u, _), eps in clusters.items():
                user_episodes[u].extend(eps)

            facts_created = 0
            facts_updated = 0
            verified_skipped = 0
            for u, eps in user_episodes.items():
                for fact in self._heuristic_distill(u, eps):
                    res = self.db.upsert_semantic_fact(
                        user=u,
                        fact_key=fact["fact_key"],
                        fact_text=fact["fact_text"],
                        category=fact.get("category", "fact"),
                        importance_score=float(fact.get("importance_score", 0.6)),
                        confidence=float(fact.get("confidence", 0.7)),
                        source_episode_ids=fact.get("source_episode_ids", []),
                    )
                    if res.get("skipped_verified"):
                        verified_skipped += 1
                    elif res.get("updated"):
                        facts_updated += 1
                    else:
                        facts_created += 1

            decay_stats = self.db.apply_memory_decay(half_life_days=half_life_days)
            promise_sync_stats: Dict[str, int] = {}
            if sync_promises and self.markdown_sync is not None:
                promise_sync_stats = self.markdown_sync.sync_promises_bidirectional(self.db)
            return {
                "episodes_processed": len(episodes),
                "clusters": len(clusters),
                "facts_created": facts_created,
                "facts_updated": facts_updated,
                "verified_skipped": verified_skipped,
                "decay": decay_stats,
                "promises_sync": promise_sync_stats,
            }
        except RuntimeError:
            return asyncio.run(
                self.consolidate_async(
                    limit=limit,
                    user=user,
                    half_life_days=half_life_days,
                    sync_promises=sync_promises,
                )
            )
