import time
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field

@dataclass
class UserProfile:
    username: str
    interaction_count: int = 0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    known_facts: List[str] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)

    def record_interaction(self, message: str):
        self.interaction_count += 1
        self.last_seen = time.time()
        
        # Tagging heuristics
        if self.interaction_count >= 5:
            self.tags.add("regular")
        if self.interaction_count >= 15:
            self.tags.add("superfan")

        # Basic fact discovery
        msg_lower = message.lower()
        if "aku suka " in msg_lower:
            part = msg_lower.split("aku suka ")[1].split(".")[0].split(",")[0].strip()
            if len(part) < 30 and part not in self.known_facts:
                self.known_facts.append(f"likes {part}")
        elif "i love " in msg_lower:
            part = msg_lower.split("i love ")[1].split(".")[0].split(",")[0].strip()
            if len(part) < 30 and part not in self.known_facts:
                self.known_facts.append(f"loves {part}")

    def get_summary(self) -> str:
        tag_str = ", ".join(self.tags) if self.tags else "new chatter"
        facts_str = f" (notes: {', '.join(self.known_facts[-2:])})" if self.known_facts else ""
        return f"{self.username} [{tag_str}, {self.interaction_count} messages]{facts_str}"


class UserMemory:
    """Tracks viewer identities, rapport, and recurring chat participants."""

    def __init__(self):
        self.users: Dict[str, UserProfile] = {}

    def get_or_create(self, username: str) -> UserProfile:
        clean_name = username.strip() or "Chatter"
        if clean_name not in self.users:
            self.users[clean_name] = UserProfile(username=clean_name)
        return self.users[clean_name]

    def record_message(self, username: str, text: str):
        profile = self.get_or_create(username)
        profile.record_interaction(text)

    def get_active_chatters(self, within_seconds: float = 240.0) -> List[str]:
        now = time.time()
        active = [
            u.username for u in self.users.values()
            if (now - u.last_seen) <= within_seconds
        ]
        return active[-5:]  # Top 5 most recently active chatters

    def get_social_context(self, current_user: str) -> str:
        """Generates a brief summary of the social room context for the LLM."""
        active = self.get_active_chatters()
        current_profile = self.get_or_create(current_user)
        
        other_active = [u for u in active if u.lower() != current_user.lower()]
        social_bits = [f"Current speaker: {current_profile.get_summary()}"]
        
        if other_active:
            social_bits.append(f"Other active chatters in the room: {', '.join(other_active)}")
        else:
            social_bits.append("Chat room is listening closely.")
            
        return " | ".join(social_bits)


class ContextMemory:
    """
    Maintains short-term rolling conversation buffer and long-term
    rolling summary to avoid sudden amnesia during long streams.
    """

    def __init__(self, max_buffer_turns: int = 16):
        self.max_buffer_turns = max_buffer_turns
        self.buffer: List[Dict[str, Any]] = []
        self.rolling_summary: str = ""

    def add_turn(self, role: str, user: str, content: str):
        self.buffer.append({
            "role": role,
            "user": user,
            "content": content,
            "timestamp": time.time()
        })
        
        # When buffer exceeds limit, summarize older messages
        if len(self.buffer) > self.max_buffer_turns:
            oldest = self.buffer.pop(0)
            self._update_rolling_summary(oldest)

    def _update_rolling_summary(self, old_turn: Dict[str, Any]):
        u = old_turn.get("user", "User")
        c = old_turn.get("content", "")
        # Keep an ultra-compact 2-line memory digest of earlier events
        short_line = f"{u}: {c[:60]}"
        if not self.rolling_summary:
            self.rolling_summary = f"Earlier in stream: {short_line}"
        else:
            lines = self.rolling_summary.split(" | ")
            lines.append(short_line)
            if len(lines) > 4:
                lines = lines[-4:]
            self.rolling_summary = " | ".join(lines)

    def get_history_for_llm(self) -> List[Dict[str, str]]:
        """Returns standard list of role/content message dicts."""
        history = []
        for turn in self.buffer:
            if turn["role"] == "user":
                history.append({
                    "role": "user",
                    "content": f"{turn['user']}: {turn['content']}"
                })
            else:
                history.append({
                    "role": "assistant",
                    "content": turn["content"]
                })
        return history

    def clear(self):
        self.buffer.clear()
        self.rolling_summary = ""


class TopicTracker:
    """Tracks active themes, story threads, debates, and roleplays."""

    TOPIC_KEYWORDS = {
        "Minecraft & Gaming": ["minecraft", "game", "speedrun", "ender dragon", "creeper", "build", "pvp", "server", "mining", "roblox", "valorant", "genshin"],
        "Food & Drinks": ["makan", "minum", "pizza", "nanas", "kopi", "teh", "mie", "indomie", "bubur", "ayam", "snack", "cookie"],
        "AI & Sci-Fi": ["ai", "robot", "human", "future", "world", "komputer", "skynet", "code", "neural", "vtuber", "digital"],
        "Singing & Music": ["sing", "song", "nyanyi", "lagu", "karaoke", "music", "vocal"],
        "Philosophy & Life": ["hidup", "cinta", "meaning", "life", "filsafat", "teman", "perasaan", "hati"]
    }

    def __init__(self):
        self.current_topic: str = "General Banter"
        self.active_roleplay: Optional[str] = None
        self.active_story: Optional[str] = None

    def update_topic(self, text: str):
        text_lower = text.lower()
        for topic_name, keywords in self.TOPIC_KEYWORDS.items():
            if any(k in text_lower for k in keywords):
                self.current_topic = topic_name
                return
        if self.current_topic == "General Banter":
            self.current_topic = "Casual Chat"

    def set_roleplay(self, role: Optional[str]):
        self.active_roleplay = role.strip() if role else None

    def set_story_mode(self, story_theme: Optional[str]):
        self.active_story = story_theme.strip() if story_theme else None
