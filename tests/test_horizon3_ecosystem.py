import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import tests  # noqa: F401
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

import chess

import run
from core.chess.chess_engine import ChessEngine
from core.collab.manager import CollabManager
from core.collab.protocol import CollabEnvelope, DEFAULT_COLLAB_CAPABILITIES
from core.plugins.registry import PluginRegistry
from core.security_net import SSRFValidationError, validate_outbound_url


async def _run_asgi_ws(
    path: str,
    headers: list[tuple[bytes, bytes]] | None = None,
    subprotocols: list[str] | None = None,
    query_string: str = "",
):
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query_string.encode("latin-1"),
        "headers": headers or [(b"origin", b"http://127.0.0.1:7860")],
        "client": ("127.0.0.1", 50200),
        "server": ("127.0.0.1", 7860),
        "subprotocols": subprotocols or [],
    }
    queue = [
        {"type": "websocket.connect"},
        {"type": "websocket.disconnect", "code": 1000},
    ]
    sent: list[dict] = []

    async def receive():
        if queue:
            return queue.pop(0)
        await asyncio.sleep(0)
        return {"type": "websocket.disconnect", "code": 1000}

    async def send(message):
        sent.append(message)

    await run.app(scope, receive, send)
    return sent


class TestSSRFValidation(unittest.TestCase):
    def test_blocks_unsafe_schemes_metadata_and_private_ips(self) -> None:
        for bad_url in (
            "file:///etc/passwd",
            "ftp://example.com/resource",
            "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1:8080/internal",
            "http://10.0.0.5/admin",
        ):
            with self.assertRaises(SSRFValidationError, msg=f"Should block {bad_url}"):
                validate_outbound_url(bad_url, allow_private=False)

    def test_allows_private_when_enabled_or_allowlisted(self) -> None:
        self.assertEqual(
            validate_outbound_url("http://127.0.0.1:9880/tts", allow_private=True),
            "http://127.0.0.1:9880/tts",
        )
        self.assertEqual(
            validate_outbound_url(
                "http://127.0.0.1:9880/tts",
                allow_private=False,
                allowlist=["127.0.0.1"],
            ),
            "http://127.0.0.1:9880/tts",
        )

    def test_allows_public_ip_and_blocks_dns_rebinding_to_private(self) -> None:
        public_addr = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch("core.security_net.socket.getaddrinfo", return_value=public_addr):
            self.assertEqual(
                validate_outbound_url("https://example.com/api", allow_private=False),
                "https://example.com/api",
            )

        rebound_addr = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))]
        with patch("core.security_net.socket.getaddrinfo", return_value=rebound_addr):
            with self.assertRaises(SSRFValidationError):
                validate_outbound_url("https://rebind.example/api", allow_private=False)


class TestCollabBidirectionalAndHello(unittest.IsolatedAsyncioTestCase):
    async def test_hello_and_bidirectional_sync_callbacks(self) -> None:
        duet_events: list[CollabEnvelope] = []
        emote_events: list[CollabEnvelope] = []
        move_events: list[CollabEnvelope] = []

        mgr = CollabManager(
            settings={
                "collab": {
                    "enabled": True,
                    "shared_secret": "h3-collab-secret",
                }
            },
            self_id="eve-host",
            self_name="Eve",
            on_duet_sync=lambda env: duet_events.append(env),
            on_emote_sync=lambda env: emote_events.append(env),
            on_game_move=lambda env: move_events.append(env),
        )

        sent_frames: list[dict] = []

        class _FakeWS:
            closed = False

            async def send_json(self, data: dict) -> None:
                sent_frames.append(data)

        mgr._ws_client = _FakeWS()
        mgr.peer_connected = True

        # Outbound hello + sync frames
        hello_res = await mgr.send_hello()
        self.assertTrue(hello_res["sent"])
        duet_res = await mgr.send_duet_sync("song-1", lyric_index=3, timestamp=12.5, track="harmony")
        self.assertTrue(duet_res["sent"])
        emote_res = await mgr.send_emote_sync("happy", action="wave")
        self.assertTrue(emote_res["sent"])
        move_res = await mgr.send_game_move("e2e4", game="chess")
        self.assertTrue(move_res["sent"])
        self.assertEqual(len(sent_frames), 4)

        # Inbound hello updates peer_capabilities
        peer_hello = CollabEnvelope(
            sender_id="peer-1",
            sender_name="Peer",
            event_type="hello",
            payload={"capabilities": ["duet_sync", "emote_sync", "game_move"]},
        )
        peer_hello.sign("h3-collab-secret")
        res_hello = await mgr.handle_incoming_envelope(peer_hello.to_dict())
        self.assertTrue(res_hello["accepted"])
        self.assertEqual(mgr.peer_capabilities, ["duet_sync", "emote_sync", "game_move"])

        # Inbound duet_sync, emote_sync, game_move trigger registered callbacks
        for etype, payload in (
            ("duet_sync", {"song_id": "song-1", "lyric_index": 4, "timestamp": 15.0, "track": "lead"}),
            ("emote_sync", {"emotion": "excited", "action": "cheer"}),
            ("game_move", {"game": "chess", "move": "e7e5", "uci": "e7e5"}),
        ):
            env = CollabEnvelope(
                sender_id="peer-1",
                sender_name="Peer",
                event_type=etype,
                payload=payload,
            )
            env.sign("h3-collab-secret")
            res = await mgr.handle_incoming_envelope(env.to_dict())
            self.assertTrue(res["accepted"], f"Expected {etype} to be accepted")

        self.assertEqual(len(duet_events), 1)
        self.assertEqual(duet_events[0].payload["lyric_index"], 4)
        self.assertEqual(len(emote_events), 1)
        self.assertEqual(emote_events[0].payload["action"], "cheer")
        self.assertEqual(len(move_events), 1)
        self.assertEqual(move_events[0].payload["move"], "e7e5")
        self.assertIn("duet_sync", DEFAULT_COLLAB_CAPABILITIES)


