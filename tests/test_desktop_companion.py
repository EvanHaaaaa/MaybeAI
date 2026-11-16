import unittest
import shutil
from pathlib import Path

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
from core.desktop.engine import DesktopCompanionEngine
from core.brain import Brain


class TestDesktopModels(unittest.TestCase):
    def test_default_config(self):
        cfg = DesktopPermissionConfig()
        self.assertTrue(cfg.master_enabled)
        self.assertTrue(cfg.categories[PermissionCategory.APP_LAUNCH.value])
        self.assertTrue(cfg.categories[PermissionCategory.MEDIA_CONTROL.value])
        self.assertTrue(cfg.categories[PermissionCategory.VOLUME_CONTROL.value])
        self.assertTrue(cfg.categories[PermissionCategory.NOTIFICATIONS_READ.value])
        self.assertFalse(cfg.categories[PermissionCategory.STREAMING_OPS.value])
        self.assertTrue(cfg.require_confirmation_for_high)
        self.assertIn("spotify.exe", cfg.allowed_apps)

        d = cfg.to_dict()
        cfg2 = DesktopPermissionConfig.from_dict(d)
        self.assertEqual(cfg2.current_volume, 50)
        self.assertEqual(cfg2.media_state, "paused")

    def test_action_request_and_notification_models(self):
        req = DesktopActionRequest(
            category=PermissionCategory.VOLUME_CONTROL.value,
            action_type="set_volume",
            params={"volume": 65},
            risk_level=RiskLevel.LOW.value,
            status=ActionStatus.EXECUTED.value,
            details="Set volume ke 65%"
        )
        d_req = req.to_dict()
        req2 = DesktopActionRequest.from_dict(d_req)
        self.assertEqual(req2.action_type, "set_volume")
        self.assertEqual(req2.params["volume"], 65)

        notif = DesktopNotification(
            source="OBS",
            title="Stream Ready",
            body="Encoder OK"
        )
        d_notif = notif.to_dict()
        notif2 = DesktopNotification.from_dict(d_notif)
        self.assertEqual(notif2.source, "OBS")
        self.assertFalse(notif2.is_read)


class TestPermissionManager(unittest.TestCase):
    def setUp(self):
        self.mgr = PermissionManager()

    def test_master_toggle(self):
        self.assertTrue(self.mgr.config.master_enabled)
        self.mgr.toggle_master(False)
        self.assertFalse(self.mgr.config.master_enabled)

        # Action should be blocked when master is disabled
        ok, reason, risk, req_conf = self.mgr.evaluate_action("volume_control", "adjust_volume", {"delta": 5})
        self.assertFalse(ok)
        self.assertIn("dinonaktifkan", reason)

    def test_category_toggle(self):
        # Disable volume control
        self.mgr.toggle_category("volume_control", False)
        ok, reason, _, _ = self.mgr.evaluate_action("volume_control", "adjust_volume", {"delta": 5})
        self.assertFalse(ok)
        self.assertIn("belum diaktifkan", reason)

        # Re-enable
        self.mgr.toggle_category("volume_control", True)
        ok, _, _, _ = self.mgr.evaluate_action("volume_control", "adjust_volume", {"delta": 5})
        self.assertTrue(ok)

    def test_app_whitelist(self):
        self.assertFalse(self.mgr.add_allowed_app("spotify.exe"))  # Already in
        self.assertTrue(self.mgr.add_allowed_app("blender.exe"))
        self.assertIn("blender.exe", self.mgr.config.allowed_apps)

        self.assertTrue(self.mgr.remove_allowed_app("blender.exe"))
        self.assertNotIn("blender.exe", self.mgr.config.allowed_apps)

    def test_risk_and_confirmation_evaluation(self):
        # 1. Low risk: small volume change
        ok, _, risk, req_conf = self.mgr.evaluate_action("volume_control", "adjust_volume", {"delta": 5})
        self.assertTrue(ok)
        self.assertEqual(risk, RiskLevel.LOW)
        self.assertFalse(req_conf)

        # 2. High risk: unwhitelisted app when confirmation enabled
        ok, _, risk, req_conf = self.mgr.evaluate_action("app_launch", "launch_app", {"app_name": "malicious.exe"})
        self.assertTrue(ok)
        self.assertEqual(risk, RiskLevel.HIGH)
        self.assertTrue(req_conf)

        # 3. Streaming ops (when enabled): stop_stream is HIGH risk
        self.mgr.toggle_category("streaming_ops", True)
        ok, _, risk, req_conf = self.mgr.evaluate_action("streaming_ops", "stop_stream", {})
        self.assertTrue(ok)
        self.assertEqual(risk, RiskLevel.HIGH)
        self.assertTrue(req_conf)


