import asyncio
import copy
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import run
from core.brain import Brain, ProviderCircuitBreaker
from core.event_bus import EventBus
from core.memory import EpisodicMemoryStore
from core.metrics import MetricsCollector
from core.mood.engine import MoodEngine
from core.planning.engine import GoalEngine
from core.planning.executor import AutonomousMissionExecutor
from core.vts_client import VTSClient


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


async def _asgi_ws_binary(
    binary_frames,
    path: str = "/ws",
    client_host: str = "127.0.0.1",
    query_string: str = "",
    headers=None,
):
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()]
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query_string.encode("ascii"),
        "headers": raw_headers,
        "client": (client_host, 50001),
        "server": ("127.0.0.1", 7860),
    }
    frames = list(binary_frames)
    sent = []
    connected = False

    async def receive():
        nonlocal connected
        if not connected:
            connected = True
            return {"type": "websocket.connect"}
        if frames:
            payload = frames.pop(0)
            return {"type": "websocket.receive", "bytes": payload}
        await asyncio.sleep(0.05)
        return {"type": "websocket.disconnect", "code": 1000}

    async def send(message):
        sent.append(message)

    await run.app(scope, receive, send)
    return sent


class TestHorizon2ExitGates(unittest.IsolatedAsyncioTestCase):
    """Horizon 2 Exit-Gate verification suite (H2-01 through H2-07)."""

    # ------------------------------------------------------------------
    # H2-01: Failover & Circuit Breaker Gate
    # ------------------------------------------------------------------
    async def test_h2_01_gemini_429_failover_to_ollama_and_mock_under_2s(self):
        with patch.dict(
            os.environ,
            {"MAYBEAI_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake-gem-key", "OPENAI_API_KEY": ""},
            clear=False,
        ):
            brain = Brain()
            brain.conversation.episodic_memory.embedder.provider = "hash"
            brain.settings = copy.deepcopy(brain.settings)
            brain.settings["llm"] = {
                **brain.settings.get("llm", {}),
                "provider": "gemini",
                "failover_enabled": True,
                "failover_timeout_sec": 1.5,
                "circuit_breaker_failure_threshold": 3,
                "circuit_breaker_cooldown_sec": 30.0,
                "retry_attempts": 1,
                "temperature": 0.8,
            }
            with (
                patch.object(brain, "_try_gemini", new=AsyncMock(return_value=(None, 429, "Rate limited"))) as mock_gem,
                patch.object(brain, "_try_ollama", new=AsyncMock(return_value=("[happy] Halo dari Ollama!", None, None))) as mock_oll,
            ):
                t0 = time.perf_counter()
                reply = await brain.generate_response(
                    user_name="Creator",
                    message="Tes failover?",
                    is_creator=True,
                )
                elapsed = time.perf_counter() - t0
                self.assertLess(elapsed, 2.0)
                self.assertIn("Ollama", reply)
                mock_gem.assert_awaited()
                mock_oll.assert_awaited()

            # Now fail Ollama too -> clean fallback to offline mock in < 2s
            with (
                patch.object(brain, "_try_gemini", new=AsyncMock(return_value=(None, 429, "Rate limited"))),
                patch.object(brain, "_try_ollama", new=AsyncMock(return_value=(None, 503, "Ollama down"))),
            ):
                t0 = time.perf_counter()
                mock_reply = await brain.generate_response(
                    user_name="Viewer",
                    message="Halo Eve!",
                    is_creator=False,
                )
                elapsed = time.perf_counter() - t0
                self.assertLess(elapsed, 2.0)
                self.assertIsInstance(mock_reply, str)
                self.assertTrue(len(mock_reply.strip()) > 0)

    async def test_h2_01_circuit_breaker_trips_and_half_open_recovers(self):
        cb = ProviderCircuitBreaker(failure_threshold=2, cooldown_sec=0.05)
        self.assertTrue(cb.allow_request("gemini"))

        cb.record_failure("gemini", reason="HTTP 429", status_code=429)
        self.assertTrue(cb.allow_request("gemini"))

        cb.record_failure("gemini", reason="HTTP 429", status_code=429)
        self.assertFalse(cb.allow_request("gemini"))

        await asyncio.sleep(0.06)
        # Half-open allows exactly one probe
        self.assertTrue(cb.allow_request("gemini"))
        self.assertFalse(cb.allow_request("gemini"))

        # Success closes circuit again
        cb.record_success("gemini")
        self.assertTrue(cb.allow_request("gemini"))

    # ------------------------------------------------------------------
    # H2-02 & H2-06: Mood Temperature, Shared Embedder & Approval TTL
    # ------------------------------------------------------------------
    def test_h2_02_mood_engine_modulates_temperature_within_bounds(self):
        mood = MoodEngine()
        mood.dimensions["excitement"] = 1.0
        mood.dimensions["curiosity"] = 1.0
        mood.dimensions["competitiveness"] = 0.0
        mod = mood.get_temperature_modifier()
        self.assertGreater(mod, 0.0)
        self.assertLessEqual(mod, 0.15)

        brain = Brain()
        brain.conversation.mood = mood
        brain.settings = {"llm": {"provider": "mock", "temperature": 0.8}}
        eff_mid = brain._get_effective_temperature()
        self.assertGreaterEqual(eff_mid, 0.2)
        self.assertLessEqual(eff_mid, 1.2)
        self.assertAlmostEqual(eff_mid, round(0.8 + mod, 4), places=4)

        brain.settings = {"llm": {"provider": "mock", "temperature": 0.05}}
        self.assertGreaterEqual(brain._get_effective_temperature(), 0.2)

        brain.settings = {"llm": {"provider": "mock", "temperature": 1.8}}
        self.assertLessEqual(brain._get_effective_temperature(), 1.2)

    def test_h2_06_episodic_memory_shares_single_embedding_engine(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            store = EpisodicMemoryStore(
                db_path=str(Path(tmp) / "mem.db"),
                markdown_dir=str(Path(tmp) / "brain"),
                embedding_provider="hash",
            )
            self.assertIs(store.embedder, store.db.embedder)

    async def test_h2_06_approval_timeout_expires_stale_pending_approval(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            ge = GoalEngine(storage_dir=tmp)
            executor = AutonomousMissionExecutor(
                goal_engine=ge,
                human_approval_required=True,
                approval_timeout_sec=0.05,
            )
            res1 = await executor.step_once(force=False)
            self.assertEqual(res1["status"], "awaiting_approval")
            self.assertIsNotNone(executor.pending_approval)

            await asyncio.sleep(0.07)
            res2 = await executor.step_once(force=False)
            self.assertIn("status", res2)
            expired_events = [h for h in executor.history if h.get("status") == "approval_expired"]
            self.assertGreaterEqual(len(expired_events), 1)

    # ------------------------------------------------------------------
    # H2-04 & H2-07: /api/metrics Auth & /ws Binary PCM Enqueue
    # ------------------------------------------------------------------
    async def test_h2_04_07_api_metrics_enforces_creator_auth_and_returns_snapshot(self):
        orig_settings = copy.deepcopy(run.config_mgr.settings)
        run.config_mgr.settings.setdefault("security", {})["creator_token"] = "h2-secret-token"
        try:
            with patch.dict(os.environ, {"MAYBEAI_CREATOR_TOKEN": ""}, clear=False):
                # Remote / unauthenticated request must be rejected
                status_unauth, _ = await _asgi_http("GET", "/api/metrics", client_host="10.0.0.5")
                self.assertIn(status_unauth, (401, 403))

                # Wrong token must be rejected
                status_bad, _ = await _asgi_http(
                    "GET",
                    "/api/metrics",
                    headers={"Authorization": "Bearer wrong-token"},
                    client_host="10.0.0.5",
                )
                self.assertIn(status_bad, (401, 403))

                # Valid Creator token returns 200 with MetricsCollector snapshot
                status_ok, body_ok = await _asgi_http(
                    "GET",
                    "/api/metrics",
                    headers={"Authorization": "Bearer h2-secret-token"},
                    client_host="10.0.0.5",
                )
                self.assertEqual(status_ok, 200)
                payload = json.loads(body_ok.decode("utf-8"))
                self.assertIn("orchestrator", payload)
                self.assertIn("counters", payload["orchestrator"])
                self.assertIn("gauges", payload["orchestrator"])
                self.assertIn("histograms", payload["orchestrator"])
                self.assertIn("active_ws_clients", payload)
        finally:
            run.config_mgr.settings = orig_settings

    async def test_h2_04_ws_binary_pcm_frames_enqueue_into_voice_queue(self):
        orig_settings = copy.deepcopy(run.config_mgr.settings)
        run.config_mgr.settings.setdefault("security", {})["creator_token"] = "h2-ws-token"
        pcm_frame = b"\x01\x00" * 160
        try:
            with (
                patch.dict(os.environ, {"MAYBEAI_CREATOR_TOKEN": ""}, clear=False),
                patch.object(
                    run.orchestrator,
                    "process_voice_chunk",
                    new=AsyncMock(return_value={"ok": True, "bytes": len(pcm_frame)}),
                ) as mock_voice,
            ):
                sent = await _asgi_ws_binary(
                    [pcm_frame],
                    query_string="token=h2-ws-token",
                    client_host="127.0.0.1",
                )
                mock_voice.assert_awaited_once_with(
                    pcm_frame,
                    user="Creator",
                    language=None,
                )
                ack_msgs = [
                    json.loads(m["text"])
                    for m in sent
                    if m.get("type") == "websocket.send" and "text" in m
                ]
                self.assertTrue(any(m.get("type") == "voice_chunk_ack" for m in ack_msgs))
        finally:
            run.config_mgr.settings = orig_settings

    # ------------------------------------------------------------------
    # H2-05: Air-Gapped LAN Assets & VTS Token Persistence
    # ------------------------------------------------------------------
    def test_h2_05_zero_cdn_links_in_web_assets(self):
        web_dir = Path("web")
        targets = list(web_dir.glob("*.html")) + list(web_dir.glob("*.js"))
        style_css = web_dir / "style.css"
        if style_css.exists():
            targets.append(style_css)

        forbidden = ("https://esm.sh", "https://fonts.googleapis.com")
        for file_path in targets:
            content = file_path.read_text(encoding="utf-8")
            for bad in forbidden:
                self.assertNotIn(bad, content, f"Forbidden CDN {bad} found in {file_path}")

        self.assertTrue((web_dir / "vendor" / "three.module.js").exists())
        self.assertTrue((web_dir / "vendor" / "three-vrm.module.js").exists())
        self.assertTrue((web_dir / "vendor" / "fonts.css").exists())

    def test_h2_05_vts_client_persists_token_to_vts_token_json(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            token_file = Path(tmp) / "vts_token.json"
            client1 = VTSClient(token_path=str(token_file))
            client1._save_token("persisted-vts-token-123")
            self.assertTrue(token_file.exists())

            client2 = VTSClient(token_path=str(token_file))
            self.assertEqual(client2._load_token(), "persisted-vts-token-123")

    # ------------------------------------------------------------------
    # H2-07: Simulated Async Soak Gate (200+ ops, 0 leaked tasks, bounded mem)
    # ------------------------------------------------------------------
    async def test_h2_07_async_soak_200_ops_zero_leaked_tasks_and_bounded_memory(self):
        bus = EventBus()
        metrics = MetricsCollector()
        received = 0

        async def _on_event(_event_name, _payload):
            nonlocal received
            received += 1

        bus.subscribe("soak.tick", _on_event)

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            store = EpisodicMemoryStore(
                db_path=str(Path(tmp) / "soak.db"),
                markdown_dir=str(Path(tmp) / "soak_md"),
                embedding_provider="hash",
            )
            current = asyncio.current_task()
            before_tasks = {t for t in asyncio.all_tasks() if t is not current and not t.done()}

            iterations = 250
            for i in range(iterations):
                await bus.publish("soak.tick", {"seq": i})
                metrics.inc("soak_events")
                metrics.observe("soak_step_ms", float(i % 10) * 0.1)
                if i % 25 == 0:
                    _ = await store.embedder.aencode(f"soak memory query {i}")
                    snap = metrics.snapshot()
                    self.assertIn("counters", snap)

            await asyncio.sleep(0)
            after_tasks = {t for t in asyncio.all_tasks() if t is not current and not t.done()}
            leaked = after_tasks - before_tasks
            self.assertEqual(len(leaked), 0, f"Leaked asyncio tasks: {leaked}")
            self.assertEqual(received, iterations)

            stats = bus.get_stats()
            self.assertEqual(stats["total_published"], iterations)
            self.assertEqual(stats["handler_errors"], 0)

            final_snap = metrics.snapshot()
            self.assertEqual(final_snap["counters"]["soak_events"], iterations)
            self.assertLessEqual(final_snap["histograms"]["soak_step_ms"]["count"], iterations)
            self.assertLessEqual(len(metrics._histograms["soak_step_ms"].samples), 1000)


if __name__ == "__main__":
    unittest.main()
