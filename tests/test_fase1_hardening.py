import asyncio
import base64
import copy
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import run
from core.brain import Brain
from core.collab.manager import CollabManager
from core.desktop.controller import DesktopController
from core.orchestrator import Orchestrator
from core.singer import Singer
from core.tts import TTSEngine


async def _asgi_http(method: str, path: str, headers=None, body: bytes = b"", client_host: str = "127.0.0.1"):
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_host, 50000),
        "server": ("127.0.0.1", 7860),
    }
    sent = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await run.app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    resp_body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], resp_body


async def _asgi_ws(
    path: str = "/ws",
    origin=None,
    client_host: str = "127.0.0.1",
    query_string: str = "",
    headers=None,
    incoming_json=None,
):
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()]
    if origin is not None:
        raw_headers.append((b"origin", origin.encode("latin-1")))
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query_string.encode("latin-1"),
        "headers": raw_headers,
        "client": (client_host, 50001),
        "server": ("127.0.0.1", 7860),
        "subprotocols": [],
    }
    queue = [{"type": "websocket.connect"}]
    for payload in incoming_json or []:
        queue.append({"type": "websocket.receive", "text": json.dumps(payload)})
    queue.append({"type": "websocket.disconnect", "code": 1000})
    sent = []

    async def receive():
        if queue:
            return queue.pop(0)
        await asyncio.sleep(0)
        return {"type": "websocket.disconnect", "code": 1000}

    async def send(message):
        sent.append(message)

    await run.app(scope, receive, send)
    return sent