class TestDesktopController(unittest.TestCase):
    def setUp(self):
        self.cfg = DesktopPermissionConfig()
        self.ctrl = DesktopController(self.cfg)

    def test_volume_controls(self):
        vol, _ = self.ctrl.set_volume(80)
        self.assertEqual(vol, 80)
        self.assertEqual(self.cfg.current_volume, 80)

        # Clamp max
        vol_max, _ = self.ctrl.set_volume(150)
        self.assertEqual(vol_max, 100)

        # Adjust
        vol_adj, _ = self.ctrl.adjust_volume(-15)
        self.assertEqual(vol_adj, 85)

        # Mute toggle
        is_muted, _ = self.ctrl.toggle_mute()
        self.assertTrue(is_muted)
        is_muted2, _ = self.ctrl.toggle_mute()
        self.assertFalse(is_muted2)

    def test_media_controls(self):
        self.assertEqual(self.cfg.media_state, "paused")
        st, _ = self.ctrl.media_play_pause()
        self.assertEqual(st, "playing")

        track, _ = self.ctrl.media_next_track()
        self.assertNotEqual(track, "")
        self.assertEqual(self.cfg.media_state, "playing")

    def test_notifications(self):
        notifs = self.ctrl.get_unread_notifications()
        self.assertGreaterEqual(len(notifs), 1)

        new_n = self.ctrl.add_notification("TestApp", "Halo", "Isi pesan")
        self.assertEqual(new_n.source, "TestApp")

        self.ctrl.mark_all_read()
        self.assertEqual(len(self.ctrl.get_unread_notifications()), 0)


class TestDesktopCompanionEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path("data/test_desktop_temp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.engine = DesktopCompanionEngine(
            data_dir=str(self.temp_dir),
            second_brain_dir=str(self.temp_dir / "second_brain")
        )

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_engine_state_and_directive(self):
        state = self.engine.get_state()
        self.assertTrue(state["master_enabled"])
        self.assertIn("volume_control", state["categories"])
        self.assertIn("spotify.exe", state["allowed_apps"])

        directive = self.engine.get_prompt_directive()
        self.assertIn("DESKTOP COMPANION & COMPUTER INTERACTION", directive)
        self.assertIn("Master Desktop Mode: ENABLED", directive)

    def test_auto_approved_action_flow(self):
        req, speech = self.engine.request_action("volume_control", "set_volume", {"volume": 40})
        self.assertEqual(req.status, ActionStatus.EXECUTED.value)
        self.assertEqual(self.engine.config.current_volume, 40)
        self.assertIn("40%", speech)

    def test_blocked_action_flow(self):
        # Streaming ops is disabled by default
        req, speech = self.engine.request_action("streaming_ops", "switch_scene", {"scene_name": "Game"})
        self.assertEqual(req.status, ActionStatus.BLOCKED.value)
        self.assertIn("belum punya izin", speech)

    def test_risky_confirmation_flow(self):
        # Enable streaming ops, then trigger high-risk stop_stream
        self.engine.toggle_category("streaming_ops", True)
        req, speech = self.engine.request_action("streaming_ops", "stop_stream", {})
        self.assertEqual(req.status, ActionStatus.PENDING.value)
        self.assertIn(req.id, self.engine.pending_actions)
        self.assertIn("konfirmasi manual", speech)

        # Confirm approval
        req_res, speech_appr = self.engine.confirm_action(req.id, approved=True)
        self.assertEqual(req_res.status, ActionStatus.EXECUTED.value)
        self.assertNotIn(req.id, self.engine.pending_actions)

    def test_risky_rejection_flow(self):
        self.engine.toggle_category("streaming_ops", True)
        req, _ = self.engine.request_action("streaming_ops", "stop_stream", {})
        self.assertEqual(req.status, ActionStatus.PENDING.value)

        # Reject
        req_res, speech_rej = self.engine.confirm_action(req.id, approved=False)
        self.assertEqual(req_res.status, ActionStatus.REJECTED.value)
        self.assertIn("dibatalkan", speech_rej)

    def test_second_brain_sync(self):
        self.engine.sync_to_second_brain()
        f = self.temp_dir / "second_brain" / "desktop" / "permissions.md"
        self.assertTrue(f.exists())
        content = f.read_text(encoding="utf-8")
        self.assertIn("Desktop Companion & Security Permissions", content)
        self.assertIn("Master Companion Mode", content)


class TestDesktopIntegration(unittest.TestCase):
    def setUp(self):
        self.brain = Brain()
        self.conv = self.brain.conversation

    def test_brain_property_and_state(self):
        self.assertIsNotNone(self.brain.desktop)
        state = self.brain.get_conversation_state()
        self.assertIn("desktop", state)
        self.assertTrue(state["desktop"]["master_enabled"])

    def test_conversational_mock_responses(self):
        # Test volume down
        r1 = self.conv.generate_mock_response("User", "eve kecilin volume dong")
        self.assertTrue(any(w in r1.lower() for w in ["volume", "turun", "nyaman", "siap"]))

        # Test media next
        r2 = self.conv.generate_mock_response("User", "eve ganti lagu dong")
        self.assertTrue(any(w in r2.lower() for w in ["lagu", "musik", "berikut"]))

        # Test app launch
        r3 = self.conv.generate_mock_response("User", "eve tolong buka notepad")
        self.assertTrue(any(w in r3.lower() for w in ["notepad", "aplikasi", "buka"]))


if __name__ == "__main__":
    unittest.main()
