import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import run
from core.collab.manager import CollabEnvelope, CollabManager
from core.config_manager import ConfigManager
from core.event_bus import EventBus
from core.highlights.clipper import ClipPipeline
from core.planning.models import Goal, GoalStatus, Subtask
from core.planning.replanner import MAX_REPLAN_ATTEMPTS, StrategyReplanner


class TestHorizon0Hardening(unittest.IsolatedAsyncioTestCase):
    async def test_event_bus_concurrent_publish_does_not_stall_fast_subscriber(self):
        bus = EventBus()
        fast_elapsed = None

        async def slow_subscriber(event_name, payload):
            await asyncio.sleep(0.2)

        async def fast_subscriber(event_name, payload):
            nonlocal fast_elapsed
            fast_elapsed = time.perf_counter() - start

        bus.subscribe("tick", slow_subscriber)
        bus.subscribe("tick", fast_subscriber)

        start = time.perf_counter()
        completed = await bus.publish("tick", {"n": 1})

        self.assertEqual(completed, 2)
        self.assertIsNotNone(fast_elapsed)
        self.assertLess(fast_elapsed, 0.05)

    async def test_collab_replay_rejection_and_skew(self):
        mgr = CollabManager(settings={"enabled": True, "shared_secret": "secret-key"})
        mgr.max_timestamp_skew_sec = 60.0

        env = CollabEnvelope(
            sender_id="peer-1",
            sender_name="Peer",
            event_type="hello",
            timestamp=time.time(),
        )
        env.sign("secret-key")
        raw = env.to_dict()

        first = await mgr.handle_incoming_envelope(raw, is_loopback=False)
        self.assertTrue(first["accepted"])

        replay = await mgr.handle_incoming_envelope(raw, is_loopback=False)
        self.assertFalse(replay["accepted"])
        self.assertEqual(replay.get("reason"), "duplicate_nonce")

        stale = CollabEnvelope(
            sender_id="peer-1",
            sender_name="Peer",
            event_type="hello",
            timestamp=time.time() - 65.0,
        )
        stale.sign("secret-key")
        stale_res = await mgr.handle_incoming_envelope(stale.to_dict(), is_loopback=False)
        self.assertFalse(stale_res["accepted"])
        self.assertEqual(stale_res.get("reason"), "timestamp_skew_exceeded")

    def test_collab_is_loopback_url_rejects_spoofed_hosts(self):
        self.assertTrue(CollabManager._is_loopback_url("ws://127.0.0.1:7860/ws/collab"))
        self.assertTrue(CollabManager._is_loopback_url("ws://localhost:7860/ws/collab"))
        self.assertTrue(CollabManager._is_loopback_url("ws://[::1]:7860/ws/collab"))
        self.assertFalse(CollabManager._is_loopback_url("ws://localhost.evil.com/ws/collab"))
        self.assertFalse(CollabManager._is_loopback_url("ws://127.0.0.1.evil.com/ws/collab"))
        self.assertFalse(CollabManager._is_loopback_url("ws://example.com/ws/collab"))

    def test_collab_refresh_cooldown_recovers_to_idle(self):
        mgr = CollabManager(settings={"enabled": True})
        mgr.floor_state = "cooldown"
        mgr.turn_count = 6
        mgr.cooldown_until = time.monotonic() - 1.0

        mgr._refresh_cooldown()

        self.assertEqual(mgr.turn_count, 0)
        self.assertEqual(mgr.floor_state, "idle")
        self.assertEqual(mgr.cooldown_until, 0.0)

    def test_goal_with_replanned_subtask_completes_and_respects_max_replan_cap(self):
        self.assertEqual(MAX_REPLAN_ATTEMPTS, 3)

        sub1 = Subtask(id="sub_1", title="Mine iron", status=GoalStatus.IN_PROGRESS.value, attempts=1)
        goal = Goal(id="goal_1", title="Get Iron", subtasks=[sub1], status=GoalStatus.IN_PROGRESS.value)

        new_sub, _ = StrategyReplanner.replan_subtask(goal, sub1, "diserang creeper")
        self.assertIsNotNone(new_sub)
        self.assertEqual(sub1.status, GoalStatus.REPLANNED.value)
        goal.subtasks.append(new_sub)
        new_sub.mark_completed()
        goal.recalculate_progress()
        self.assertEqual(goal.status, GoalStatus.COMPLETED.value)
        self.assertEqual(goal.progress, 1.0)

        # Exceeding MAX_REPLAN_ATTEMPTS stops infinite replanning and fails goal
        capped_sub = Subtask(
            id="sub_cap",
            title="Impossible task",
            status=GoalStatus.IN_PROGRESS.value,
            attempts=MAX_REPLAN_ATTEMPTS,
        )
        capped_goal = Goal(
            id="goal_cap",
            title="Capped Goal",
            subtasks=[capped_sub],
            status=GoalStatus.IN_PROGRESS.value,
        )
        next_sub, _ = StrategyReplanner.replan_subtask(capped_goal, capped_sub, "still failing")
        self.assertIsNone(next_sub)
        self.assertEqual(capped_sub.status, GoalStatus.FAILED.value)
        self.assertEqual(capped_goal.status, GoalStatus.FAILED.value)

    async def test_clip_pipeline_rejects_path_traversal_outside_clips_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            clips_dir = Path(tmpdir) / "data" / "clips"
            clips_dir.mkdir(parents=True)
            outside_file = Path(tmpdir) / "secret.mp4"
            outside_file.write_bytes(b"fake")

            pipeline = ClipPipeline(clips_dir=str(clips_dir))
            with self.assertRaises(ValueError):
                pipeline._resolve_confined_path("../secret.mp4")

            res_in = await pipeline.create_vertical_clip(
                input_path="../secret.mp4",
                output_path="out.mp4",
            )
            self.assertFalse(res_in["success"])
            self.assertIn("escapes", res_in["error"])

            res_out = await pipeline.create_vertical_clip(
                input_path="in.mp4",
                output_path="../escaped.mp4",
            )
            self.assertFalse(res_out["success"])
            self.assertIn("escapes", res_out["error"])

    def test_config_manager_masks_llm_api_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_dir = Path(tmpdir) / "config"
            mgr = ConfigManager(config_dir=str(cfg_dir))
            mgr.settings["llm"]["gemini_api_key"] = "AIzaSy-secret-gemini-key"
            mgr.settings["llm"]["openai_api_key"] = "sk-secret-openai-key"
            mgr._atomic_write_json(mgr.settings_file, mgr.settings)

            public_cfg = mgr.get_public_config()
            self.assertEqual(public_cfg["llm"]["gemini_api_key"], "********")
            self.assertTrue(public_cfg["llm"]["gemini_api_key_configured"])
            self.assertEqual(public_cfg["llm"]["openai_api_key"], "********")
            self.assertTrue(public_cfg["llm"]["openai_api_key_configured"])

    async def test_ws_creator_auth_for_non_loopback_and_rejects_unauthenticated_mutations(self):
        fake_ws_valid = SimpleNamespace(
            headers={"x-creator-token": "docker-lan-secret"},
            query_params={},
            client=SimpleNamespace(host="172.17.0.5"),
        )
        fake_ws_invalid = SimpleNamespace(
            headers={},
            query_params={},
            client=SimpleNamespace(host="172.17.0.5"),
        )

        with patch.dict(os.environ, {"MAYBEAI_CREATOR_TOKEN": "docker-lan-secret"}):
            self.assertTrue(run._is_ws_creator_authorized(fake_ws_valid))
            self.assertFalse(run._is_ws_creator_authorized(fake_ws_invalid))

            creator_action = next(iter(run._CREATOR_ONLY_WS_ACTIONS))
            scope = {
                "type": "websocket",
                "asgi": {"version": "3.0"},
                "scheme": "ws",
                "path": "/ws",
                "raw_path": b"/ws",
                "query_string": b"",
                "headers": [(b"origin", b"http://127.0.0.1:7860")],
                "client": ("172.17.0.5", 50201),
                "server": ("127.0.0.1", 7860),
            }
            sent = []
            step = 0

            async def receive():
                nonlocal step
                step += 1
                if step == 1:
                    return {"type": "websocket.connect"}
                if step == 2:
                    return {
                        "type": "websocket.receive",
                        "text": json.dumps({"type": creator_action, "data": {}}),
                    }
                return {"type": "websocket.disconnect", "code": 1000}

            async def send(message):
                sent.append(message)

            await run.app(scope, receive, send)
            json_msgs = [
                json.loads(m["text"])
                for m in sent
                if m.get("type") == "websocket.send" and m.get("text")
            ]
            error_msgs = [m for m in json_msgs if m.get("type") == "error"]
            self.assertTrue(error_msgs, "Expected forbidden error for unauthenticated WS mutation")
            self.assertEqual(error_msgs[0].get("data", {}).get("code"), "forbidden")
