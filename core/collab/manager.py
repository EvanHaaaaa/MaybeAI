import asyncio
import inspect
import os
import time
import uuid
from collections import deque
from typing import Any, Awaitable, Callable, Deque, Dict, Optional, Tuple

import aiohttp

from core.collab.protocol import CollabEnvelope


VALID_FLOOR_STATES: Tuple[str, ...] = (
    "idle",
    "speaking",
    "yielding",
    "listening",
    "cooldown",
)


class CollabManager:
    """
    Manages AI-to-AI VTuber collaboration sessions over WebSocket:
    - Turn-taking floor state machine ("idle", "speaking", "yielding", "listening", "cooldown")
    - Anti-loop protection via `max_collab_turns` and `turn_cooldown_sec`
    - Outbound WS client (`connect_peer` / `disconnect_peer`)
    - Inbound envelope handler (`handle_incoming_envelope`) for `/ws/collab`
    - Emits `collab.message` and `collab.state` on EventBus
    """

    def __init__(
        self,
        settings: Optional[Dict[str, Any]] = None,
        event_bus: Optional[Any] = None,
        self_id: str = "eve-maybe",
        self_name: str = "EveMaybe",
        allow_unauthenticated_loopback: bool = True,
    ):
        self.event_bus = event_bus
        self.self_id = self_id
        self.self_name = self_name
        self.allow_unauthenticated_loopback = allow_unauthenticated_loopback

        self.enabled: bool = False
        self.peer_name: str = "NeuroPeer"
        self.peer_ws_url: str = ""
        self.shared_secret: str = ""
        self.max_collab_turns: int = 6
        self.turn_cooldown_sec: float = 2.5

        self.floor_state: str = "idle"
        self.turn_count: int = 0
        self.last_turn_timestamp: float = 0.0
        self.cooldown_until: float = 0.0

        self.peer_connected: bool = False
        self.connected_peer: Optional[str] = None
        self.history: Deque[Dict[str, Any]] = deque(maxlen=50)

        self._http_session: Optional[aiohttp.ClientSession] = None
        self._ws_client: Optional[aiohttp.ClientWebSocketResponse] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._inbound_send_cb: Optional[Callable[[Dict[str, Any]], Awaitable[Any]]] = None
        self._inbound_senders: Dict[str, Callable[[Dict[str, Any]], Awaitable[Any]]] = {}
        self._on_reply_needed: Optional[Callable[[CollabEnvelope], Any]] = None
        self._lock = asyncio.Lock()

        self.update_config(settings or {})

    @staticmethod
    def _extract_collab_cfg(settings: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(settings, dict):
            return {}
        if "collab" in settings and isinstance(settings["collab"], dict):
            return settings["collab"]
        return settings

    def update_config(self, settings: Dict[str, Any]) -> None:
        cfg = self._extract_collab_cfg(settings)
        if not cfg:
            env_secret = os.getenv("MAYBEAI_COLLAB_SECRET", "").strip()
            if env_secret and not self.shared_secret:
                self.shared_secret = env_secret
            return

        if "enabled" in cfg:
            self.enabled = bool(cfg.get("enabled", False))
        if "peer_name" in cfg:
            self.peer_name = str(cfg.get("peer_name") or "NeuroPeer").strip() or "NeuroPeer"
        if "peer_ws_url" in cfg:
            self.peer_ws_url = str(cfg.get("peer_ws_url") or "").strip()
        if "shared_secret" in cfg:
            raw_secret = str(cfg.get("shared_secret") or "")
            if raw_secret != "********":
                self.shared_secret = raw_secret
        if not self.shared_secret:
            env_secret = os.getenv("MAYBEAI_COLLAB_SECRET", "").strip()
            if env_secret:
                self.shared_secret = env_secret
        if "max_collab_turns" in cfg:
            self.max_collab_turns = max(1, int(cfg.get("max_collab_turns", 6) or 6))
        if "turn_cooldown_sec" in cfg:
            self.turn_cooldown_sec = max(0.0, float(cfg.get("turn_cooldown_sec", 2.5)))

    def set_reply_callback(self, callback: Optional[Callable[[CollabEnvelope], Any]]) -> None:
        self._on_reply_needed = callback

    def register_peer_sender(
        self,
        send_cb: Callable[[Dict[str, Any]], Awaitable[Any]],
        peer_name: Optional[str] = None,
        conn_id: Optional[str] = None,
    ) -> str:
        """Registers an inbound `/ws/collab` peer sender callback under a unique connection ID."""
        sender_id = conn_id or uuid.uuid4().hex
        self._inbound_senders[sender_id] = send_cb
        self._inbound_send_cb = send_cb
        self.peer_connected = True
        if peer_name:
            self.connected_peer = peer_name
        return sender_id

    def unregister_peer_sender(self, conn_id: str) -> None:
        """Removes a specific inbound `/ws/collab` peer sender callback without clearing other peers."""
        self._inbound_senders.pop(conn_id, None)
        if self._inbound_senders:
            self._inbound_send_cb = next(reversed(self._inbound_senders.values()))
            self.peer_connected = True
        else:
            self._inbound_send_cb = None
            has_outbound = self._ws_client is not None and not self._ws_client.closed
            if not has_outbound:
                self.peer_connected = False
                self.connected_peer = None

    def set_peer_sender(self, send_cb: Optional[Callable[[Dict[str, Any]], Awaitable[Any]]], peer_name: Optional[str] = None) -> None:
        """Registers or clears inbound `/ws/collab` peer sender callbacks."""
        if send_cb is None:
            self._inbound_senders.clear()
            self._inbound_send_cb = None
            has_outbound = self._ws_client is not None and not self._ws_client.closed
            if not has_outbound:
                self.peer_connected = False
                self.connected_peer = None
        else:
            self.register_peer_sender(send_cb, peer_name=peer_name)

    async def _emit(self, event_name: str, payload: Dict[str, Any]) -> None:
        if self.event_bus is None:
            return
        try:
            await self.event_bus.publish(event_name, payload)
        except Exception as exc:
            print(f"[CollabManager] EventBus publish error for '{event_name}': {exc}")

    def _refresh_cooldown(self) -> None:
        """Exits time-based cooldown once `turn_cooldown_sec` elapses, unless turn limit is exhausted."""
        if self.floor_state == "cooldown" and self.turn_count < self.max_collab_turns:
            if time.monotonic() >= self.cooldown_until:
                self.floor_state = "idle"

    async def _set_floor_state(self, new_state: str, reason: str = "") -> None:
        if new_state not in VALID_FLOOR_STATES:
            raise ValueError(f"Invalid floor state '{new_state}'")
        self.floor_state = new_state
        await self._emit(
            "collab.state",
            {
                "floor_state": self.floor_state,
                "turn_count": self.turn_count,
                "max_collab_turns": self.max_collab_turns,
                "turn_cooldown_sec": self.turn_cooldown_sec,
                "peer_name": self.connected_peer or self.peer_name,
                "peer_connected": self.peer_connected,
                "turns_exhausted": self.turn_count >= self.max_collab_turns,
                "reason": reason,
            },
        )

    def _build_envelope(
        self,
        event_type: str,
        speech: str = "",
        emotion: str = "neutral",
        topic: str = "",
        payload: Optional[Dict[str, Any]] = None,
        turn_index: Optional[int] = None,
    ) -> CollabEnvelope:
        env = CollabEnvelope(
            sender_id=self.self_id,
            sender_name=self.self_name,
            event_type=event_type,
            speech=speech,
            emotion=emotion,
            topic=topic,
            payload=dict(payload or {}),
            turn_index=self.turn_count if turn_index is None else turn_index,
        )
        env.sign(self.shared_secret)
        return env

    async def _send_envelope(self, envelope: CollabEnvelope) -> bool:
        """Sends an envelope over the active outbound WS client or inbound `/ws/collab` sender."""
        data = envelope.to_dict()
        sent = False
        if self._ws_client is not None and not self._ws_client.closed:
            try:
                await self._ws_client.send_json(data)
                sent = True
            except Exception as exc:
                print(f"[CollabManager] Outbound WS send failed: {exc}")
                self.peer_connected = False
        elif self._inbound_senders:
            for sender_id, cb in list(self._inbound_senders.items()):
                try:
                    res = cb(data)
                    if inspect.isawaitable(res):
                        await res
                    sent = True
                except Exception as exc:
                    print(f"[CollabManager] Inbound peer send failed ({sender_id}): {exc}")
        elif self._inbound_send_cb is not None:
            try:
                res = self._inbound_send_cb(data)
                if inspect.isawaitable(res):
                    await res
                sent = True
            except Exception as exc:
                print(f"[CollabManager] Inbound peer send failed: {exc}")
        return sent

    async def connect_peer(self, ws_url: Optional[str] = None, peer_name: Optional[str] = None) -> bool:
        """Connects as an outbound WebSocket client to a peer VTuber's `/ws/collab` endpoint."""
        target_url = (ws_url or self.peer_ws_url).strip()
        target_peer = (peer_name or self.peer_name).strip() or "NeuroPeer"
        if not target_url:
            return False

        await self.disconnect_peer()
        self.peer_ws_url = target_url
        self.peer_name = target_peer

        try:
            self._http_session = aiohttp.ClientSession()
            self._ws_client = await self._http_session.ws_connect(target_url, heartbeat=30.0)
            self.peer_connected = True
            self.connected_peer = target_peer

            hello_env = self._build_envelope(
                event_type="hello",
                speech=f"Halo {target_peer}! Eve siap collab.",
                emotion="happy",
                payload={"peer_name": target_peer},
            )
            await self._send_envelope(hello_env)
            self._receive_task = asyncio.create_task(self._receive_loop())
            await self._set_floor_state("idle", reason="peer_connected")
            return True
        except Exception as exc:
            print(f"[CollabManager] Failed to connect to peer '{target_url}': {exc}")
            await self.disconnect_peer()
            return False

    async def _receive_loop(self) -> None:
        ws = self._ws_client
        if ws is None:
            return
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        raw = msg.json()
                    except Exception:
                        continue
                    await self.handle_incoming_envelope(
                        raw,
                        on_reply_needed=self._on_reply_needed,
                        is_loopback=self._is_loopback_url(self.peer_ws_url),
                    )
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[CollabManager] Peer receive loop error: {exc}")
        finally:
            self.peer_connected = False
            self.connected_peer = None
            await self._set_floor_state("idle", reason="peer_disconnected")

    @staticmethod
    def _is_loopback_url(url: str) -> bool:
        lower = (url or "").lower()
        return any(host in lower for host in ("127.0.0.1", "localhost", "::1"))

    async def disconnect_peer(self) -> None:
        """Closes any active outbound peer WebSocket connection cleanly."""
        if self._ws_client is not None and not self._ws_client.closed:
            try:
                bye_env = self._build_envelope(event_type="bye", speech="", emotion="neutral")
                await self._ws_client.send_json(bye_env.to_dict())
            except Exception:
                pass
            try:
                await self._ws_client.close()
            except Exception:
                pass

        if self._receive_task is not None and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except (asyncio.CancelledError, Exception):
                pass
        self._receive_task = None
        self._ws_client = None

        if self._http_session is not None and not self._http_session.closed:
            try:
                await self._http_session.close()
            except Exception:
                pass
        self._http_session = None

        was_connected = self.peer_connected
        self.peer_connected = False
        self.connected_peer = None
        if was_connected:
            await self._set_floor_state("idle", reason="disconnected")

    async def initiate_prompt(self, topic_or_text: str) -> Dict[str, Any]:
        """Starts or nudges a collaborative exchange with the given topic or opening line."""
        text = (topic_or_text or "").strip()
        if not text:
            return {"sent": False, "error": "Empty prompt text."}
        return await self.send_utterance(
            speech=text,
            emotion="happy",
            yield_turn=True,
            topic=text,
        )

    # Alias requested for compatibility
    initiate_Prompt = initiate_prompt

    async def send_utterance(
        self,
        speech: str,
        emotion: str = "neutral",
        yield_turn: bool = True,
        topic: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Sends a collaborative speech turn, enforcing floor state, max turns, and cooldown."""
        async with self._lock:
            self._refresh_cooldown()
            if self.turn_count >= self.max_collab_turns:
                self.cooldown_until = time.monotonic() + self.turn_cooldown_sec
                await self._set_floor_state("cooldown", reason="max_collab_turns_reached")
                return {
                    "sent": False,
                    "reason": "max_collab_turns_reached",
                    "floor_state": self.floor_state,
                    "turn_count": self.turn_count,
                }
            if self.floor_state == "cooldown" and time.monotonic() < self.cooldown_until:
                return {
                    "sent": False,
                    "reason": "turn_cooldown_active",
                    "floor_state": self.floor_state,
                    "turn_count": self.turn_count,
                }

            await self._set_floor_state("speaking", reason="outbound_utterance")
            self.turn_count += 1
            self.last_turn_timestamp = time.time()

            env = self._build_envelope(
                event_type="turn_utterance",
                speech=speech,
                emotion=emotion,
                topic=topic,
                payload=payload,
                turn_index=self.turn_count,
            )
            delivered = await self._send_envelope(env)
            record = {"direction": "outbound", **env.to_dict()}
            self.history.append(record)
            await self._emit("collab.message", record)

            if yield_turn:
                if self.turn_count >= self.max_collab_turns:
                    self.cooldown_until = time.monotonic() + self.turn_cooldown_sec
                    await self._set_floor_state("cooldown", reason="max_collab_turns_reached")
                else:
                    await self._set_floor_state("yielding", reason="yielding_floor")
                    yield_env = self._build_envelope(
                        event_type="turn_yield",
                        speech="",
                        emotion=emotion,
                        topic=topic,
                        turn_index=self.turn_count,
                    )
                    await self._send_envelope(yield_env)
                    await self._set_floor_state("listening", reason="awaiting_peer")
            else:
                await self._set_floor_state("idle", reason="utterance_complete")

            return {
                "sent": True,
                "delivered": delivered,
                "envelope": env.to_dict(),
                "floor_state": self.floor_state,
                "turn_count": self.turn_count,
            }

    async def send_duet_sync(self, song_id: str, lyric_index: int, timestamp: float) -> Dict[str, Any]:
        """Broadcasts synchronized karaoke/duet timing cue to the collab peer."""
        env = self._build_envelope(
            event_type="duet_sync",
            topic=song_id,
            payload={
                "song_id": song_id,
                "lyric_index": int(lyric_index),
                "timestamp": float(timestamp),
            },
        )
        delivered = await self._send_envelope(env)
        record = {"direction": "outbound", **env.to_dict()}
        self.history.append(record)
        await self._emit("collab.message", record)
        return {"sent": True, "delivered": delivered, "envelope": env.to_dict()}

    async def send_emote_sync(self, emotion: str, action: str = "") -> Dict[str, Any]:
        """Broadcasts synchronized avatar emotion/action cue to the collab peer."""
        env = self._build_envelope(
            event_type="emote_sync",
            emotion=emotion,
            payload={"emotion": emotion, "action": action},
        )
        delivered = await self._send_envelope(env)
        record = {"direction": "outbound", **env.to_dict()}
        self.history.append(record)
        await self._emit("collab.message", record)
        return {"sent": True, "delivered": delivered, "envelope": env.to_dict()}

    async def handle_incoming_envelope(
        self,
        raw_dict: Dict[str, Any],
        on_reply_needed: Optional[Callable[[CollabEnvelope], Any]] = None,
        is_loopback: bool = True,
    ) -> Dict[str, Any]:
        """
        Validates, authenticates, and processes an inbound CollabEnvelope from a peer.
        Invokes `on_reply_needed(envelope)` only when the floor can safely pass to Eve.
        """
        try:
            env = CollabEnvelope.from_dict(raw_dict)
        except Exception as exc:
            return {"accepted": False, "error": str(exc)}

        allow_unsigned = bool(self.allow_unauthenticated_loopback and is_loopback and not self.shared_secret)
        if not env.verify(self.shared_secret, allow_unsigned=allow_unsigned):
            return {"accepted": False, "error": "Invalid or missing collab HMAC signature."}

        reply_cb = on_reply_needed if on_reply_needed is not None else self._on_reply_needed
        trigger_reply = False
        reply_reason = "no_reply_needed"

        async with self._lock:
            self._refresh_cooldown()
            record = {"direction": "inbound", **env.to_dict()}
            self.history.append(record)
            await self._emit("collab.message", record)

            if env.event_type == "hello":
                self.peer_connected = True
                self.connected_peer = env.sender_name or env.sender_id or self.peer_name
                await self._set_floor_state("idle", reason="peer_hello")
            elif env.event_type == "bye":
                self.peer_connected = False
                self.connected_peer = None
                await self._set_floor_state("idle", reason="peer_bye")
            elif env.event_type == "turn_yield":
                if self.turn_count >= self.max_collab_turns:
                    self.cooldown_until = time.monotonic() + self.turn_cooldown_sec
                    await self._set_floor_state("cooldown", reason="max_collab_turns_reached")
                elif self.floor_state == "listening":
                    await self._set_floor_state("idle", reason="peer_yielded")
            elif env.event_type == "turn_utterance":
                self.peer_connected = True
                if env.sender_name or env.sender_id:
                    self.connected_peer = env.sender_name or env.sender_id

                # Prevent talking over self or looping past max_collab_turns
                if self.floor_state == "speaking":
                    reply_reason = "already_speaking"
                elif self.floor_state == "cooldown" and time.monotonic() < self.cooldown_until:
                    reply_reason = "turn_cooldown_active"
                elif self.turn_count >= self.max_collab_turns:
                    self.cooldown_until = time.monotonic() + self.turn_cooldown_sec
                    await self._set_floor_state("cooldown", reason="max_collab_turns_reached")
                    reply_reason = "max_collab_turns_reached"
                else:
                    self.turn_count += 1
                    self.last_turn_timestamp = time.time()
                    if self.turn_count >= self.max_collab_turns:
                        self.cooldown_until = time.monotonic() + self.turn_cooldown_sec
                        await self._set_floor_state("cooldown", reason="max_collab_turns_reached")
                        reply_reason = "max_collab_turns_reached"
                    else:
                        await self._set_floor_state("idle", reason="peer_utterance_received")
                        trigger_reply = reply_cb is not None
                        reply_reason = "floor_acquired"

        if trigger_reply and reply_cb is not None:
            try:
                res = reply_cb(env)
                if inspect.isawaitable(res):
                    await res
            except Exception as exc:
                print(f"[CollabManager] Reply callback error: {exc}")

        return {
            "accepted": True,
            "event_type": env.event_type,
            "reply_triggered": trigger_reply,
            "reason": reply_reason,
            "floor_state": self.floor_state,
            "turn_count": self.turn_count,
        }

    async def reset_turns(self) -> Dict[str, Any]:
        """Resets the collab turn counter and exits cooldown back to 'idle'."""
        async with self._lock:
            self.turn_count = 0
            self.cooldown_until = 0.0
            await self._set_floor_state("idle", reason="turns_reset")
        return self.get_status()

    async def shutdown(self) -> None:
        await self.disconnect_peer()
        self._inbound_senders.clear()
        self._inbound_send_cb = None

    def get_status(self) -> Dict[str, Any]:
        self._refresh_cooldown()
        cooldown_rem = max(0.0, round(self.cooldown_until - time.monotonic(), 2)) if self.floor_state == "cooldown" else 0.0
        return {
            "enabled": self.enabled,
            "peer_name": self.connected_peer or self.peer_name,
            "peer_ws_url": self.peer_ws_url,
            "peer_connected": self.peer_connected,
            "floor_state": self.floor_state,
            "turn_count": self.turn_count,
            "max_collab_turns": self.max_collab_turns,
            "turn_cooldown_sec": self.turn_cooldown_sec,
            "cooldown_remaining_sec": cooldown_rem,
            "turns_exhausted": self.turn_count >= self.max_collab_turns,
            "secret_configured": bool(self.shared_secret),
            "history_count": len(self.history),
            "recent_messages": list(self.history)[-10:],
        }
