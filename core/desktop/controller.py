import os
import re
import sys
import time
import shutil
import subprocess
from typing import Dict, Any, List, Tuple, Optional
from core.desktop.models import (
    DesktopPermissionConfig,
    DesktopNotification
)


_SHELL_METACHAR_RE = re.compile(r"[&|;$><`\\/\n\r\x00(){}\[\]*?~'\"%^!]")


class DesktopController:
    """
    Executes permitted desktop environment actions: volume adjustments,
    media player control, whitelisted application launching, notification reading,
    and streaming scene management.
    """

    def __init__(self, config: DesktopPermissionConfig):
        self.config = config
        self.notifications: List[DesktopNotification] = []
        self._seed_default_notifications()

    def _seed_default_notifications(self):
        self.notifications = [
            DesktopNotification(
                source="Discord",
                title="Pesan Baru di #squad-maybe",
                body="DiamondHunter: Eve, aku udah kumpulin 32 iron lagi buat base!"
            ),
            DesktopNotification(
                source="YouTube Studio",
                title="Milestone Baru Tercapai! 🎉",
                body="Stream kamu mencapai 2,500 penonton serentak!"
            ),
            DesktopNotification(
                source="OBS Studio",
                title="Status Siaran",
                body="Koneksi stream stabil (60 FPS, Bitrate 6000 kbps)."
            )
        ]

    # --- 1. Volume Control ---
    def set_volume(self, target_volume: int) -> Tuple[int, str]:
        clamped = max(0, min(100, int(target_volume)))
        old_vol = self.config.current_volume
        diff = clamped - old_vol
        self.config.current_volume = clamped
        self.config.is_muted = False if clamped > 0 else self.config.is_muted
        if diff != 0:
            steps = max(1, min(25, abs(diff) // 2))
            key_type = "volume_up" if diff > 0 else "volume_down"
            for _ in range(steps):
                self._send_windows_media_key(key_type)
        msg = f"Volume sistem diatur ke {clamped}%."
        return clamped, msg

    def adjust_volume(self, delta: int) -> Tuple[int, str]:
        new_vol = max(0, min(100, self.config.current_volume + int(delta)))
        self.config.current_volume = new_vol
        steps = max(1, min(15, abs(int(delta)) // 2))
        key_type = "volume_up" if delta > 0 else "volume_down"
        for _ in range(steps):
            self._send_windows_media_key(key_type)
        msg = f"Volume {'dinaikkan' if delta > 0 else 'diturunkan'} ke {new_vol}%."
        return new_vol, msg

    def toggle_mute(self) -> Tuple[bool, str]:
        self.config.is_muted = not self.config.is_muted
        self._send_windows_media_key("volume_mute")
        msg = "Volume sistem dibisukan (Muted)." if self.config.is_muted else f"Volume sistem aktif kembali ({self.config.current_volume}%)."
        return self.config.is_muted, msg

    # --- 2. Media Player Control ---
    def media_play_pause(self) -> Tuple[str, str]:
        if self.config.media_state == "playing":
            self.config.media_state = "paused"
            msg = f"Media player dijeda (Paused): '{self.config.current_track}'."
        else:
            self.config.media_state = "playing"
            msg = f"Memutar media (Playing): '{self.config.current_track}'."
        self._send_windows_media_key("play_pause")
        return self.config.media_state, msg

    def media_next_track(self, next_title: Optional[str] = None) -> Tuple[str, str]:
        tracks = [
            "ChilledCow - Lofi Girl Beats",
            "Mili - Rightfully (Eve Acoustic Cover)",
            "Kavinsky - Nightcall (Synthwave Remix)",
            "Yoasobi - Racing Into the Night (Piano ver.)"
        ]
        if next_title:
            self.config.current_track = next_title
        else:
            # Pick next track from playlist
            try:
                curr_idx = tracks.index(self.config.current_track)
                next_idx = (curr_idx + 1) % len(tracks)
                self.config.current_track = tracks[next_idx]
            except ValueError:
                self.config.current_track = tracks[0]

        self.config.media_state = "playing"
        self._send_windows_media_key("next_track")
        msg = f"Melompat ke lagu berikutnya: '{self.config.current_track}'."
        return self.config.current_track, msg

    def media_prev_track(self) -> Tuple[str, str]:
        self.config.media_state = "playing"
        self._send_windows_media_key("prev_track")
        msg = f"Mengulang / kembali ke lagu sebelumnya: '{self.config.current_track}'."
        return self.config.current_track, msg

    # --- 3. App Launch ---
    def _resolve_known_app_path(self, app_exe: str) -> Optional[str]:
        which_path = shutil.which(app_exe)
        if which_path and os.path.isfile(which_path):
            return os.path.abspath(which_path)

        if sys.platform != "win32":
            return None

        exe_lower = app_exe.lower()
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        app_data = os.environ.get("APPDATA", "")

        known_candidates: Dict[str, List[str]] = {
            "notepad.exe": [os.path.join(system_root, "System32", "notepad.exe")],
            "calc.exe": [os.path.join(system_root, "System32", "calc.exe")],
            "chrome.exe": [
                os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            ],
            "obs64.exe": [
                os.path.join(program_files, "obs-studio", "bin", "64bit", "obs64.exe"),
                os.path.join(program_files_x86, "obs-studio", "bin", "64bit", "obs64.exe"),
            ],
            "spotify.exe": [
                os.path.join(app_data, "Spotify", "Spotify.exe"),
                os.path.join(local_app_data, "Microsoft", "WindowsApps", "Spotify.exe"),
            ],
            "discord.exe": [
                os.path.join(local_app_data, "Discord", "Update.exe"),
            ],
        }
        for candidate in known_candidates.get(exe_lower, []):
            if candidate and os.path.isfile(candidate):
                return os.path.abspath(candidate)
        return None

    def launch_app(self, app_name: str) -> Tuple[bool, str]:
        if not isinstance(app_name, str) or not app_name.strip():
            return False, "Nama aplikasi tidak boleh kosong."

        clean = app_name.strip()
        if ".." in clean or _SHELL_METACHAR_RE.search(clean):
            return False, f"Target aplikasi '{clean}' ditolak karena mengandung karakter tidak aman."

        allowed_map: Dict[str, str] = {}
        for entry in self.config.allowed_apps:
            a_clean = str(entry).strip()
            if not a_clean or ".." in a_clean or _SHELL_METACHAR_RE.search(a_clean):
                continue
            allowed_map[a_clean.lower()] = a_clean

        clean_lower = clean.lower()
        matched = allowed_map.get(clean_lower)
        if not matched and not clean_lower.endswith((".exe", ".lnk")):
            matched = allowed_map.get(f"{clean_lower}.exe")

        if not matched:
            return False, f"Aplikasi '{clean}' tidak diizinkan oleh whitelist."

        resolved_path = self._resolve_known_app_path(matched)
        if not resolved_path:
            return False, f"Aplikasi '{matched}' tidak ditemukan di jalur sistem yang dikenal."

        try:
            if sys.platform == "win32" and resolved_path.lower().endswith(".lnk"):
                os.startfile(resolved_path)
            else:
                subprocess.Popen([resolved_path])
            return True, f"Aplikasi '{matched}' berhasil diluncurkan di desktop."
        except Exception as e:
            return False, f"Gagal membuka aplikasi '{clean}': {e}"

    # --- 4. Streaming Ops ---
    def switch_streaming_scene(self, scene_name: str) -> Tuple[str, str]:
        self.config.streaming_scene = scene_name
        msg = f"Scene OBS berhasil dialihkan ke: '{scene_name}'."
        return scene_name, msg

    def toggle_streaming(self) -> Tuple[bool, str]:
        self.config.is_streaming = not self.config.is_streaming
        msg = "Siaran langsung (Live Stream) DIMULAI! 🎉" if self.config.is_streaming else "Siaran langsung DIHENTIKAN."
        return self.config.is_streaming, msg

    # --- 5. Notifications ---
    def get_unread_notifications(self) -> List[DesktopNotification]:
        return [n for n in self.notifications if not n.is_read and n.is_allowed]

    def mark_all_read(self):
        for n in self.notifications:
            n.is_read = True

    def add_notification(self, source: str, title: str, body: str) -> DesktopNotification:
        notif = DesktopNotification(source=source, title=title, body=body)
        self.notifications.insert(0, notif)
        if len(self.notifications) > 20:
            self.notifications.pop()
        return notif

    # --- Helper: Windows Virtual Media Key Events ---
    def _send_windows_media_key(self, key_type: str):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            # Virtual-Key codes
            vk_map = {
                "volume_mute": 0xAD,
                "volume_down": 0xAE,
                "volume_up": 0xAF,
                "next_track": 0xB0,
                "prev_track": 0xB1,
                "stop": 0xB2,
                "play_pause": 0xB3,
                "volume_set": 0xAF
            }
            code = vk_map.get(key_type)
            if code:
                # Key press & release simulation
                ctypes.windll.user32.keybd_event(code, 0, 0, 0)
                time.sleep(0.01)
                ctypes.windll.user32.keybd_event(code, 0, 2, 0)
        except Exception:
            pass  # Non-blocking fallback
