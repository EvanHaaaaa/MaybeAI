import time
import uuid
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional


class VisualSceneType(str, Enum):
    MINECRAFT_PLAYING = "minecraft_playing"   # In-game gameplay Minecraft (eksplorasi, mining, survival)
    MINECRAFT_DEFEAT = "minecraft_defeat"     # Layar kematian Minecraft ("You Died!", red screen overlay)
    MINECRAFT_DIAMOND = "minecraft_diamond"   # Menemukan urat bijih diamond bercahaya di gua
    CHESS_MATCH = "chess_match"               # Papan catur aktif dalam pertandingan
    CHESS_GAMEOVER = "chess_gameover"         # Papan catur berakhir (skakmat / victory / defeat)
    VIDEO_WATCHING = "video_watching"         # Sedang menonton video YouTube / livestream media player
    DESKTOP_GENERAL = "desktop_general"       # Tampilan desktop umum, code editor (IDE), atau browser
    UNKNOWN = "unknown"                       # Scene visual belum teridentifikasi


@dataclass
class VisualObservation:
    id: str = field(default_factory=lambda: f"vis_{uuid.uuid4().hex[:8]}")
    timestamp: float = field(default_factory=time.time)
    scene_type: str = VisualSceneType.DESKTOP_GENERAL.value
    scene_label: str = "Desktop / General Workspace"
    confidence: float = 0.85
    summary: str = "Tampilan umum desktop dan jendela aktif."
    details: Dict[str, Any] = field(default_factory=dict)
    change_delta: float = 0.0          # 0.0 to 1.0 (perubahan visual dibanding frame sebelumnya)
    is_event: bool = False             # Apakah frame ini menandai peristiwa penting (mati, menang, diamond, dll)
    event_type: Optional[str] = None   # "player_defeat", "diamond_found", "checkmate", "video_funny", "scene_change"
    thumbnail_base64: Optional[str] = None  # Base64 JPEG data URI untuk UI & VLM
    eve_commentary: Optional[str] = None    # Komentar Eve berdasarkan apa yang dilihatnya di layar

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "scene_type": self.scene_type,
            "scene_label": self.scene_label,
            "confidence": round(self.confidence, 2),
            "summary": self.summary,
            "details": self.details,
            "change_delta": round(self.change_delta, 3),
            "is_event": self.is_event,
            "event_type": self.event_type,
            "thumbnail_base64": self.thumbnail_base64,
            "eve_commentary": self.eve_commentary,
            "formatted_time": time.strftime("%H:%M:%S", time.localtime(self.timestamp))
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisualObservation":
        clean = {k: v for k, v in data.items() if k != "formatted_time"}
        return cls(**clean)


@dataclass
class VisionConfig:
    capture_interval_sec: float = 5.0
    auto_perception: bool = True
    change_threshold: float = 0.08         # 8% perbedaan piksel dianggap perubahan visual signifikan
    max_thumbnail_width: int = 480
    max_thumbnail_height: int = 270
    cooldown_commentary_sec: float = 10.0  # Jeda minimal antar komentar visual otomatis Eve
    use_simulation_fallback: bool = True   # Fallback ke generator sintetis jika display native terhalang
