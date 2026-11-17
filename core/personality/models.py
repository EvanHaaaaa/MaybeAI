import time
import uuid
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


class TraitKey(str, Enum):
    COMPETITIVENESS = "competitiveness"  # Ambisi menang, tryhard, sensitif terhadap kekalahan
    CONFIDENCE = "confidence"            # Percaya diri, keberanian, kebanggaan kemampuan AI
    WARMTH = "warmth"                    # Kehangatan, empati, keakraban pada penonton & mabar
    SASSINESS = "sassiness"              # Sarkasme, deadpan wit, ketajaman lidah, tsundere teasing
    INTELLECT = "intellect"              # Keingintahuan filosofis, daya analitis, pemikiran mendalam


@dataclass
class Milestone:
    id: str
    title: str
    description: str
    icon: str
    category: str
    unlocked_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Milestone":
        return cls(**data)


@dataclass
class ExperienceLog:
    id: str
    timestamp: float
    category: str
    trigger: str
    trait_changes: Dict[str, float]
    exp_gained: int
    narrative: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperienceLog":
        return cls(**data)


@dataclass
class EvolutionProfile:
    level: int = 1
    exp: int = 0
    exp_to_next_level: int = 100
    traits: Dict[str, float] = field(default_factory=lambda: {
        TraitKey.COMPETITIVENESS.value: 0.35,
        TraitKey.CONFIDENCE.value: 0.50,
        TraitKey.WARMTH.value: 0.60,
        TraitKey.SASSINESS.value: 0.40,
        TraitKey.INTELLECT.value: 0.50,
    })
    archetype: str = "Rookie Streamer 🌸"
    archetype_desc: str = "Idol streamer pemula yang ramah, sedikit pemalu, namun penuh potensi."
    milestones: List[Milestone] = field(default_factory=list)
    history: List[ExperienceLog] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "exp": self.exp,
            "exp_to_next_level": self.exp_to_next_level,
            "traits": {k: round(v, 4) for k, v in self.traits.items()},
            "archetype": self.archetype,
            "archetype_desc": self.archetype_desc,
            "milestones": [m.to_dict() for m in self.milestones],
            "history": [h.to_dict() for h in self.history[-30:]]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvolutionProfile":
        traits_data = data.get("traits", {})
        default_traits = {
            TraitKey.COMPETITIVENESS.value: 0.35,
            TraitKey.CONFIDENCE.value: 0.50,
            TraitKey.WARMTH.value: 0.60,
            TraitKey.SASSINESS.value: 0.40,
            TraitKey.INTELLECT.value: 0.50,
        }
        for k, v in default_traits.items():
            if k not in traits_data:
                traits_data[k] = v

        milestones = [Milestone.from_dict(m) for m in data.get("milestones", [])]
        history = [ExperienceLog.from_dict(h) for h in data.get("history", [])]

        return cls(
            level=data.get("level", 1),
            exp=data.get("exp", 0),
            exp_to_next_level=data.get("exp_to_next_level", 100),
            traits=traits_data,
            archetype=data.get("archetype", "Rookie Streamer 🌸"),
            archetype_desc=data.get("archetype_desc", "Idol streamer pemula yang ramah."),
            milestones=milestones,
            history=history
        )
