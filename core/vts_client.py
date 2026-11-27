import json
import asyncio
import os
import time
from pathlib import Path
import websockets
from typing import Optional, Dict, Any, List


def _resolve_vts_token_path(token_path: Optional[str] = None) -> Path:
    if token_path:
        return Path(token_path)
    data_root = os.getenv("MAYBEAI_DATA_DIR", "").strip()
    if data_root:
        return Path(data_root) / "vts_token.json"
    return Path("data") / "vts_token.json"


class VTSClient:
    """
    Client for VTube Studio WebSocket API.
    Controls Live2D mouth movements, head gestures, and facial expressions.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8001,
        plugin_name: str = "MaybeAI-VTuber",
        token_path: Optional[str] = None,
        auto_reconnect: bool = False,
        reconnect_base_delay: float = 1.0,
        reconnect_max_delay: float = 60.0,
    ):
        self.host = host
        self.port = port
        self.uri = f"ws://{host}:{port}"
        self.plugin_name = plugin_name
        self.token_path: Path = _resolve_vts_token_path(token_path)
        self.auto_reconnect: bool = bool(auto_reconnect)
        self.reconnect_base_delay: float = max(0.01, float(reconnect_base_delay))
        self.reconnect_max_delay: float = max(self.reconnect_base_delay, float(reconnect_max_delay))
        self.reconnect_attempts: int = 0
        self._reconnect_task: Optional[asyncio.Task] = None
        self._closing: bool = False

        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.auth_token: Optional[str] = None
        self.connected = False
        self.is_running = False
        self.last_error: Optional[str] = None
        self.last_connected_time: Optional[float] = None
        self._rig_state: Dict[str, float] = {
            "FaceAngleX": 0.0,
            "FaceAngleY": 0.0,
            "FaceAngleZ": 0.0,
            "EyeOpenLeft": 1.0,
            "EyeOpenRight": 1.0,
            "BrowLeftY": 0.0,
            "BrowRightY": 0.0,
            "MouthForm": 0.0,
            "MouthOpen": 0.0,
        }
        self._load_token()

    def _load_token(self) -> Optional[str]:
        """Loads persisted VTS authentication token from disk if available."""
        try:
            if not self.token_path.exists():
                return None
            raw = self.token_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                return None
            stored_plugin = data.get("plugin_name")
            if stored_plugin and stored_plugin != self.plugin_name:
                return None
            tok = data.get("authenticationToken") or data.get("token")
            if isinstance(tok, str) and tok.strip():
                self.auth_token = tok.strip()
                return self.auth_token
        except Exception:
            pass
        return None

    def _save_token(self, token: Optional[str]) -> None:
        """Persists the VTS authentication token to disk."""
        if not token:
            return
        try:
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "authenticationToken": token,
                "plugin_name": self.plugin_name,
                "host": self.host,
                "port": self.port,
                "updated_at": time.time(),
            }
            self.token_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"[VTS] Failed to persist token to {self.token_path}: {exc}")

    def _clear_saved_token(self) -> None:
        """Removes a stale/rejected persisted VTS token from disk."""
        try:
            if self.token_path.exists():
                self.token_path.unlink()
        except Exception:
            pass

    def start_auto_reconnect(self) -> Optional[asyncio.Task]:
        """Starts the exponential-backoff auto-reconnect loop if not already running."""
        if self._closing or self.connected:
            return None
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return self._reconnect_task
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        self._reconnect_task = loop.create_task(self.auto_reconnect_loop())
        return self._reconnect_task

    async def auto_reconnect_loop(self) -> bool:
        """Reconnects to VTube Studio with exponential backoff until connected or stopped."""
        delay = self.reconnect_base_delay
        while not self._closing and not self.connected:
            self.reconnect_attempts += 1
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return False
            if self._closing or self.connected:
                break
            ok = await self.connect(_from_reconnect_loop=True)
            if ok:
                self.reconnect_attempts = 0
                return True
            delay = min(self.reconnect_max_delay, delay * 2.0)
        return self.connected

    async def disconnect(self, _stop_auto_reconnect: bool = True):
        if _stop_auto_reconnect:
            self._closing = True
            if self._reconnect_task is not None and not self._reconnect_task.done():
                self._reconnect_task.cancel()
                try:
                    await self._reconnect_task
                except asyncio.CancelledError:
                    pass
            self._reconnect_task = None

        self.connected = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

    async def close(self):
        """Alias for disconnect() to cleanly stop auto-reconnect and close WebSocket."""
        await self.disconnect(_stop_auto_reconnect=True)

    async def reconnect(self, host: Optional[str] = None, port: Optional[int] = None) -> bool:
        await self.disconnect(_stop_auto_reconnect=False)
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
            "has_token": bool(self.auth_token),
            "auto_reconnect": self.auto_reconnect,
            "reconnect_attempts": self.reconnect_attempts,
            "last_connected_time": self.last_connected_time,
            "last_error": self.last_error
        }

    async def connect(self, _from_reconnect_loop: bool = False) -> bool:
        self._closing = False
        try:
            self.ws = await websockets.connect(self.uri, open_timeout=3.0)
            self.connected = True
            self.last_connected_time = time.time()
            self.last_error = None
            self.reconnect_attempts = 0
            print(f"[VTS] Connected to VTube Studio at {self.uri}")
            await self._authenticate()
            return True
        except Exception as e:
            self.connected = False
            self.last_error = str(e)
            print(f"[VTS] VTube Studio not detected ({e}). Running in standalone/virtual avatar mode.")
            if self.auto_reconnect and not self._closing and not _from_reconnect_loop:
                self.start_auto_reconnect()
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

        # Try cached/persisted token first
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
                self._save_token(self.auth_token)
                print("[VTS] Authenticated successfully with VTube Studio!")
                return
            # Token was rejected/revoked; clear and request a fresh token
            self.auth_token = None
            self._clear_saved_token()

        # Request new token
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

        # Authenticate session with newly acquired token
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
                self._save_token(self.auth_token)
                print("[VTS] Authenticated successfully with VTube Studio!")

    async def set_parameter(self, parameter_id: str, value: float, weight: float = 1.0):
        """
        Injects a parameter like 'MouthOpen', 'FaceAngleX', 'EyeBlink' into VTS.
        """
        self._rig_state[parameter_id] = float(value)
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
            if self.auto_reconnect and not self._closing:
                self.start_auto_reconnect()
            if self.auto_reconnect and not self._closing:
                self.start_auto_reconnect()

    async def set_parameters(self, params: Dict[str, float], weight: float = 1.0):
        """
        Injects multiple Live2D parameters in a single batch InjectParameterDataRequest.
        """
        if not params:
            return

        for param_id, value in params.items():
            self._rig_state[str(param_id)] = float(value)

        if not self.connected or not self.ws:
            return

        parameter_values = [
            {
                "id": str(param_id),
                "value": float(value),
                "weight": float(weight),
            }
            for param_id, value in params.items()
        ]
        payload = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": "params_batch",
            "messageType": "InjectParameterDataRequest",
            "data": {
                "faceFound": True,
                "mode": "set",
                "parameterValues": parameter_values,
            },
        }
        try:
            await self.ws.send(json.dumps(payload))
        except Exception:
            self.connected = False
            if self.auto_reconnect and not self._closing:
                self.start_auto_reconnect()
            if self.auto_reconnect and not self._closing:
                self.start_auto_reconnect()

    def get_rig_state(self) -> Dict[str, float]:
        """Returns a snapshot of the last applied Live2D rig parameters."""
        return dict(self._rig_state)

    async def apply_mood_rig(
        self,
        emotion: str,
        mood_dims: Optional[Dict[str, float]] = None,
        singing: bool = False,
    ) -> Dict[str, float]:
        """
        Computes and applies multi-parameter Live2D rig targets from emotion,
        mood dimensions, and singing state.
        """
        emo = (emotion or "neutral").lower().strip()
        presets: Dict[str, Dict[str, float]] = {
            "happy": {
                "FaceAngleX": 3.0, "FaceAngleY": 5.0, "FaceAngleZ": 6.0,
                "EyeOpenLeft": 1.05, "EyeOpenRight": 1.05,
                "BrowLeftY": 0.45, "BrowRightY": 0.45, "MouthForm": 0.85,
            },
            "excited": {
                "FaceAngleX": 0.0, "FaceAngleY": 8.0, "FaceAngleZ": 8.0,
                "EyeOpenLeft": 1.15, "EyeOpenRight": 1.15,
                "BrowLeftY": 0.7, "BrowRightY": 0.7, "MouthForm": 1.0,
            },
            "smug": {
                "FaceAngleX": -5.0, "FaceAngleY": 3.0, "FaceAngleZ": -8.0,
                "EyeOpenLeft": 0.72, "EyeOpenRight": 0.82,
                "BrowLeftY": 0.25, "BrowRightY": -0.15, "MouthForm": 0.65,
            },
            "angry": {
                "FaceAngleX": 0.0, "FaceAngleY": -8.0, "FaceAngleZ": -3.0,
                "EyeOpenLeft": 0.9, "EyeOpenRight": 0.9,
                "BrowLeftY": -0.75, "BrowRightY": -0.75, "MouthForm": -0.7,
            },
            "annoyed": {
                "FaceAngleX": -4.0, "FaceAngleY": -5.0, "FaceAngleZ": -4.0,
                "EyeOpenLeft": 0.75, "EyeOpenRight": 0.75,
                "BrowLeftY": -0.45, "BrowRightY": -0.45, "MouthForm": -0.45,
            },
            "sad": {
                "FaceAngleX": 0.0, "FaceAngleY": -10.0, "FaceAngleZ": 5.0,
                "EyeOpenLeft": 0.6, "EyeOpenRight": 0.6,
                "BrowLeftY": -0.4, "BrowRightY": -0.4, "MouthForm": -0.65,
            },
            "blush": {
                "FaceAngleX": 6.0, "FaceAngleY": 4.0, "FaceAngleZ": 9.0,
                "EyeOpenLeft": 0.82, "EyeOpenRight": 0.82,
                "BrowLeftY": 0.2, "BrowRightY": 0.2, "MouthForm": 0.5,
            },
            "confused": {
                "FaceAngleX": 4.0, "FaceAngleY": 2.0, "FaceAngleZ": 14.0,
                "EyeOpenLeft": 1.0, "EyeOpenRight": 0.78,
                "BrowLeftY": 0.45, "BrowRightY": -0.2, "MouthForm": -0.1,
            },
            "thinking": {
                "FaceAngleX": 6.0, "FaceAngleY": 4.0, "FaceAngleZ": 10.0,
                "EyeOpenLeft": 0.85, "EyeOpenRight": 0.85,
                "BrowLeftY": 0.2, "BrowRightY": -0.1, "MouthForm": 0.0,
            },
            "neutral": {
                "FaceAngleX": 0.0, "FaceAngleY": 0.0, "FaceAngleZ": 0.0,
                "EyeOpenLeft": 1.0, "EyeOpenRight": 1.0,
                "BrowLeftY": 0.0, "BrowRightY": 0.0, "MouthForm": 0.1,
            },
        }
        rig = dict(presets.get(emo, presets["neutral"]))

        if mood_dims:
            energy = float(mood_dims.get("energy", mood_dims.get("arousal", 0.5)))
            positivity = float(mood_dims.get("positivity", mood_dims.get("valence", 0.5)))
            playfulness = float(mood_dims.get("playfulness", 0.5))
            rig["FaceAngleY"] += (energy - 0.5) * 8.0
            rig["FaceAngleZ"] += (playfulness - 0.5) * 8.0
            rig["EyeOpenLeft"] += (energy - 0.5) * 0.2
            rig["EyeOpenRight"] += (energy - 0.5) * 0.2
            rig["BrowLeftY"] += (positivity - 0.5) * 0.3
            rig["BrowRightY"] += (positivity - 0.5) * 0.3
            rig["MouthForm"] += (positivity - 0.5) * 0.5

        if singing:
            rig["FaceAngleY"] += 4.0
            rig["FaceAngleZ"] += 5.0
            rig["EyeOpenLeft"] = max(rig["EyeOpenLeft"], 1.05)
            rig["EyeOpenRight"] = max(rig["EyeOpenRight"], 1.05)
            rig["BrowLeftY"] += 0.2
            rig["BrowRightY"] += 0.2
            rig["MouthForm"] = max(rig["MouthForm"], 0.45)

        def _clamp(val: float, lo: float, hi: float) -> float:
            return round(max(lo, min(hi, float(val))), 3)

        rig["FaceAngleX"] = _clamp(rig["FaceAngleX"], -30.0, 30.0)
        rig["FaceAngleY"] = _clamp(rig["FaceAngleY"], -30.0, 30.0)
        rig["FaceAngleZ"] = _clamp(rig["FaceAngleZ"], -30.0, 30.0)
        rig["EyeOpenLeft"] = _clamp(rig["EyeOpenLeft"], 0.0, 1.2)
        rig["EyeOpenRight"] = _clamp(rig["EyeOpenRight"], 0.0, 1.2)
        rig["BrowLeftY"] = _clamp(rig["BrowLeftY"], -1.0, 1.0)
        rig["BrowRightY"] = _clamp(rig["BrowRightY"], -1.0, 1.0)
        rig["MouthForm"] = _clamp(rig["MouthForm"], -1.0, 1.0)

        await self.set_parameters(rig)
        return rig

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
