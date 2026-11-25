import json
import unittest
from unittest.mock import AsyncMock, patch

from core.vts_client import VTSClient


class FakeWebSocket:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []
        self.closed = False

    async def send(self, message: str):
        self.sent.append(json.loads(message))

    async def recv(self) -> str:
        return json.dumps(self.responses.pop(0))

    async def close(self):
        self.closed = True


class TestVTSClient(unittest.IsolatedAsyncioTestCase):
    async def test_connect_and_authenticate_success(self):
        fake_ws = FakeWebSocket([
            {"messageType": "APIStateResponse", "data": {"active": True}},
            {"messageType": "AuthenticationTokenResponse", "data": {"authenticationToken": "vts-tok-123"}},
            {"messageType": "AuthenticationResponse", "data": {"authenticated": True}},
        ])
        client = VTSClient(host="127.0.0.1", port=8001, plugin_name="TestPlugin")

        with patch("core.vts_client.websockets.connect", new=AsyncMock(return_value=fake_ws)) as mock_conn:
            ok = await client.connect()

        self.assertTrue(ok)
        mock_conn.assert_awaited_once_with("ws://127.0.0.1:8001", open_timeout=3.0)
        self.assertTrue(client.connected)
        self.assertEqual(client.auth_token, "vts-tok-123")
        self.assertIsNone(client.last_error)

        msg_types = [m["messageType"] for m in fake_ws.sent]
        self.assertEqual(
            msg_types,
            ["APIStateRequest", "AuthenticationTokenRequest", "AuthenticationRequest"],
        )
        status = client.get_status()
        self.assertTrue(status["connected"])
        self.assertTrue(status["authenticated"])
        self.assertEqual(status["port"], 8001)

    async def test_connect_reuses_existing_token(self):
        fake_ws = FakeWebSocket([
            {"messageType": "APIStateResponse", "data": {"active": True}},
            {"messageType": "AuthenticationResponse", "data": {"authenticated": True}},
        ])
        client = VTSClient()
        client.auth_token = "cached-token"

        with patch("core.vts_client.websockets.connect", new=AsyncMock(return_value=fake_ws)):
            ok = await client.connect()

        self.assertTrue(ok)
        msg_types = [m["messageType"] for m in fake_ws.sent]
        self.assertEqual(msg_types, ["APIStateRequest", "AuthenticationRequest"])

    async def test_connect_failure_sets_last_error(self):
        client = VTSClient()
        with patch("core.vts_client.websockets.connect", new=AsyncMock(side_effect=OSError("refused"))):
            ok = await client.connect()

        self.assertFalse(ok)
        self.assertFalse(client.connected)
        self.assertIn("refused", client.last_error)
        self.assertFalse(client.get_status()["authenticated"])

    async def test_set_parameter_mouth_expression_and_disconnect(self):
        fake_ws = FakeWebSocket([])
        client = VTSClient()
        client.ws = fake_ws
        client.connected = True

        await client.update_mouth(0.75)
        await client.trigger_expression("smug")
        await client.trigger_expression("neutral")

        param_ids = [m["data"]["parameterValues"][0]["id"] for m in fake_ws.sent]
        self.assertEqual(param_ids[0], "MouthOpen")
        self.assertEqual(fake_ws.sent[0]["data"]["parameterValues"][0]["value"], 0.75)
        self.assertIn("FaceAngleZ", param_ids)
        self.assertIn("MouthSmile", param_ids)

        await client.disconnect()
        self.assertFalse(client.connected)
        self.assertIsNone(client.ws)
        self.assertTrue(fake_ws.closed)

    async def test_set_parameter_send_error_marks_disconnected(self):
        client = VTSClient()
        client.ws = AsyncMock()
        client.ws.send = AsyncMock(side_effect=RuntimeError("socket broken"))
        client.connected = True

        await client.set_parameter("MouthOpen", 0.5)
        self.assertFalse(client.connected)

    async def test_reconnect_updates_target(self):
        fake_ws = FakeWebSocket([
            {"messageType": "APIStateResponse", "data": {}},
            {"messageType": "AuthenticationTokenResponse", "data": {"authenticationToken": "tok2"}},
            {"messageType": "AuthenticationResponse", "data": {"authenticated": True}},
        ])
        client = VTSClient()
        with patch("core.vts_client.websockets.connect", new=AsyncMock(return_value=fake_ws)):
            ok = await client.reconnect(host="127.0.0.2", port=8002)

        self.assertTrue(ok)
        self.assertEqual(client.host, "127.0.0.2")
        self.assertEqual(client.port, 8002)
        self.assertEqual(client.uri, "ws://127.0.0.2:8002")


if __name__ == "__main__":
    unittest.main()
