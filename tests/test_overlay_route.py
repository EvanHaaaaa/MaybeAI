import asyncio
import json
import os
import unittest

try:
    import tests  # noqa: F401  # Ensure tests/__init__.py sets MAYBEAI_LLM_PROVIDER=mock
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

import run


async def _run_http_get(path: str, headers=None):
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 50100),
        "server": ("127.0.0.1", 7860),
    }
    sent = []
    delivered = False
    done_event = asyncio.Event()

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await done_event.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            done_event.set()

    await run.app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    resp_body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    resp_headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in start.get("headers", [])}
    return start["status"], resp_headers, resp_body


class TestOverlayAndEventBusRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_get_overlay_returns_200_html_with_stage_elements(self):
        status, headers, body = await _run_http_get("/overlay")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("content-type", ""))

        html = body.decode("utf-8")
        self.assertIn('id="avatarCanvas"', html)
        self.assertIn('id="subtitles"', html)
        self.assertIn('id="donation-alert-banner"', html)
        self.assertIn("/static/overlay.css", html)
        self.assertIn("/static/overlay.js", html)
        # Overlay must stay clean without studio forms or input fields
        self.assertNotIn("<form", html.lower())
        self.assertNotIn("<input", html.lower())

    async def test_overlay_css_enforces_transparent_background(self):
        status, _, body = await _run_http_get("/static/overlay.css")
        self.assertEqual(status, 200)
        css = body.decode("utf-8")
        self.assertIn("transparent", css)

    async def test_get_eventbus_stats_returns_200_json(self):
        status, headers, body = await _run_http_get("/api/eventbus/stats")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("content-type", ""))

        data = json.loads(body.decode("utf-8"))
        for key in (
            "subscriber_counts",
            "total_subscribers",
            "total_published",
            "handler_errors",
            "history_size",
            "max_history",
            "recent_event_types",
        ):
            self.assertIn(key, data)
        self.assertIsInstance(data["subscriber_counts"], dict)
        self.assertIsInstance(data["recent_event_types"], list)

    async def test_get_platforms_status_returns_200_json(self):
        status, headers, body = await _run_http_get("/api/platforms/status")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("content-type", ""))

        data = json.loads(body.decode("utf-8"))
        for platform in ("twitch", "youtube", "discord"):
            self.assertIn(platform, data)


if __name__ == "__main__":
    unittest.main()
