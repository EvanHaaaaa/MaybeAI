import asyncio
import inspect
import os
import time
import uuid
from collections import OrderedDict, deque
from typing import Any, Awaitable, Callable, Deque, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import aiohttp

from core.collab.protocol import (
    DEFAULT_COLLAB_CAPABILITIES,
    NON_UTTERANCE_EVENT_TYPES,
    PROTOCOL_VERSION,
    CollabEnvelope,
)
from core.security_net import SSRFValidationError, validate_outbound_url


VALID_FLOOR_STATES: Tuple[str, ...] = (
    "idle",
    "thinking",
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
        allow_private_peers: bool = False,
        peer_allowlist: Optional[Iterable[str]] = None,
        capabilities: Optional[Iterable[str]] = None,
        rate_limit_max_events: int = 10,
        rate_limit_window_sec: float = 5.0,
        on_duet_sync: Optional[Callable[[CollabEnvelope], Any]] = None,
        on_emote_sync: Optional[Callable[[CollabEnvelope], Any]] = None,
        on_game_move: Optional[Callable[[CollabEnvelope], Any]] = None,
    ):
        self.event_bus = event_bus
        self.self_id = self_id
        self.self_name = self_name
        self.allow_unauthenticated_loopback = allow_unauthenticated_loopback
        self.allow_private_peers: bool = bool(allow_private_peers)
        self.peer_allowlist: Optional[List[str]] = (
            [str(x).strip() for x in peer_allowlist if str(x).strip()] if peer_allowlist else None
        )
        self.capabilities: List[str] = (
            [str(c).strip() for c in capabilities if str(c).strip()]
            if capabilities is not None
            else list(DEFAULT_COLLAB_CAPABILITIES)
        )
        self.peer_capabilities: List[str] = []
        self.peer_protocol_version: str = ""
        self.rate_limit_max_events: int = max(1, int(rate_limit_max_events))
        self.rate_limit_window_sec: float = max(0.1, float(rate_limit_window_sec))
        self._rate_limit_buckets: Dict[str, Deque[float]] = {}

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
        self._on_duet_sync: Optional[Callable[[CollabEnvelope], Any]] = on_duet_sync
        self._on_emote_sync: Optional[Callable[[CollabEnvelope], Any]] = on_emote_sync
        self._on_game_move: Optional[Callable[[CollabEnvelope], Any]] = on_game_move
        self._reply_tasks: Set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self.max_timestamp_skew_sec: float = 60.0
        self._nonce_cache_maxsize: int = 1024
        self._seen_nonces: OrderedDict[Tuple[str, str], float] = OrderedDict()

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
        if "allow_private_peers" in cfg:
            self.allow_private_peers = bool(cfg.get("allow_private_peers", False))
        if "peer_allowlist" in cfg:
            raw_al = cfg.get("peer_allowlist")
            if isinstance(raw_al, (list, tuple, set)):
                self.peer_allowlist = [str(x).strip() for x in raw_al if str(x).strip()] or None
            else:
                self.peer_allowlist = None
        if "capabilities" in cfg and isinstance(cfg.get("capabilities"), (list, tuple, set)):
            self.capabilities = [str(c).strip() for c in cfg["capabilities"] if str(c).strip()]
        if "rate_limit_max_events" in cfg:
            self.rate_limit_max_events = max(1, int(cfg.get("rate_limit_max_events", 10) or 10))
        if "rate_limit_window_sec" in cfg:
            self.rate_limit_window_sec = max(0.1, float(cfg.get("rate_limit_window_sec", 5.0)))

    def set_reply_callback(self, callback: Optional[Callable[[CollabEnvelope], Any]]) -> None:
        self._on_reply_needed = callback

    def set_action_callbacks(
        self,
        on_duet_sync: Optional[Callable[[CollabEnvelope], Any]] = None,
        on_emote_sync: Optional[Callable[[CollabEnvelope], Any]] = None,
        on_game_move: Optional[Callable[[CollabEnvelope], Any]] = None,
    ) -> None:
        """Registers optional async/sync callbacks for inbound duet_sync, emote_sync, and game_move."""
        if on_duet_sync is not None:
            self._on_duet_sync = on_duet_sync
        if on_emote_sync is not None:
            self._on_emote_sync = on_emote_sync
        if on_game_move is not None:
            self._on_game_move = on_game_move

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
        """Exits time-based cooldown once `turn_cooldown_sec` elapses and resets `turn_count`."""
        if self.floor_state == "cooldown" and time.monotonic() >= self.cooldown_until:
            self.turn_count = 0
            self.cooldown_until = 0.0
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

    @staticmethod
    def _strip_secret_query_params(url: str) -> str:
        parsed = urlparse(url)
        if not parsed.query:
            return url
        filtered = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in {"secret", "token"}
        ]
        return urlunparse(parsed._replace(query=urlencode(filtered)))

    def _check_rate_limit(self, direction: str, event_type: str) -> bool:
        """Sliding-window per-type rate limiter for non-utterance collab frames."""
        key = f"{direction}:{event_type}"
        now = time.monotonic()
        bucket = self._rate_limit_buckets.get(key)
        if bucket is None:
            bucket = deque()
            self._rate_limit_buckets[key] = bucket
        cutoff = now - self.rate_limit_window_sec
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.rate_limit_max_events:
            return False
        bucket.append(now)
        return True

    async def send_hello(
        self,
        capabilities: Optional[Iterable[str]] = None,
        speech: str = "",
        peer_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sends a `hello` capability handshake envelope to the connected peer."""
        if not self.enabled:
            return {"sent": False, "reason": "collab_disabled"}
        caps = [
            str(c).strip()
            for c in (capabilities if capabilities is not None else self.capabilities)
            if str(c).strip()
        ]
        target_peer = (peer_name or self.peer_name or "NeuroPeer").strip() or "NeuroPeer"
        env = self._build_envelope(
            event_type="hello",
            speech=speech or f"Halo {target_peer}! Eve siap collab.",
            emotion="happy",
            payload={
                "peer_name": target_peer,
                "capabilities": caps,
                "protocol_version": PROTOCOL_VERSION,
            },
        )
        delivered = await self._send_envelope(env)
        record = {"direction": "outbound", **env.to_dict()}
        self.history.append(record)
        await self._emit("collab.message", record)
        return {
            "sent": True,
            "delivered": delivered,
            "envelope": env.to_dict(),
            "capabilities": caps,
        }

    async def connect_peer(
        self,
        ws_url: Optional[str] = None,
        peer_name: Optional[str] = None,
        allow_private: Optional[bool] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        subprotocols: Optional[Sequence[str]] = None,
    ) -> bool:
        """Connects as an outbound WebSocket client to a peer VTuber's `/ws/collab` endpoint."""
        if not self.enabled:
            return False
        raw_url = (ws_url or self.peer_ws_url).strip()
        target_peer = (peer_name or self.peer_name).strip() or "NeuroPeer"
        if not raw_url:
            return False

        effective_allow_private = self.allow_private_peers if allow_private is None else bool(allow_private)
        try:
            validated_url = validate_outbound_url(
                raw_url,
                allowed_schemes=("ws", "wss"),
                allow_private=effective_allow_private,
                allowlist=self.peer_allowlist,
            )
        except SSRFValidationError as exc:
            print(f"[CollabManager] Blocked outbound peer URL '{raw_url}': {exc}")
            return False

        clean_url = self._strip_secret_query_params(validated_url)

        await self.disconnect_peer()
        self.peer_ws_url = clean_url
        self.peer_name = target_peer

        headers: Dict[str, str] = dict(extra_headers or {})
        if self.shared_secret:
            lower_keys = {k.lower() for k in headers}
            if "x-collab-secret" not in lower_keys:
                headers["x-collab-secret"] = self.shared_secret
            if "authorization" not in lower_keys:
                headers["Authorization"] = f"Bearer {self.shared_secret}"

        ws_kwargs: Dict[str, Any] = {"heartbeat": 30.0}
        if headers:
            ws_kwargs["headers"] = headers
        if subprotocols:
            ws_kwargs["protocols"] = [str(p) for p in subprotocols if str(p).strip()]

        try:
            self._http_session = aiohttp.ClientSession()
            self._ws_client = await self._http_session.ws_connect(clean_url, **ws_kwargs)
            self.peer_connected = True
            self.connected_peer = target_peer

            await self.send_hello(peer_name=target_peer)
            self._receive_task = asyncio.create_task(self._receive_loop())
            await self._set_floor_state("idle", reason="peer_connected")
            return True
        except Exception as exc:
            print(f"[CollabManager] Failed to connect to peer '{clean_url}': {exc}")
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
        try:
            hostname = (urlparse((url or "").strip()).hostname or "").lower()
        except ValueError:
            return False
        return hostname in {"127.0.0.1", "localhost", "::1"}

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
        """Sends a collaborative speech turn, enforcing enabled flag, floor state, max turns, and cooldown."""
        if not self.enabled:
            return {
                "sent": False,
                "reason": "collab_disabled",
                "floor_state": self.floor_state,
                "turn_count": self.turn_count,
            }
        async with self._lock:
            self._refresh_cooldown()
            if self.floor_state in ("speaking", "yielding"):
                return {
                    "sent": False,
                    "reason": f"floor_{self.floor_state}",
                    "floor_state": self.floor_state,
                    "turn_count": self.turn_count,
                }
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

    async def send_duet_sync(
        self,
        song_id: str,
        lyric_index: int,
        timestamp: float,
        track: str = "",
    ) -> Dict[str, Any]:
        """Broadcasts synchronized karaoke/duet timing cue to the collab peer."""
        if not self.enabled:
            return {"sent": False, "reason": "collab_disabled"}
        async with self._lock:
            self._refresh_cooldown()
            if not self._check_rate_limit("out", "duet_sync"):
                return {"sent": False, "reason": "rate_limited", "floor_state": self.floor_state}
            if self.floor_state == "cooldown" and time.monotonic() < self.cooldown_until:
                return {"sent": False, "reason": "turn_cooldown_active", "floor_state": self.floor_state}
            if self.floor_state in ("speaking", "yielding"):
                return {"sent": False, "reason": f"floor_{self.floor_state}", "floor_state": self.floor_state}
            env = self._build_envelope(
                event_type="duet_sync",
                topic=song_id,
                payload={
                    "song_id": str(song_id),
                    "lyric_index": int(lyric_index),
                    "timestamp": float(timestamp),
                    "track": str(track),
                },
            )
            delivered = await self._send_envelope(env)
            record = {"direction": "outbound", **env.to_dict()}
            self.history.append(record)
            await self._emit("collab.message", record)
            return {"sent": True, "delivered": delivered, "envelope": env.to_dict()}

    async def send_emote_sync(self, emotion: str, action: str = "") -> Dict[str, Any]:
        """Broadcasts synchronized avatar emotion/action cue to the collab peer."""
        if not self.enabled:
            return {"sent": False, "reason": "collab_disabled"}
        async with self._lock:
            self._refresh_cooldown()
            if not self._check_rate_limit("out", "emote_sync"):
                return {"sent": False, "reason": "rate_limited", "floor_state": self.floor_state}
            if self.floor_state == "cooldown" and time.monotonic() < self.cooldown_until:
                return {"sent": False, "reason": "turn_cooldown_active", "floor_state": self.floor_state}
            if self.floor_state in ("speaking", "yielding"):
                return {"sent": False, "reason": f"floor_{self.floor_state}", "floor_state": self.floor_state}
            env = self._build_envelope(
                event_type="emote_sync",
                emotion=emotion,
                payload={"emotion": str(emotion), "action": str(action)},
            )
            delivered = await self._send_envelope(env)
            record = {"direction": "outbound", **env.to_dict()}
            self.history.append(record)
            await self._emit("collab.message", record)
            return {"sent": True, "delivered": delivered, "envelope": env.to_dict()}

    async def send_game_move(
        self,
        move: str,
        game: str = "chess",
        fen: str = "",
        **extra: Any,
    ) -> Dict[str, Any]:
        """Broadcasts a game move (e.g. chess UCI/SAN move) to the collab peer."""
        if not self.enabled:
            return {"sent": False, "reason": "collab_disabled"}
        move_str = str(move or "").strip()
        if not move_str:
            return {"sent": False, "reason": "empty_move"}
        async with self._lock:
            self._refresh_cooldown()
            if not self._check_rate_limit("out", "game_move"):
                return {"sent": False, "reason": "rate_limited", "floor_state": self.floor_state}
            if self.floor_state == "cooldown" and time.monotonic() < self.cooldown_until:
                return {"sent": False, "reason": "turn_cooldown_active", "floor_state": self.floor_state}
            if self.floor_state in ("speaking", "yielding"):
                return {"sent": False, "reason": f"floor_{self.floor_state}", "floor_state": self.floor_state}
            move_payload: Dict[str, Any] = {
                "game": str(game or "chess").strip() or "chess",
                "move": move_str,
                "uci": move_str,
            }
            if fen:
                move_payload["fen"] = str(fen)
            for k, v in extra.items():
                if v is not None and k not in move_payload:
                    move_payload[k] = v
            env = self._build_envelope(
                event_type="game_move",
                topic=move_payload["game"],
                payload=move_payload,
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
        if not self.enabled:
            return {"accepted": False, "error": "Collab is disabled.", "reason": "collab_disabled"}

        try:
            env = CollabEnvelope.from_dict(raw_dict)
        except Exception as exc:
            return {"accepted": False, "error": str(exc)}

        allow_unsigned = bool(self.allow_unauthenticated_loopback and is_loopback and not self.shared_secret)
        if not env.verify(self.shared_secret, allow_unsigned=allow_unsigned):
            return {"accepted": False, "error": "Invalid or missing collab HMAC signature."}

        now = time.time()
        if abs(now - env.timestamp) > self.max_timestamp_skew_sec:
            return {
                "accepted": False,
                "error": "Collab envelope timestamp outside ±60s skew window.",
                "reason": "timestamp_skew_exceeded",
            }

        reply_cb = on_reply_needed if on_reply_needed is not None else self._on_reply_needed
        trigger_reply = False
        reply_reason = "no_reply_needed"
        action_cb: Optional[Callable[[CollabEnvelope], Any]] = None

        async with self._lock:
            nonce_key = (env.sender_id, env.message_id)
            if nonce_key in self._seen_nonces:
                self._seen_nonces.move_to_end(nonce_key)
                return {
                    "accepted": False,
                    "error": "Duplicate collab message_id detected (replay rejected).",
                    "reason": "duplicate_nonce",
                }
            if env.event_type in NON_UTTERANCE_EVENT_TYPES and not self._check_rate_limit("in", env.event_type):
                return {
                    "accepted": False,
                    "error": f"Rate limit exceeded for '{env.event_type}'.",
                    "reason": "rate_limited",
                }
            self._seen_nonces[nonce_key] = now
            while len(self._seen_nonces) > self._nonce_cache_maxsize:
                self._seen_nonces.popitem(last=False)

            self._refresh_cooldown()
            record = {"direction": "inbound", **env.to_dict()}
            self.history.append(record)
            await self._emit("collab.message", record)

            if env.event_type == "hello":
                self.peer_connected = True
                self.connected_peer = env.sender_name or env.sender_id or self.peer_name
                raw_caps = env.payload.get("capabilities")
                if isinstance(raw_caps, list):
                    self.peer_capabilities = [
                        str(c).strip() for c in raw_caps if isinstance(c, str) and c.strip()
                    ]
                self.peer_protocol_version = str(
                    env.payload.get("protocol_version") or env.protocol_version or PROTOCOL_VERSION
                )
                await self._set_floor_state("idle", reason="peer_hello")
            elif env.event_type == "bye":
                self.peer_connected = False
                self.connected_peer = None
                self.peer_capabilities = []
                self.peer_protocol_version = ""
                await self._set_floor_state("idle", reason="peer_bye")
            elif env.event_type == "duet_sync":
                if "lyric_index" in raw_dict and "lyric_index" not in env.payload:
                    env.payload["lyric_index"] = int(raw_dict["lyric_index"])
                if "timestamp" in raw_dict and "timestamp" not in env.payload:
                    env.payload["timestamp"] = float(raw_dict["timestamp"])
                if "track" in raw_dict and "track" not in env.payload:
                    env.payload["track"] = str(raw_dict["track"])
                action_cb = self._on_duet_sync
                reply_reason = "duet_sync_received"
            elif env.event_type == "emote_sync":
                if "action" in raw_dict and "action" not in env.payload:
                    env.payload["action"] = str(raw_dict["action"])
                if "emotion" not in env.payload and env.emotion:
                    env.payload["emotion"] = env.emotion
                elif env.payload.get("emotion") and env.emotion == "neutral":
                    env.emotion = str(env.payload["emotion"])
                action_cb = self._on_emote_sync
                reply_reason = "emote_sync_received"
            elif env.event_type == "game_move":
                action_cb = self._on_game_move
                reply_reason = "game_move_received"
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

                # Prevent talking over self, concurrent reply storms, or looping past max_collab_turns
                if self.floor_state in ("thinking", "speaking"):
                    reply_reason = f"already_{self.floor_state}"
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
                        trigger_reply = reply_cb is not None
                        if trigger_reply:
                            await self._set_floor_state("thinking", reason="generating_reply")
                        else:
                            await self._set_floor_state("idle", reason="peer_utterance_received")
                        reply_reason = "floor_acquired"

        if action_cb is not None:
            try:
                res = action_cb(env)
                if inspect.isawaitable(res):
                    await res
            except Exception as exc:
                print(f"[CollabManager] Action callback error ({env.event_type}): {exc}")

        if trigger_reply and reply_cb is not None:
            if asyncio.iscoroutinefunction(reply_cb):
                task = asyncio.create_task(self._run_reply_callback(reply_cb, env))
                self._reply_tasks.add(task)
                task.add_done_callback(self._reply_tasks.discard)
            else:
                spawned_async = False
                try:
                    res = reply_cb(env)
                    if inspect.isawaitable(res):
                        spawned_async = True
                        task = asyncio.create_task(self._await_reply_result(res))
                        self._reply_tasks.add(task)
                        task.add_done_callback(self._reply_tasks.discard)
                except Exception as exc:
                    print(f"[CollabManager] Reply callback error: {exc}")
                finally:
                    if not spawned_async:
                        async with self._lock:
                            if self.floor_state == "thinking":
                                await self._set_floor_state("idle", reason="reply_complete")

        return {
            "accepted": True,
            "event_type": env.event_type,
            "reply_triggered": trigger_reply,
            "reason": reply_reason,
            "floor_state": self.floor_state,
            "turn_count": self.turn_count,
        }

    async def _release_thinking_floor(self) -> None:
        async with self._lock:
            if self.floor_state == "thinking":
                await self._set_floor_state("idle", reason="reply_complete")

    async def _await_reply_result(self, awaitable: Awaitable[Any]) -> None:
        try:
            await awaitable
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[CollabManager] Reply callback error: {exc}")
        finally:
            await self._release_thinking_floor()

    async def _run_reply_callback(
        self,
        reply_cb: Callable[[CollabEnvelope], Any],
        env: CollabEnvelope,
    ) -> None:
        try:
            res = reply_cb(env)
            if inspect.isawaitable(res):
                await res
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[CollabManager] Reply callback error: {exc}")
        finally:
            await self._release_thinking_floor()

    async def reset_turns(self) -> Dict[str, Any]:
        """Resets the collab turn counter and exits cooldown back to 'idle'."""
        async with self._lock:
            self.turn_count = 0
            self.cooldown_until = 0.0
            await self._set_floor_state("idle", reason="turns_reset")
        return self.get_status()

    async def shutdown(self) -> None:
        for task in list(self._reply_tasks):
            if not task.done():
                task.cancel()
        if self._reply_tasks:
            await asyncio.gather(*list(self._reply_tasks), return_exceptions=True)
        self._reply_tasks.clear()
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
            "allow_private_peers": self.allow_private_peers,
            "capabilities": list(self.capabilities),
            "peer_capabilities": list(self.peer_capabilities),
            "history_count": len(self.history),
            "recent_messages": list(self.history)[-10:],
        }
