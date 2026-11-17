import json
import asyncio
import websockets
from typing import Optional, Dict, Any, List

class VTSClient:
    """
    Client for VTube Studio WebSocket API.
    Controls Live2D mouth movements, head gestures, and facial expressions.
    """

    def __init__(self, host: str = "localhost", port: int = 8001, plugin_name: str = "MaybeAI-VTuber"):
        self.host = host
        self.port = port
        self.uri = f"ws://{host}:{port}"
        self.plugin_name = plugin_name
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.auth_token: Optional[str] = None
        self.connected = False
        self.is_running = False
        self.last_error: Optional[str] = None
        self.last_connected_time: Optional[float] = None

    async def disconnect(self):
        self.connected = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

    async def reconnect(self, host: Optional[str] = None, port: Optional[int] = None) -> bool:
        await self.disconnect()
        if host:
            self.host = host
        if port:
            self.port = int(port)
        self.uri = f"ws://{self.host}:{self.port}"
        return await self.connect()

    def get_status(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "host": self.host,
            "port": self.port,
            "plugin_name": self.plugin_name,
            "authenticated": bool(self.auth_token and self.connected),
            "last_connected_time": self.last_connected_time,
            "last_error": self.last_error
        }

    async def connect(self) -> bool:
        try:
            self.ws = await websockets.connect(self.uri, open_timeout=3.0)
            self.connected = True
            import time
            self.last_connected_time = time.time()
            self.last_error = None
            print(f"[VTS] Connected to VTube Studio at {self.uri}")
            await self._authenticate()
            return True
        except Exception as e:
            self.connected = False
            self.last_error = str(e)
            print(f"[VTS] VTube Studio not detected ({e}). Running in standalone/virtual avatar mode.")
            return False

    async def _authenticate(self):
        if not self.connected or not self.ws:
            return

        # Check API state
        state_req = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "state_check",
            "messageType": "APIStateRequest"
        }
        await self.ws.send(json.dumps(state_req))
        resp = json.loads(await self.ws.recv())

        # If not authenticated, request token
        if not self.auth_token:
            token_req = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "token_req",
                "messageType": "AuthenticationTokenRequest",
                "data": {
                    "pluginName": self.plugin_name,
                    "pluginDeveloper": "MaybeAI"
                }
            }
            await self.ws.send(json.dumps(token_req))
            resp = json.loads(await self.ws.recv())
            self.auth_token = resp.get("data", {}).get("authenticationToken")

        # Authenticate session
        if self.auth_token:
            auth_req = {
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": "auth_session",
                "messageType": "AuthenticationRequest",
                "data": {
                    "pluginName": self.plugin_name,
                    "pluginDeveloper": "MaybeAI",
                    "authenticationToken": self.auth_token
                }
            }
            await self.ws.send(json.dumps(auth_req))
            auth_resp = json.loads(await self.ws.recv())
            if auth_resp.get("data", {}).get("authenticated"):
                print("[VTS] Authenticated successfully with VTube Studio!")

    async def set_parameter(self, parameter_id: str, value: float, weight: float = 1.0):
        """
        Injects a parameter like 'MouthOpen', 'FaceAngleX', 'EyeBlink' into VTS.
        """
        if not self.connected or not self.ws:
            return

        payload = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": f"param_{parameter_id}",
            "messageType": "InjectParameterDataRequest",
            "data": {
                "faceFound": True,
                "mode": "set",
                "parameterValues": [
                    {
                        "id": parameter_id,
                        "value": value,
                        "weight": weight
                    }
                ]
            }
        }
        try:
            await self.ws.send(json.dumps(payload))
        except Exception:
            self.connected = False

    async def update_mouth(self, mouth_open: float):
        """
        Convenience method to set MouthOpen parameter (0.0 to 1.0).
        """
        await self.set_parameter("MouthOpen", mouth_open)

    async def trigger_expression(self, emotion: str):
        """
        Maps emotion tags to VTS parameters (blush, eyes, tilt).
        """
        if not self.connected:
            return

        emotion = emotion.lower()
        if emotion == "smug":
            await self.set_parameter("FaceAngleZ", -8.0)
            await self.set_parameter("MouthSmile", 0.9)
        elif emotion == "happy":
            await self.set_parameter("MouthSmile", 1.0)
            await self.set_parameter("EyeOpenLeft", 1.0)
            await self.set_parameter("EyeOpenRight", 1.0)
        elif emotion == "angry":
            await self.set_parameter("FaceAngleY", -10.0)
            await self.set_parameter("MouthSmile", -0.5)
        elif emotion == "blush":
            await self.set_parameter("CheekPuff", 0.8)
            await self.set_parameter("FaceAngleY", 5.0)
        elif emotion == "confused":
            await self.set_parameter("FaceAngleZ", 15.0)
        else:
            # Reset to neutral
            await self.set_parameter("FaceAngleZ", 0.0)
            await self.set_parameter("MouthSmile", 0.0)