class TestNonQueryWebSocketAuth(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._orig_security = dict(run.config_mgr.settings.get("security", {}))
        self._orig_collab = dict(run.config_mgr.settings.get("collab", {}))
        self._orig_env_token = os.environ.get("MAYBEAI_CREATOR_TOKEN")
        self._orig_collab_secret = run.orchestrator.collab.shared_secret

    async def asyncTearDown(self) -> None:
        run.config_mgr.settings["security"] = self._orig_security
        run.config_mgr.settings["collab"] = self._orig_collab
        run.orchestrator.collab.shared_secret = self._orig_collab_secret
        if self._orig_env_token is None:
            os.environ.pop("MAYBEAI_CREATOR_TOKEN", None)
        else:
            os.environ["MAYBEAI_CREATOR_TOKEN"] = self._orig_env_token

    async def test_ws_accepts_bearer_and_subprotocol_auth(self) -> None:
        os.environ["MAYBEAI_CREATOR_TOKEN"] = "ws-bearer-secret"

        async def _send_creator_msg(headers, subprotocols=None):
            while not run.orchestrator.chat.queue.empty():
                run.orchestrator.chat.queue.get_nowait()
            scope = {
                "type": "websocket",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "scheme": "ws",
                "path": "/ws",
                "raw_path": b"/ws",
                "query_string": b"",
                "headers": headers,
                "client": ("127.0.0.1", 50200),
                "server": ("127.0.0.1", 7860),
                "subprotocols": subprotocols or [],
            }
            queue = [
                {"type": "websocket.connect"},
                {
                    "type": "websocket.receive",
                    "text": json.dumps({"type": "user_message", "user": "Host", "text": "hi", "source": "creator"}),
                },
                {"type": "websocket.disconnect", "code": 1000},
            ]
            sent = []

            async def receive():
                if queue:
                    return queue.pop(0)
                await asyncio.sleep(0)
                return {"type": "websocket.disconnect", "code": 1000}

            async def send(message):
                sent.append(message)

            await run.app(scope, receive, send)
            msg = await run.orchestrator.chat.get_next_message()
            return sent, msg

        # Unauthenticated /ws connects as viewer (is_creator=False)
        _, msg_unauth = await _send_creator_msg(headers=[(b"origin", b"http://127.0.0.1:7860")])
        self.assertFalse(msg_unauth.is_creator)

        # Authorization: Bearer grants creator auth (is_creator=True)
        _, msg_bearer = await _send_creator_msg(
            headers=[
                (b"origin", b"http://127.0.0.1:7860"),
                (b"authorization", b"Bearer ws-bearer-secret"),
            ],
        )
        self.assertTrue(msg_bearer.is_creator)

        # Sec-WebSocket-Protocol grants creator auth and echoes subprotocol
        proto = "maybeai.token.ws-bearer-secret"
        sent_proto, msg_proto = await _send_creator_msg(
            headers=[
                (b"origin", b"http://127.0.0.1:7860"),
                (b"sec-websocket-protocol", proto.encode("latin-1")),
            ],
            subprotocols=[proto],
        )
        accepts = [m for m in sent_proto if m["type"] == "websocket.accept"]
        self.assertEqual(len(accepts), 1)
        self.assertEqual(accepts[0].get("subprotocol"), proto)
        self.assertTrue(msg_proto.is_creator)

    async def test_ws_collab_accepts_bearer_and_subprotocol_secret(self) -> None:
        run.orchestrator.collab.shared_secret = "collab-proto-secret"

        # Unauthenticated rejected
        sent_unauth = await _run_asgi_ws("/ws/collab")
        self.assertNotIn("websocket.accept", [m["type"] for m in sent_unauth])

        # Sec-WebSocket-Protocol accepted and echoed
        proto = "maybeai.collab.collab-proto-secret"
        sent_proto = await _run_asgi_ws(
            "/ws/collab",
            headers=[
                (b"origin", b"http://127.0.0.1:7860"),
                (b"sec-websocket-protocol", proto.encode("latin-1")),
            ],
            subprotocols=[proto],
        )
        accepts = [m for m in sent_proto if m["type"] == "websocket.accept"]
        self.assertEqual(len(accepts), 1)
        self.assertEqual(accepts[0].get("subprotocol"), proto)


class TestPluginPermissionsAndSandboxBoundary(unittest.IsolatedAsyncioTestCase):
    async def test_plugin_registry_denies_unapproved_permissions_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "plugins"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            plugin_file = plugin_dir / "req_perms.py"
            plugin_file.write_text(
                "\n".join([
                    "from core.plugins.sdk import MaybeAIPlugin, PluginManifest",
                    "class ReqPermsPlugin(MaybeAIPlugin):",
                    "    manifest = PluginManifest(",
                    "        id='req_perms',",
                    "        name='Req Perms',",
                    "        permissions=['chat:read', 'tts:speak'],",
                    "    )",
                ]),
                encoding="utf-8",
            )

            registry = PluginRegistry(
                plugins_dir=str(plugin_dir),
                granted_permissions={"req_perms": ["tts:speak"]},
            )
            await registry.discover_plugins()
            try:
                plugins = {p["id"]: p for p in registry.list_plugins()}
                meta = plugins["req_perms"]
                self.assertEqual(sorted(meta["requested_permissions"]), ["chat:read", "tts:speak"])
                self.assertEqual(meta["granted_permissions"], ["tts:speak"])
                self.assertEqual(meta["denied_permissions"], ["chat:read"])
            finally:
                await registry.shutdown()

    def test_sandbox_worker_blocks_env_read_without_fs_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scratch = root / "scratch"
            scratch.mkdir()
            env_file = root / ".env"
            env_file.write_text("SECRET_KEY=top_secret\n", encoding="utf-8")

            script = (
                "from pathlib import Path; "
                "from core.plugins.sandbox_worker import install_boundary_guards; "
                f"install_boundary_guards(Path({str(scratch)!r}), Path({str(root)!r}), permissions=[]); "
                f"open({str(env_file)!r}, 'r').read()"
            )
            proc = subprocess.run(
                [sys.executable, "-c", script],
                cwd=str(Path(__file__).resolve().parent.parent),
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("PermissionError", proc.stderr)


class TestChessEngineStockfishFallback(unittest.TestCase):
    def test_falls_back_to_alpha_beta_when_stockfish_absent_or_fails(self) -> None:
        with patch("core.chess.chess_engine.shutil.which", return_value=None):
            engine = ChessEngine(elo=1000, use_stockfish=True)
            self.assertEqual(engine.backend, "alpha_beta")
            self.assertFalse(engine.is_stockfish_available())
            move = engine.choose_move()
            self.assertIsNotNone(move)
            self.assertIn(move, engine.board.legal_moves)

        with patch("core.chess.chess_engine.chess.engine.SimpleEngine.popen_uci", side_effect=OSError("missing binary")):
            engine2 = ChessEngine(elo=1000, use_stockfish=True, stockfish_path="fake-stockfish")
            move2 = engine2.choose_move()
            self.assertTrue(engine2._stockfish_failed)
            self.assertEqual(engine2.backend, "alpha_beta")
            self.assertIsNotNone(move2)
            self.assertIn(move2, engine2.board.legal_moves)


if __name__ == "__main__":
    unittest.main()