class TestFase1SecretMasking(unittest.IsolatedAsyncioTestCase):
    async def test_configuration_updated_broadcast_masks_all_secrets(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orch = Orchestrator()
            orch.memory_dir = Path(tmp)
            captured = []

            async def fake_listener(payload):
                captured.append(payload)

            orch.register_listener(fake_listener)
            try:
                new_settings = {
                    "security": {"creator_token": "super-secret-creator", "allowed_origins": []},
                    "collab": {"shared_secret": "super-secret-collab"},
                    "twitch": {"oauth_token": "oauth:super-secret-twitch"},
                    "youtube": {"api_key": "AIzaSuperSecretYouTube"},
                    "discord": {"bot_token": "discord.secret.token"},
                    "tts": {"enabled": True, "output_mode": "browser"},
                }
                await orch.apply_configuration_hot_reload(new_settings)
            finally:
                orch.unregister_listener(fake_listener)

            cfg_events = [e for e in captured if e.get("type") == "configuration_updated"]
            self.assertEqual(len(cfg_events), 1)
            settings_out = cfg_events[0]["data"]["settings"]
            self.assertEqual(settings_out["security"]["creator_token"], "********")
            self.assertEqual(settings_out["collab"]["shared_secret"], "********")
            self.assertEqual(settings_out["twitch"]["oauth_token"], "********")
            self.assertEqual(settings_out["youtube"]["api_key"], "********")
            self.assertEqual(settings_out["discord"]["bot_token"], "********")
            self.assertEqual(settings_out["tts"]["output_mode"], "browser")


class TestFase1HttpAndWsAuthParity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._orig_settings = copy.deepcopy(run.config_mgr.settings)

    async def asyncTearDown(self):
        run.config_mgr.settings = self._orig_settings

    async def test_http_api_creator_auth_parity(self):
        run.config_mgr.settings.setdefault("security", {})["creator_token"] = "fase1-token"
        with patch.dict(os.environ, {"MAYBEAI_CREATOR_TOKEN": ""}, clear=False):
            # Missing token -> 401 on GET /api/config, PUT /api/config, POST /api/missions/step
            s1, _ = await _asgi_http("GET", "/api/config")
            s2, _ = await _asgi_http("PUT", "/api/config", body=b"{}")
            s3, _ = await _asgi_http("POST", "/api/missions/step", body=b"{}")
            self.assertEqual(s1, 401)
            self.assertEqual(s2, 401)
            self.assertEqual(s3, 401)

            # Valid X-Creator-Token / Authorization Bearer passes auth
            s_get_ok, _ = await _asgi_http(
                "GET", "/api/config", headers={"X-Creator-Token": "fase1-token"}
            )
            self.assertEqual(s_get_ok, 200)

            with patch.object(run.config_mgr, "save_config", return_value=(True, [], False)):
                s_put_ok, _ = await _asgi_http(
                    "PUT",
                    "/api/config",
                    headers={"Authorization": "Bearer fase1-token", "Content-Type": "application/json"},
                    body=json.dumps({"settings": {"tts": {"output_mode": "both"}}}).encode("utf-8"),
                )
            self.assertEqual(s_put_ok, 200)

            with patch.object(run.orchestrator.missions, "step_once", new=AsyncMock(return_value={"status": "idle"})):
                s_step_ok, _ = await _asgi_http(
                    "POST",
                    "/api/missions/step",
                    headers={"X-Creator-Token": "fase1-token", "Content-Type": "application/json"},
                    body=b"{}",
                )
            self.assertEqual(s_step_ok, 200)

        # No token configured: non-loopback rejected with 403
        run.config_mgr.settings["security"]["creator_token"] = ""
        with patch.dict(os.environ, {"MAYBEAI_CREATOR_TOKEN": ""}, clear=False):
            s_remote, _ = await _asgi_http("GET", "/api/config", client_host="198.51.100.10")
            self.assertEqual(s_remote, 403)

    async def test_ws_mutating_actions_require_creator(self):
        run.config_mgr.settings.setdefault("security", {})["creator_token"] = "fase1-ws-secret"
        mutating_msgs = [
            {"type": "config_action", "data": {"action": "reload"}},
            {"type": "desktop_action", "data": {"action": "toggle_master", "enabled": True}},
            {"type": "minecraft_action", "data": {"action": "set_mode", "mode": "guard"}},
            {"type": "chess_action", "data": {"action": "set_elo", "elo": 1200}},
            {"type": "set_llm_provider", "data": {"provider": "mock"}},
        ]
        with patch.dict(os.environ, {"MAYBEAI_CREATOR_TOKEN": ""}, clear=False):
            sent = await _asgi_ws(
                path="/ws",
                origin="http://127.0.0.1:7860",
                client_host="127.0.0.1",
                query_string="",  # missing token -> non-creator
                incoming_json=mutating_msgs,
            )

        self.assertTrue(any(m.get("type") == "websocket.accept" for m in sent))
        err_frames = [
            json.loads(m["text"])
            for m in sent
            if m.get("type") == "websocket.send" and json.loads(m["text"]).get("type") == "error"
        ]
        self.assertEqual(len(err_frames), len(mutating_msgs))
        for frame in err_frames:
            self.assertEqual(frame["data"]["code"], "forbidden")

    async def test_mock_mode_desktop_controller_blocked_for_non_creators(self):
        brain = Brain("config/settings.json", "config/character.json")
        brain.provider = "mock"
        with patch.object(DesktopController, "launch_app") as mock_launch, \
             patch.object(DesktopController, "adjust_volume") as mock_vol:
            resp = await brain.generate_response(
                "ViewerTroll",
                "eve tolong buka notepad dan kecilin volume",
                is_creator=False,
            )
            self.assertIn("creator", resp.lower())
            mock_launch.assert_not_called()
            mock_vol.assert_not_called()


class TestFase1CollabHardening(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._orig_settings = copy.deepcopy(run.config_mgr.settings)

    async def asyncTearDown(self):
        run.config_mgr.settings = self._orig_settings

    async def test_ws_collab_enforces_shared_secret_on_loopback(self):
        run.config_mgr.settings.setdefault("collab", {})["shared_secret"] = "collab-hmac-key"
        with patch.dict(os.environ, {"MAYBEAI_COLLAB_SECRET": ""}, clear=False):
            # Loopback without secret must be rejected (1008)
            sent_no_secret = await _asgi_ws(
                path="/ws/collab",
                client_host="127.0.0.1",
                query_string="",
            )
            self.assertEqual(sent_no_secret[0]["type"], "websocket.close")
            self.assertEqual(sent_no_secret[0]["code"], 1008)

            # Loopback with valid secret is accepted
            sent_ok = await _asgi_ws(
                path="/ws/collab",
                client_host="127.0.0.1",
                query_string="secret=collab-hmac-key",
            )
            self.assertEqual(sent_ok[0]["type"], "websocket.accept")

    async def test_collab_manager_independent_multi_socket_cleanup(self):
        mgr = CollabManager(settings={"collab": {"enabled": True, "shared_secret": "k"}})
        cb1 = AsyncMock()
        cb2 = AsyncMock()
        mgr.register_peer_sender(cb1, conn_id="sock-1")
        mgr.register_peer_sender(cb2, conn_id="sock-2")
        self.assertIsNotNone(mgr._inbound_send_cb)
        self.assertEqual(len(mgr._inbound_senders), 2)

        mgr.unregister_peer_sender("sock-1")
        # sock-2 still registered -> _inbound_send_cb remains active and routes to cb2
        self.assertIsNotNone(mgr._inbound_send_cb)
        self.assertEqual(len(mgr._inbound_senders), 1)
        await mgr._inbound_send_cb({"type": "hello"})
        cb1.assert_not_called()
        cb2.assert_awaited_once()

        mgr.unregister_peer_sender("sock-2")
        self.assertIsNone(mgr._inbound_send_cb)
        self.assertEqual(len(mgr._inbound_senders), 0)


class TestFase1AudioAndLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_tts_browser_mode_emits_audio_chunk_without_pygame(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orch = Orchestrator()
            orch.memory_dir = Path(tmp)
            captured = []

            async def fake_listener(payload):
                captured.append(payload)

            orch.register_listener(fake_listener)
            try:
                tts = TTSEngine(
                    voice="id-ID-GadisNeural",
                    enabled=True,
                    output_mode="browser",
                    on_audio_ready=orch._on_tts_audio_ready,
                )
                tts.temp_dir = Path(tmp)

                class FakeCommunicate:
                    def __init__(self, text, voice, rate, pitch):
                        pass

                    async def save(self, out_path):
                        Path(out_path).write_bytes(b"FAKE_MP3_BROWSER_BYTES")

                with patch("core.tts.edge_tts.Communicate", side_effect=FakeCommunicate), \
                     patch("core.tts.asyncio.sleep", new=AsyncMock()), \
                     patch.dict(sys.modules, {"pygame": None}):
                    await tts.speak("Halo browser audio!")
            finally:
                orch.unregister_listener(fake_listener)

            chunks = [e for e in captured if e.get("type") == "audio_chunk"]
            self.assertEqual(len(chunks), 1)
            self.assertEqual(
                base64.b64decode(chunks[0]["data"]["audio_b64"]),
                b"FAKE_MP3_BROWSER_BYTES",
            )
            self.assertEqual(chunks[0]["data"]["mime"], "audio/mpeg")
            self.assertEqual(list(Path(tmp).glob("speech_*.mp3")), [])

    async def test_singer_sing_cleans_vocal_temp_files(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            singer = Singer(output_mode="browser")
            singer.temp_dir = Path(tmp)
            singer.songs["test_song"] = {
                "title": "Test Song",
                "bgm_file": None,
                "lyrics": [
                    {"text": "Line one", "delay_before": 0.0, "emotion": "happy"},
                    {"text": "Line two", "delay_before": 0.0, "emotion": "blush"},
                ],
            }
            vocal_cb = AsyncMock()

            class FakeCommunicate:
                def __init__(self, text, voice, pitch, rate):
                    self.text = text

                async def save(self, out_path):
                    Path(out_path).write_bytes(b"VOCAL_MP3_" + self.text.encode("utf-8"))

            with patch("core.singer.edge_tts.Communicate", side_effect=FakeCommunicate), \
                 patch("core.singer.asyncio.sleep", new=AsyncMock()):
                ok = await singer.sing("test_song", on_vocal_audio=vocal_cb)

            self.assertTrue(ok)
            self.assertEqual(vocal_cb.await_count, 2)
            self.assertEqual(list(Path(tmp).glob("vocal_*.mp3")), [])

    async def test_orchestrator_shutdown_cancels_background_tasks_cleanly(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            orch = Orchestrator()
            orch.memory_dir = Path(tmp)

            async def endless_worker():
                await asyncio.sleep(60)

            t1 = orch._spawn_bg_task(endless_worker())
            t2 = orch._spawn_bg_task(endless_worker())
            self.assertEqual(len(orch._bg_tasks), 2)

            await orch.shutdown()

            self.assertTrue(t1.cancelled() or t1.done())
            self.assertTrue(t2.cancelled() or t2.done())
            self.assertEqual(len(orch._bg_tasks), 0)


if __name__ == "__main__":
    unittest.main()
