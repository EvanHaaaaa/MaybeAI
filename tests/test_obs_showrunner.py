import asyncio
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

try:
    import tests  # noqa: F401  # Ensure tests/__init__.py sets MAYBEAI_LLM_PROVIDER=mock
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

import run
from core.desktop.controller import DesktopController, DesktopPermissionConfig
from core.desktop.obs_client import DEFAULT_SCENE_MAP, OBSWebSocketClient
from core.performance.director import PerformanceDirector
from core.planning.executor import AutonomousMissionExecutor
from core.planning.models import Goal, GoalCategory, GoalStatus, Subtask


async def _run_asgi_request(
    method: str,
    path: str,
    body: bytes = b"",
    headers=None,
    client=("127.0.0.1", 50200),
):
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": raw_headers,
        "client": client,
        "server": ("127.0.0.1", 7860),
    }
    sent = []
    delivered = False
    done_event = asyncio.Event()

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await done_event.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            done_event.set()

    await run.app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    resp_body = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    resp_headers = {
        k.decode("latin-1").lower(): v.decode("latin-1")
        for k, v in start.get("headers", [])
    }
    return start["status"], resp_headers, resp_body


class TestOBSWebSocketClient(unittest.IsolatedAsyncioTestCase):
    async def test_offline_fallback_when_disabled_or_missing_package(self):
        disabled_client = OBSWebSocketClient(enabled=False)
        self.assertFalse(await disabled_client.connect())
        self.assertFalse(disabled_client.is_connected)

        res = await disabled_client.switch_scene("Minecraft")
        self.assertFalse(res["success"])
        self.assertFalse(res["connected"])

        enabled_client = OBSWebSocketClient(enabled=True)
        with patch("core.desktop.obs_client._import_req_client", return_value=None):
            ok = await enabled_client.connect()
        self.assertFalse(ok)
        self.assertIn("obsws-python", enabled_client.last_error or "")

    async def test_mocked_obsws_python_lifecycle_and_controls(self):
        fake_req = MagicMock()
        fake_req.get_current_program_scene.return_value = SimpleNamespace(
            current_program_scene_name="Just Chatting"
        )
        fake_req.get_scene_list.return_value = SimpleNamespace(
            scenes=[
                {"sceneName": "Just Chatting"},
                {"sceneName": "Minecraft"},
                {"sceneName": "Karaoke Stage"},
            ]
        )
        fake_req.get_stream_status.return_value = SimpleNamespace(output_active=False)
        fake_req.toggle_stream.return_value = SimpleNamespace(output_active=True)
        fake_req.get_scene_item_id.return_value = SimpleNamespace(scene_item_id=42)

        factory = MagicMock(return_value=fake_req)
        obs = OBSWebSocketClient(
            host="127.0.0.1",
            port=4455,
            password="secret",
            enabled=True,
        )

        with patch("core.desktop.obs_client._import_req_client", return_value=factory):
            self.assertTrue(await obs.connect())

        self.assertTrue(obs.is_connected)
        self.assertEqual(obs.current_scene, "Just Chatting")
        self.assertEqual(obs.available_scenes, ["Just Chatting", "Minecraft", "Karaoke Stage"])

        sw = await obs.switch_scene("minecraft", reason="domain:minecraft")
        self.assertTrue(sw["success"])
        self.assertEqual(sw["scene"], "Minecraft")
        fake_req.set_current_program_scene.assert_called_with("Minecraft")

        st = await obs.toggle_streaming(True)
        self.assertTrue(st["success"])
        self.assertTrue(st["is_streaming"])
        fake_req.start_stream.assert_called_once()

        rb_start = await obs.start_replay_buffer()
        self.assertTrue(rb_start["success"])
        self.assertTrue(obs.replay_buffer_active)

        rb_save = await obs.save_replay_buffer()
        self.assertTrue(rb_save["success"])
        fake_req.save_replay_buffer.assert_called_once()

        vis = await obs.set_source_visibility("minecraft", "Webcam", False)
        self.assertTrue(vis["success"])
        fake_req.set_scene_item_enabled.assert_called_with("Minecraft", 42, False)

        status = obs.get_status()
        self.assertEqual(status["current_scene"], "Minecraft")
        self.assertTrue(await obs.disconnect())
        self.assertFalse(obs.is_connected)


