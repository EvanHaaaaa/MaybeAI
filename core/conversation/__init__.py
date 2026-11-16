"""
Conversation Engine Package for MaybeAI (Eve Maybe).
Provides advanced multi-user context memory, Neuro-sama style humor,
spontaneous storytelling, opinion generation, roleplay, and improvisation.
"""
from core.conversation.memory import UserMemory, ContextMemory, TopicTracker
from core.conversation.prompts import MasterPromptBuilder
from core.conversation.engine import ConversationEngine

__all__ = [
    "UserMemory",
    "ContextMemory",
    "TopicTracker",
    "MasterPromptBuilder",
    "ConversationEngine"
]
