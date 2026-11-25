import os
import json
import tempfile
import unittest
import asyncio
from pathlib import Path

try:
    import tests  # noqa: F401
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

from core.config_manager import ConfigManager
from core.orchestrator import Orchestrator
from run import (
    orchestrator,
    config_mgr,
    get_settings_page,
    get_configuration,
    get_configuration_schema,
    update_configuration,
    validate_configuration,
    reset_configuration,
    test_feature_diagnostic,
    get_system_diagnostics_report
)


class TestConfigurationCenter(unittest.TestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_dir = self._temp_dir_obj.name
        self.cfg_mgr = ConfigManager(config_dir=self.temp_dir)

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    def test_default_config_loading_and_merging(self):
        cfg = self.cfg_mgr.get_public_config()
        self.assertIn("system", cfg)
        self.assertIn("llm", cfg)
        self.assertIn("personality", cfg)
        self.assertIn("tts", cfg)
        self.assertIn("vts", cfg)
        self.assertIn("twitch", cfg)
        self.assertIn("moderator", cfg)
        self.assertIn("minecraft", cfg)
        self.assertEqual(cfg["system"]["name"], "MaybeAI")
        self.assertTrue(cfg["system"]["bot_enabled"])

    def test_secret_masking(self):
        """Verify that OAuth tokens and secrets are NEVER returned in plain text on GET."""
        # Inject secret token
        raw_settings = json.loads(json.dumps(self.cfg_mgr.settings))
        raw_settings["twitch"]["oauth_token"] = "oauth:secret_token_12345"
        self.cfg_mgr.save_config(raw_settings)

        public_cfg = self.cfg_mgr.get_public_config()
        self.assertEqual(public_cfg["twitch"]["oauth_token"], "********")
        self.assertTrue(public_cfg["twitch"]["oauth_configured"])
        self.assertIn("api_keys", public_cfg)

    def test_schema_metadata_integrity(self):
        schema = self.cfg_mgr.get_schema()
        self.assertGreater(len(schema), 15)
        paths = [item["path"] for item in schema]
        self.assertIn("system.bot_enabled", paths)
        self.assertIn("llm.provider", paths)
        self.assertIn("personality.humor_intensity", paths)
        self.assertIn("tts.voice", paths)
        self.assertIn("vts.port", paths)
        self.assertIn("moderator.strict_mode", paths)
        self.assertIn("minecraft.default_mode", paths)

        for item in schema:
            self.assertIn("path", item)
            self.assertIn("category", item)
            self.assertIn("label", item)
            self.assertIn("type", item)
            self.assertIn("restart_required", item)

    def test_validation_rules(self):
        # Valid payload
        valid_payload = {"system": {"bot_enabled": False}, "llm": {"temperature": 0.9}}
        is_valid, errors = self.cfg_mgr.validate_config(valid_payload)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

        # Invalid toggle type (string instead of boolean)
        invalid_payload = {"system": {"bot_enabled": "yes"}}
        is_valid, errors = self.cfg_mgr.validate_config(invalid_payload)
        self.assertFalse(is_valid)
        self.assertIn("boolean", errors[0])

        # Out-of-range slider
        out_of_range = {"llm": {"temperature": 5.0}}
        is_valid, errors = self.cfg_mgr.validate_config(out_of_range)
        self.assertFalse(is_valid)
        self.assertTrue(any("<=" in e for e in errors))

    def test_atomic_save_and_persistence(self):
        payload = {"system": {"bot_enabled": False, "language": "en-US"}}
        success, errors, restart_req = self.cfg_mgr.save_config(payload)
        self.assertTrue(success)

        # Verify persistent read from disk
        with open(self.cfg_mgr.settings_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        self.assertFalse(disk_data["system"]["bot_enabled"])
        self.assertEqual(disk_data["system"]["language"], "en-US")

    def test_masked_secret_preservation(self):
        """When client saves with masked '********', the existing token on disk must be preserved."""
        # 1. Save original token
        self.cfg_mgr.save_config({"twitch": {"oauth_token": "oauth:real_secret_token"}})
        self.assertEqual(self.cfg_mgr.settings["twitch"]["oauth_token"], "oauth:real_secret_token")

        # 2. Client sends masked payload
        self.cfg_mgr.save_config({"twitch": {"oauth_token": "********", "channel": "myeve"}})

        # 3. Token must remain real_secret_token
        self.assertEqual(self.cfg_mgr.settings["twitch"]["oauth_token"], "oauth:real_secret_token")
        self.assertEqual(self.cfg_mgr.settings["twitch"]["channel"], "myeve")

    def test_reset_category_and_all(self):
        # Modify humor
        self.cfg_mgr.save_config({"personality": {"humor_intensity": 10}})
        self.assertEqual(self.cfg_mgr.settings["personality"]["humor_intensity"], 10)

        # Reset personality category
        self.cfg_mgr.reset_to_defaults("personality")
        self.assertEqual(self.cfg_mgr.settings["personality"]["humor_intensity"], 75)

    def test_system_diagnostics(self):
        diag = self.cfg_mgr.get_system_diagnostics(orchestrator)
        self.assertIn("uptime_seconds", diag)
        self.assertIn("uptime_human", diag)
        self.assertIn("modules", diag)
        self.assertIn("llm_brain", diag["modules"])
        self.assertIn("tts", diag["modules"])
        self.assertIn("vts", diag["modules"])
        self.assertIn("twitch", diag["modules"])
        self.assertIn("moderator", diag["modules"])
        self.assertIn("minecraft", diag["modules"])

    def test_feature_diagnostics_runners(self):
        async def run_diag_tests():
            # Moderator probe test
            mod_test = await self.cfg_mgr.test_feature("moderator", orchestrator, {"text": "hello test safe"})
            self.assertTrue(mod_test["success"])
            self.assertTrue(mod_test["result"]["is_safe"])

            # Memory probe test
            mem_test = await self.cfg_mgr.test_feature("memory", orchestrator)
            self.assertTrue(mem_test["success"])
            self.assertIn("stats", mem_test)

            # LLM test (offline persona / mock fallback)
            llm_test = await self.cfg_mgr.test_feature("llm", orchestrator, {"message": "Halo Eve!"})
            self.assertTrue(llm_test["success"])
            self.assertIn("response", llm_test)

        asyncio.run(run_diag_tests())

    def test_fastapi_endpoints(self):
        async def run_endpoint_tests():
            # GET /settings
            resp_settings = await get_settings_page()
            self.assertTrue(os.path.exists(resp_settings.path))
            self.assertIn("settings.html", resp_settings.path)

            # GET /api/config
            cfg = await get_configuration()
            self.assertIn("system", cfg)
            self.assertIn("llm", cfg)

            # GET /api/config/schema
            schema_data = await get_configuration_schema()
            self.assertIsInstance(schema_data, list)
            self.assertGreater(len(schema_data), 10)

            # PUT /api/config
            prev_debug = cfg.get("system", {}).get("debug_mode", False)
            try:
                put_res = await update_configuration({"system": {"debug_mode": True}})
                self.assertTrue(put_res["success"])
            finally:
                await update_configuration({"system": {"debug_mode": prev_debug}})

            # POST /api/config/validate
            val_res = await validate_configuration({"llm": {"temperature": 0.7}})
            self.assertTrue(val_res["valid"])

            # POST /api/config/test/moderator
            test_res = await test_feature_diagnostic("moderator", {"text": "clean test message"})
            self.assertTrue(test_res["success"])

            # GET /api/system/diagnostics
            diag_res = await get_system_diagnostics_report()
            self.assertIn("modules", diag_res)

        asyncio.run(run_endpoint_tests())

    def test_runtime_hot_reload_live(self):
        """Verify that updating configuration propagates into active runtime components."""
        async def run_hot_reload():
            # 1. Test TTS disable hot reload
            await orchestrator.apply_configuration_hot_reload({
                "tts": {"enabled": False, "voice": "id-ID-GadisNeural"}
            })
            self.assertFalse(orchestrator.tts.enabled)
            self.assertEqual(orchestrator.tts.voice, "id-ID-GadisNeural")
            self.assertEqual(orchestrator.singer.voice, "id-ID-GadisNeural")

            # 2. Test Moderator max length hot reload
            await orchestrator.apply_configuration_hot_reload({
                "moderator": {"max_message_length": 180, "strict_mode": False}
            })
            self.assertEqual(orchestrator.moderator.max_message_length, 180)
            self.assertFalse(orchestrator.moderator.strict_mode)

            # 3. Restore defaults
            await orchestrator.apply_configuration_hot_reload({
                "tts": {"enabled": True, "voice": "en-US-AnaNeural"},
                "moderator": {"max_message_length": 250, "strict_mode": True}
            })
            self.assertTrue(orchestrator.tts.enabled)
            self.assertEqual(orchestrator.moderator.max_message_length, 250)

        asyncio.run(run_hot_reload())


if __name__ == "__main__":
    unittest.main()
