import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Any, Optional


class PerformanceStatus(str, Enum):
    IDLE = "idle"                            # Panggung standby
    MC_INTRO = "mc_intro"                    # Eve membuka panggung, interaksi dengan chat
    PERFORMING = "performing"                # Bernyanyi + koreografi aktif
    MC_OUTRO = "mc_outro"                    # Ulasan vokal, terima kasih, self-rating
    ENCORE = "encore"                        # Encore lagu tambahan dari chat


class SongMoodCategory(str, Enum):
    HYPE_ENERGETIC = "hype_energetic"        # Lagu semangat/pop banger (HYPE_EXCITED)
    EMOTIONAL_CHILL = "emotional_chill"      # Lagu lofi/ballad (CURIOUS_PENSIVE)
    SASSY_COMPETITIVE = "sassy_competitive"  # Lagu cyber-rock/rap cepat (TRYHARD_COMPETITIVE)
    CUTE_PLAYFUL = "cute_playful"            # Lagu anime tsundere/parodi (SASSY_ANNOYED / HYPE)


class StageMovement(str, Enum):
    SWAY_LEFT = "sway_left"                  # Goyang badan ke kiri
    SWAY_RIGHT = "sway_right"                # Goyang badan ke kanan
    BOUNCE = "bounce"                        # Melompat berirama
    SPARKLE_POSE = "sparkle_pose"            # Pose idol berkilau
    HEAD_TILT = "head_tilt"                  # Memiringkan kepala imut
    BOW = "bow"                              # Membungkuk hormat idol


@dataclass
class ChoreographyStep:
    section: str = "verse"                   # "intro", "verse", "pre_chorus", "chorus", "bridge", "drop", "outro"
    emotion: str = "happy"                   # "happy", "smug", "blush", "excited", "surprised", "pout"
    action: str = "wink"                     # "wink", "nod", "tilt", "giggle", "gasp"
    movement: str = StageMovement.SWAY_LEFT.value
    stage_lighting: str = "neon_cyan"        # "neon_cyan", "magenta_pop", "golden_glow", "starlight_blue"
    crowd_callout: Optional[str] = None      # "Ayo angkat glowstick kalian!", "Mana suaranya chat?!"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChoreographyStep":
        return cls(**data)


@dataclass
class SetlistItem:
    order: int
    song_id: str
    title: str
    mood_category: str
    status: str = "queued"                   # "queued", "current", "completed"
    reason: str = "Dipilih otomatis berdasarkan energi stream."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SetlistItem":
        return cls(**data)


@dataclass
class PerformanceSession:
    id: str = field(default_factory=lambda: f"show_{uuid.uuid4().hex[:6]}")
    status: str = PerformanceStatus.IDLE.value
    current_song_id: Optional[str] = None
    current_title: Optional[str] = None
    current_section: str = "intro"
    current_step: Optional[ChoreographyStep] = None
    dominant_mood: str = "HYPE_EXCITED"
    mood_reason: str = "Eve bersemangat menyapa para penonton!"
    setlist: List[SetlistItem] = field(default_factory=list)
    audience_glowsticks: int = 42
    performance_score: int = 95              # Self-rating 0-100
    cheers_history: List[Dict[str, Any]] = field(default_factory=list)
    encore_requested: bool = False
    total_shows_completed: int = 1
    last_mc_intro: str = "Selamat datang di panggung musik Eve Maybe! Siapin glowstick kalian ya!"
    last_mc_outro: str = "Terima kasih semuanya sudah menyanyi bersama Eve! Penampilan tadi kuberi nilai 95/100!"
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "current_song_id": self.current_song_id,
            "current_title": self.current_title,
            "current_section": self.current_section,
            "current_step": self.current_step.to_dict() if self.current_step else None,
            "dominant_mood": self.dominant_mood,
            "mood_reason": self.mood_reason,
            "setlist": [item.to_dict() for item in self.setlist],
            "audience_glowsticks": self.audience_glowsticks,
            "performance_score": self.performance_score,
            "cheers_history": self.cheers_history[-10:],
            "encore_requested": self.encore_requested,
            "total_shows_completed": self.total_shows_completed,
            "last_mc_intro": self.last_mc_intro,
            "last_mc_outro": self.last_mc_outro,
            "started_at_str": time.strftime("%H:%M:%S", time.localtime(self.started_at)),
            "updated_at_str": time.strftime("%H:%M:%S", time.localtime(self.updated_at))
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerformanceSession":
        step = ChoreographyStep.from_dict(data["current_step"]) if data.get("current_step") else None
        setlist = [SetlistItem.from_dict(it) for it in data.get("setlist", [])]

        return cls(
            id=data.get("id", f"show_{uuid.uuid4().hex[:6]}"),
            status=data.get("status", PerformanceStatus.IDLE.value),
            current_song_id=data.get("current_song_id"),
            current_title=data.get("current_title"),
            current_section=data.get("current_section", "intro"),
            current_step=step,
            dominant_mood=data.get("dominant_mood", "HYPE_EXCITED"),
            mood_reason=data.get("mood_reason", "Standby panggung."),
            setlist=setlist,
            audience_glowsticks=data.get("audience_glowsticks", 0),
            performance_score=data.get("performance_score", 90),
            cheers_history=data.get("cheers_history", []),
            encore_requested=data.get("encore_requested", False),
            total_shows_completed=data.get("total_shows_completed", 0),
            last_mc_intro=data.get("last_mc_intro", ""),
            last_mc_outro=data.get("last_mc_outro", ""),
            started_at=data.get("started_at", time.time()),
            updated_at=data.get("updated_at", time.time())
        )
