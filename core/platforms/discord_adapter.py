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

    def __init__(
        self,
        receiver: Optional[Any] = None,
        bot_token: str = "",
        channel_id: str = "",
        poll_interval_sec: float = 3.0,
        enabled: bool = False,
        on_message: Optional[Callable[..., Awaitable[Any]]] = None,
    ):
        super().__init__(receiver=receiver, on_message=on_message, enabled=enabled)
        raw_token = (bot_token or "").strip()
        if raw_token.lower().startswith("bot "):
            raw_token = raw_token[4:].strip()
        self.bot_token = raw_token
        self.channel_id = str(channel_id or "").strip()
        self.poll_interval_sec = max(1.0, float(poll_interval_sec or 3.0))

        self._last_message_id: Optional[str] = None
        self._seen_ids: Set[str] = set()
        self._seen_order: Deque[str] = deque(maxlen=1000)
        self._task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None

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

                if isinstance(messages, list) and messages:
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
        self._task = asyncio.create_task(self._poll_loop())
        return True

    async def stop(self) -> None:
        self.is_running = False
        self.is_connected = False
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
            "messages_received": self.messages_received,
            "last_error": self.last_error,
        }
