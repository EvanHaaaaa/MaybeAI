import time
import uuid
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional


class PermissionCategory(str, Enum):
    APP_LAUNCH = "app_launch"              # Izin membuka aplikasi desktop
    MEDIA_CONTROL = "media_control"        # Izin mengontrol media player (play, pause, next)
    VOLUME_CONTROL = "volume_control"      # Izin mengatur volume sistem & mute
    NOTIFICATIONS_READ = "notifications_read" # Izin membaca notifikasi tertentu
    STREAMING_OPS = "streaming_ops"        # Izin mengelola OBS / streaming scenes


class RiskLevel(str, Enum):
    SAFE = "safe"                          # Query read-only, cek volume/status
    LOW = "low"                            # Play/pause lagu, naik/turun volume sedikit
    MEDIUM = "medium"                      # Buka aplikasi terdaftar, baca notifikasi privat
    HIGH = "high"                          # Tutup aplikasi, ganti scene live OBS, mulai/stop stream


class ActionStatus(str, Enum):
    PENDING = "pending"                    # Menunggu konfirmasi pengguna
    APPROVED = "approved"                  # Disetujui oleh pengguna
    REJECTED = "rejected"                  # Ditolak oleh pengguna
    EXECUTED = "executed"                  # Berhasil dieksekusi
    BLOCKED = "blocked"                    # Ditolak otomatis karena izin kategori mati
    FAILED = "failed"                      # Gagal saat eksekusi teknis


@dataclass
class DesktopPermissionConfig:
    master_enabled: bool = True
    categories: Dict[str, bool] = field(default_factory=lambda: {
        PermissionCategory.APP_LAUNCH.value: True,
        PermissionCategory.MEDIA_CONTROL.value: True,
        PermissionCategory.VOLUME_CONTROL.value: True,
        PermissionCategory.NOTIFICATIONS_READ.value: True,
        PermissionCategory.STREAMING_OPS.value: False   # Default protektif untuk siaran langsung
    })
    require_confirmation_for_medium: bool = False
    require_confirmation_for_high: bool = True          # Tindakan berisiko tinggi wajib konfirmasi
    allowed_apps: List[str] = field(default_factory=lambda: [
        "obs64.exe",
        "spotify.exe",
        "discord.exe",
        "chrome.exe",
        "notepad.exe",
        "calc.exe"
    ])
    current_volume: int = 50                            # 0 to 100
    is_muted: bool = False
    media_state: str = "paused"                         # "playing", "paused", "stopped"
    current_track: str = "ChilledCow - Lofi Girl Beats"
    streaming_scene: str = "Just Chatting"
    is_streaming: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesktopPermissionConfig":
        return cls(**data)


@dataclass
class DesktopActionRequest:
    id: str = field(default_factory=lambda: f"act_{uuid.uuid4().hex[:8]}")
    category: str = PermissionCategory.VOLUME_CONTROL.value
    action_type: str = "set_volume"
    params: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = RiskLevel.LOW.value
    status: str = ActionStatus.EXECUTED.value
    requested_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    details: str = "Menyesuaikan volume suara sistem."
    result_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "action_type": self.action_type,
            "params": self.params,
            "risk_level": self.risk_level,
            "status": self.status,
            "requested_at": self.requested_at,
            "requested_at_str": time.strftime("%H:%M:%S", time.localtime(self.requested_at)),
            "resolved_at": self.resolved_at,
            "details": self.details,
            "result_summary": self.result_summary
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesktopActionRequest":
        clean = {k: v for k, v in data.items() if k != "requested_at_str"}
        return cls(**clean)


@dataclass
class DesktopNotification:
    id: str = field(default_factory=lambda: f"notif_{uuid.uuid4().hex[:6]}")
    source: str = "Discord"
    title: str = "Pesan Masuk"
    body: str = "Chatter: Eve, kapan stream Minecraft bareng squad lagi?"
    timestamp: float = field(default_factory=time.time)
    is_read: bool = False
    is_allowed: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "body": self.body,
            "timestamp": self.timestamp,
            "time_str": time.strftime("%H:%M:%S", time.localtime(self.timestamp)),
            "is_read": self.is_read,
            "is_allowed": self.is_allowed
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesktopNotification":
        clean = {k: v for k, v in data.items() if k != "time_str"}
        return cls(**clean)
