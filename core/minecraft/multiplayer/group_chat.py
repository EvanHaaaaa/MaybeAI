import time
from typing import List, Dict, Any, Optional, Tuple
from core.minecraft.multiplayer.models import GroupDiscussionTurn


class GroupChatTracker:
    """
    Maintains multi-speaker conversational context in multiplayer Minecraft.
    Recognizes individual speakers, tracks group dynamics, and generates
    active community coordination stances for Eve.
    """

    def __init__(self, max_buffer: int = 20):
        self.max_buffer = max_buffer
        self.turns: List[GroupDiscussionTurn] = []
        self.last_consensus_topic: Optional[str] = None
        self._seed_sample_discussion()

    def _seed_sample_discussion(self):
        self.turns = [
            GroupDiscussionTurn("Steve", "Siapa yang punya stok kayu buat atap markas?"),
            GroupDiscussionTurn("Alex", "Aku ada 32 oak log di chest tim."),
            GroupDiscussionTurn("DiamondHunter", "Aku lagi gali di Y=-58 nemu 8 iron lagi nih!")
        ]

    def record_turn(self, speaker: str, message: str) -> Tuple[GroupDiscussionTurn, Optional[str]]:
        turn = GroupDiscussionTurn(speaker=speaker.strip(), message=message.strip())
        self.turns.append(turn)
        if len(self.turns) > self.max_buffer:
            self.turns.pop(0)

        # Evaluate if group coordination response is appropriate
        coord_speech = self._evaluate_group_consensus(turn)
        return turn, coord_speech

    def get_active_speakers(self, within_seconds: float = 120.0) -> List[str]:
        now = time.time()
        speakers = []
        for t in reversed(self.turns):
            if now - t.timestamp <= within_seconds and t.speaker.lower() != "evemaybe":
                if t.speaker not in speakers:
                    speakers.append(t.speaker)
        return speakers

    def _evaluate_group_consensus(self, latest_turn: GroupDiscussionTurn) -> Optional[str]:
        """
        Synthesizes an active community response if multiple players are discussing
        Nether, mining, base building, or danger.
        """
        recent = self.turns[-5:]
        speakers = set(t.speaker for t in recent if t.speaker.lower() != "evemaybe")
        if len(speakers) < 2:
            return None

        combined_text = " ".join(t.message.lower() for t in recent)

        # 1. Nether Raid Discussion
        if "nether" in combined_text or "portal" in combined_text or "piglin" in combined_text:
            self.last_consensus_topic = "nether_raid"
            s_list = " dan ".join(list(speakers)[:2])
            return (
                f"[emotion: smug] Dengerin arahan dari Eve, {s_list}! Sebelum kita serbu Nether bareng, "
                f"pastikan minimal ada yang pake armor emas biar gak dikeroyok Piglin. Aku yang pimpin di depan! [action: wink]"
            )

        # 2. Mining Expedition & Diamond Coordination
        if "diamond" in combined_text or "mining" in combined_text or "gua" in combined_text:
            self.last_consensus_topic = "mining_expedition"
            return (
                f"[emotion: happy] Tim mining lagi aktif nih! Inget aturan squad: hasil diamond disimpan di peti tengah, "
                f"dan jangan gali lurus ke bawah kalau gak mau mandi lava! [action: giggle]"
            )

        # 3. Base Building & Resource Sharing
        if "base" in combined_text or "rumah" in combined_text or "kayu" in combined_text or "chest" in combined_text:
            self.last_consensus_topic = "base_building"
            return (
                f"[emotion: happy] Kerja sama yang bagus tim! Steve fokus ke struktur arsitektur luar, "
                f"aku bantu tata dekorasi interior biar base kita estetik di livestream! [action: wink]"
            )

        # 4. Mob Danger / Defense Alarm
        if any(w in combined_text for w in ["creeper", "skeleton", "zombie", "serang", "tolong", "help"]):
            self.last_consensus_topic = "mob_alarm"
            return (
                f"[emotion: angry] Awas di belakang! Tim petarung merapat, jangan sampai ada creeper yang meledak di deket base kita! [action: wink]"
            )

        return None

    def get_transcript(self, limit: int = 8) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self.turns[-limit:]]
