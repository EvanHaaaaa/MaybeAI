import re
from typing import Dict, Any, Optional
from core.memory.database import MemoryDatabase
from core.memory.markdown_sync import MarkdownBrainSync

class MemoryExtractor:
    """
    Intelligently extracts, categorizes, and commits episodic experiences,
    viewer preferences, promises, and funny stream moments to the Second Brain.
    """

    def __init__(self, db: MemoryDatabase, markdown_sync: MarkdownBrainSync):
        self.db = db
        self.markdown_sync = markdown_sync

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
        """Stores memory into SQLite and syncs to Karpathy Markdown journal."""
        mem_id = self.db.add_episodic_memory(
            title=title,
            content=content,
            episode_type=episode_type,
            user=user,
            emotional_tag=emotional_tag,
            importance_score=importance_score,
            game_context=game_context,
            metadata=metadata
        )
        saved = self.db.get_memory(mem_id)
        if saved:
            self.markdown_sync.sync_episodic_memory(saved)
        return mem_id

    # --- Minecraft Event Ingestion ---

    def on_minecraft_gift(self, player: str, item: str):
        title = f"{player} Memberi Hadiah {item}"
        content = f"{player} memberikan Eve hadiah {item} di Minecraft! Eve sangat senang dan berjanji akan menyimpannya baik-baik."
        self.record_episode(
            title=title,
            content=content,
            episode_type="minecraft_gift",
            user=player,
            emotional_tag="happy",
            importance_score=0.9,
            game_context="Minecraft Survival"
        )
        self.db.add_user_note(player, f"Pernah ngasih hadiah {item} di Minecraft")
        self.db.add_user_preference(player, "gifted_items", item)

    def on_minecraft_attack(self, player: str):
        title = f"{player} Menyerang Eve di Minecraft"
        content = f"{player} memukul Eve di Minecraft! Eve terkejut dan mencatat kejadian jahil ini di memori utamanya."
        self.record_episode(
            title=title,
            content=content,
            episode_type="funny_moment",
            user=player,
            emotional_tag="angry",
            importance_score=0.75,
            game_context="Minecraft Survival"
        )
        self.db.add_user_note(player, "Pernah memukul/menyerang Eve di Minecraft")

    def on_minecraft_guard_incident(self, player: str, mob: str):
        title = f"Eve Melindungi {player} dari {mob}"
        content = f"Eve berhasil melindungi {player} dari ancaman {mob} saat bertugas sebagai bodyguard di Minecraft."
        self.record_episode(
            title=title,
            content=content,
            episode_type="minecraft_guard",
            user=player,
            emotional_tag="smug",
            importance_score=0.8,
            game_context="Minecraft Guard Mode"
        )
        self.db.add_user_note(player, f"Pernah dijaga Eve dari serangan {mob}")

    def on_minecraft_joined(self, player: str):
        self.db.record_user_game(player, "minecraft", "played")

    # --- Chess Event Ingestion ---

    def on_chess_game_ended(
        self,
        player: str,
        eve_won: bool,
        player_won: bool,
        result: str,
        moves_count: int,
        elo: int
    ):
        outcome = "Eve Menang" if eve_won else ("Pemain Menang" if player_won else "Seri")
        title = f"Pertandingan Catur vs {player} ({outcome})"
        content = f"Eve bertanding catur melawan {player} di ELO {elo} selama {moves_count} langkah. Hasil akhir: {outcome} ({result})."
        
        self.record_episode(
            title=title,
            content=content,
            episode_type="chess_match",
            user=player,
            emotional_tag="smug" if eve_won else ("surprised" if player_won else "neutral"),
            importance_score=0.85,
            game_context=f"Chess Arena ELO {elo}"
        )
        res_key = "won" if player_won else ("loss" if eve_won else "draw")
        self.db.record_user_game(player, "chess", res_key)
        self.db.add_user_note(player, f"Pernah tanding catur di ELO {elo} ({outcome})")

    def on_chess_queen_capture(self, player: str, eve_captured_player_queen: bool, san: str):
        if eve_captured_player_queen:
            title = f"Eve Menumbangkan Ratu {player}"
            content = f"Eve memakan Ratu milik {player} dengan langkah {san} di papan catur! Momen dramatis."
            self.record_episode(
                title=title,
                content=content,
                episode_type="chess_highlight",
                user=player,
                emotional_tag="smug",
                importance_score=0.8,
                game_context="Chess Match"
            )
            self.db.add_user_note(player, "Pernah blunder Ratu di depan Eve saat main catur")

    # --- Live Chat Ingestion & NLP Heuristics ---

    def extract_from_chat(self, user: str, text: str, is_donation: bool = False, donation_amount: str = ""):
        if not user or user in ("Chat", "System", "Eve"):
            return

        # 1. Update basic chatter metrics
        self.db.update_user_interaction(user, text)

        # 2. Donation / Superchat extraction
        if is_donation and donation_amount:
            self.db.record_donation(user, donation_amount)
            title = f"Superchat {donation_amount} dari {user}"
            content = f"{user} mengirimkan donasi sebesar {donation_amount} dengan pesan: '{text}'"
            self.record_episode(
                title=title,
                content=content,
                episode_type="donation",
                user=user,
                emotional_tag="blush",
                importance_score=0.95,
                game_context="Live Stream Donation"
            )
            self.db.add_user_note(user, f"Pernah donasi {donation_amount}")
            return

        lower = text.lower()

        # 3. Preferences ("aku suka X", "makanan favoritku X", "i love X")
        if "aku suka " in lower or "i like " in lower or "i love " in lower or "gemar " in lower:
            pref = ""
            for pat in ["aku suka banget ", "aku suka sekali ", "aku suka ", "i really like ", "i like ", "i love ", "gemar "]:
                if pat in lower:
                    pref = lower.split(pat, 1)[1].split(".")[0].split(",")[0].strip(" !?.,")
                    break
            if pref and len(pref) < 40:
                self.db.add_user_preference(user, "likes", pref)
                self.db.add_user_note(user, f"Suka {pref}")

        if "makanan favoritku" in lower or "favorite food" in lower:
            match = re.search(r"(?:makanan favoritku|favorite food) (?:adalah |is )?([a-zA-Z0-9\s]{3,30})", lower)
            if match:
                food = match.group(1).strip()
                self.db.add_user_preference(user, "favorite_food", food)
                self.db.add_user_note(user, f"Makanan favorit: {food}")

        # 4. Promises ("aku janji", "eve janji", "i promise")
        if "aku janji" in lower or "i promise" in lower:
            promise_text = text.strip()
            pid = self.db.add_promise_or_challenge(user=user, text=promise_text, ptype="promise")
            self.markdown_sync.sync_promise(pid, user, promise_text, "promise", "pending")
            self.record_episode(
                title=f"Janji dari {user}",
                content=f"{user} membuat janji kepada Eve: '{promise_text}'",
                episode_type="promise",
                user=user,
                emotional_tag="happy",
                importance_score=0.85
            )

        # 5. Challenges ("aku tantang", "i challenge you", "tantangan:")
        if "aku tantang" in lower or "i challenge" in lower or "tantangan:" in lower:
            challenge_text = text.strip()
            cid = self.db.add_promise_or_challenge(user=user, text=challenge_text, ptype="challenge")
            self.markdown_sync.sync_promise(cid, user, challenge_text, "challenge", "pending")
            self.record_episode(
                title=f"Tantangan dari {user}",
                content=f"{user} memberikan tantangan: '{challenge_text}'",
                episode_type="challenge",
                user=user,
                emotional_tag="smug",
                importance_score=0.85
            )

        # 6. Personal stories ("kemarin aku", "tadi siang aku", "!story")
        if lower.startswith("!story") or "kemarin aku " in lower or "tadi siang aku " in lower:
            clean_story = text.replace("!story", "").strip()
            if len(clean_story) > 15:
                self.db.add_user_story(user, clean_story)
                self.record_episode(
                    title=f"Cerita dari {user}",
                    content=f"{user} menceritakan pengalamannya: '{clean_story}'",
                    episode_type="viewer_story",
                    user=user,
                    emotional_tag="surprised",
                    importance_score=0.75
                )
                self.db.add_user_note(user, f"Pernah cerita: {clean_story[:50]}...")
