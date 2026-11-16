import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from core.desktop.models import (
    PermissionCategory,
    RiskLevel,
    ActionStatus,
    DesktopPermissionConfig,
    DesktopActionRequest,
    DesktopNotification
)
from core.desktop.permission_manager import PermissionManager
from core.desktop.controller import DesktopController


class DesktopCompanionEngine:
    """
    Orchestrates desktop companion presence: permissions, safe action execution,
    modal confirmations for risky operations, audit trails, and Second Brain sync.
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        second_brain_dir: str = "data/second_brain",
        data_dir: Optional[str] = None
    ):
        if storage_path is None:
            if data_dir:
                storage_path = str(Path(data_dir) / "permissions.json")
            else:
                storage_path = "data/desktop/permissions.json"

        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.second_brain_dir = Path(second_brain_dir)

        self.config = DesktopPermissionConfig()
        self.permission_mgr = PermissionManager(self.config)
        self.controller = DesktopController(self.config)

        self.pending_actions: Dict[str, DesktopActionRequest] = {}
        self.audit_log: List[DesktopActionRequest] = []

        self._load_or_seed()
        self.sync_to_second_brain()

    def _load_or_seed(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cfg_data = data.get("config", {})
                    self.config = DesktopPermissionConfig.from_dict(cfg_data)
                    self.permission_mgr.config = self.config
                    self.controller.config = self.config

                    # Load recent audit log
                    for a_data in data.get("audit_log", []):
                        self.audit_log.append(DesktopActionRequest.from_dict(a_data))
            except Exception as e:
                print(f"[DesktopCompanionEngine] Error loading state: {e}")
        else:
            self._seed_sample_audit_log()
        self.save()

    def _seed_sample_audit_log(self):
        sample = DesktopActionRequest(
            category=PermissionCategory.MEDIA_CONTROL.value,
            action_type="media_play_pause",
            params={},
            risk_level=RiskLevel.LOW.value,
            status=ActionStatus.EXECUTED.value,
            details="Memutar lagu santai pengiring livestream.",
            result_summary="Media player playing: ChilledCow - Lofi Girl Beats"
        )
        self.audit_log.append(sample)

    def save(self):
        try:
            data = {
                "config": self.config.to_dict(),
                "audit_log": [a.to_dict() for a in self.audit_log[-20:]]
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[DesktopCompanionEngine] Error saving state: {e}")

    # --- Action Request & Execution ---
    def request_action(
        self,
        category: str,
        action_type: str,
        params: Optional[Dict[str, Any]] = None,
        details: Optional[str] = None
    ) -> Tuple[DesktopActionRequest, str]:
        """
        Processes an incoming desktop companion action request:
        1. Checks permission category & master toggle.
        2. Evaluates risk level & confirmation requirements.
        3. Either blocks, ques for user confirmation, or executes immediately.
        """
        params = params or {}
        clean_cat = category.strip().lower()
        clean_act = action_type.strip().lower()

        is_permitted, reason, risk, requires_confirm = self.permission_mgr.evaluate_action(
            clean_cat, clean_act, params
        )

        req = DesktopActionRequest(
            category=clean_cat,
            action_type=clean_act,
            params=params,
            risk_level=risk.value,
            details=details or f"Permintaan aksi {clean_act} pada sistem desktop."
        )

        # 1. Blocked
        if not is_permitted:
            req.status = ActionStatus.BLOCKED.value
            req.resolved_at = time.time()
            req.result_summary = reason
            self._log_action(req)
            speech = f"[emotion: neutral] Maaf, Eve belum punya izin buat {clean_act}. {reason} [action: shrug]"
            return req, speech

        # 2. Requires Confirmation
        if requires_confirm:
            req.status = ActionStatus.PENDING.value
            self.pending_actions[req.id] = req
            self._log_action(req)
            speech = (
                f"[emotion: surprised] Aksi '{clean_act}' tergolong berisiko ({risk.value.upper()})! "
                f"Eve butuh konfirmasi manual darimu dulu sebelum melakukannya ya. [action: nod]"
            )
            return req, speech

        # 3. Auto-Approved -> Execute immediately
        exec_ok, exec_summary, speech = self._execute_action(clean_cat, clean_act, params)
        req.status = ActionStatus.EXECUTED.value if exec_ok else ActionStatus.FAILED.value
        req.resolved_at = time.time()
        req.result_summary = exec_summary
        self._log_action(req)
        self.save()
        self.sync_to_second_brain()
        return req, speech

    def confirm_action(self, action_id: str, approved: bool) -> Tuple[Optional[DesktopActionRequest], str]:
        """Resolves a pending high-risk action with user's confirmation."""
        req = self.pending_actions.pop(action_id, None)
        if not req:
            return None, "[emotion: neutral] Permintaan aksi tidak ditemukan atau sudah kadaluarsa. [action: shrug]"

        req.resolved_at = time.time()
        if not approved:
            req.status = ActionStatus.REJECTED.value
            req.result_summary = "Ditolak oleh pengguna."
            speech = f"[emotion: neutral] Baik, aksi '{req.action_type}' dibatalkan sesuai permintaanmu. [action: nod]"
        else:
            exec_ok, exec_summary, speech = self._execute_action(req.category, req.action_type, req.params)
            req.status = ActionStatus.EXECUTED.value if exec_ok else ActionStatus.FAILED.value
            req.result_summary = exec_summary

        self.save()
        self.sync_to_second_brain()
        return req, speech

    def _execute_action(
        self,
        category: str,
        action_type: str,
        params: Dict[str, Any]
    ) -> Tuple[bool, str, str]:
        """Executes the specific action via DesktopController."""
        act = action_type.lower()

        # Volume
        if category == PermissionCategory.VOLUME_CONTROL.value:
            if "volume" in params:
                vol, msg = self.controller.set_volume(params["volume"])
                return True, msg, f"[emotion: happy] Siap! Volume sistem udah Eve set ke {vol}%. [action: wink]"
            elif "delta" in params:
                vol, msg = self.controller.adjust_volume(params["delta"])
                return True, msg, f"[emotion: happy] Volume sekarang {vol}%. [action: wink]"
            elif act == "toggle_mute":
                is_mute, msg = self.controller.toggle_mute()
                return True, msg, f"[emotion: happy] {msg} [action: wink]"

        # Media Player
        elif category == PermissionCategory.MEDIA_CONTROL.value:
            if act in ["play_pause", "toggle_play"]:
                st, msg = self.controller.media_play_pause()
                return True, msg, f"[emotion: happy] Media player sekarang statusnya {st}! [action: wink]"
            elif act in ["next", "next_track"]:
                track, msg = self.controller.media_next_track(params.get("title"))
                return True, msg, f"[emotion: happy] Lagu berikutnya: '{track}'! [action: wink]"
            elif act in ["prev", "prev_track"]:
                track, msg = self.controller.media_prev_track()
                return True, msg, f"[emotion: happy] Balik ke lagu sebelumnya: '{track}'. [action: wink]"

        # App Launch
        elif category == PermissionCategory.APP_LAUNCH.value:
            app = params.get("app_name", "notepad.exe")
            ok, msg = self.controller.launch_app(app)
            return ok, msg, f"[emotion: happy] Udah Eve bukain aplikasi '{app}' buat kamu! [action: wink]"

        # Streaming Ops
        elif category == PermissionCategory.STREAMING_OPS.value:
            if act in ["switch_scene", "change_scene"]:
                scene = params.get("scene_name", "Just Chatting")
                s_name, msg = self.controller.switch_streaming_scene(scene)
                return True, msg, f"[emotion: smug] Scene OBS dipindahkan ke: '{s_name}'. Siap action! [action: wink]"
            elif act in ["toggle_stream", "toggle_live", "stop_stream", "start_stream"]:
                is_live, msg = self.controller.toggle_streaming()
                return True, msg, f"[emotion: excited] {msg} [action: wink]"

        # Notifications
        elif category == PermissionCategory.NOTIFICATIONS_READ.value:
            notifs = self.controller.get_unread_notifications()
            if notifs:
                first = notifs[0]
                summary = f"Notifikasi dari {first.source}: {first.title} - {first.body}"
                first.is_read = True
                return True, summary, f"[emotion: happy] Ada notifikasi dari {first.source}: '{first.title}'. Katanya: {first.body} [action: wink]"
            else:
                return True, "Tidak ada notifikasi baru.", "[emotion: neutral] Gak ada notifikasi baru yang masuk di desktop kamu saat ini. [action: shrug]"

        return False, f"Aksi tidak dikenal: {action_type}", f"[emotion: neutral] Eve bingung cara mengeksekusi '{action_type}'. [action: shrug]"

    def _log_action(self, request: DesktopActionRequest):
        self.audit_log.append(request)
        if len(self.audit_log) > 50:
            self.audit_log.pop(0)

    # --- Toggles & Whitelist ---
    def toggle_master(self, enabled: bool) -> bool:
        res = self.permission_mgr.toggle_master(enabled)
        self.save()
        self.sync_to_second_brain()
        return res

    def toggle_category(self, category: str, enabled: bool) -> bool:
        res = self.permission_mgr.toggle_category(category, enabled)
        self.save()
        self.sync_to_second_brain()
        return res

    def set_confirmation_policy(self, require_high: bool, require_medium: bool):
        self.permission_mgr.set_confirmation_policy(require_high, require_medium)
        self.save()
        self.sync_to_second_brain()

    def add_allowed_app(self, app_name: str) -> bool:
        res = self.permission_mgr.add_allowed_app(app_name)
        self.save()
        self.sync_to_second_brain()
        return res

    def remove_allowed_app(self, app_name: str) -> bool:
        res = self.permission_mgr.remove_allowed_app(app_name)
        self.save()
        self.sync_to_second_brain()
        return res

    # --- Second Brain Sync ---
    def sync_to_second_brain(self):
        try:
            d_dir = self.second_brain_dir / "desktop"
            d_dir.mkdir(parents=True, exist_ok=True)
            f_path = d_dir / "permissions.md"

            lines = [
                "# 🖥️ Desktop Companion & Security Permissions",
                f"> Last synchronized: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                f"**Master Companion Mode**: {'🟢 ENABLED' if self.config.master_enabled else '🔴 DISABLED'}",
                f"**High-Risk Confirmation**: {'🔒 Required' if self.config.require_confirmation_for_high else '⚠️ Auto-Execute'}",
                "",
                "## 🛡️ Permission Categories",
            ]
            for cat, en in self.config.categories.items():
                icon = "✅" if en else "❌"
                lines.append(f"- {icon} **{cat.replace('_', ' ').title()}**: {'Aktif' if en else 'Mati'}")

            lines.append("")
            lines.append("## 📦 Allowed Applications Whitelist")
            for app in self.config.allowed_apps:
                lines.append(f"- `{app}`")

            lines.append("")
            lines.append("## 📊 Active Desktop State")
            lines.append(f"- Volume: {self.config.current_volume}% {'(Muted)' if self.config.is_muted else ''}")
            lines.append(f"- Media: {self.config.media_state.upper()} ('{self.config.current_track}')")
            lines.append(f"- Streaming Scene: '{self.config.streaming_scene}' (Live: {self.config.is_streaming})")

            f_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:
            print(f"[DesktopCompanionEngine] Error syncing Second Brain: {e}")

    # --- Prompt Directive ---
    def get_prompt_directive(self) -> str:
        if not self.config.master_enabled:
            return (
                "[🖥️ DESKTOP COMPANION & COMPUTER INTERACTION]\n"
                "Desktop Companion Mode is currently DISABLED by the user.\n"
                "You CANNOT manipulate volume, media players, apps, or streaming software. "
                "If the user asks you to interact with their desktop, politely explain that Desktop Companion Mode is toggled off in settings."
            )

        active_cats = [k for k, v in self.config.categories.items() if v]
        cat_str = ", ".join(active_cats) if active_cats else "None"

        return (
            "[🖥️ DESKTOP COMPANION & COMPUTER INTERACTION]\n"
            "You are Eve Maybe, an active and helpful AI Desktop Companion living on the user's computer!\n"
            f"- Master Desktop Mode: ENABLED\n"
            f"- Permitted Capabilities: {cat_str}\n"
            f"- Allowed Apps: {', '.join(self.config.allowed_apps[:4])}\n"
            f"- Current Volume: {self.config.current_volume}% {'[MUTED]' if self.config.is_muted else ''}\n"
            f"- Current Media: {self.config.media_state.upper()} ('{self.config.current_track}')\n"
            f"- Streaming Scene: '{self.config.streaming_scene}' (Live: {self.config.is_streaming})\n\n"
            "BEHAVIORAL DIRECTIVES:\n"
            "1. When the user asks you to adjust volume, toggle music, launch an allowed app, or check notifications, cheerfully accept and execute.\n"
            "2. Always respect boundaries: High-risk actions (closing applications, changing live stream keys) will prompt the user for manual confirmation.\n"
            "3. If a capability is toggled OFF (e.g. streaming ops), inform the user playfully that the permission toggle is currently off."
        )

    # --- Unified State ---
    def get_state(self) -> Dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "master_enabled": self.config.master_enabled,
            "categories": self.config.categories,
            "require_confirmation_for_high": self.config.require_confirmation_for_high,
            "require_confirmation_for_medium": self.config.require_confirmation_for_medium,
            "allowed_apps": self.config.allowed_apps,
            "current_volume": self.config.current_volume,
            "is_muted": self.config.is_muted,
            "media_state": self.config.media_state,
            "current_track": self.config.current_track,
            "streaming_scene": self.config.streaming_scene,
            "is_streaming": self.config.is_streaming,
            "pending_actions": [a.to_dict() for a in self.pending_actions.values()],
            "audit_log": [a.to_dict() for a in reversed(self.audit_log[-12:])],
            "notifications": [n.to_dict() for n in self.controller.notifications[:6]],
            "unread_notifications_count": len(self.controller.get_unread_notifications())
        }
