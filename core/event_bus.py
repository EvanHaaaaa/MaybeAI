import asyncio
import inspect
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Union

# Canonical EventBus event name constants
CHAT_RECEIVED = "chat.received"
INTERACTION_STARTED = "interaction.started"
AI_RESPONSE_CHUNK = "ai.chunk"
AI_RESPONSE = "ai.response"
AVATAR_STATE = "avatar.state"
MOOD_UPDATED = "mood.updated"
GOAL_UPDATED = "goal.updated"
DONATION_RECEIVED = "donation.received"
SONG_STARTED = "song.started"
SONG_ENDED = "song.ended"
LYRIC_LINE = "lyric.line"
PLATFORM_STATUS = "platform.status"
CONVERSATION_STATE = "conversation.state"
RELATIONSHIP_UPDATED = "relationship.updated"
CONFIGURATION_UPDATED = "configuration.updated"
VISION_UPDATED = "vision.updated"
VOICE_BARGE_IN = "voice.barge_in"
VOICE_VAD_STATE = "voice.vad_state"
STT_PARTIAL = "stt.partial"
STT_FINAL = "stt.final"
MISSION_STEP = "mission.step"
MISSION_STATUS = "mission.status"
COLLAB_MESSAGE = "collab.message"
COLLAB_STATE = "collab.state"
PLUGIN_EVENT = "plugin.event"


class Events:
    """Namespace of standard EventBus event name constants."""

    CHAT_RECEIVED = CHAT_RECEIVED
    INTERACTION_STARTED = INTERACTION_STARTED
    AI_RESPONSE_CHUNK = AI_RESPONSE_CHUNK
    AI_RESPONSE = AI_RESPONSE
    AVATAR_STATE = AVATAR_STATE
    MOOD_UPDATED = MOOD_UPDATED
    GOAL_UPDATED = GOAL_UPDATED
    DONATION_RECEIVED = DONATION_RECEIVED
    SONG_STARTED = SONG_STARTED
    SONG_ENDED = SONG_ENDED
    LYRIC_LINE = LYRIC_LINE
    PLATFORM_STATUS = PLATFORM_STATUS
    CONVERSATION_STATE = CONVERSATION_STATE
    RELATIONSHIP_UPDATED = RELATIONSHIP_UPDATED
    CONFIGURATION_UPDATED = CONFIGURATION_UPDATED
    VISION_UPDATED = VISION_UPDATED
    VOICE_BARGE_IN = VOICE_BARGE_IN
    VOICE_VAD_STATE = VOICE_VAD_STATE
    STT_PARTIAL = STT_PARTIAL
    STT_FINAL = STT_FINAL
    MISSION_STEP = MISSION_STEP
    MISSION_STATUS = MISSION_STATUS
    COLLAB_MESSAGE = COLLAB_MESSAGE
    COLLAB_STATE = COLLAB_STATE
    PLUGIN_EVENT = PLUGIN_EVENT


# Bidirectional mapping between legacy WebSocket event types and canonical EventBus names
WS_TO_BUS_EVENT: Dict[str, str] = {
    "chat_received": CHAT_RECEIVED,
    "interaction_started": INTERACTION_STARTED,
    "ai_chunk": AI_RESPONSE_CHUNK,
    "ai_response": AI_RESPONSE,
    "avatar_state": AVATAR_STATE,
    "mood_updated": MOOD_UPDATED,
    "goal_updated": GOAL_UPDATED,
    "donation_received": DONATION_RECEIVED,
    "song_started": SONG_STARTED,
    "song_ended": SONG_ENDED,
    "lyric_line": LYRIC_LINE,
    "platform_status": PLATFORM_STATUS,
    "conversation_state": CONVERSATION_STATE,
    "relationship_updated": RELATIONSHIP_UPDATED,
    "configuration_updated": CONFIGURATION_UPDATED,
    "vision_updated": VISION_UPDATED,
    "voice_barge_in": VOICE_BARGE_IN,
    "voice_vad_state": VOICE_VAD_STATE,
    "stt_partial": STT_PARTIAL,
    "stt_final": STT_FINAL,
    "mission_step": MISSION_STEP,
    "mission_status": MISSION_STATUS,
    "collab_message": COLLAB_MESSAGE,
    "collab_state": COLLAB_STATE,
    "plugin_event": PLUGIN_EVENT,
}
BUS_TO_WS_EVENT: Dict[str, str] = {v: k for k, v in WS_TO_BUS_EVENT.items()}

EventHandler = Callable[[str, Dict[str, Any]], Union[Awaitable[Any], Any]]


@dataclass(frozen=True)
class EventRecord:
    """Immutable record of an event published on the EventBus."""

    name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "payload": dict(self.payload),
            "timestamp": self.timestamp,
        }


