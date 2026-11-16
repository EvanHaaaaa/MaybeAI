import time
import uuid
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


class RelationshipTier(str, Enum):
    NEW_FRIEND = "new_friend"          # Teman Baru / Penonton Baru (Sopan, ramah, mengamati)
    REGULAR_VIEWER = "regular_viewer"  # Penonton Setia / Reguler (Akrab, sering hadir di stream)
    GAMING_PARTNER = "gaming_partner"  # Partner Mabar / Rekan Game (Sinergi coop Minecraft, survival jokes)
    RIVAL = "rival"                    # Rival Sengit / Lawan Tanding (Catur, PvP, adu ELO, trash-talk)
    TRUSTED_FRIEND = "trusted_friend"  # Sahabat Dekat / Orang Tepercaya (Inside jokes eksklusif, curhat hangat)


@dataclass
class InsideJoke:
    id: str
    topic: str
    punchline: str
    context: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InsideJoke":
        return cls(**data)


@dataclass
class SharedExperience:
    id: str
    category: str  # "minecraft", "chess", "chat", "donation", "secret"
    summary: str
    impact: str = "positive"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SharedExperience":
        return cls(**data)


@dataclass
class RelationshipProfile:
    username: str
    tier: str = RelationshipTier.NEW_FRIEND.value
    familiarity: float = 0.10      # 0.0 to 1.0 (seberapa sering & lama berinteraksi)
    trust: float = 0.20            # 0.0 to 1.0 (kepercayaan, obrolan mendalam, janji)
    rivalry: float = 0.05          # 0.0 to 1.0 (rivalitas catur, tantangan game, pvp)
    gaming_affinity: float = 0.05  # 0.0 to 1.0 (pengalaman bermain bersama di Minecraft/Catur)
    affection: float = 0.30        # 0.0 to 1.0 (kehangatan dan kedekatan emosional)
    interaction_count: int = 0
    special_nickname: Optional[str] = None
    inside_jokes: List[InsideJoke] = field(default_factory=list)
    shared_experiences: List[SharedExperience] = field(default_factory=list)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def recalculate_tier(self) -> str:
        """
        Dynamically determines relationship archetype based on multi-dimensional
        interaction history, not merely raw message counts.
        """
        # Rival: High rivalry score from chess duels or friendly combat
        if self.rivalry >= 0.45:
            self.tier = RelationshipTier.RIVAL.value
            if not self.special_nickname:
                self.special_nickname = "Rival Abadi"

        # Gaming Partner: High coop synergy from Minecraft or joint game sessions
        elif self.gaming_affinity >= 0.45:
            self.tier = RelationshipTier.GAMING_PARTNER.value
            if not self.special_nickname:
                self.special_nickname = "Partner Mabar"

        # Trusted Friend: High trust and familiarity built through sincere conversations
        elif self.trust >= 0.60 and self.familiarity >= 0.45:
            self.tier = RelationshipTier.TRUSTED_FRIEND.value
            if not self.special_nickname:
                self.special_nickname = "Bestie Stream"

        # Regular Viewer: Consistent stream presence
        elif self.familiarity >= 0.30 or self.interaction_count >= 8:
            self.tier = RelationshipTier.REGULAR_VIEWER.value
            if not self.special_nickname:
                self.special_nickname = "Penonton Setia"

        # Baseline newcomer
        else:
            self.tier = RelationshipTier.NEW_FRIEND.value

        return self.tier

    def add_inside_joke(self, topic: str, punchline: str, context: str = "") -> InsideJoke:
        joke = InsideJoke(
            id=f"joke_{uuid.uuid4().hex[:6]}",
            topic=topic,
            punchline=punchline,
            context=context
        )
        self.inside_jokes.append(joke)
        if len(self.inside_jokes) > 10:
            self.inside_jokes = self.inside_jokes[-10:]
        return joke

    def record_experience(self, category: str, summary: str, impact: str = "positive") -> SharedExperience:
        exp = SharedExperience(
            id=f"exp_{uuid.uuid4().hex[:6]}",
            category=category,
            summary=summary,
            impact=impact
        )
        self.shared_experiences.append(exp)
        if len(self.shared_experiences) > 20:
            self.shared_experiences = self.shared_experiences[-20:]
        return exp

    def get_tier_label(self) -> str:
        labels = {
            RelationshipTier.NEW_FRIEND.value: "New Friend 🌟",
            RelationshipTier.REGULAR_VIEWER.value: "Regular Viewer ☕",
            RelationshipTier.GAMING_PARTNER.value: "Gaming Partner 🎮",
            RelationshipTier.RIVAL.value: "Rival Sengit ⚔️",
            RelationshipTier.TRUSTED_FRIEND.value: "Trusted Friend 💖"
        }
        return labels.get(self.tier, "Friend")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "username": self.username,
            "tier": self.tier,
            "tier_label": self.get_tier_label(),
            "familiarity": round(self.familiarity, 2),
            "trust": round(self.trust, 2),
            "rivalry": round(self.rivalry, 2),
            "gaming_affinity": round(self.gaming_affinity, 2),
            "affection": round(self.affection, 2),
            "interaction_count": self.interaction_count,
            "special_nickname": self.special_nickname,
            "inside_jokes": [j.to_dict() if isinstance(j, InsideJoke) else j for j in self.inside_jokes],
            "shared_experiences": [e.to_dict() if isinstance(e, SharedExperience) else e for e in self.shared_experiences],
            "first_seen": self.first_seen,
            "last_seen": self.last_seen
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelationshipProfile":
        d = dict(data)
        d.pop("tier_label", None)
        jokes = [InsideJoke.from_dict(j) if isinstance(j, dict) else j for j in d.get("inside_jokes", [])]
        exps = [SharedExperience.from_dict(e) if isinstance(e, dict) else e for e in d.get("shared_experiences", [])]
        d["inside_jokes"] = jokes
        d["shared_experiences"] = exps
        return cls(**d)