class TestDesktopAndAutonomousSceneSwitching(unittest.IsolatedAsyncioTestCase):
    def test_desktop_controller_delegates_to_connected_obs_client(self):
        fake_obs = MagicMock()
        fake_obs.is_connected = True

        async def _fake_switch(scene):
            return {"success": True, "scene": scene}

        async def _fake_toggle(target_state=None):
            return {"success": True, "is_streaming": True}

        fake_obs.switch_scene = _fake_switch
        fake_obs.toggle_streaming = _fake_toggle

        ctrl = DesktopController(config=DesktopPermissionConfig(), obs_client=fake_obs)
        scene, msg = ctrl.switch_streaming_scene("Minecraft")
        self.assertEqual(scene, "Minecraft")
        self.assertIn("OBS", msg)

        ok, stream_msg = ctrl.toggle_streaming()
        self.assertTrue(ok)
        self.assertIn("Live Stream", stream_msg)

    async def test_executor_and_director_trigger_scene_switcher(self):
        switched = []

        async def _scene_switcher(scene_name: str, reason: str):
            switched.append((scene_name, reason))

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
            goal = Goal(
                id="g-mc-1",
                title="Gather wood",
                category=GoalCategory.MINECRAFT,
                status=GoalStatus.IN_PROGRESS,
                subtasks=[Subtask(id="st-1", title="Chop tree", status="pending")],
            )
            goal_engine = MagicMock()
            goal_engine.get_active_goals.return_value = [goal]
            goal_engine.autonomous_select_next_activity.return_value = (goal, "next")

            mc = MagicMock()
            mc.connection_status = "connected"
            mc.current_mode = "santai"
            mc.set_mode = AsyncMock()
            mc.toggle_wander = AsyncMock()

            executor = AutonomousMissionExecutor(
                goal_engine=goal_engine,
                minecraft=mc,
                scene_switcher=_scene_switcher,
            )
            await executor.step_once()
            self.assertEqual(len(switched), 1)
            self.assertEqual(switched[0][0], DEFAULT_SCENE_MAP["minecraft"])
            self.assertIn("minecraft", switched[0][1].lower())

        switched.clear()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as perf_tmp:
            director = PerformanceDirector(data_dir=perf_tmp, scene_switcher=_scene_switcher)
            director.start_performance(song_id="digital_world", dominant_mood="HYPE_EXCITED")
            await asyncio.sleep(0)
            self.assertTrue(any(s == DEFAULT_SCENE_MAP["performance"] for s, _ in switched))

            director.finish_performance()
            await asyncio.sleep(0)
            self.assertTrue(any(s == DEFAULT_SCENE_MAP["social"] for s, _ in switched))


class TestOBSAsgiRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_get_obs_status_and_auth_enforced_post_action(self):
        status, headers, body = await _run_asgi_request("GET", "/api/obs/status")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("content-type", ""))
        data = json.loads(body.decode("utf-8"))
        self.assertIn("connected", data)

        with patch.dict(os.environ, {"MAYBEAI_CREATOR_TOKEN": "top-secret-token"}):
            deny_status, _, _ = await _run_asgi_request(
                "POST",
                "/api/obs/action",
                body=json.dumps({"action": "status"}).encode("utf-8"),
                headers={"content-type": "application/json"},
                client=("192.0.2.50", 50201),
            )
            self.assertEqual(deny_status, 401)

            ok_status, _, ok_body = await _run_asgi_request(
                "POST",
                "/api/obs/action",
                body=json.dumps({"action": "status"}).encode("utf-8"),
                headers={
                    "content-type": "application/json",
                    "x-creator-token": "top-secret-token",
                },
                client=("192.0.2.50", 50202),
            )
            self.assertEqual(ok_status, 200)
            ok_data = json.loads(ok_body.decode("utf-8"))
            self.assertTrue(ok_data.get("success"))


if __name__ == "__main__":
    unittest.main()