class EventBus:
    """
    Lightweight, typed async pub/sub EventBus with:
    - Exact event subscriptions and wildcard "*" subscriptions
    - Per-handler exception isolation so one failing subscriber never crashes the bus
    - Bounded event history ring buffer for debugging and inspection
    - Synchronous-safe `publish_nowait` helper for non-async callers
    """

    WILDCARD = "*"

    def __init__(self, max_history: int = 200):
        self.max_history = max(1, int(max_history))
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._history: Deque[EventRecord] = deque(maxlen=self.max_history)
        self._total_published: int = 0
        self._handler_errors: int = 0

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """Registers an async or sync handler for `event_name` (or '*' for all events)."""
        handlers = self._subscribers.setdefault(event_name, [])
        if handler not in handlers:
            handlers.append(handler)

    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        """Unregisters `handler` from `event_name`. Safe to call if not subscribed."""
        handlers = self._subscribers.get(event_name)
        if not handlers:
            return
        try:
            handlers.remove(handler)
        except ValueError:
            return
        if not handlers:
            self._subscribers.pop(event_name, None)

    def _collect_handlers(self, event_name: str) -> List[EventHandler]:
        """Returns matching exact and wildcard handlers in registration order without duplicates."""
        exact = list(self._subscribers.get(event_name, ()))
        if event_name == self.WILDCARD:
            return exact
        wildcard = list(self._subscribers.get(self.WILDCARD, ()))
        if not wildcard:
            return exact
        seen = {id(h) for h in exact}
        combined = list(exact)
        for h in wildcard:
            if id(h) not in seen:
                seen.add(id(h))
                combined.append(h)
        return combined

    def _record_event(self, event_name: str, payload: Dict[str, Any]) -> EventRecord:
        record = EventRecord(name=event_name, payload=dict(payload), timestamp=time.time())
        self._history.append(record)
        self._total_published += 1
        return record

    async def publish(self, event_name: str, payload: Optional[Dict[str, Any]] = None) -> int:
        """
        Publishes `event_name` with `payload` to all matching subscribers (exact + '*').
        Awaits each handler with per-handler exception isolation.
        Returns the number of handlers that completed without raising.
        """
        data: Dict[str, Any] = dict(payload) if payload is not None else {}
        self._record_event(event_name, data)

        handlers = self._collect_handlers(event_name)
        delivered = 0
        for handler in handlers:
            try:
                res = handler(event_name, data)
                if inspect.isawaitable(res):
                    await res
                delivered += 1
            except Exception as exc:
                self._handler_errors += 1
                print(f"[EventBus] Handler error for '{event_name}': {exc}")
        return delivered

    def publish_nowait(self, event_name: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """
        Fire-and-forget publish usable from synchronous code.
        Schedules `publish()` on the running event loop if one is active;
        otherwise records history and invokes any synchronous subscribers directly.
        """
        data: Dict[str, Any] = dict(payload) if payload is not None else {}
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event_name, data))
            return
        except RuntimeError:
            pass

        # No running event loop (e.g. synchronous test or init path)
        self._record_event(event_name, data)
        for handler in self._collect_handlers(event_name):
            if inspect.iscoroutinefunction(handler):
                continue
            try:
                res = handler(event_name, data)
                if inspect.isawaitable(res) and hasattr(res, "close"):
                    res.close()
            except Exception as exc:
                self._handler_errors += 1
                print(f"[EventBus] Sync handler error for '{event_name}': {exc}")

    def get_history(self, limit: int = 50, event_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns up to `limit` most recent event records (oldest-to-newest within the slice)."""
        records = list(self._history)
        if event_name is not None:
            records = [r for r in records if r.name == event_name]
        if limit > 0:
            records = records[-limit:]
        return [r.to_dict() for r in records]

    def get_stats(self) -> Dict[str, Any]:
        """Returns read-only statistics about subscribers and recent events."""
        subscriber_counts = {name: len(handlers) for name, handlers in self._subscribers.items()}
        recent_records = list(self._history)[-20:]
        recent_event_types: List[str] = []
        for rec in reversed(recent_records):
            if rec.name not in recent_event_types:
                recent_event_types.append(rec.name)
        return {
            "subscriber_counts": subscriber_counts,
            "total_subscribers": sum(subscriber_counts.values()),
            "total_published": self._total_published,
            "handler_errors": self._handler_errors,
            "history_size": len(self._history),
            "max_history": self.max_history,
            "recent_event_types": recent_event_types,
        }

    def clear(self, include_history: bool = True) -> None:
        """Removes all subscribers and optionally clears the event history ring buffer."""
        self._subscribers.clear()
        if include_history:
            self._history.clear()
            self._total_published = 0
            self._handler_errors = 0
