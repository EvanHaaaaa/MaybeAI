"""
Conversation Engine Package for MaybeAI (Eve Maybe).
Provides advanced multi-user context memory, Neuro-sama style humor,
spontaneous storytelling, opinion generation, roleplay, improvisation,
and intelligent real-time chat curation with donation handling.
"""
from core.conversation.memory import UserMemory, ContextMemory, TopicTracker
from core.conversation.prompts import MasterPromptBuilder
from core.conversation.chat_curator import ChatCurator, LiveChatMessage, ChatInteraction
from core.conversation.engine import ConversationEngine

__all__ = [
    "UserMemory",
    "ContextMemory",
    "TopicTracker",
    "MasterPromptBuilder",
    "ChatCurator",
    "LiveChatMessage",
    "ChatInteraction",
    "ConversationEngine"
]
