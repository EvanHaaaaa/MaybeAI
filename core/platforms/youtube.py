import asyncio
from collections import deque
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Set

import aiohttp

from core.platforms.base import BasePlatformAdapter


class YouTubeLiveAdapter(BasePlatformAdapter):
    """
    YouTube Live Chat ingestion adapter polling YouTube Data API v3 `liveChatMessages.list`.
    Maps regular chat messages and SuperChat / SuperSticker events (`is_donation=True`,
    `source="youtube"`) into ChatReceiver. Degrades gracefully when disabled or unconfigured.
    """

    platform_name = "youtube"
    API_URL = "https://www.googleapis.com/youtube/v3/liveChat/messages"

    def __init__(
        self,
        receiver: Optional[Any] = None,
        api_key: str = "",
        live_chat_id: str = "",
        poll_interval_sec: float = 5.0,
        enabled: bool = False,
        on_message: Optional[Callable[..., Awaitable[Any]]] = None,
    ):
        super().__init__(receiver=receiver, on_message=on_message, enabled=enabled)
        self.api_key = (api_key or "").strip()
        self.live_chat_id = (live_chat_id or "").strip()
        self.poll_interval_sec = max(1.0, float(poll_interval_sec or 5.0))

        self._next_page_token: Optional[str] = None
        self._seen_ids: Set[str] = set()
        self._seen_order: Deque[str] = deque(maxlen=1000)
        self._task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None

    def is_configured(self) -> bool:
        return bool(self.enabled and self.api_key and self.live_chat_id)

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

    def _parse_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        msg_id = str(item.get("id", "")).strip()
        if msg_id and self._mark_seen(msg_id):
            return None

        author_details = item.get("authorDetails") or {}
        snippet = item.get("snippet") or {}

        user = str(author_details.get("displayName") or "YouTubeViewer").strip()
        msg_type = str(snippet.get("type") or "")

        is_donation = False
        donation_amount = ""
        donation_currency = ""
        text = ""

        if msg_type == "superChatEvent" or "superChatDetails" in snippet:
            sc = snippet.get("superChatDetails") or {}
            is_donation = True
            donation_amount = str(sc.get("amountDisplayString") or "").strip()
            donation_currency = str(sc.get("currency") or "").strip()
            text = str(
                sc.get("userComment")
                or snippet.get("displayMessage")
                or f"Sent a SuperChat ({donation_amount})"
            ).strip()
        elif msg_type == "superStickerEvent" or "superStickerDetails" in snippet:
            ss = snippet.get("superStickerDetails") or {}
            is_donation = True
            donation_amount = str(ss.get("amountDisplayString") or "").strip()
            donation_currency = str(ss.get("currency") or "").strip()
            text = str(
                snippet.get("displayMessage")
                or f"Sent a SuperSticker ({donation_amount})"
            ).strip()
        else:
            text_details = snippet.get("textMessageDetails") or {}
            text = str(
                snippet.get("displayMessage")
                or text_details.get("messageText")
                or ""
            ).strip()

        if not text:
            return None

        return {
            "user": user,
            "text": text,
            "source": "youtube",
            "is_donation": is_donation,
            "donation_amount": donation_amount,
            "donation_currency": donation_currency,
        }

    async def poll_once(self, session: Optional[aiohttp.ClientSession] = None) -> float:
        """
        Executes a single poll against YouTube Data API v3 liveChatMessages.
        Returns the recommended delay (seconds) before the next poll.
        """
        if not self.api_key or not self.live_chat_id:
            self.is_connected = False
            self.last_error = "YouTube API key or live_chat_id not configured."
            return self.poll_interval_sec

        params: Dict[str, str] = {
            "liveChatId": self.live_chat_id,
            "part": "snippet,authorDetails",
            "key": self.api_key,
        }
        if self._next_page_token:
            params["pageToken"] = self._next_page_token

        own_session = False
        active_session = session or self._session
        if active_session is None or active_session.closed:
            active_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15.0))
            own_session = True

        try:
            async with active_session.get(self.API_URL, params=params) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    self.is_connected = False
                    self.last_error = f"HTTP {resp.status}: {body[:200]}"
                    return max(self.poll_interval_sec, 10.0)

                data = await resp.json()
                self.is_connected = True
                self.last_error = None

                next_token = data.get("nextPageToken")
                if next_token:
                    self._next_page_token = next_token

                items: List[Dict[str, Any]] = data.get("items") or []
                for item in items:
                    parsed = self._parse_item(item)
                    if parsed:
                        await self._emit_message(**parsed)

                api_interval_ms = data.get("pollingIntervalMillis")
                if isinstance(api_interval_ms, (int, float)) and api_interval_ms > 0:
                    return max(self.poll_interval_sec, float(api_interval_ms) / 1000.0)
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
        if not self.api_key or not self.live_chat_id:
            self.is_running = False
            self.is_connected = False
            self.last_error = "YouTube Live adapter enabled but api_key or live_chat_id is missing."
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
            "live_chat_id": self.live_chat_id,
            "poll_interval_sec": self.poll_interval_sec,
            "messages_received": self.messages_received,
            "last_error": self.last_error,
        }
