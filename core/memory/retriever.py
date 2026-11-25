from typing import Dict, Any, List, Optional
from core.memory.database import MemoryDatabase

class MemoryRecallResult:
    def __init__(
        self,
        episodes: List[Dict[str, Any]],
        user_profile: Optional[Dict[str, Any]],
        promises: List[Dict[str, Any]]
    ):
        self.episodes = episodes
        self.user_profile = user_profile
        self.promises = promises

    def to_prompt_text(self, current_user: str) -> str:
        """Generates the prompt injection block for MasterPromptBuilder."""
        sections = []

        # 1. User Profile, Rapport & Known Preferences
        if self.user_profile and self.user_profile.get("username") not in ("Chat", "System"):
            u = self.user_profile
            user_bits = []
            
            # Tags & Interactions
            tags = ", ".join(u.get("tags", [])) or "viewer"
            count = u.get("interaction_count", 0)
            user_bits.append(f"Relationship: [{tags}, {count} past interactions]")

            # Preferences
            prefs = u.get("preferences", {})
            pref_strs = []
            for k, vals in prefs.items():
                if vals:
                    pref_strs.append(f"{k}: {', '.join(vals[:3])}")
            if pref_strs:
                user_bits.append(f"Known preferences: {'; '.join(pref_strs)}")

            # Game history
            games = u.get("games_played", {})
            if games:
                g_str = ", ".join(f"{g} ({cnt}x)" for g, cnt in games.items())
                user_bits.append(f"Games played with Eve: {g_str}")

            # Notes
            notes = u.get("notes", [])
            if notes:
                user_bits.append(f"Key memories: {'; '.join(notes[-3:])}")

            sections.append(f"- Viewer Lore for {current_user}:\n  * " + "\n  * ".join(user_bits))

        # 2. Relevant Past Episodes
        if self.episodes:
            ep_lines = []
            for ep in self.episodes[:3]:
                date_str = ep.get("date_str", "")[:10]
                ep_type = ep.get("episode_type", "event")
                title = ep.get("title", "")
                content = ep.get("content", "")
                ep_lines.append(f"[{date_str} - {ep_type}] **{title}**: {content}")
            sections.append("- Relevant Past Episodes from Eve's Memory:\n  * " + "\n  * ".join(ep_lines))

        # 3. Active Promises & Challenges
        if self.promises:
            p_lines = []
            for p in self.promises[:2]:
                p_lines.append(f"[{p.get('type', 'promise').upper()}] {p.get('text', '')}")
            sections.append("- Pending Promises / Challenges with this viewer:\n  * " + "\n  * ".join(p_lines))

        if not sections:
            return ""

        joined_sections = "\n\n".join(sections)
        return f"""[🧠 EVE'S SECOND BRAIN & EPISODIC MEMORY RECALL]
{joined_sections}

INSTRUCTION FOR EVE:
Casually and charmingly reference these past memories! E.g.:
- "Eh, kamu yang kemarin ngasih aku diamond, kan?"
- "Bukannya kamu kemarin blunder ratu di catur?"
- "Janji kamu kemarin mau bawain martabak manis mana nih?"
Speak naturally like an AI streamer who truly remembers her community."""


class MemoryRetriever:
    """Retrieval orchestrator performing semantic & user-targeted memory lookups."""

    def __init__(self, db: MemoryDatabase):
        self.db = db

    def recall(
        self,
        query: str,
        current_user: str = "Chat",
        game_context: str = "",
        top_k: int = 3
    ) -> MemoryRecallResult:
        """
        Retrieves episodic memories, user lore, and promises relevant to current turn.
        """
        # 1. Retrieve user profile
        user_profile = None
        if current_user and current_user not in ("Chat", "System", "Eve", "EveMaybe"):
            user_profile = self.db.get_or_create_user(current_user)

        # 2. Retrieve user-specific and topical episodic memories
        query_text = f"{current_user} {query} {game_context}".strip()
        try:
            matched_episodes = self.db.hybrid_search(
                query_str=query_text,
                top_k=top_k
            )
        except Exception:
            matched_episodes = []

        # If user has specific memories not yet in matched, prepend them
        if current_user and current_user not in ("Chat", "System"):
            user_specific = self.db.get_recent_memories(limit=2, user=current_user)
            seen_ids = {e["id"] for e in matched_episodes}
            for u_ep in user_specific:
                if u_ep["id"] not in seen_ids:
                    matched_episodes.insert(0, u_ep)

        # 3. Retrieve pending promises
        promises = self.db.get_pending_promises(user=current_user if current_user not in ("Chat", "System") else None)

        return MemoryRecallResult(
            episodes=matched_episodes[:top_k],
            user_profile=user_profile,
            promises=promises
        )

    async def arecall(
        self,
        query: str,
        current_user: str = "Chat",
        game_context: str = "",
        top_k: int = 3
    ) -> MemoryRecallResult:
        """
        Async counterpart to recall(), using non-blocking ahybrid_search.
        """
        user_profile = None
        if current_user and current_user not in ("Chat", "System", "Eve", "EveMaybe"):
            user_profile = self.db.get_or_create_user(current_user)

        query_text = f"{current_user} {query} {game_context}".strip()
        try:
            matched_episodes = await self.db.ahybrid_search(
                query_str=query_text,
                top_k=top_k
            )
        except Exception:
            matched_episodes = []

        if current_user and current_user not in ("Chat", "System"):
            user_specific = self.db.get_recent_memories(limit=2, user=current_user)
            seen_ids = {e["id"] for e in matched_episodes}
            for u_ep in user_specific:
                if u_ep["id"] not in seen_ids:
                    matched_episodes.insert(0, u_ep)

        promises = self.db.get_pending_promises(user=current_user if current_user not in ("Chat", "System") else None)

        return MemoryRecallResult(
            episodes=matched_episodes[:top_k],
            user_profile=user_profile,
            promises=promises
        )
