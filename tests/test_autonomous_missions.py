import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

try:
    import tests  # noqa: F401
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

import run
from core.event_bus import EventBus
from core.planning.engine import GoalEngine
from core.planning.executor import AutonomousMissionExecutor
from core.planning.models import GoalCategory, GoalStatus, GoalTier


class TestAutonomousMissionExecutor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.storage_dir = self._tmp.name
        self.goal_engine = GoalEngine(storage_dir=self.storage_dir)
        self.event_bus = EventBus()

    def tearDown(self):
        self._tmp.cleanup()

    async def test_minecraft_goal_closed_loop_and_agenda_update(self):
        mc_mock = MagicMock()
        mc_mock.connection_status = "connected"
        mc_mock.current_mode = "kompe"
        mc_mock.set_mode = AsyncMock()
        mc_mock.toggle_wander = AsyncMock()

        # Default active goal is Minecraft ("Membangun rumah di Minecraft")
        executor = AutonomousMissionExecutor(
            goal_engine=self.goal_engine,
            minecraft=mc_mock,
            event_bus=self.event_bus,
            human_approval_required=False,
        )

        res = await executor.step_once()
        self.assertTrue(res["executed"])
        self.assertEqual(res["domain"], "minecraft")
        mc_mock.set_mode.assert_awaited_once_with("santai")
        mc_mock.toggle_wander.assert_awaited_once()

        agenda_path = Path(self.storage_dir) / "agenda.md"
        self.assertTrue(agenda_path.exists())
        agenda_text = agenda_path.read_text(encoding="utf-8")
        self.assertIn("Autonomous Goal & Planning Agenda", agenda_text)
        self.assertGreater(res["goal_progress"], 0.0)

    async def test_chess_goal_start_and_move(self):
        chess_mock = MagicMock()
        chess_mock.is_active = False
        chess_mock.start_game = MagicMock()
        chess_mock.make_bot_move = MagicMock(return_value="e4")

        chess_goal = self.goal_engine.create_goal(
            title="Capai ELO 1500 di Catur",
            description="Menang duel catur di stream",
            tier=GoalTier.SHORT_TERM.value,
            category=GoalCategory.CHESS.value,
            priority=9,
        )
        self.goal_engine.set_active_goal(chess_goal.id)

        executor = AutonomousMissionExecutor(
            goal_engine=self.goal_engine,
            chess=chess_mock,
            event_bus=self.event_bus,
        )

        # Step 1 starts the chess game
        res1 = await executor.step_once()
        self.assertTrue(res1["executed"])
        self.assertEqual(res1["domain"], "chess")
        self.assertEqual(res1["action_name"], "chess_start_game")
        chess_mock.start_game.assert_called_once()

        # Step 2 plays a move when game is active
        chess_mock.is_active = True
        res2 = await executor.step_once()
        self.assertTrue(res2["executed"])
        self.assertEqual(res2["action_name"], "chess_play_move")
        chess_mock.make_bot_move.assert_called_once()

    async def test_performance_director_goal_closed_loop(self):
        perf_runner = AsyncMock(return_value={"success": True, "song_id": "digital_world"})
        perf_goal = self.goal_engine.create_goal(
            title="Konser Karaoke digital_world untuk Fans",
            description="Tampil menyanyi lagu idol",
            tier=GoalTier.DAILY.value,
            category=GoalCategory.PERFORMANCE.value,
            priority=9,
        )
        self.goal_engine.set_active_goal(perf_goal.id)

        executor = AutonomousMissionExecutor(
            goal_engine=self.goal_engine,
            performance_runner=perf_runner,
            event_bus=self.event_bus,
        )
        res = await executor.step_once()
        self.assertTrue(res["executed"])
        self.assertEqual(res["domain"], "performance")
        perf_runner.assert_awaited_once_with("digital_world")

    async def test_social_goal_outreach(self):
        spoken = []

        async def fake_speak(text):
            spoken.append(text)

        social_goals = [g for g in self.goal_engine.get_all_goals() if g.tier == GoalTier.SOCIAL.value]
        self.assertGreater(len(social_goals), 0)
        self.goal_engine.set_active_goal(social_goals[0].id)

        executor = AutonomousMissionExecutor(
            goal_engine=self.goal_engine,
            speak_fn=fake_speak,
            event_bus=self.event_bus,
        )
        res = await executor.step_once()
        self.assertTrue(res["executed"])
        self.assertEqual(res["domain"], "social")
        self.assertEqual(len(spoken), 1)

    async def test_failure_triggers_strategy_replanner_and_updates_agenda(self):
        spoken = []

        async def fake_speak(text):
            spoken.append(text)

        async def failing_perf(song_id=None):
            raise RuntimeError("Audio mixer crashed during setlist")

        perf_goal = self.goal_engine.create_goal(
            title="Konser Karaoke Gagal Test",
            description="Tes replanning",
            tier=GoalTier.DAILY.value,
            category=GoalCategory.PERFORMANCE.value,
            priority=10,
        )
        self.goal_engine.set_active_goal(perf_goal.id)

        executor = AutonomousMissionExecutor(
            goal_engine=self.goal_engine,
            performance_runner=failing_perf,
            speak_fn=fake_speak,
            event_bus=self.event_bus,
        )
        res = await executor.step_once()
        self.assertFalse(res["executed"])
        self.assertTrue(res["replanned"])
        self.assertEqual(res["status"], "replanned")
        self.assertIsNotNone(res["new_subtask"])
        self.assertIn("Plan B", res["new_subtask"]["title"])
        self.assertTrue(any("Plan B" in s for s in spoken))

        agenda_text = (Path(self.storage_dir) / "agenda.md").read_text(encoding="utf-8")
        self.assertIn("Plan B", agenda_text)

    async def test_human_approval_gate_approve_and_reject(self):
        mc_mock = MagicMock()
        mc_mock.connection_status = "connected"
        mc_mock.current_mode = "kompe"
        mc_mock.set_mode = AsyncMock()
        mc_mock.toggle_wander = AsyncMock()

        executor = AutonomousMissionExecutor(
            goal_engine=self.goal_engine,
            minecraft=mc_mock,
            human_approval_required=True,
            event_bus=self.event_bus,
        )

        # First step blocks for approval
        res_wait = await executor.step_once()
        self.assertFalse(res_wait["executed"])
        self.assertEqual(res_wait["status"], "awaiting_approval")
        self.assertIsNotNone(executor.pending_approval)

        # Reject clears pending_approval without advancing goal
        res_reject = await executor.reject_pending("Wait until after chat Q&A")
        self.assertEqual(res_reject["status"], "rejected")
        self.assertFalse(res_reject["executed"])
        self.assertIsNone(executor.pending_approval)

        # Re-queue and approve executes closed loop
        res_wait2 = await executor.step_once()
        self.assertEqual(res_wait2["status"], "awaiting_approval")
        res_approve = await executor.approve_pending()
        self.assertTrue(res_approve["executed"])
        self.assertEqual(res_approve["status"], "executed")
        self.assertIsNone(executor.pending_approval)

    async def test_pause_resume_and_loop_lifecycle(self):
        executor = AutonomousMissionExecutor(
            goal_engine=self.goal_engine,
            tick_interval_sec=0.05,
            event_bus=self.event_bus,
        )
        executor.pause()
        paused_res = await executor.step_once()
        self.assertEqual(paused_res["status"], "paused")
        self.assertFalse(paused_res["executed"])

        executor.resume()
        await executor.start_loop()
        self.assertTrue(executor.is_running)
        await executor.stop_loop()
        self.assertFalse(executor.is_running)


