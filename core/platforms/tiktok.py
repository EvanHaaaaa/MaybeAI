import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional

import aiohttp

from core.platforms.base import BasePlatformAdapter

try:
    from TikTokLive import TikTokLiveClient  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    TikTokLiveClient = None


class TikTokLiveAdapter(BasePlatformAdapter):
    """
    TikTok Live chat & gift ingestion adapter (`source="tiktok"`).
    Supports optional `TikTokLive` library, a custom Webcast WebSocket URL (`webcast_ws_url`),
    or direct event injection via `handle_tiktok_event(event_type, data)`.
    Degrades gracefully when disabled or unconfigured.
    """

    platform_name = "tiktok"

    def __init__(
        self,
        receiver: Optional[Any] = None,
        username: str = "",
        webcast_ws_url: str = "",
        enabled: bool = False,
        on_message: Optional[Callable[..., Awaitable[Any]]] = None,
    ):
        super().__init__(receiver=receiver, on_message=on_message, enabled=enabled)
        self.username = str(username or "").strip().lstrip("@")
        self.webcast_ws_url = str(webcast_ws_url or "").strip()
        self._task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._tiktok_client: Optional[Any] = None

    def is_configured(self) -> bool:
        return bool(self.enabled and (self.username or self.webcast_ws_url))

    async def handle_tiktok_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Normalizes a TikTok Live event (`comment`, `gift`, `like`, `follow`)
        and emits it to the bound ChatReceiver or callback.
        """
        payload = data if isinstance(data, dict) else {}
        evt = str(event_type or "").strip().lower()
        user = str(
            payload.get("nickname")
            or payload.get("unique_id")
            or payload.get("user")
            or payload.get("username")
            or "TikTokViewer"
        ).strip()

        if evt == "comment":
            text = str(payload.get("comment") or payload.get("text") or "").strip()
            if not text:
                return False
            await self._emit_message(user=user, text=text, source="tiktok", is_donation=False)
            return True

        if evt == "gift":
            gift_name = str(payload.get("gift_name") or payload.get("giftName") or payload.get("name") or "Gift").strip()
            count = int(payload.get("repeat_count") or payload.get("count") or 1)
            diamonds = payload.get("diamond_count") or payload.get("diamonds") or payload.get("amount") or count
            text = str(payload.get("text") or f"Sent {count}x {gift_name}!").strip()
            await self._emit_message(
                user=user,
                text=text,
                source="tiktok",
                is_donation=True,
                donation_amount=str(diamonds),
                donation_currency="diamonds",
            )
            return True

        if evt == "like":
            count = int(payload.get("like_count") or payload.get("count") or 1)
            text = str(payload.get("text") or f"liked the stream ({count}x)").strip()
            await self._emit_message(user=user, text=text, source="tiktok", is_donation=False)
            return True

        if evt == "follow":
            text = str(payload.get("text") or "followed the stream!").strip()
            await self._emit_message(user=user, text=text, source="tiktok", is_donation=False)
            return True

        return False

    async def _run_webcast_ws(self) -> None:
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30.0))
        try:
            async with self._session.ws_connect(self.webcast_ws_url, heartbeat=30.0) as ws:
                self._ws = ws
                self.is_connected = True
                self.last_error = None
                async for msg in ws:
                    if not self.is_running:
                        break
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = msg.json()
                        except Exception:
                            continue
                        if isinstance(data, dict):
                            evt = data.get("type") or data.get("event_type") or "comment"
                            await self.handle_tiktok_event(evt, data.get("data", data))
                    elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = str(exc)
        finally:
            self._ws = None
            self.is_connected = False
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None

    async def _run_tiktoklive_client(self) -> None:
        if TikTokLiveClient is None or not self.username:
            return
        try:
            client = TikTokLiveClient(unique_id=f"@{self.username}")
            self._tiktok_client = client

            @client.on("comment")
            async def _on_comment(event: Any) -> None:
                user_obj = getattr(event, "user", None)
                user = getattr(user_obj, "nickname", None) or getattr(user_obj, "unique_id", None) or "TikTokViewer"
                await self.handle_tiktok_event("comment", {"user": user, "comment": getattr(event, "comment", "")})

            @client.on("gift")
            async def _on_gift(event: Any) -> None:
                user_obj = getattr(event, "user", None)
                gift_obj = getattr(event, "gift", None)
                user = getattr(user_obj, "nickname", None) or getattr(user_obj, "unique_id", None) or "TikTokViewer"
                gift_name = getattr(gift_obj, "name", None) or "Gift"
                diamonds = getattr(gift_obj, "diamond_count", 1)
                count = getattr(event, "repeat_count", 1)
                await self.handle_tiktok_event(
                    "gift",
                    {"user": user, "gift_name": gift_name, "repeat_count": count, "diamond_count": diamonds},
                )

            @client.on("like")
            async def _on_like(event: Any) -> None:
                user_obj = getattr(event, "user", None)
                user = getattr(user_obj, "nickname", None) or getattr(user_obj, "unique_id", None) or "TikTokViewer"
                await self.handle_tiktok_event("like", {"user": user, "like_count": getattr(event, "count", 1)})

            @client.on("follow")
            async def _on_follow(event: Any) -> None:
                user_obj = getattr(event, "user", None)
                user = getattr(user_obj, "nickname", None) or getattr(user_obj, "unique_id", None) or "TikTokViewer"
                await self.handle_tiktok_event("follow", {"user": user})

            self.is_connected = True
            self.last_error = None
            await client.start()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = str(exc)
        finally:
            self.is_connected = False
            self._tiktok_client = None

    async def start(self) -> bool:
        if not self.enabled:
            self.is_running = False
            self.is_connected = False
            return False
        if not self.username and not self.webcast_ws_url:
            self.is_running = False
            self.is_connected = False
            self.last_error = "TikTok adapter enabled but username/webcast_ws_url is missing."
            return False
        if self.is_running and self._task and not self._task.done():
            return True

        self.is_running = True
        self.last_error = None

        if self.webcast_ws_url:
            self._task = asyncio.create_task(self._run_webcast_ws())
            return True
        if TikTokLiveClient is not None and self.username:
            self._task = asyncio.create_task(self._run_tiktoklive_client())
            return True

        self.last_error = "TikTokLive package not installed and no webcast_ws_url configured."
        self.is_connected = False
        return False

    async def stop(self) -> None:
        self.is_running = False
        self.is_connected = False
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._tiktok_client is not None:
            try:
                disconnect_fn = getattr(self._tiktok_client, "disconnect", None)
                if callable(disconnect_fn):
                    res = disconnect_fn()
                    if asyncio.iscoroutine(res):
                        await res
            except Exception:
                pass
            self._tiktok_client = None
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
            "username": self.username,
            "webcast_ws_url": self.webcast_ws_url,
            "tiktoklive_installed": TikTokLiveClient is not None,
            "messages_received": self.messages_received,
            "last_error": self.last_error,
        }
