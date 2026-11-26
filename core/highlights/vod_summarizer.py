"""Session VOD Summarizer writing Markdown reports to Second Brain."""

import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.event_bus import CHAT_RECEIVED, DONATION_RECEIVED, SONG_STARTED

GOAL_COMPLETED = "goal.completed"
HIGHLIGHT_MARKED = "highlight.marked"
VOD_SUMMARY_READY = "vod.summary_ready"


class VODSummarizer:
    """
    Tracks stream session metrics and writes a Markdown VOD summary to
    `data/second_brain/streams/YYYY-MM-DD.md` (with unique suffix if needed).
    """

    def __init__(
        self,
        streams_dir: str = "data/second_brain/streams",
        event_bus: Any = None,
    ):
        self.streams_dir = Path(streams_dir)
        self.event_bus = event_bus
        self.start_time: float = time.time()
        self.session_title: str = "Eve Maybe Live Stream"
        self.chat_count: int = 0
        self.top_chatters: Counter[str] = Counter()
        self.donations: List[Dict[str, Any]] = []
        self.goals_completed: List[Dict[str, Any]] = []
        self.songs_performed: List[Dict[str, Any]] = []
        self.highlights: List[Dict[str, Any]] = []

        if self.event_bus is not None:
            self.subscribe(self.event_bus)

    def subscribe(self, event_bus: Any) -> None:
        """Optionally subscribe to EventBus events to track session metrics automatically."""
        if event_bus is None:
            return
        self.event_bus = event_bus
        event_bus.subscribe(CHAT_RECEIVED, self._on_chat)
        event_bus.subscribe(DONATION_RECEIVED, self._on_donation)
        event_bus.subscribe(GOAL_COMPLETED, self._on_goal)
        event_bus.subscribe(SONG_STARTED, self._on_song)
        event_bus.subscribe(HIGHLIGHT_MARKED, self._on_highlight)

    def start_session(
        self,
        title: Optional[str] = None,
        start_time: Optional[float] = None,
    ) -> None:
        """Reset session counters for a new stream."""
        self.start_time = float(start_time if start_time is not None else time.time())
        self.session_title = str(title or "Eve Maybe Live Stream")
        self.chat_count = 0
        self.top_chatters.clear()
        self.donations.clear()
        self.goals_completed.clear()
        self.songs_performed.clear()
        self.highlights.clear()

    def record_chat(self, user: str, _text: str = "") -> None:
        self.chat_count += 1
        chatter = str(user or "Anonymous").strip() or "Anonymous"
        self.top_chatters[chatter] += 1

    def record_donation(
        self,
        user: str,
        amount: Any,
        currency: str = "",
        text: str = "",
        timestamp: Optional[float] = None,
    ) -> None:
        self.donations.append({
            "user": str(user or "Anonymous"),
            "amount": amount,
            "currency": str(currency or ""),
            "text": str(text or ""),
            "timestamp": float(timestamp if timestamp is not None else time.time()),
        })

    def record_goal_completed(
        self,
        title: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.goals_completed.append({
            "title": str(title or "Goal"),
            "details": dict(details or {}),
            "timestamp": time.time(),
        })

    def record_song(self, title: str, artist: str = "") -> None:
        self.songs_performed.append({
            "title": str(title or "Untitled Song"),
            "artist": str(artist or ""),
            "timestamp": time.time(),
        })

    def record_highlight(self, marker: Any) -> None:
        if hasattr(marker, "to_dict"):
            data = marker.to_dict()
        elif isinstance(marker, dict):
            data = dict(marker)
        else:
            data = {"reason": str(marker), "timestamp": time.time()}
        self.highlights.append(data)

    def _on_chat(self, _event_name: str, payload: Dict[str, Any]) -> None:
        self.record_chat(
            user=str(payload.get("user") or "Anonymous"),
            _text=str(payload.get("text") or ""),
        )

    def _on_donation(self, _event_name: str, payload: Dict[str, Any]) -> None:
        self.record_donation(
            user=str(payload.get("user") or "Anonymous"),
            amount=payload.get("amount", ""),
            currency=str(payload.get("currency") or ""),
            text=str(payload.get("text") or ""),
        )

    def _on_goal(self, _event_name: str, payload: Dict[str, Any]) -> None:
        if payload.get("goal_completed") is False:
            return
        self.record_goal_completed(
            title=str(payload.get("title") or payload.get("goal") or "Autonomous Goal"),
            details=payload,
        )

    def _on_song(self, _event_name: str, payload: Dict[str, Any]) -> None:
        self.record_song(
            title=str(payload.get("title") or payload.get("song") or "Untitled Song"),
            artist=str(payload.get("artist") or ""),
        )

    def _on_highlight(self, _event_name: str, payload: Dict[str, Any]) -> None:
        self.record_highlight(payload)

    def _resolve_output_path(self, date_str: str) -> Path:
        self.streams_dir.mkdir(parents=True, exist_ok=True)
        candidate = self.streams_dir / f"{date_str}.md"
        if not candidate.exists():
            return candidate
        idx = 2
        while True:
            suffixed = self.streams_dir / f"{date_str}_{idx}.md"
            if not suffixed.exists():
                return suffixed
            idx += 1

    def get_stats(self, end_time: Optional[float] = None) -> Dict[str, Any]:
        end_ts = float(end_time if end_time is not None else time.time())
        duration_sec = max(0.0, end_ts - self.start_time)
        top_list = [
            {"user": user, "messages": count}
            for user, count in self.top_chatters.most_common(10)
        ]
        return {
            "title": self.session_title,
            "start_time": self.start_time,
            "end_time": end_ts,
            "duration_sec": round(duration_sec, 2),
            "chat_count": self.chat_count,
            "unique_chatters": len(self.top_chatters),
            "top_chatters": top_list,
            "donation_count": len(self.donations),
            "donations": list(self.donations),
            "goals_completed_count": len(self.goals_completed),
            "goals_completed": list(self.goals_completed),
            "songs_performed_count": len(self.songs_performed),
            "songs_performed": list(self.songs_performed),
            "highlights_count": len(self.highlights),
            "highlights": list(self.highlights),
        }

    def generate_summary(
        self,
        end_time: Optional[float] = None,
        title: Optional[str] = None,
        event_bus: Any = None,
    ) -> Dict[str, Any]:
        """
        Compile session metrics into a Markdown VOD summary file and return
        `{path, markdown, stats}`.
        """
        if title:
            self.session_title = str(title)
        stats = self.get_stats(end_time=end_time)
        start_dt = datetime.fromtimestamp(self.start_time, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(stats["end_time"], tz=timezone.utc)
        date_str = start_dt.strftime("%Y-%m-%d")

        mins, secs = divmod(int(stats["duration_sec"]), 60)
        hours, mins = divmod(mins, 60)
        duration_fmt = f"{hours:02d}:{mins:02d}:{secs:02d}"

        lines: List[str] = [
            f"# VOD Summary: {self.session_title} ({date_str})",
            "",
            "## Session Overview",
            f"- **Start (UTC):** {start_dt.isoformat()}",
            f"- **End (UTC):** {end_dt.isoformat()}",
            f"- **Duration:** {duration_fmt}",
            f"- **Total Chat Messages:** {stats['chat_count']}",
            f"- **Unique Chatters:** {stats['unique_chatters']}",
            f"- **Highlights Marked:** {stats['highlights_count']}",
            f"- **Donations / SuperChats:** {stats['donation_count']}",
            f"- **Goals Completed:** {stats['goals_completed_count']}",
            f"- **Songs Performed:** {stats['songs_performed_count']}",
            "",
            "## Highlights",
        ]

        if self.highlights:
            for h in self.highlights:
                ts = float(h.get("timestamp") or self.start_time)
                offset_sec = max(0, int(ts - self.start_time))
                om, os_ = divmod(offset_sec, 60)
                oh, om = divmod(om, 60)
                reason = h.get("reason") or "Highlight"
                category = h.get("category") or "general"
                user = h.get("user") or "System"
                lines.append(f"- `[{oh:02d}:{om:02d}:{os_:02d}]` **[{category}]** {reason} *(by {user})*")
        else:
            lines.append("- No highlights recorded.")

        lines.extend(["", "## Top Chatters"])
        if stats["top_chatters"]:
            for idx, entry in enumerate(stats["top_chatters"], start=1):
                lines.append(f"{idx}. **{entry['user']}** — {entry['messages']} messages")
        else:
            lines.append("- No chat messages recorded.")

        lines.extend(["", "## Donations & SuperChats"])
        if self.donations:
            for d in self.donations:
                amt = f"{d['amount']} {d['currency']}".strip()
                msg = f": {d['text']}" if d.get("text") else ""
                lines.append(f"- **{d['user']}** ({amt}){msg}")
        else:
            lines.append("- No donations recorded.")

        lines.extend(["", "## Goals Completed"])
        if self.goals_completed:
            for g in self.goals_completed:
                lines.append(f"- {g['title']}")
        else:
            lines.append("- No goals completed.")

        lines.extend(["", "## Songs Performed"])
        if self.songs_performed:
            for s in self.songs_performed:
                artist = f" — {s['artist']}" if s.get("artist") else ""
                lines.append(f"- {s['title']}{artist}")
        else:
            lines.append("- No songs performed.")

        markdown = "\n".join(lines) + "\n"
        out_path = self._resolve_output_path(date_str)
        out_path.write_text(markdown, encoding="utf-8")

        bus = event_bus if event_bus is not None else self.event_bus
        if bus is not None:
            bus.publish_nowait(VOD_SUMMARY_READY, {"path": str(out_path), "stats": stats})

        return {
            "path": str(out_path),
            "markdown": markdown,
            "stats": stats,
        }
