"""Event-driven Highlight Auto-Marker for live stream moments."""

import asyncio
import inspect
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional

from core.event_bus import (
    CHAT_RECEIVED,
    DONATION_RECEIVED,
    MOOD_UPDATED,
    VOICE_BARGE_IN,
)

GOAL_COMPLETED = "goal.completed"
PERFORMANCE_UPDATED = "performance.updated"
HIGHLIGHT_MARKED = "highlight.marked"


@dataclass
class HighlightMarker:
    """Timestamped highlight marker recorded during a stream."""

    id: str
    timestamp: float
    iso_time: str
    reason: str
    category: str
    source: str
    user: str = "System"
    details: Dict[str, Any] = field(default_factory=dict)
    replay_saved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HighlightDetector:
    """
    Subscribes to EventBus stream signals and marks highlight moments with
    cooldown deduplication and optional OBS Replay Buffer saving.
    """

    def __init__(
        self,
        event_bus: Any = None,
        on_save_replay: Optional[Callable[[HighlightMarker], Any]] = None,
        chat_burst_threshold: int = 8,
        burst_window_sec: float = 10.0,
        cooldown_sec: float = 30.0,
        enabled: bool = True,
        excitement_threshold: float = 0.80,
        max_markers: int = 500,
    ):
        self.event_bus = event_bus
        self.on_save_replay = on_save_replay
        self.chat_burst_threshold = max(1, int(chat_burst_threshold))
        self.burst_window_sec = max(1.0, float(burst_window_sec))
        self.cooldown_sec = max(0.0, float(cooldown_sec))
        self.enabled = bool(enabled)
        self.excitement_threshold = max(0.0, min(1.0, float(excitement_threshold)))
        self.max_markers = max(1, int(max_markers))

        self._chat_timestamps: Deque[float] = deque()
        self._markers: Deque[HighlightMarker] = deque(maxlen=self.max_markers)
        self._last_auto_highlight_at: float = 0.0
        self._subscribed: bool = False

        if self.event_bus is not None:
            self.subscribe(self.event_bus)

    def subscribe(self, event_bus: Any) -> None:
        """Subscribe to stream highlight trigger events on `event_bus`."""
        if event_bus is None:
            return
        self.event_bus = event_bus
        event_bus.subscribe(CHAT_RECEIVED, self._on_chat_received)
        event_bus.subscribe(DONATION_RECEIVED, self._on_donation_received)
        event_bus.subscribe(VOICE_BARGE_IN, self._on_voice_barge_in)
        event_bus.subscribe(GOAL_COMPLETED, self._on_goal_completed)
        event_bus.subscribe(MOOD_UPDATED, self._on_mood_updated)
        event_bus.subscribe(PERFORMANCE_UPDATED, self._on_performance_updated)
        self._subscribed = True

    def _in_cooldown(self, now: float) -> bool:
        if self.cooldown_sec <= 0.0 or self._last_auto_highlight_at <= 0.0:
            return False
        return (now - self._last_auto_highlight_at) < self.cooldown_sec

    @staticmethod
    def _is_replay_success(result: Any) -> bool:
        if isinstance(result, dict):
            return bool(result.get("success", False))
        if isinstance(result, bool):
            return result
        return True

    async def _await_replay_result(self, coro: Any, marker: HighlightMarker) -> None:
        try:
            result = await coro
            marker.replay_saved = self._is_replay_success(result)
        except Exception as exc:
            marker.replay_saved = False
            print(f"[HighlightDetector] async on_save_replay error: {exc}")

    def _trigger_replay_callback(self, marker: HighlightMarker) -> bool:
        if self.on_save_replay is None:
            return False
        try:
            res = self.on_save_replay(marker)
            if inspect.isawaitable(res):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._await_replay_result(res, marker))
                except RuntimeError:
                    if hasattr(res, "close"):
                        res.close()
                return False
            return self._is_replay_success(res)
        except Exception as exc:
            print(f"[HighlightDetector] on_save_replay error: {exc}")
            return False

    def _record_marker(
        self,
        reason: str,
        category: str,
        source: str,
        user: str = "System",
        details: Optional[Dict[str, Any]] = None,
        is_manual: bool = False,
        now: Optional[float] = None,
    ) -> Optional[HighlightMarker]:
        ts = float(now if now is not None else time.time())
        if not is_manual:
            if not self.enabled or self._in_cooldown(ts):
                return None
            self._last_auto_highlight_at = ts

        iso_time = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        marker = HighlightMarker(
            id=uuid.uuid4().hex[:12],
            timestamp=ts,
            iso_time=iso_time,
            reason=reason,
            category=category,
            source=source,
            user=user,
            details=dict(details or {}),
            replay_saved=False,
        )
        marker.replay_saved = self._trigger_replay_callback(marker)
        self._markers.append(marker)

        if self.event_bus is not None:
            self.event_bus.publish_nowait(HIGHLIGHT_MARKED, marker.to_dict())

        return marker

    def _on_chat_received(self, _event_name: str, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        now = time.time()
        self._chat_timestamps.append(now)
        cutoff = now - self.burst_window_sec
        while self._chat_timestamps and self._chat_timestamps[0] < cutoff:
            self._chat_timestamps.popleft()

        if len(self._chat_timestamps) >= self.chat_burst_threshold:
            count = len(self._chat_timestamps)
            marker = self._record_marker(
                reason=f"Chat velocity burst ({count} msgs in {self.burst_window_sec:.0f}s)",
                category="chat_burst",
                source=str(payload.get("source") or "chat"),
                user=str(payload.get("user") or "Chat"),
                details={"message_count": count, "window_sec": self.burst_window_sec},
                now=now,
            )
            if marker is not None:
                self._chat_timestamps.clear()

    def _on_donation_received(self, _event_name: str, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        user = str(payload.get("user") or "Viewer")
        amount = payload.get("amount", "")
        currency = str(payload.get("currency") or "")
        amount_label = f"{amount} {currency}".strip() or "SuperChat"
        self._record_marker(
            reason=f"SuperChat / Donation from {user} ({amount_label})",
            category="donation",
            source="donation",
            user=user,
            details={"amount": amount, "currency": currency, "text": payload.get("text", "")},
        )

    def _on_voice_barge_in(self, _event_name: str, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        user = str(payload.get("user") or "Creator")
        self._record_marker(
            reason=f"Voice barge-in by {user}",
            category="barge_in",
            source="voice",
            user=user,
            details=dict(payload),
        )

    def _on_goal_completed(self, _event_name: str, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        if payload.get("goal_completed") is False:
            return
        goal_title = str(payload.get("title") or payload.get("goal") or "Autonomous Goal")
        self._record_marker(
            reason=f"Goal completed: {goal_title}",
            category="goal_completed",
            source="planning",
            user="Eve",
            details=dict(payload),
        )

    def _on_mood_updated(self, _event_name: str, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        dims = payload.get("dimensions")
        excitement = None
        if isinstance(dims, dict) and "excitement" in dims:
            excitement = dims.get("excitement")
        elif "excitement" in payload:
            excitement = payload.get("excitement")

        if excitement is None:
            return
        try:
            exc_val = float(excitement)
        except (TypeError, ValueError):
            return

        if exc_val >= self.excitement_threshold:
            dominant = str(payload.get("dominant_mood") or "HYPE_EXCITED")
            self._record_marker(
                reason=f"High-excitement mood spike ({dominant}, {exc_val:.2f})",
                category="mood_spike",
                source="mood",
                user="Eve",
                details={"excitement": exc_val, "dominant_mood": dominant},
            )

    def _on_performance_updated(self, _event_name: str, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        is_highlight = bool(payload.get("is_highlight") or payload.get("highlight"))
        hype_val = payload.get("excitement", payload.get("energy", payload.get("hype")))
        high_energy = False
        if hype_val is not None:
            try:
                high_energy = float(hype_val) >= self.excitement_threshold
            except (TypeError, ValueError):
                high_energy = False

        if not (is_highlight or high_energy):
            return

        label = str(payload.get("reason") or payload.get("event") or payload.get("stage") or "Performance peak")
        self._record_marker(
            reason=f"Performance highlight: {label}",
            category="performance",
            source="performance",
            user="Eve",
            details=dict(payload),
        )

    def mark_manual(
        self,
        reason: str = "Manual highlight",
        user: str = "Creator",
        details: Optional[Dict[str, Any]] = None,
    ) -> HighlightMarker:
        """Manually mark a highlight moment regardless of cooldown."""
        marker = self._record_marker(
            reason=str(reason or "Manual highlight"),
            category="manual",
            source="manual",
            user=str(user or "Creator"),
            details=details,
            is_manual=True,
        )
        assert marker is not None
        return marker

    def update_config(
        self,
        enabled: Optional[bool] = None,
        chat_burst_threshold: Optional[int] = None,
        burst_window_sec: Optional[float] = None,
        cooldown_sec: Optional[float] = None,
        excitement_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Update detector configuration dynamically."""
        if enabled is not None:
            self.enabled = bool(enabled)
        if chat_burst_threshold is not None:
            self.chat_burst_threshold = max(1, int(chat_burst_threshold))
        if burst_window_sec is not None:
            self.burst_window_sec = max(1.0, float(burst_window_sec))
        if cooldown_sec is not None:
            self.cooldown_sec = max(0.0, float(cooldown_sec))
        if excitement_threshold is not None:
            self.excitement_threshold = max(0.0, min(1.0, float(excitement_threshold)))
        return self.get_status()

    def get_highlights(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return recorded highlight markers as dictionaries (oldest first, or last `limit`)."""
        items = [m.to_dict() for m in self._markers]
        if limit is not None and limit >= 0:
            return items[-int(limit):] if limit > 0 else []
        return items

    def get_status(self) -> Dict[str, Any]:
        """Return current detector configuration and telemetry."""
        now = time.time()
        cooldown_remaining = 0.0
        if self._last_auto_highlight_at > 0.0 and self.cooldown_sec > 0.0:
            cooldown_remaining = max(0.0, self.cooldown_sec - (now - self._last_auto_highlight_at))

        return {
            "enabled": self.enabled,
            "subscribed": self._subscribed,
            "chat_burst_threshold": self.chat_burst_threshold,
            "burst_window_sec": self.burst_window_sec,
            "cooldown_sec": self.cooldown_sec,
            "excitement_threshold": self.excitement_threshold,
            "cooldown_remaining_sec": round(cooldown_remaining, 2),
            "total_highlights": len(self._markers),
            "recent_highlights": self.get_highlights(limit=5),
        }
