import asyncio
import json
import os
import unittest
from unittest.mock import patch

import run


async def _run_http_request(method: str, path: str, headers=None, body: bytes = b""):
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
        "client": ("127.0.0.1", 50000),
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


async def _run_ws_session(
    origin=None,
    client_host: str = "127.0.0.1",
    query_string: str = "",
    incoming_json=None,
):
    headers = []
    if origin is not None:
        headers.append((b"origin", origin.encode("latin-1")))
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/ws",
        "raw_path": b"/ws",
        "query_string": query_string.encode("latin-1"),
        "headers": headers,
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


class TestWebSocketAndOriginSecurity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._drain_chat_queue()
        self._orig_security = dict(run.config_mgr.settings.get("security", {}))

    async def asyncTearDown(self):
        self._drain_chat_queue()
        run.config_mgr.settings["security"] = self._orig_security

    def _drain_chat_queue(self):
        while not run.orchestrator.chat.queue.empty():
            run.orchestrator.chat.queue.get_nowait()

    async def test_ws_rejects_foreign_origin_with_1008(self):
        sent = await _run_ws_session(origin="https://evil.example")
        types = [m["type"] for m in sent]
        self.assertNotIn("websocket.accept", types)
        close_msgs = [m for m in sent if m["type"] == "websocket.close"]
        self.assertEqual(len(close_msgs), 1)
        self.assertEqual(close_msgs[0]["code"], 1008)

    async def test_ws_allows_localhost_and_configured_origins(self):
        sent_local = await _run_ws_session(origin="http://127.0.0.1:7860")
        self.assertIn("websocket.accept", [m["type"] for m in sent_local])

        run.config_mgr.settings["security"] = {
            "creator_token": "",
            "allowed_origins": ["https://studio.example"],
        }
        sent_cfg = await _run_ws_session(origin="https://studio.example")
        self.assertIn("websocket.accept", [m["type"] for m in sent_cfg])

    async def test_mutating_api_rejects_foreign_origin_with_403(self):
        status, body = await _run_http_request(
            "PUT",
            "/api/config",
            headers={"Origin": "https://evil.example", "Content-Type": "application/json"},
            body=b"{}",
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["detail"], "Forbidden origin")

    async def test_ws_ignores_spoofed_is_creator_from_non_loopback(self):
        await _run_ws_session(
            origin="http://localhost:7860",
            client_host="198.51.100.42",
            incoming_json=[
                {
                    "type": "user_message",
                    "user": "Attacker",
                    "text": "!desktop open calc",
                    "source": "creator",
                    "is_creator": True,
                },
                {
                    "type": "user_message",
                    "user": "Attacker2",
                    "text": "mic spoof",
                    "source": "mic",
                    "is_creator": True,
                },
            ],
        )
        m1 = await run.orchestrator.chat.get_next_message()
        m2 = await run.orchestrator.chat.get_next_message()
        self.assertFalse(m1.is_creator)
        self.assertEqual(m1.source, "web")
        self.assertFalse(m2.is_creator)
        self.assertEqual(m2.source, "web")

    async def test_ws_loopback_requires_matching_token_when_configured(self):
        run.config_mgr.settings["security"] = {"creator_token": "", "allowed_origins": []}
        with patch.dict(os.environ, {"MAYBEAI_CREATOR_TOKEN": "top-secret-token"}, clear=False):
            # Missing token -> downgraded
            await _run_ws_session(
                origin="http://127.0.0.1:7860",
                client_host="127.0.0.1",
                query_string="",
                incoming_json=[
                    {"type": "user_message", "user": "Spoofer", "text": "no token", "source": "creator", "is_creator": True}
                ],
            )
            m_no_tok = await run.orchestrator.chat.get_next_message()
            self.assertFalse(m_no_tok.is_creator)
            self.assertEqual(m_no_tok.source, "web")

            # Wrong token -> downgraded
            await _run_ws_session(
                origin="http://127.0.0.1:7860",
                client_host="127.0.0.1",
                query_string="token=wrong",
                incoming_json=[
                    {"type": "user_message", "user": "Spoofer", "text": "bad token", "source": "mic", "is_creator": True}
                ],
            )
            m_bad_tok = await run.orchestrator.chat.get_next_message()
            self.assertFalse(m_bad_tok.is_creator)
            self.assertEqual(m_bad_tok.source, "web")

            # Valid token + loopback -> creator allowed
            await _run_ws_session(
                origin="http://127.0.0.1:7860",
                client_host="127.0.0.1",
                query_string="token=top-secret-token",
                incoming_json=[
                    {"type": "user_message", "user": "Host", "text": "valid token", "source": "creator", "is_creator": True}
                ],
            )
            m_ok = await run.orchestrator.chat.get_next_message()
            self.assertTrue(m_ok.is_creator)
            self.assertEqual(m_ok.source, "creator")

    async def test_ws_loopback_without_configured_token_retains_creator(self):
        run.config_mgr.settings["security"] = {"creator_token": "", "allowed_origins": []}
        env_patch = {"MAYBEAI_CREATOR_TOKEN": ""}
        with patch.dict(os.environ, env_patch, clear=False):
            await _run_ws_session(
                origin="http://localhost:7860",
                client_host="127.0.0.1",
                incoming_json=[
                    {"type": "user_message", "user": "Host", "text": "local host", "source": "creator"}
                ],
            )
        msg = await run.orchestrator.chat.get_next_message()
        self.assertTrue(msg.is_creator)
        self.assertEqual(msg.source, "creator")


if __name__ == "__main__":
    unittest.main()
