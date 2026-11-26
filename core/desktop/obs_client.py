import asyncio
from typing import Any, Dict, List, Optional


DEFAULT_SCENE_MAP: Dict[str, str] = {
    "social": "Just Chatting",
    "minecraft": "Minecraft",
    "performance": "Karaoke Stage",
    "chess": "Chess",
    "collab": "Collab Split-Screen",
}


def _import_req_client() -> Optional[Any]:
    """Lazily imports obsws_python.ReqClient without failing if not installed."""
    try:
        import obsws_python as obs  # type: ignore
        return getattr(obs, "ReqClient", None)
    except ImportError:
        return None


class OBSWebSocketClient:
    """
    Async-friendly wrapper around obsws-python (obs-websocket v5) for autonomous
    multi-scene OBS showrunning, streaming control, replay buffer, and source visibility.
    Works cleanly with zero errors when obsws-python is not installed or OBS is offline.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 4455,
        password: str = "",
        enabled: bool = False,
        scene_map: Optional[Dict[str, str]] = None,
    ):
        self.host = str(host or "localhost").strip()
        self.port = int(port)
        self.password = password or ""
        self.enabled = bool(enabled)

        self.scene_map: Dict[str, str] = dict(DEFAULT_SCENE_MAP)
        if scene_map:
            for key, val in scene_map.items():
                if val:
                    self.scene_map[str(key).strip().lower()] = str(val).strip()

        self._client: Optional[Any] = None
        self.is_connected: bool = False
        self.current_scene: Optional[str] = None
        self.is_streaming: bool = False
        self.replay_buffer_active: bool = False
        self.available_scenes: List[str] = []
        self.last_error: Optional[str] = None

    def resolve_scene(self, scene_or_domain: str) -> str:
        """Resolves a domain key via scene_map, or returns the explicit scene name."""
        key = str(scene_or_domain).strip().lower()
        return self.scene_map.get(key, scene_or_domain)

    async def connect(self) -> bool:
        """Connects to OBS Studio via obs-websocket v5 without blocking the event loop."""
        if not self.enabled:
            self.is_connected = False
            self._client = None
            return False

        req_client_cls = _import_req_client()
        if req_client_cls is None:
            self.is_connected = False
            self._client = None
            self.last_error = "obsws-python is not installed"
            return False

        try:
            client = await asyncio.to_thread(
                req_client_cls,
                host=self.host,
                port=self.port,
                password=self.password,
            )
            self._client = client
            self.is_connected = True
            self.last_error = None
            await self._sync_initial_state()
            return True
        except Exception as exc:
            self._client = None
            self.is_connected = False
            self.last_error = str(exc)
            return False

    async def _sync_initial_state(self) -> None:
        """Best-effort sync of current scene, scene list, and stream status after connect."""
        if not self._client:
            return
        try:
            if hasattr(self._client, "get_current_program_scene"):
                scene_res = await asyncio.to_thread(self._client.get_current_program_scene)
                scene_name = getattr(scene_res, "current_program_scene_name", None) or getattr(scene_res, "scene_name", None)
                if scene_name:
                    self.current_scene = str(scene_name)
        except Exception:
            pass

        try:
            if hasattr(self._client, "get_scene_list"):
                list_res = await asyncio.to_thread(self._client.get_scene_list)
                scenes = getattr(list_res, "scenes", None) or []
                parsed = [
                    str(s.get("sceneName"))
                    for s in scenes
                    if isinstance(s, dict) and s.get("sceneName")
                ]
                if parsed:
                    self.available_scenes = parsed
        except Exception:
            pass

        try:
            if hasattr(self._client, "get_stream_status"):
                stream_res = await asyncio.to_thread(self._client.get_stream_status)
                if hasattr(stream_res, "output_active"):
                    self.is_streaming = bool(stream_res.output_active)
        except Exception:
            pass

    async def disconnect(self) -> bool:
        """Disconnects cleanly from OBS Studio."""
        client = self._client
        self._client = None
        self.is_connected = False
        if client is not None:
            try:
                if hasattr(client, "disconnect"):
                    await asyncio.to_thread(client.disconnect)
                elif hasattr(client, "base_client") and hasattr(client.base_client, "ws"):
                    await asyncio.to_thread(client.base_client.ws.close)
            except Exception:
                pass
        return True

    async def switch_scene(self, scene_name: str, reason: str = "") -> Dict[str, Any]:
        """Switches the active OBS program scene."""
        target = self.resolve_scene(scene_name)
        if not self._client or not self.is_connected:
            return {
                "success": False,
                "scene": target,
                "reason": reason,
                "connected": False,
                "error": self.last_error or "OBS is not connected",
            }
        try:
            await asyncio.to_thread(self._client.set_current_program_scene, target)
            self.current_scene = target
            self.last_error = None
            return {
                "success": True,
                "scene": target,
                "reason": reason,
                "connected": True,
            }
        except Exception as exc:
            self.last_error = str(exc)
            self.is_connected = False
            self._client = None
            return {
                "success": False,
                "scene": target,
                "reason": reason,
                "connected": self.is_connected,
                "error": str(exc),
            }

    async def toggle_streaming(self, target_state: Optional[bool] = None) -> Dict[str, Any]:
        """Starts, stops, or toggles OBS live streaming."""
        if not self._client or not self.is_connected:
            return {
                "success": False,
                "is_streaming": self.is_streaming,
                "connected": False,
                "error": self.last_error or "OBS is not connected",
            }
        try:
            if target_state is True:
                await asyncio.to_thread(self._client.start_stream)
                self.is_streaming = True
            elif target_state is False:
                await asyncio.to_thread(self._client.stop_stream)
                self.is_streaming = False
            else:
                res = await asyncio.to_thread(self._client.toggle_stream)
                if hasattr(res, "output_active"):
                    self.is_streaming = bool(res.output_active)
                else:
                    self.is_streaming = not self.is_streaming
            self.last_error = None
            return {
                "success": True,
                "is_streaming": self.is_streaming,
                "connected": True,
            }
        except Exception as exc:
            self.last_error = str(exc)
            self.is_connected = False
            self._client = None
            return {
                "success": False,
                "is_streaming": self.is_streaming,
                "connected": self.is_connected,
                "error": str(exc),
            }

    async def start_replay_buffer(self) -> Dict[str, Any]:
        """Starts the OBS replay buffer."""
        if not self._client or not self.is_connected:
            return {
                "success": False,
                "active": self.replay_buffer_active,
                "connected": False,
                "error": self.last_error or "OBS is not connected",
            }
        try:
            await asyncio.to_thread(self._client.start_replay_buffer)
            self.replay_buffer_active = True
            self.last_error = None
            return {"success": True, "active": True, "connected": True}
        except Exception as exc:
            self.last_error = str(exc)
            self.is_connected = False
            self._client = None
            return {
                "success": False,
                "active": self.replay_buffer_active,
                "connected": self.is_connected,
                "error": str(exc),
            }

    async def save_replay_buffer(self) -> Dict[str, Any]:
        """Saves the current OBS replay buffer clip."""
        if not self._client or not self.is_connected:
            return {
                "success": False,
                "connected": False,
                "error": self.last_error or "OBS is not connected",
            }
        try:
            await asyncio.to_thread(self._client.save_replay_buffer)
            self.last_error = None
            return {"success": True, "connected": True}
        except Exception as exc:
            self.last_error = str(exc)
            self.is_connected = False
            self._client = None
            return {
                "success": False,
                "connected": self.is_connected,
                "error": str(exc),
            }

    async def set_source_visibility(
        self, scene_name: str, source_name: str, visible: bool
    ) -> Dict[str, Any]:
        """Shows or hides a source item inside an OBS scene."""
        target_scene = self.resolve_scene(scene_name)
        if not self._client or not self.is_connected:
            return {
                "success": False,
                "scene": target_scene,
                "source": source_name,
                "visible": bool(visible),
                "connected": False,
                "error": self.last_error or "OBS is not connected",
            }
        try:
            item_res = await asyncio.to_thread(
                self._client.get_scene_item_id, target_scene, source_name
            )
            item_id = (
                item_res
                if isinstance(item_res, int)
                else getattr(item_res, "scene_item_id", None)
            )
            if item_id is None:
                raise ValueError(f"Scene item '{source_name}' not found in '{target_scene}'")

            await asyncio.to_thread(
                self._client.set_scene_item_enabled,
                target_scene,
                item_id,
                bool(visible),
            )
            self.last_error = None
            return {
                "success": True,
                "scene": target_scene,
                "source": source_name,
                "visible": bool(visible),
                "connected": True,
            }
        except Exception as exc:
            self.last_error = str(exc)
            self.is_connected = False
            self._client = None
            return {
                "success": False,
                "scene": target_scene,
                "source": source_name,
                "visible": bool(visible),
                "connected": self.is_connected,
                "error": str(exc),
            }

    def update_config(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        enabled: Optional[bool] = None,
        scene_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Updates runtime OBS connection and scene-map configuration."""
        if host is not None and str(host).strip():
            self.host = str(host).strip()
        if port is not None:
            self.port = int(port)
        if password is not None:
            self.password = password
        if enabled is not None:
            self.enabled = bool(enabled)
        if scene_map is not None:
            for key, val in scene_map.items():
                if val:
                    self.scene_map[str(key).strip().lower()] = str(val).strip()
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        """Returns a JSON-serializable telemetry snapshot of the OBS client."""
        return {
            "enabled": self.enabled,
            "connected": self.is_connected,
            "host": self.host,
            "port": self.port,
            "current_scene": self.current_scene,
            "is_streaming": self.is_streaming,
            "replay_buffer_active": self.replay_buffer_active,
            "scene_map": dict(self.scene_map),
            "available_scenes": list(self.available_scenes),
            "last_error": self.last_error,
        }
