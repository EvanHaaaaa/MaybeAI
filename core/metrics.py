import ctypes
import os
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional


def _get_rss_mb() -> float:
    """Returns current process resident set size (RSS) in megabytes."""
    try:
        import psutil  # type: ignore

        return round(psutil.Process(os.getpid()).memory_info().rss / (1024.0 * 1024.0), 3)
    except Exception:
        pass

    if sys.platform.startswith("win"):
        try:
            class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = _PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return round(counters.WorkingSetSize / (1024.0 * 1024.0), 3)
        except Exception:
            pass
        return 0.0

    try:
        import resource  # type: ignore

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes; Linux reports kilobytes.
        divisor = (1024.0 * 1024.0) if sys.platform == "darwin" else 1024.0
        return round(usage / divisor, 3)
    except Exception:
        return 0.0


@dataclass
class _HistogramTracker:
    """Bounded sample tracker for latency/duration observations."""

    max_samples: int = 1000
    samples: Deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    count: int = 0
    total: float = 0.0
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    last_val: Optional[float] = None

    def __post_init__(self) -> None:
        if self.samples.maxlen != self.max_samples:
            self.samples = deque(self.samples, maxlen=self.max_samples)

    def observe(self, value: float) -> None:
        val = float(value)
        self.samples.append(val)
        self.count += 1
        self.total += val
        self.last_val = val
        self.min_val = val if self.min_val is None else min(self.min_val, val)
        self.max_val = val if self.max_val is None else max(self.max_val, val)

    def _percentile(self, pct: float) -> float:
        if not self.samples:
            return 0.0
        ordered = sorted(self.samples)
        idx = int(round((pct / 100.0) * (len(ordered) - 1)))
        idx = max(0, min(len(ordered) - 1, idx))
        return round(ordered[idx], 3)

    def to_dict(self) -> Dict[str, Any]:
        if self.count == 0:
            return {
                "count": 0,
                "min_ms": 0.0,
                "max_ms": 0.0,
                "avg_ms": 0.0,
                "p50_ms": 0.0,
                "p95_ms": 0.0,
                "last_ms": 0.0,
            }
        return {
            "count": self.count,
            "min_ms": round(self.min_val or 0.0, 3),
            "max_ms": round(self.max_val or 0.0, 3),
            "avg_ms": round(self.total / self.count, 3),
            "p50_ms": self._percentile(50.0),
            "p95_ms": self._percentile(95.0),
            "last_ms": round(self.last_val or 0.0, 3),
        }


class MetricsCollector:
    """
    Lightweight structured observability collector tracking counters, gauges,
    latency histograms, process RSS memory, and uptime.
    """

    DEFAULT_COUNTERS = (
        "event_bus_published",
        "event_bus_errors",
        "llm_requests",
        "llm_failovers",
    )
    DEFAULT_GAUGES = (
        "active_ws_clients",
        "bg_tasks_active",
    )
    DEFAULT_HISTOGRAMS = (
        "tts_latency_ms",
        "stt_latency_ms",
    )

    def __init__(self, max_samples: int = 1000) -> None:
        self._start_monotonic: float = time.monotonic()
        self._max_samples: int = max(10, int(max_samples))
        self._counters: Dict[str, int] = {name: 0 for name in self.DEFAULT_COUNTERS}
        self._gauges: Dict[str, float] = {name: 0 for name in self.DEFAULT_GAUGES}
        self._histograms: Dict[str, _HistogramTracker] = {
            name: _HistogramTracker(max_samples=self._max_samples)
            for name in self.DEFAULT_HISTOGRAMS
        }

    def inc(self, name: str, amount: int = 1) -> int:
        """Increments a counter by `amount` and returns the new value."""
        new_val = self._counters.get(name, 0) + int(amount)
        self._counters[name] = new_val
        return new_val

    def set_counter(self, name: str, value: int) -> None:
        """Sets a counter to an explicit integer value."""
        self._counters[name] = int(value)

    def get_counter(self, name: str) -> int:
        """Returns the current value of counter `name`."""
        return self._counters.get(name, 0)

    def set_gauge(self, name: str, value: float) -> None:
        """Sets a gauge metric to `value`."""
        self._gauges[name] = value

    def get_gauge(self, name: str, default: float = 0.0) -> float:
        """Returns the current value of gauge `name`."""
        return self._gauges.get(name, default)

    def observe(self, name: str, value_ms: float) -> None:
        """Records a latency/duration observation in milliseconds."""
        tracker = self._histograms.get(name)
        if tracker is None:
            tracker = _HistogramTracker(max_samples=self._max_samples)
            self._histograms[name] = tracker
        tracker.observe(value_ms)

    def record_latency(self, name: str, value_ms: float) -> None:
        """Alias for `observe(name, value_ms)`."""
        self.observe(name, value_ms)

    def get_uptime_sec(self) -> float:
        """Returns collector uptime in seconds."""
        return round(max(0.0, time.monotonic() - self._start_monotonic), 3)

    def get_rss_mb(self) -> float:
        """Returns current process RSS memory in megabytes."""
        return _get_rss_mb()

    def snapshot(self) -> Dict[str, Any]:
        """Returns a JSON-serializable snapshot of all metrics."""
        uptime_sec = self.get_uptime_sec()
        rss_mb = self.get_rss_mb()
        gauges = dict(self._gauges)
        gauges["rss_mb"] = rss_mb
        gauges["uptime_sec"] = uptime_sec

        return {
            "uptime_sec": uptime_sec,
            "rss_mb": rss_mb,
            "counters": dict(self._counters),
            "gauges": gauges,
            "histograms": {name: tracker.to_dict() for name, tracker in self._histograms.items()},
        }
