import time
import uuid
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional


class MiniGameType(str, Enum):
    TRIVIA = "trivia"                        # Trivia Quiz interaktif
    GUESS_NUMBER = "guess_number"            # Tebak Angka Rahasia (1-100)
    WORD_ASSOCIATION = "word_association"    # Asosiasi Kata / Sambung Kata bertema
    RIDDLE = "riddle"                        # Teka-Teki Asah Otak
    WOULD_YOU_RATHER = "would_you_rather"    # Polling Pilihan Dilematis & Hot Take
    GUESS_SONG = "guess_song"                # Tebak Judul Lagu dari Lirik / Clue


class GameStatus(str, Enum):
    IDLE = "idle"                            # Menunggu permainan dimulai
    ACTIVE = "active"                        # Ronde permainan sedang berjalan
    ROUND_END = "round_end"                  # Ronde selesai, menampilkan skor & pemenang
    GAME_OVER = "game_over"                  # Seluruh ronde selesai, juara diumumkan


@dataclass
class PlayerScore:
    username: str
    score: int = 0
    correct_answers: int = 0
    games_won: int = 0
    streak: int = 0
    last_active: float = field(default_factory=time.time)

    def add_points(self, points: int):
        self.score += points
        self.correct_answers += 1
        self.streak += 1
        self.last_active = time.time()

    def reset_streak(self):
        self.streak = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "username": self.username,
            "score": self.score,
            "correct_answers": self.correct_answers,
            "games_won": self.games_won,
            "streak": self.streak,
            "last_active_str": time.strftime("%H:%M:%S", time.localtime(self.last_active))
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlayerScore":
        clean = {k: v for k, v in data.items() if k != "last_active_str"}
        return cls(**clean)


@dataclass
class TriviaQuestion:
    id: str
    category: str
    question: str
    options: List[str]               # e.g. ["A) Python", "B) Java", "C) Rust", "D) C++"]
    correct_index: int               # 0, 1, 2, or 3
    correct_answer_text: str
    explanation: str
    points: int = 10

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiddleItem:
    id: str
    riddle: str
    answer: str
    accepted_keywords: List[str]
    hints: List[str]
    explanation: str
    points: int = 15

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WouldYouRatherItem:
    id: str
    topic: str
    option_a: str
    option_b: str
    eve_choice: str                  # "A" or "B"
    eve_hot_take: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SongQuizItem:
    id: str
    title: str
    artist: str
    clue_lyrics: str
    genre: str
    accepted_titles: List[str]
    points: int = 10

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MiniGameSession:
    id: str = field(default_factory=lambda: f"game_{uuid.uuid4().hex[:6]}")
    game_type: str = MiniGameType.TRIVIA.value
    status: str = GameStatus.IDLE.value
    round_number: int = 1
    total_rounds: int = 3
    started_at: float = field(default_factory=time.time)
    time_limit_sec: int = 35
    expires_at: float = 0.0

    current_challenge: Dict[str, Any] = field(default_factory=dict)
    revealed_hints: List[str] = field(default_factory=list)

    # Round state
    round_attempts: List[Dict[str, Any]] = field(default_factory=list)
    round_winner: Optional[str] = None
    round_correct_answer: Optional[str] = None

    # Would You Rather poll state
    poll_votes: Dict[str, int] = field(default_factory=lambda: {"A": 0, "B": 0})
    voters: Dict[str, str] = field(default_factory=dict)  # username -> option ("A" or "B")

    # Word Association chain state
    word_chain: List[str] = field(default_factory=list)
    active_theme: str = "Umum"

    # Guess Number state
    min_number: int = 1
    max_number: int = 100
    target_number: int = 42
    last_guess_feedback: str = ""
    last_guess_val: Optional[int] = None

    # Host & AI vs Chat scoring
    host_speech: str = ""
    ai_score: int = 0
    chat_score: int = 0

    def is_expired(self) -> bool:
        return time.time() > self.expires_at if self.expires_at > 0 else False

    def get_remaining_seconds(self) -> int:
        if self.status != GameStatus.ACTIVE.value or self.expires_at <= 0:
            return 0
        return max(0, int(self.expires_at - time.time()))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["remaining_seconds"] = self.get_remaining_seconds()
        d["poll_percentages"] = self._calculate_poll_percentages()
        return d

    def _calculate_poll_percentages(self) -> Dict[str, int]:
        total = self.poll_votes.get("A", 0) + self.poll_votes.get("B", 0)
        if total == 0:
            return {"A": 50, "B": 50, "total": 0}
        pct_a = round((self.poll_votes.get("A", 0) / total) * 100)
        return {"A": pct_a, "B": 100 - pct_a, "total": total}
