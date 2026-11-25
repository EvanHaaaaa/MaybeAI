import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

try:
    import tests  # noqa: F401  # Ensure tests/__init__.py sets MAYBEAI_LLM_PROVIDER=mock
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

from core.event_bus import (
    EventBus,
    Events,
    CHAT_RECEIVED,
    DONATION_RECEIVED,
    MOOD_UPDATED,
    AVATAR_STATE,
    AI_RESPONSE,
)
from core.conversation.engine import ConversationEngine
from core.memory import EpisodicMemoryStore
from core.orchestrator import Orchestrator


class TestEventBus(unittest.IsolatedAsyncioTestCase):
    async def test_subscribe_publish_and_unsubscribe(self):
        bus = EventBus(max_history=50)
        received = []

        async def async_handler(name, payload):
            received.append(("async", name, payload))

        def sync_handler(name, payload):
            received.append(("sync", name, payload))

        bus.subscribe(CHAT_RECEIVED, async_handler)
        bus.subscribe(CHAT_RECEIVED, async_handler)  # Duplicate ignored
        bus.subscribe(CHAT_RECEIVED, sync_handler)

        delivered = await bus.publish(CHAT_RECEIVED, {"user": "Alice", "text": "Hi"})
        self.assertEqual(delivered, 2)
        self.assertEqual(len(received), 2)
        self.assertEqual(received[0], ("async", CHAT_RECEIVED, {"user": "Alice", "text": "Hi"}))
        self.assertEqual(received[1], ("sync", CHAT_RECEIVED, {"user": "Alice", "text": "Hi"}))

        bus.unsubscribe(CHAT_RECEIVED, async_handler)
        bus.unsubscribe(CHAT_RECEIVED, async_handler)  # Safe when already removed
        bus.unsubscribe("nonexistent.event", sync_handler)  # Safe when event unknown

        delivered2 = await bus.publish(CHAT_RECEIVED, {"user": "Bob", "text": "Hello"})
        self.assertEqual(delivered2, 1)
        self.assertEqual(len(received), 3)
        self.assertEqual(received[-1][0], "sync")

    async def test_wildcard_subscription_and_deduplication(self):
        bus = EventBus()
        events_seen = []

        async def wildcard_handler(name, payload):
            events_seen.append((name, payload.get("v")))

        bus.subscribe(EventBus.WILDCARD, wildcard_handler)
        # Also subscribe same handler to an exact event: should still fire only once
        bus.subscribe(AVATAR_STATE, wildcard_handler)

        delivered_avatar = await bus.publish(AVATAR_STATE, {"v": 1})
        delivered_mood = await bus.publish(MOOD_UPDATED, {"v": 2})

        self.assertEqual(delivered_avatar, 1)
        self.assertEqual(delivered_mood, 1)
        self.assertEqual(events_seen, [(AVATAR_STATE, 1), (MOOD_UPDATED, 2)])

    async def test_handler_exception_isolation(self):
        bus = EventBus()
        survivor_calls = []

        async def bad_async_handler(name, payload):
            raise RuntimeError("boom async")

        def bad_sync_handler(name, payload):
            raise ValueError("boom sync")

        async def good_handler(name, payload):
            survivor_calls.append((name, payload))

        bus.subscribe(AI_RESPONSE, bad_async_handler)
        bus.subscribe(AI_RESPONSE, bad_sync_handler)
        bus.subscribe(AI_RESPONSE, good_handler)

        delivered = await bus.publish(AI_RESPONSE, {"speech": "still alive"})
        self.assertEqual(delivered, 1)
        self.assertEqual(len(survivor_calls), 1)
        self.assertEqual(survivor_calls[0][1]["speech"], "still alive")
        self.assertEqual(bus.get_stats()["handler_errors"], 2)

    async def test_history_ring_buffer_stats_and_clear(self):
        bus = EventBus(max_history=3)
        bus.subscribe(CHAT_RECEIVED, lambda n, p: None)
        bus.subscribe("*", lambda n, p: None)

        for i in range(5):
            ev = CHAT_RECEIVED if i % 2 == 0 else MOOD_UPDATED
            await bus.publish(ev, {"idx": i})

        history_all = bus.get_history(limit=10)
        self.assertEqual(len(history_all), 3)
        self.assertEqual([h["payload"]["idx"] for h in history_all], [2, 3, 4])

        history_filtered = bus.get_history(limit=10, event_name=CHAT_RECEIVED)
        self.assertEqual([h["payload"]["idx"] for h in history_filtered], [2, 4])

        stats = bus.get_stats()
        self.assertEqual(stats["total_published"], 5)
        self.assertEqual(stats["history_size"], 3)
        self.assertEqual(stats["max_history"], 3)
        self.assertEqual(stats["total_subscribers"], 2)
        self.assertEqual(stats["subscriber_counts"][CHAT_RECEIVED], 1)
        self.assertEqual(stats["subscriber_counts"]["*"], 1)
        self.assertIn(CHAT_RECEIVED, stats["recent_event_types"])
        self.assertIn(MOOD_UPDATED, stats["recent_event_types"])

        bus.clear(include_history=True)
        stats_after = bus.get_stats()
        self.assertEqual(stats_after["total_subscribers"], 0)
        self.assertEqual(stats_after["total_published"], 0)
        self.assertEqual(stats_after["history_size"], 0)

    async def test_publish_nowait_on_running_loop(self):
        bus = EventBus()
        seen = []

        async def handler(name, payload):
            seen.append((name, payload))

        bus.subscribe(Events.GOAL_UPDATED, handler)
        bus.publish_nowait(Events.GOAL_UPDATED, {"goal": "speedrun"})
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0], (Events.GOAL_UPDATED, {"goal": "speedrun"}))