async def _run_http_request(method: str, path: str, payload=None):
    body_bytes = json.dumps(payload).encode("utf-8") if payload is not None else b""
    headers = [(b"content-type", b"application/json")] if payload is not None else []
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 50300),
        "server": ("127.0.0.1", 7860),
    }
    sent = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await run.app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    resp_body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], json.loads(resp_body.decode("utf-8"))


class TestMissionsASGIEndpoints(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._orig_missions = run.orchestrator.missions
        iso_goals = GoalEngine(storage_dir=self._tmp.name)
        mc_mock = MagicMock()
        mc_mock.connection_status = "connected"
        mc_mock.current_mode = "kompe"
        mc_mock.set_mode = AsyncMock()
        mc_mock.toggle_wander = AsyncMock()
        run.orchestrator.missions = AutonomousMissionExecutor(
            goal_engine=iso_goals,
            minecraft=mc_mock,
            event_bus=run.orchestrator.event_bus,
            human_approval_required=False,
            tick_interval_sec=30.0,
        )

    async def asyncTearDown(self):
        await run.orchestrator.missions.stop_loop()
        run.orchestrator.missions = self._orig_missions
        self._tmp.cleanup()

    async def test_missions_status_step_and_toggle_endpoints(self):
        st_code, st_data = await _run_http_request("GET", "/api/missions/status")
        self.assertEqual(st_code, 200)
        self.assertIn("active_goal_title", st_data)
        self.assertIn("running", st_data)

        step_code, step_data = await _run_http_request("POST", "/api/missions/step", {"action": "step"})
        self.assertEqual(step_code, 200)
        self.assertTrue(step_data["executed"])
        self.assertGreaterEqual(step_data["status"]["step_count"], 1)

        # Approval gate via POST /api/missions/step
        run.orchestrator.missions.update_config(human_approval_required=True)
        wait_code, wait_data = await _run_http_request("POST", "/api/missions/step", {"action": "step"})
        self.assertEqual(wait_code, 200)
        self.assertEqual(wait_data["status"] if isinstance(wait_data["status"], str) else wait_data.get("executed"), False)
        self.assertIsNotNone(run.orchestrator.missions.pending_approval)

        app_code, app_data = await _run_http_request("POST", "/api/missions/step", {"action": "approve"})
        self.assertEqual(app_code, 200)
        self.assertTrue(app_data["executed"])

        # Toggle running/paused via POST /api/missions/toggle
        tog_on_code, tog_on = await _run_http_request("POST", "/api/missions/toggle", {"enabled": True})
        self.assertEqual(tog_on_code, 200)
        self.assertTrue(tog_on["success"])
        self.assertTrue(tog_on["is_running"])
        self.assertFalse(tog_on["is_paused"])

        tog_off_code, tog_off = await _run_http_request("POST", "/api/missions/toggle", {"paused": True})
        self.assertEqual(tog_off_code, 200)
        self.assertTrue(tog_off["success"])
        self.assertTrue(tog_off["is_paused"])


if __name__ == "__main__":
    unittest.main()
