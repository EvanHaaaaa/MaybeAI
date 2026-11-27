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
    PERFORMANCE = "performance"
    CREATIVE = "creative"
    GENERAL = "general"


@dataclass
class ReflectionLesson:
    """Structured causal lesson learned from a goal or subtask failure/adaptation."""
    strategy_used: str
    failure_reason: str
    root_cause: str
    recommended_alternative: str
    category: str = GoalCategory.GENERAL.value
    subtask_title: str = ""
    goal_title: str = ""
    outcome: str = "failed"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReflectionLesson":
        return cls(
            strategy_used=str(data.get("strategy_used", "")),
            failure_reason=str(data.get("failure_reason", "")),
            root_cause=str(data.get("root_cause", "general_execution_failure")),
            recommended_alternative=str(data.get("recommended_alternative", "")),
            category=str(data.get("category", GoalCategory.GENERAL.value)),
            subtask_title=str(data.get("subtask_title", "")),
            goal_title=str(data.get("goal_title", "")),
            outcome=str(data.get("outcome", "failed")),
            timestamp=float(data.get("timestamp", time.time())),
        )


def parse_reflection_lesson(entry: Any) -> Optional[ReflectionLesson]:
    """Converts a ReflectionLesson, dict, Goal, or reflection string into a ReflectionLesson."""
    if entry is None:
        return None
    if isinstance(entry, ReflectionLesson):
        return entry
    if isinstance(entry, dict):
        if any(k in entry for k in ("strategy_used", "failure_reason", "root_cause", "recommended_alternative")):
            return ReflectionLesson.from_dict(entry)
        return None
    if isinstance(entry, Goal):
        lessons = entry.get_recent_lessons(limit=1)
        return lessons[0] if lessons else None
    if isinstance(entry, str):
        text = entry.strip()
        if not text:
            return None
        return ReflectionLesson(
            strategy_used="",
            failure_reason=text,
            root_cause="historical_reflection",
            recommended_alternative=text,
            category=GoalCategory.GENERAL.value,
        )
    return None


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
    reflection_lessons: List[ReflectionLesson] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def add_reflection_lesson(
        self,
        strategy_used: str,
        failure_reason: str,
        root_cause: str,
        recommended_alternative: str,
        category: Optional[str] = None,
        subtask_title: str = "",
        outcome: str = "failed",
        max_lessons: int = 10,
    ) -> ReflectionLesson:
        """Records a structured reflection lesson and updates `Goal.reflection` summary."""
        lesson = ReflectionLesson(
            strategy_used=strategy_used,
            failure_reason=failure_reason,
            root_cause=root_cause,
            recommended_alternative=recommended_alternative,
            category=category or self.category,
            subtask_title=subtask_title,
            goal_title=self.title,
            outcome=outcome,
        )
        self.reflection_lessons.append(lesson)
        if len(self.reflection_lessons) > max(1, max_lessons):
            self.reflection_lessons = self.reflection_lessons[-max(1, max_lessons):]
        self.reflection = (
            f"[{root_cause}] Subtask '{subtask_title or self.title}' gagal: {failure_reason}. "
            f"Strategi: '{strategy_used}' -> Alternatif: '{recommended_alternative}'."
        )
        return lesson

    def get_recent_lessons(self, limit: int = 5) -> List[ReflectionLesson]:
        """Returns up to `limit` most recent structured reflection lessons for this goal."""
        cap = max(1, int(limit))
        if self.reflection_lessons:
            return list(self.reflection_lessons[-cap:])
        if self.reflection and self.reflection.strip():
            return [
                ReflectionLesson(
                    strategy_used="",
                    failure_reason=self.reflection.strip(),
                    root_cause="historical_reflection",
                    recommended_alternative=self.reflection.strip(),
                    category=self.category,
                    goal_title=self.title,
                )
            ]
        return []

    def recalculate_progress(self) -> float:
        """Recalculates overall goal progress based on active (non-replanned) subtasks."""
        active_subtasks = [
            s for s in self.subtasks
            if s.status != GoalStatus.REPLANNED.value
        ]
        if not active_subtasks:
            self.progress = 1.0 if self.status == GoalStatus.COMPLETED.value else 0.0
            return self.progress

        total_prog = sum(s.progress for s in active_subtasks)
        self.progress = round(total_prog / len(active_subtasks), 2)
        if all(s.status == GoalStatus.COMPLETED.value for s in active_subtasks):
            self.status = GoalStatus.COMPLETED.value
            if not self.completed_at:
                self.completed_at = time.time()
        elif any(s.status == GoalStatus.IN_PROGRESS.value for s in active_subtasks):
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
        d["reflection_lessons"] = [
            l.to_dict() if isinstance(l, ReflectionLesson) else l for l in self.reflection_lessons
        ]
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

        raw_lessons = d.get("reflection_lessons", [])
        lessons = []
        for l in raw_lessons:
            if isinstance(l, dict):
                lessons.append(ReflectionLesson.from_dict(l))
            elif isinstance(l, ReflectionLesson):
                lessons.append(l)
        d["reflection_lessons"] = lessons
        return cls(**d)
