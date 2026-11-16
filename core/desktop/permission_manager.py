import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from core.desktop.models import (
    PermissionCategory,
    RiskLevel,
    DesktopPermissionConfig
)


class PermissionManager:
    """
    Manages security boundaries, granular toggle states, app whitelists,
    and risk assessment for desktop actions.
    """

    def __init__(self, config: Optional[DesktopPermissionConfig] = None):
        self.config = config or DesktopPermissionConfig()

    def toggle_master(self, enabled: bool) -> bool:
        """Enables or disables all desktop companion interactions."""
        self.config.master_enabled = bool(enabled)
        return self.config.master_enabled

    def toggle_category(self, category: str, enabled: bool) -> bool:
        """Toggles a specific permission category."""
        clean_cat = category.strip().lower()
        if clean_cat in self.config.categories:
            self.config.categories[clean_cat] = bool(enabled)
            return True
        return False

    def is_category_enabled(self, category: str) -> bool:
        if not self.config.master_enabled:
            return False
        return self.config.categories.get(category.strip().lower(), False)

    def set_confirmation_policy(self, require_high: bool, require_medium: bool):
        self.config.require_confirmation_for_high = bool(require_high)
        self.config.require_confirmation_for_medium = bool(require_medium)

    def add_allowed_app(self, app_name: str) -> bool:
        clean = app_name.strip().lower()
        if clean and clean not in [a.lower() for a in self.config.allowed_apps]:
            self.config.allowed_apps.append(clean)
            return True
        return False

    def remove_allowed_app(self, app_name: str) -> bool:
        clean = app_name.strip().lower()
        for i, a in enumerate(self.config.allowed_apps):
            if a.lower() == clean:
                self.config.allowed_apps.pop(i)
                return True
        return False

    def evaluate_action(
        self,
        category: str,
        action_type: str,
        params: Dict[str, Any]
    ) -> Tuple[bool, str, RiskLevel, bool]:
        """
        Evaluates an action request against active security policies.
        Returns:
            (is_permitted, reason, risk_level, requires_confirmation)
        """
        # 1. Master toggle check
        if not self.config.master_enabled:
            return False, "Desktop Companion Mode dinonaktifkan oleh pengguna.", RiskLevel.SAFE, False

        # 2. Category check
        clean_cat = category.strip().lower()
        if not self.config.categories.get(clean_cat, False):
            return False, f"Izin untuk kategori '{clean_cat}' belum diaktifkan.", RiskLevel.SAFE, False

        # 3. Risk Level Assessment
        risk = self._determine_risk_level(clean_cat, action_type, params)

        # 4. Whitelist check for App Launch
        if clean_cat == PermissionCategory.APP_LAUNCH.value:
            app_target = str(params.get("app_name", "")).strip().lower()
            allowed = [a.lower() for a in self.config.allowed_apps]
            if app_target not in allowed and not any(a.startswith(app_target) for a in allowed):
                # Unwhitelisted apps are either blocked or treated as high-risk confirmation
                if self.config.require_confirmation_for_high:
                    return True, f"Aplikasi '{app_target}' di luar whitelist, membutuhkan izin manual.", RiskLevel.HIGH, True
                else:
                    return False, f"Aplikasi '{app_target}' tidak terdaftar dalam whitelist yang diizinkan.", RiskLevel.HIGH, False

        # 5. Confirmation Requirement Check
        requires_confirm = False
        if risk == RiskLevel.HIGH and self.config.require_confirmation_for_high:
            requires_confirm = True
        elif risk == RiskLevel.MEDIUM and self.config.require_confirmation_for_medium:
            requires_confirm = True

        reason = "Aksi disetujui untuk dieksekusi." if not requires_confirm else "Aksi berisiko membutuhkan konfirmasi manual dari pengguna."
        return True, reason, risk, requires_confirm

    def _determine_risk_level(self, category: str, action_type: str, params: Dict[str, Any]) -> RiskLevel:
        act = action_type.strip().lower()

        # Streaming Operations are typically HIGH risk (affecting live broadcast)
        if category == PermissionCategory.STREAMING_OPS.value:
            if act in ["stop_stream", "start_stream", "change_stream_key"]:
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM  # Scene switch

        # App Launch
        if category == PermissionCategory.APP_LAUNCH.value:
            if act in ["kill_app", "terminate_process"]:
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM

        # Volume Control
        if category == PermissionCategory.VOLUME_CONTROL.value:
            delta = abs(params.get("delta", 0))
            target_vol = params.get("volume", 50)
            if delta > 25 or target_vol == 0 or target_vol == 100:
                return RiskLevel.MEDIUM
            return RiskLevel.LOW

        # Media Control
        if category == PermissionCategory.MEDIA_CONTROL.value:
            return RiskLevel.LOW

        # Notifications
        if category == PermissionCategory.NOTIFICATIONS_READ.value:
            return RiskLevel.SAFE

        return RiskLevel.MEDIUM

    def save_to_file(self, file_path: Path):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.config.to_dict(), f, indent=2)

    def load_from_file(self, file_path: Path) -> bool:
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.config = DesktopPermissionConfig.from_dict(data)
                    return True
            except Exception as e:
                print(f"[PermissionManager] Gagal memuat izin: {e}")
        return False
