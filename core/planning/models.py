from dataclasses import dataclass, field, asdict
from enum import Enum
import time
from typing import List, Dict, Any, Optional


class GoalTier(str, Enum):
    DAILY = "daily"            # Tujuan hari ini (e.g. membangun rumah di Minecraft)
    WEEKLY = "weekly"          # Tujuan mingguan (e.g. menyelesaikan tantangan speedrun)
    SHORT_TERM = "short_term"  # Tujuan berikutnya / sub-goal (e.g. mengumpulkan 64 iron)
    SOCIAL = "social"          # Tujuan sosial (e.g. berinteraksi dengan player belum dikenal)


class GoalStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"
    REPLANNED = "replanned"


class GoalCategory(str, Enum):
    MINECRAFT = "minecraft"
    CHESS = "chess"
    SOCIAL = "social"
    STREAM = "stream"
    CREATIVE = "creative"
    GENERAL = "general"


@dataclass
class Subtask:
    id: str
    title: str
    description: str = ""
    category: str = "general"
    status: str = GoalStatus.PENDING.value
    progress: float = 0.0
    current_count: float = 0.0
    target_count: float = 1.0
    unit: str = "step"
    strategy: str = ""
    failure_reason: Optional[str] = None
    alternative_strategy: Optional[str] = None
    attempts: int = 1
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def update_progress(self, delta: float = 1.0) -> bool:
        """Increments current count, updates progress ratio, returns True if just completed."""
        self.current_count = min(self.target_count, self.current_count + delta)
        if self.target_count > 0:
            self.progress = min(1.0, max(0.0, self.current_count / self.target_count))
        else:
            self.progress = 1.0

        if self.progress >= 1.0 and self.status != GoalStatus.COMPLETED.value:
            self.status = GoalStatus.COMPLETED.value
            self.completed_at = time.time()
            return True
        return False

    def mark_completed(self):
        self.current_count = self.target_count
        self.progress = 1.0
        self.status = GoalStatus.COMPLETED.value
        self.completed_at = time.time()

    def mark_failed(self, reason: str, alternative_strategy: str = ""):
        self.status = GoalStatus.FAILED.value
        self.failure_reason = reason
        self.alternative_strategy = alternative_strategy

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Subtask":
        return cls(**data)


@dataclass
class Goal:
    id: str
    title: str
    description: str = ""
    tier: str = GoalTier.DAILY.value
    category: str = GoalCategory.GENERAL.value
    status: str = GoalStatus.PENDING.value
    subtasks: List[Subtask] = field(default_factory=list)
    active_subtask_index: int = 0
    priority: int = 5  # 1 (lowest) to 10 (highest)
    autonomous: bool = True
    progress: float = 0.0
    reflection: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def recalculate_progress(self) -> float:
        """Recalculates overall goal progress based on subtasks."""
        if not self.subtasks:
            self.progress = 1.0 if self.status == GoalStatus.COMPLETED.value else 0.0
            return self.progress

        total_prog = sum(s.progress for s in self.subtasks)
        self.progress = round(total_prog / len(self.subtasks), 2)
        if all(s.status == GoalStatus.COMPLETED.value for s in self.subtasks):
            self.status = GoalStatus.COMPLETED.value
            if not self.completed_at:
                self.completed_at = time.time()
        elif any(s.status == GoalStatus.IN_PROGRESS.value for s in self.subtasks):
            self.status = GoalStatus.IN_PROGRESS.value
        return self.progress

    def get_active_subtask(self) -> Optional[Subtask]:
        """Returns the first currently in-progress or pending subtask."""
        for s in self.subtasks:
            if s.status in (GoalStatus.IN_PROGRESS.value, GoalStatus.PENDING.value):
                return s
        return None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["subtasks"] = [s.to_dict() if isinstance(s, Subtask) else s for s in self.subtasks]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Goal":
        d = dict(data)
        raw_subs = d.get("subtasks", [])
        subs = []
        for s in raw_subs:
            if isinstance(s, dict):
                subs.append(Subtask.from_dict(s))
            elif isinstance(s, Subtask):
                subs.append(s)
        d["subtasks"] = subs
        return cls(**d)
