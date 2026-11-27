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

from core.brain import Brain, ContextBudgetManager, ProviderCircuitBreaker


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

    def test_max_tokens_aligned_between_openai_and_gemini(self):
        no_max_path = self.temp_dir / "no_max_settings.json"
        no_max_path.write_text(json.dumps({"llm": {"provider": "openai"}}), encoding="utf-8")
        brain = Brain(settings_path=str(no_max_path), character_path="config/character.json")

        openai_payload = brain._build_openai_payload("sys", "Viewer", "hi", False, "")
        gemini_payload = brain._build_gemini_payload("sys", "Viewer", "hi", False, "")
        self.assertEqual(openai_payload["max_tokens"], 800)
        self.assertEqual(gemini_payload["generationConfig"]["maxOutputTokens"], 800)

    def test_context_budget_manager_priority_truncation(self):
        mgr = ContextBudgetManager({"llm": {"input_token_budget": 180}})
        system_prompt = "\n\n".join([
            "You are Eve Maybe.",
            "[CREATOR VERIFIED]\nCreator authority active.",
            "[MOOD DIRECTIVE]\n" + ("mood " * 40),
            "[EVE'S SECOND BRAIN & EPISODIC MEMORY RECALL]\n" + ("memory " * 60),
            "CORE CHARACTER LORE:\n" + ("lore " * 120),
            "10 CONVERSATIONAL PILLARS (NEURO-SAMA STYLE):\nKeep snappy.",
        ])
        history = [
            {"role": "user", "content": "oldest turn " + ("x" * 120)},
            {"role": "assistant", "content": "newest reply"},
        ]

        bounded_prompt, bounded_history = mgr.apply("openai", system_prompt, history, "Viewer: hi")
        total_tokens = (
            mgr.estimate_tokens(bounded_prompt)
            + sum(mgr.estimate_tokens(item["content"]) for item in bounded_history)
            + mgr.estimate_tokens("Viewer: hi")
        )
        self.assertLessEqual(total_tokens, 180)
        self.assertIn("You are Eve Maybe.", bounded_prompt)
        self.assertIn("[CREATOR VERIFIED]", bounded_prompt)
        self.assertNotIn("CORE CHARACTER LORE:", bounded_prompt)
        self.assertNotIn("EPISODIC MEMORY RECALL", bounded_prompt)

    async def test_is_creator_plumbed_to_live_prompt_and_error_fallbacks(self):
        brain = Brain(settings_path=str(self.settings_path), character_path="config/character.json")
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            if "generativelanguage.googleapis.com" in url:
                captured["json"] = json
            return _FakeAsyncResp(status=500, text_data="Internal Server Error")

        fake_session = MagicMock()
        fake_session.post = fake_post

        try:
            with patch.dict(
                os.environ,
                {"MAYBEAI_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-gem-secret"},
                clear=False,
            ), patch.object(brain, "_get_session", new=AsyncMock(return_value=fake_session)), patch.object(
                brain.conversation, "generate_mock_response", wraps=brain.conversation.generate_mock_response
            ) as mock_fallback:
                await brain.generate_response("Evan", "buka notepad", is_creator=True)

            sys_text = captured["json"]["systemInstruction"]["parts"][0]["text"]
            self.assertIn("[CREATOR VERIFIED]", sys_text)
            mock_fallback.assert_called_once()
            self.assertTrue(mock_fallback.call_args.kwargs.get("is_creator"))
        finally:
            await brain.close()

    def test_circuit_breaker_opens_cools_down_and_probes(self):
        cb = ProviderCircuitBreaker(failure_threshold=2, cooldown_sec=0.05)
        self.assertTrue(cb.allow_request("gemini"))
        cb.record_failure("gemini", status_code=429)
        self.assertTrue(cb.allow_request("gemini"))
        cb.record_failure("gemini", status_code=429)
        # Now open
        self.assertFalse(cb.allow_request("gemini"))
        self.assertEqual(cb.get_state("gemini")["state"], "open")

        # Wait for cooldown -> half-open probe
        import time
        time.sleep(0.07)
        self.assertTrue(cb.allow_request("gemini"))
        self.assertEqual(cb.get_state("gemini")["state"], "half_open")
        # Second concurrent request while probe in flight is blocked
        self.assertFalse(cb.allow_request("gemini"))
        # Success closes circuit
        cb.record_success("gemini")
        self.assertEqual(cb.get_state("gemini")["state"], "closed")
        self.assertTrue(cb.allow_request("gemini"))

    async def test_cross_provider_failover_chain_and_timeout(self):
        self.settings_path.write_text(
            json.dumps({
                "llm": {
                    "provider": "gemini",
                    "failover_enabled": True,
                    "failover_timeout_sec": 0.25,
                    "circuit_breaker_failure_threshold": 2,
                    "circuit_breaker_cooldown_sec": 30.0,
                }
            }),
            encoding="utf-8",
        )
        brain = Brain(settings_path=str(self.settings_path), character_path="config/character.json")
        calls = []

        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append((url, getattr(timeout, "total", None)))
            if "generativelanguage.googleapis.com" in url:
                return _FakeAsyncResp(status=429, text_data="Rate limited")
            if "api.openai.com" in url:
                return _FakeAsyncResp(
                    status=200,
                    json_data={"choices": [{"message": {"content": "[emotion: smug] OpenAI backup!"}}]},
                )
            return _FakeAsyncResp(status=500, text_data="Unexpected")

        fake_session = MagicMock()
        fake_session.post = fake_post
        try:
            with patch.dict(
                os.environ,
                {"MAYBEAI_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "g-key", "OPENAI_API_KEY": "o-key"},
                clear=False,
            ), patch.object(brain, "_get_session", new=AsyncMock(return_value=fake_session)):
                resp = await brain.generate_response("Viewer", "Halo!")
            self.assertEqual(resp, "[emotion: smug] OpenAI backup!")
            self.assertEqual(len(calls), 2)
            self.assertLess(calls[0][1], 2.0)
        finally:
            await brain.close()

    def test_mood_modulated_temperature_clamped(self):
        brain = Brain(settings_path=str(self.settings_path), character_path="config/character.json")
        brain.settings["llm"]["temperature"] = 0.85
        with patch.object(brain.mood, "get_temperature_modifier", return_value=0.12):
            self.assertAlmostEqual(brain._get_effective_temperature(), 0.97, places=3)
        brain.settings["llm"]["temperature"] = 1.15
        with patch.object(brain.mood, "get_temperature_modifier", return_value=0.15):
            self.assertEqual(brain._get_effective_temperature(), 1.2)
        brain.settings["llm"]["temperature"] = 0.25
        with patch.object(brain.mood, "get_temperature_modifier", return_value=-0.15):
            self.assertEqual(brain._get_effective_temperature(), 0.2)
        payload = brain._build_openai_payload("sys", "Viewer", "hi", False, "")
        self.assertGreaterEqual(payload["temperature"], 0.2)
        self.assertLessEqual(payload["temperature"], 1.2)


if __name__ == "__main__":
    unittest.main()
