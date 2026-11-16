import time
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

@dataclass
class LiveChatMessage:
    user: str
    text: str
    source: str = "web"
    is_donation: bool = False
    donation_amount: str = ""
    donation_currency: str = ""
    timestamp: float = field(default_factory=time.time)
    msg_type: str = "general"  # donation, joke, question, mention, debate, reaction, general
    priority_score: float = 0.0
    was_responded: bool = False

@dataclass
class ChatInteraction:
    interaction_type: str  # "donation", "single_message", "group_debate", "chat_reaction"
    primary_message: LiveChatMessage
    related_messages: List[LiveChatMessage] = field(default_factory=list)
    topic_summary: str = ""


class ChatCurator:
    """
    Intelligent live chat curator for Eve Maybe.
    1. Collects live chat from multiple streams (Twitch, Web, In-game, YouTube).
    2. Identifies message context: jokes, debates, questions, spam, donations.
    3. Scores and prioritizes messages so Eve responds to the most engaging content.
    4. Bundles multi-user discussions and chat room consensus.
    """

    JOKE_MARKERS = [
        "joke", "tebak-tebakan", "pun", "lelucon", "lawak", "wkwk", "haha", "lmao", "lol",
        "tahu gak", "tau gak", "kenapa ayam", "apa bedanya", "knock knock"
    ]

    QUESTION_MARKERS = [
        "?", "kenapa", "mengapa", "gimana", "bagaimana", "siapa", "kapan", "dimana",
        "why", "how", "what", "who", "when", "where", "apakah", "bisa gak", "menurutmu"
    ]

    REACTION_MARKERS = [
        "wkwkwk", "hahaha", "xixixi", "lol", "lmao", "kekw", "lul", "omg", "nooo", "rip",
        "gg", "clutch", "f in the chat", "f", "waduh", "anjir", "goks", "keren"
    ]

    def __init__(self, max_buffer_size: int = 50):
        self.max_buffer_size = max_buffer_size
        self.message_buffer: List[LiveChatMessage] = []
        self.recent_topics: List[str] = []
        self.last_responded_users: List[str] = []

    def add_message(
        self,
        user: str,
        text: str,
        source: str = "web",
        is_donation: bool = False,
        donation_amount: str = "",
        donation_currency: str = ""
    ) -> LiveChatMessage:
        clean_text = text.strip()
        msg_type = self._classify_message(clean_text, is_donation)
        
        msg = LiveChatMessage(
            user=user.strip() or "Chatter",
            text=clean_text,
            source=source,
            is_donation=is_donation,
            donation_amount=donation_amount,
            donation_currency=donation_currency,
            msg_type=msg_type,
            timestamp=time.time()
        )
        msg.priority_score = self._compute_priority(msg)

        self.message_buffer.append(msg)
        if len(self.message_buffer) > self.max_buffer_size:
            # Drop oldest unresponded non-donation messages first
            for i, old_msg in enumerate(self.message_buffer):
                if not old_msg.is_donation or old_msg.was_responded:
                    self.message_buffer.pop(i)
                    break

        return msg

    def _classify_message(self, text: str, is_donation: bool) -> str:
        if is_donation:
            return "donation"

        lower = text.lower()

        # Check for mention of Eve
        if "eve" in lower or "@eve" in lower or "maybe" in lower:
            if any(lower.startswith(q) for q in self.QUESTION_MARKERS) or lower.endswith("?"):
                return "mention_question"
            return "mention"

        # Check for joke / teasing
        if any(j in lower for j in self.JOKE_MARKERS):
            return "joke"

        # Check for reaction
        words = lower.split()
        if len(words) <= 3 and any(r in lower for r in self.REACTION_MARKERS):
            return "reaction"

        # Check for question
        if any(lower.startswith(q) for q in self.QUESTION_MARKERS) or lower.endswith("?"):
            return "question"

        return "general"

    def _compute_priority(self, msg: LiveChatMessage) -> float:
        score = 10.0

        # Donations always have top priority
        if msg.is_donation:
            return 200.0

        # Direct mentions of Eve
        if "mention" in msg.msg_type:
            score += 45.0

        # Viewer jokes & banter
        if msg.msg_type == "joke":
            score += 35.0

        # Direct questions
        if msg.msg_type == "question":
            score += 30.0

        # Penalize repetitive spam or super short emojis
        if len(msg.text) < 4:
            score -= 10.0
        elif len(set(msg.text.split())) <= 1 and len(msg.text.split()) > 3:
            score -= 25.0  # repetitive spam like "LUL LUL LUL LUL"

        # Give slight boost to users not recently responded to (fairness)
        if msg.user in self.last_responded_users[-3:]:
            score -= 15.0

        return score

    def select_next_interaction(self) -> Optional[ChatInteraction]:
        """
        Selects the best message or group of messages to respond to.
        Prioritizes:
        1. Pending Donations (NEVER dropped)
        2. Group Debates (if multiple chatters talk about contrasting things)
        3. Highest priority unresponded chat message
        """
        unresponded = [m for m in self.message_buffer if not m.was_responded]
        if not unresponded:
            return None

        # 1. Check for pending donations first!
        donations = [m for m in unresponded if m.is_donation]
        if donations:
            don = donations[0]
            don.was_responded = True
            self._record_responded_user(don.user)
            return ChatInteraction(
                interaction_type="donation",
                primary_message=don,
                topic_summary=f"Special Donation from {don.user} ({don.donation_amount})"
            )

        # 2. Check for Multi-User debate cluster (2+ users recently chatting about a topic)
        now = time.time()
        recent_pool = [m for m in unresponded if (now - m.timestamp) <= 30.0]
        if len(recent_pool) >= 2:
            # Check if different users are talking
            users = list({m.user for m in recent_pool})
            if len(users) >= 2:
                # Group debate detection
                top_msgs = sorted(recent_pool, key=lambda m: m.priority_score, reverse=True)[:2]
                for m in top_msgs:
                    m.was_responded = True
                    self._record_responded_user(m.user)
                return ChatInteraction(
                    interaction_type="group_debate",
                    primary_message=top_msgs[0],
                    related_messages=top_msgs[1:],
                    topic_summary=f"Debate between {top_msgs[0].user} and {top_msgs[1].user}"
                )

        # 3. Select single best message based on priority score
        best_msg = max(unresponded, key=lambda m: m.priority_score)
        best_msg.was_responded = True
        self._record_responded_user(best_msg.user)

        interaction_type = "single_message"
        if best_msg.msg_type == "joke":
            interaction_type = "joke_reaction"
        elif best_msg.msg_type == "reaction":
            interaction_type = "chat_reaction"

        return ChatInteraction(
            interaction_type=interaction_type,
            primary_message=best_msg,
            topic_summary=f"Responding to {best_msg.user} ({best_msg.msg_type})"
        )

    def _record_responded_user(self, user: str):
        self.last_responded_users.append(user)
        if len(self.last_responded_users) > 10:
            self.last_responded_users.pop(0)

    def get_chat_digest(self) -> str:
        """Returns a high-level summary of the chat room's current mood and topics."""
        if not self.message_buffer:
            return "Chat room is quiet."
        
        recent = self.message_buffer[-10:]
        users = list({m.user for m in recent})
        types = [m.msg_type for m in recent]
        
        jokes_count = types.count("joke")
        q_count = types.count("question") + types.count("mention_question")

        mood = "lively" if len(recent) >= 5 else "casual"
        notes = [f"Active participants: {', '.join(users[-4:])}", f"Room vibe: {mood}"]
        if jokes_count > 0:
            notes.append("Viewers are cracking jokes")
        if q_count > 0:
            notes.append("Viewers are asking questions")

        return " | ".join(notes)