class TestEventBusSyncPublishNowait(unittest.TestCase):
    def test_publish_nowait_without_running_loop_invokes_sync_handlers(self):
        bus = EventBus()
        seen = []

        def sync_handler(name, payload):
            seen.append((name, payload))

        bus.subscribe(CHAT_RECEIVED, sync_handler)
        bus.publish_nowait(CHAT_RECEIVED, {"user": "SyncUser"})

        self.assertEqual(seen, [(CHAT_RECEIVED, {"user": "SyncUser"})])
        self.assertEqual(bus.get_stats()["total_published"], 1)


class TestEventBusIntegration(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_dir = Path(self._temp_dir_obj.name)

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    async def test_conversation_engine_emits_chat_donation_and_mood_events(self):
        bus = EventBus()
        seen_events = []
        bus.subscribe("*", lambda name, payload: seen_events.append((name, payload)))

        character = {"name": "Eve Maybe", "nickname": "Eve", "creator": "Creator", "bio": "AI VTuber"}
        conv = ConversationEngine(character=character, event_bus=bus)
        conv.episodic_memory = EpisodicMemoryStore(
            db_path=str(self.temp_dir / "mem.db"),
            markdown_dir=str(self.temp_dir / "brain"),
        )

        conv.record_incoming_chat(
            user="Donor1",
            text="Semangat streamingnya Eve!",
            source="web",
            is_donation=True,
            donation_amount="$10.00",
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        event_names = [e[0] for e in seen_events]
        self.assertIn(CHAT_RECEIVED, event_names)
        self.assertIn(DONATION_RECEIVED, event_names)
        self.assertIn(MOOD_UPDATED, event_names)

    async def test_orchestrator_shares_event_bus_and_dispatches_listeners_once(self):
        orch = Orchestrator()
        try:
            self.assertIs(orch.event_bus, orch.brain.conversation.event_bus)

            listener = AsyncMock()
            orch.register_listener(listener)

            before_published = orch.event_bus.get_stats()["total_published"]
            await orch.broadcast("avatar_state", {"mouth_open": 0.5, "emotion": "happy"})

            listener.assert_awaited_once_with(
                {"type": "avatar_state", "data": {"mouth_open": 0.5, "emotion": "happy"}}
            )
            after_published = orch.event_bus.get_stats()["total_published"]
            self.assertEqual(after_published, before_published + 1)
        finally:
            await orch.brain.close()


if __name__ == "__main__":
    unittest.main()
