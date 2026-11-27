import asyncio
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

# Ensure isolated temp data dir and mock LLM before importing run
if "MAYBEAI_DATA_DIR" not in os.environ:
    _TEMP_DATA_DIR = tempfile.TemporaryDirectory(prefix="maybeai_e2e_data_", ignore_cleanup_errors=True)
    os.environ["MAYBEAI_DATA_DIR"] = _TEMP_DATA_DIR.name

try:
    import tests  # noqa: F401
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

import uvicorn
import websockets

import run

try:
    from playwright.sync_api import sync_playwright  # type: ignore

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False


class _LiveUvicornServer:
    """Runs `run.app` on an ephemeral 127.0.0.1:0 port in a background thread."""

    def __init__(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(32)
        self.port = self.sock.getsockname()[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.ws_base_url = f"ws://127.0.0.1:{self.port}"
        config = uvicorn.Config(
            run.app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            lifespan="on",
        )
        self.server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        asyncio.run(self.server.serve(sockets=[self.sock]))

    def start(self, timeout: float = 10.0) -> None:
        self._thread.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.server.started:
                return
            try:
                with urllib.request.urlopen(f"{self.base_url}/api/health", timeout=0.5) as resp:
                    if resp.status == 200:
                        return
            except Exception:
                time.sleep(0.05)
        raise RuntimeError("Timed out waiting for live uvicorn server to start")

    def stop(self) -> None:
        self.server.should_exit = True
        self._thread.join(timeout=5.0)
        try:
            self.sock.close()
        except OSError:
            pass


def _http_get(url: str, headers: dict | None = None) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp_headers, resp.read()
    except urllib.error.HTTPError as exc:
        resp_headers = {k.lower(): v for k, v in exc.headers.items()}
        return exc.code, resp_headers, exc.read()


class TestLiveServerContracts(unittest.IsolatedAsyncioTestCase):
    server: _LiveUvicornServer

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = _LiveUvicornServer()
        cls.server.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def setUp(self) -> None:
        self._orig_security = dict(run.config_mgr.settings.get("security", {}))
        self._orig_env_token = os.environ.get("MAYBEAI_CREATOR_TOKEN")

    def tearDown(self) -> None:
        run.config_mgr.settings["security"] = self._orig_security
        if self._orig_env_token is None:
            os.environ.pop("MAYBEAI_CREATOR_TOKEN", None)
        else:
            os.environ["MAYBEAI_CREATOR_TOKEN"] = self._orig_env_token

    def test_html_routes_return_200_with_expected_contracts(self) -> None:
        route_expectations = {
            "/": ["<html", "/static/shared-client.js", "/static/app.js"],
            "/overlay": ['id="avatarCanvas"', 'id="subtitles"', 'id="donation-alert-banner"', "/static/overlay.js"],
            "/deck": ["<html", "/static/shared-client.js", "/static/deck.js"],
            "/settings": ["<html", "/static/settings.js"],
        }
        for path, markers in route_expectations.items():
            status, headers, body = _http_get(f"{self.server.base_url}{path}")
            self.assertEqual(status, 200, f"Expected 200 for {path}, got {status}")
            self.assertIn("text/html", headers.get("content-type", ""))
            html = body.decode("utf-8", errors="replace")
            for marker in markers:
                self.assertIn(marker, html, f"Missing marker {marker!r} in {path}")

    def test_static_vendor_and_shared_client_served(self) -> None:
        for path in ("/static/shared-client.js", "/static/vendor/three.module.js"):
            status, headers, body = _http_get(f"{self.server.base_url}{path}")
            self.assertEqual(status, 200, f"Expected 200 for {path}")
            self.assertIn("javascript", headers.get("content-type", "").lower())
            self.assertGreater(len(body), 100)

    def test_api_health_returns_ok(self) -> None:
        status, headers, body = _http_get(f"{self.server.base_url}/api/health")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("content-type", ""))
        self.assertEqual(json.loads(body.decode("utf-8")), {"status": "ok"})

    def test_api_metrics_is_auth_and_origin_gated(self) -> None:
        os.environ["MAYBEAI_CREATOR_TOKEN"] = "e2e-metrics-secret"

        # Foreign origin is rejected with 403
        status_origin, _, _ = _http_get(
            f"{self.server.base_url}/api/metrics",
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(status_origin, 403)

        # Missing bearer token is rejected with 401
        status_unauth, _, _ = _http_get(f"{self.server.base_url}/api/metrics")
        self.assertEqual(status_unauth, 401)

        # Valid bearer token succeeds
        status_ok, _, body_ok = _http_get(
            f"{self.server.base_url}/api/metrics",
            headers={"Authorization": "Bearer e2e-metrics-secret"},
        )
        self.assertEqual(status_ok, 200)
        payload = json.loads(body_ok.decode("utf-8"))
        self.assertIn("uptime_sec", payload)
        self.assertIn("active_ws_clients", payload)
        self.assertIn("websocket_clients", payload)
        self.assertIn("orchestrator", payload)

    async def test_live_websocket_connect_and_origin_rejection(self) -> None:
        # Allowed localhost origin connects and receives initial payload or stays open
        async with websockets.connect(
            f"{self.server.ws_base_url}/ws",
            origin=self.server.base_url,
            open_timeout=5,
        ) as ws:
            await ws.send(json.dumps({"type": "ping"}))
            # Verify connection remains open briefly without error
            await asyncio.sleep(0.05)

        # Foreign origin is rejected during handshake or immediately closed with 1008
        rejected = False
        try:
            async with websockets.connect(
                f"{self.server.ws_base_url}/ws",
                origin="https://evil.example",
                open_timeout=5,
            ) as ws:
                await ws.recv()
        except Exception:
            rejected = True
        self.assertTrue(rejected, "Foreign origin WebSocket connection should be rejected")


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "playwright not installed")
class TestPlaywrightBrowserE2E(unittest.TestCase):
    server: _LiveUvicornServer

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = _LiveUvicornServer()
        cls.server.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_pages_render_without_uncaught_errors(self) -> None:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for path, selector in (
                    ("/", "body"),
                    ("/overlay", "#avatarCanvas"),
                    ("/deck", "body"),
                    ("/settings", "body"),
                ):
                    page = browser.new_page()
                    errors: list[str] = []
                    page.on("pageerror", lambda err: errors.append(str(err)))
                    resp = page.goto(f"{self.server.base_url}{path}", wait_until="domcontentloaded")
                    self.assertIsNotNone(resp)
                    self.assertEqual(resp.status, 200)
                    page.wait_for_selector(selector, timeout=5000)
                    self.assertEqual(errors, [], f"Uncaught JS errors on {path}: {errors}")
                    page.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
