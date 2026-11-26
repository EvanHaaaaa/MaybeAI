import asyncio
from collections import deque
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Set

import aiohttp

from core.platforms.base import BasePlatformAdapter


class DiscordAdapter(BasePlatformAdapter):
    """
    Discord channel chat ingestion adapter polling Discord REST API v10 via aiohttp
    using a Bot Token and Channel ID (`source="discord"`).
    Zero extra pip dependencies; degrades gracefully when disabled or unconfigured.
    """

    platform_name = "discord"
    API_BASE = "https://discord.com/api/v10"
    GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"

    def __init__(
        self,
        receiver: Optional[Any] = None,
        bot_token: str = "",
        channel_id: str = "",
        poll_interval_sec: float = 3.0,
        enabled: bool = False,
        on_message: Optional[Callable[..., Awaitable[Any]]] = None,
        skip_initial_backlog: bool = True,
        use_gateway: bool = False,
        gateway_url: Optional[str] = None,
    ):
        super().__init__(receiver=receiver, on_message=on_message, enabled=enabled)
        raw_token = (bot_token or "").strip()
        if raw_token.lower().startswith("bot "):
            raw_token = raw_token[4:].strip()
        self.bot_token = raw_token
        self.channel_id = str(channel_id or "").strip()
        self.poll_interval_sec = max(1.0, float(poll_interval_sec or 3.0))
        self.skip_initial_backlog = bool(skip_initial_backlog)
        self.use_gateway = bool(use_gateway)
        self.gateway_url = (gateway_url or self.GATEWAY_URL).strip()

        self._seeded_initial: bool = False
        self._last_message_id: Optional[str] = None
        self._seen_ids: Set[str] = set()
        self._seen_order: Deque[str] = deque(maxlen=1000)
        self._task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._gateway_seq: Optional[int] = None

    def is_configured(self) -> bool:
        return bool(self.enabled and self.bot_token and self.channel_id)

    def _mark_seen(self, msg_id: str) -> bool:
        if not msg_id:
            return False
        if msg_id in self._seen_ids:
            return True
        if len(self._seen_order) == self._seen_order.maxlen:
            oldest = self._seen_order.popleft()
            self._seen_ids.discard(oldest)
        self._seen_order.append(msg_id)
        self._seen_ids.add(msg_id)
        return False

    def _parse_message(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        msg_id = str(item.get("id", "")).strip()
        if msg_id and self._mark_seen(msg_id):
            return None

        author = item.get("author") or {}
        if author.get("bot"):
            return None

        content = str(item.get("content") or "").strip()
        if not content:
            return None

        user = str(
            author.get("global_name")
            or author.get("username")
            or "DiscordUser"
        ).strip()

        return {
            "user": user,
            "text": content,
            "source": "discord",
            "is_donation": False,
        }

    async def poll_once(self, session: Optional[aiohttp.ClientSession] = None) -> float:
        """
        Executes a single poll against Discord GET /channels/{channel_id}/messages.
        Returns the recommended delay (seconds) before the next poll.
        """
        if not self.bot_token or not self.channel_id:
            self.is_connected = False
            self.last_error = "Discord bot_token or channel_id not configured."
            return self.poll_interval_sec

        url = f"{self.API_BASE}/channels/{self.channel_id}/messages"
        headers = {
            "Authorization": f"Bot {self.bot_token}",
            "User-Agent": "MaybeAI-Bot (https://github.com/maybeai, 1.0)",
        }
        params: Dict[str, str] = {"limit": "20"}
        if self._last_message_id:
            params["after"] = self._last_message_id

        own_session = False
        active_session = session or self._session
        if active_session is None or active_session.closed:
            active_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15.0))
            own_session = True

        try:
            async with active_session.get(url, headers=headers, params=params) as resp:
                if resp.status == 429:
                    try:
                        rate_data = await resp.json()
                        retry_after = float(rate_data.get("retry_after", 5.0))
                    except Exception:
                        retry_after = 5.0
                    self.last_error = f"Rate limited (429), retrying in {retry_after:.1f}s"
                    return max(self.poll_interval_sec, retry_after)

                if resp.status != 200:
                    body = await resp.text()
                    self.is_connected = False
                    self.last_error = f"HTTP {resp.status}: {body[:200]}"
                    return max(self.poll_interval_sec, 10.0)

                messages: List[Dict[str, Any]] = await resp.json()
                self.is_connected = True
                self.last_error = None

                if isinstance(messages, list):
                    if not self._seeded_initial and self.skip_initial_backlog and self._last_message_id is None and self.is_running:
                        self._seeded_initial = True
                        if messages:
                            # Seed newest message ID and mark backlog seen without replaying old history on startup
                            newest_id = str(messages[0].get("id", "")).strip()
                            if newest_id:
                                self._last_message_id = newest_id
                            for item in messages:
                                mid = str(item.get("id", "")).strip()
                                if mid:
                                    self._mark_seen(mid)
                        return self.poll_interval_sec

                    self._seeded_initial = True
                    if messages:
                        # Discord returns newest first; process oldest -> newest
                        ordered = list(reversed(messages))
                        for item in ordered:
                            msg_id = str(item.get("id", "")).strip()
                            if msg_id:
                                self._last_message_id = msg_id
                            parsed = self._parse_message(item)
                            if parsed:
                                await self._emit_message(**parsed)

                return self.poll_interval_sec
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.is_connected = False
            self.last_error = str(e)
            return max(self.poll_interval_sec, 10.0)
        finally:
            if own_session and active_session and not active_session.closed:
                await active_session.close()

    async def send_message(self, text: str, channel_id: Optional[str] = None) -> bool:
        """Sends a text message to a Discord channel via REST API v10."""
        target_channel = str(channel_id or self.channel_id or "").strip()
        content = str(text or "").strip()
        if not self.bot_token or not target_channel or not content:
            return False

        url = f"{self.API_BASE}/channels/{target_channel}/messages"
        headers = {
            "Authorization": f"Bot {self.bot_token}",
            "Content-Type": "application/json",
            "User-Agent": "MaybeAI-Bot (https://github.com/maybeai, 1.0)",
        }
        own_session = False
        active_session = self._session
        if active_session is None or active_session.closed:
            active_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15.0))
            own_session = True

        try:
            async with active_session.post(url, headers=headers, json={"content": content[:2000]}) as resp:
                if resp.status in (200, 201, 204):
                    return True
                body = await resp.text()
                self.last_error = f"Discord send HTTP {resp.status}: {body[:200]}"
                return False
        except Exception as exc:
            self.last_error = str(exc)
            return False
        finally:
            if own_session and active_session and not active_session.closed:
                await active_session.close()

    async def _gateway_heartbeat_loop(self, ws: aiohttp.ClientWebSocketResponse, interval_sec: float) -> None:
        try:
            while self.is_running and not ws.closed:
                await asyncio.sleep(interval_sec)
                if not self.is_running or ws.closed:
                    break
                await ws.send_json({"op": 1, "d": self._gateway_seq})
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _handle_gateway_payload(self, ws: aiohttp.ClientWebSocketResponse, payload: Dict[str, Any]) -> bool:
        """
        Processes a single Discord Gateway JSON payload.
        Returns False if the gateway session requested reconnect/termination.
        """
        op = payload.get("op")
        seq = payload.get("s")
        if seq is not None:
            self._gateway_seq = seq
        t = payload.get("t")
        d = payload.get("d")

        if op == 10:  # HELLO
            interval_ms = float((d or {}).get("heartbeat_interval", 41250))
            interval_sec = max(1.0, interval_ms / 1000.0)
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
            self._heartbeat_task = asyncio.create_task(self._gateway_heartbeat_loop(ws, interval_sec))
            await ws.send_json({
                "op": 2,  # IDENTIFY
                "d": {
                    "token": self.bot_token,
                    "intents": 33281,  # GUILDS (1) | GUILD_MESSAGES (512) | MESSAGE_CONTENT (32768)
                    "properties": {
                        "os": "windows",
                        "browser": "maybeai",
                        "device": "maybeai",
                    },
                },
            })
            self.is_connected = True
            self.last_error = None
            return True

        if op == 1:  # HEARTBEAT request
            await ws.send_json({"op": 1, "d": self._gateway_seq})
            return True

        if op in (7, 9):  # RECONNECT / INVALID_SESSION
            return False

        if op == 0 and t == "MESSAGE_CREATE" and isinstance(d, dict):
            if str(d.get("channel_id", "")).strip() != self.channel_id:
                return True
            msg_id = str(d.get("id", "")).strip()
            if msg_id:
                self._last_message_id = msg_id
            parsed = self._parse_message(d)
            if parsed:
                await self._emit_message(**parsed)
            return True

        return True

    async def _gateway_loop(self) -> None:
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30.0))
        try:
            while self.is_running:
                try:
                    async with self._session.ws_connect(self.gateway_url, heartbeat=30.0) as ws:
                        self._ws = ws
                        async for msg in ws:
                            if not self.is_running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    payload = msg.json()
                                except Exception:
                                    continue
                                if isinstance(payload, dict):
                                    keep_going = await self._handle_gateway_payload(ws, payload)
                                    if not keep_going:
                                        break
                            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.is_connected = False
                    self.last_error = f"Gateway error (falling back to REST poll): {exc}"
                    # Clean REST fallback when Gateway is unavailable
                    await self.poll_once(self._session)
                    if not self.is_running:
                        break
                    await asyncio.sleep(self.poll_interval_sec)
                finally:
                    self._ws = None
                    if self._heartbeat_task and not self._heartbeat_task.done():
                        self._heartbeat_task.cancel()
                        try:
                            await self._heartbeat_task
                        except asyncio.CancelledError:
                            pass
                    self._heartbeat_task = None
        except asyncio.CancelledError:
            pass
        finally:
            self.is_connected = False
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None

    async def _poll_loop(self) -> None:
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15.0))
        try:
            while self.is_running:
                delay = await self.poll_once(self._session)
                if not self.is_running:
                    break
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            pass
        finally:
            self.is_connected = False
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None

    async def start(self) -> bool:
        if not self.enabled:
            self.is_running = False
            self.is_connected = False
            return False
        if not self.bot_token or not self.channel_id:
            self.is_running = False
            self.is_connected = False
            self.last_error = "Discord adapter enabled but bot_token or channel_id is missing."
            return False
        if self.is_running and self._task and not self._task.done():
            return True

        self.is_running = True
        self.last_error = None
        if self.use_gateway:
            self._task = asyncio.create_task(self._gateway_loop())
        else:
            self._task = asyncio.create_task(self._poll_loop())
        return True

    async def stop(self) -> None:
        self.is_running = False
        self.is_connected = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        self._heartbeat_task = None
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    def get_status(self) -> Dict[str, Any]:
        return {
            "platform": self.platform_name,
            "enabled": self.enabled,
            "configured": self.is_configured(),
            "is_running": self.is_running,
            "is_connected": self.is_connected,
            "channel_id": self.channel_id,
            "poll_interval_sec": self.poll_interval_sec,
            "use_gateway": self.use_gateway,
            "messages_received": self.messages_received,
            "last_error": self.last_error,
        }
