import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

try:
    import tests  # noqa: F401  # Ensure tests/__init__.py sets MAYBEAI_LLM_PROVIDER=mock under `discover tests`
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

from core.brain import Brain


class _FakeAsyncResp:
    def __init__(self, status: int, json_data=None, text_data: str = ""):
        self.status = status
        self._json_data = json_data or {}
        self._text_data = text_data

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestBrain(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_dir = Path(self._temp_dir_obj.name)
        self.settings_path = self.temp_dir / "settings.json"
        self.settings_path.write_text(
            json.dumps({
                "llm": {
                    "provider": "gemini",
                    "gemini_model": "gemini-3-flash-preview",
                    "temperature": 0.7,
                    "max_tokens": 120,
                }
            }),
            encoding="utf-8",
        )

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    async def test_env_provider_override_uses_mock_even_when_settings_gemini(self):
        brain = Brain(settings_path=str(self.settings_path), character_path="config/character.json")
        try:
            with patch.dict(os.environ, {"MAYBEAI_LLM_PROVIDER": "mock"}, clear=False):
                self.assertEqual(brain.get_provider(), "mock")
                with patch.object(brain, "_generate_gemini", new=AsyncMock()) as mock_gem:
                    resp = await brain.generate_response("Viewer", "Halo Eve!")
                mock_gem.assert_not_called()
                self.assertIn("[emotion:", resp)
        finally:
            await brain.close()

    async def test_session_reuse_and_close(self):
        brain = Brain(settings_path=str(self.settings_path), character_path="config/character.json")
        try:
            s1 = await brain._get_session()
            s2 = await brain._get_session()
            self.assertIs(s1, s2)
            self.assertFalse(s1.closed)

            await brain.close()
            self.assertTrue(s1.closed)
            self.assertIsNone(brain._session)

            s3 = await brain._get_session()
            self.assertIsNot(s3, s1)
            self.assertFalse(s3.closed)
        finally:
            await brain.close()

    async def test_gemini_sends_api_key_in_header_not_url_query(self):
        brain = Brain(settings_path=str(self.settings_path), character_path="config/character.json")
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["json"] = json
            return _FakeAsyncResp(
                status=200,
                json_data={
                    "candidates": [
                        {"content": {"parts": [{"text": "[emotion: happy] Halo dari Gemini!"}]}}
                    ]
                },
            )

        fake_session = MagicMock()
        fake_session.post = fake_post

        try:
            with patch.dict(
                os.environ,
                {"MAYBEAI_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-gem-secret"},
                clear=False,
            ), patch.object(brain, "_get_session", new=AsyncMock(return_value=fake_session)):
                resp = await brain.generate_response("Viewer", "Tes koneksi Gemini")

            self.assertEqual(resp, "[emotion: happy] Halo dari Gemini!")
            self.assertNotIn("?key=", captured["url"])
            self.assertNotIn("test-gem-secret", captured["url"])
            self.assertEqual(captured["headers"].get("x-goog-api-key"), "test-gem-secret")
        finally:
            await brain.close()

    def test_set_provider_persists_via_config_manager_and_atomic_fallback(self):
        # 1. settings.json path uses ConfigManager.save_config
        brain1 = Brain(settings_path=str(self.settings_path), character_path="config/character.json")
        chosen = brain1.set_provider("ollama")
        self.assertEqual(chosen, "ollama")
        persisted = json.loads(self.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["llm"]["provider"], "ollama")

        # 2. Non-settings.json path falls back to _atomic_write_settings
        custom_path = self.temp_dir / "custom_llm.json"
        custom_path.write_text(json.dumps({"llm": {"provider": "mock"}}), encoding="utf-8")
        brain2 = Brain(settings_path=str(custom_path), character_path="config/character.json")
        chosen2 = brain2.set_provider("openai")
        self.assertEqual(chosen2, "openai")
        persisted2 = json.loads(custom_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted2["llm"]["provider"], "openai")


if __name__ == "__main__":
    unittest.main()
