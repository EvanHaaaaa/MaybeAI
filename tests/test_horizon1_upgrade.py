import asyncio
import copy
import io
import os
import struct
import tempfile
import unittest
import wave
from unittest.mock import AsyncMock

try:
    import tests  # noqa: F401
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

from core.brain import Brain, ContextBudgetManager
from core.chat_receiver import ChatReceiver
from core.config_manager import ConfigManager
from core.conversation.prompts import MasterPromptBuilder
from core.highlights.detector import HighlightDetector
from core.orchestrator import Orchestrator
from core.tts import TTSEngine
from core.tts_providers import detect_audio_format, extract_rms_envelope_from_wav, is_edge_tts_voice
from core.vision.analyzer import VisualAnalyzer
from core.vision.models import VisualObservation


def _make_pcm_wav(samples: list[int], sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


class TestHorizon1Upgrade(unittest.IsolatedAsyncioTestCase):
    async def test_context_budget_manager_truncates_and_preserves_creator(self):
        character = {
            "name": "Eve Maybe",
            "nickname": "Eve",
            "creator": "Evan",
            "bio": "AI VTuber",
            "lore": {"backstory": " ".join(["lore_word"] * 1200)},
        }
        sys_prompt = MasterPromptBuilder.build_system_prompt(
            character=character,
            active_topic="System Control",
            memory_recall_block="SECOND BRAIN\n" + ("memory_item " * 800),
            mood_directive="[MOOD]\nHappy and energetic",
            is_creator=True,
        )
        self.assertIn("[CREATOR VERIFIED]", sys_prompt)

        history = [
            {"role": "user", "content": f"Old turn {i} " + ("x " * 120)}
            for i in range(12)
        ]

        mgr = ContextBudgetManager({"llm": {"input_token_budget": 1800}})
        trimmed_sys, trimmed_hist = mgr.apply(
            provider="openai",
            system_prompt=sys_prompt,
            history_items=history,
            current_message_text="Tolong cek status sistem.",
        )

        total_tokens = (
            mgr.estimate_tokens(trimmed_sys)
            + sum(mgr.estimate_tokens(str(item.get("content", ""))) for item in trimmed_hist)
            + mgr.estimate_tokens("Tolong cek status sistem.")
        )
        self.assertLessEqual(total_tokens, 1800)
        self.assertIn("[CREATOR VERIFIED]", trimmed_sys)

        # Verify is_creator=True is accepted by Brain.generate_response fallback path
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            brain = Brain(
                settings_path="config/settings.json",
                character_path="config/character.json",
            )
            # Isolate any conversation persistence away from repo data/
            brain.conversation.episodic_memory.db_path = os.path.join(tmpdir, "mem.db")
            reply = await brain.generate_response(
                user_name="Evan",
                message="Halo Eve, status sistem?",
                is_creator=True,
            )
            self.assertIsInstance(reply, str)
            self.assertTrue(len(reply) > 0)

    def test_extract_rms_envelope_from_wav_silence_and_tone(self):
        silence_wav = _make_pcm_wav([0] * 1600)  # 100ms at 16kHz
        tone_samples = [16000 if (i // 16) % 2 == 0 else -16000 for i in range(1600)]
        tone_wav = _make_pcm_wav(tone_samples)

        sil_env, sil_dur = extract_rms_envelope_from_wav(silence_wav, frame_ms=50)
        self.assertGreater(sil_dur, 0.0)
        self.assertGreater(len(sil_env), 0)
        self.assertTrue(all(v == 0.0 for v in sil_env))

        tone_env, tone_dur = extract_rms_envelope_from_wav(tone_wav, frame_ms=50)
        self.assertGreater(tone_dur, 0.0)
        self.assertGreater(len(tone_env), 0)
        self.assertTrue(any(v > 0.0 for v in tone_env))

    async def test_edge_tts_fallback_voice_and_audio_mime_detection(self):
        engine = TTSEngine(
            provider="kokoro",
            voice="af_heart",  # Non-Edge voice ID
            fallback_voice="en-US-AnaNeural",
        )
        self.assertFalse(is_edge_tts_voice("af_heart"))
        self.assertTrue(is_edge_tts_voice("en-US-AnaNeural"))

        engine._provider.synthesize = AsyncMock(side_effect=RuntimeError("kokoro offline"))
        engine._fallback_provider.synthesize = AsyncMock(return_value=b"ID3\x03\x00test")
        try:
            audio = await engine._synthesize_audio("Halo chat!")
            self.assertTrue(audio.startswith(b"ID3"))
            engine._fallback_provider.synthesize.assert_awaited_once()
            used_voice = engine._fallback_provider.synthesize.call_args.kwargs["voice"]
            self.assertEqual(used_voice, "en-US-AnaNeural")
            self.assertTrue(is_edge_tts_voice(used_voice))
        finally:
            await engine.close()

        wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt "
        mp3_bytes = b"ID3\x03\x00\x00\x00\x00\x00\x00"
        self.assertEqual(detect_audio_format(wav_bytes), ("audio/wav", ".wav"))
        self.assertEqual(detect_audio_format(mp3_bytes), ("audio/mpeg", ".mp3"))
        self.assertEqual(Orchestrator._detect_audio_mime(wav_bytes), "audio/wav")
        self.assertEqual(Orchestrator._detect_audio_mime(mp3_bytes), "audio/mpeg")

    async def test_chat_receiver_queue_bounded_at_500(self):
        receiver = ChatReceiver()
        self.assertEqual(receiver.max_queue_size, 500)
        self.assertEqual(receiver.queue.maxsize, 500)

        for i in range(505):
            await receiver.put_message(user=f"user_{i}", text=f"msg_{i}")

        self.assertEqual(receiver.queue.qsize(), 500)
        oldest_kept = await receiver.get_next_message()
        self.assertEqual(oldest_kept.user, "user_5")
        self.assertEqual(oldest_kept.text, "msg_5")

    def test_config_manager_validate_default_settings_zero_unschematized(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            cm = ConfigManager(config_dir=tmpdir)
            valid, errors = cm.validate_config(copy.deepcopy(ConfigManager.DEFAULT_SETTINGS))
            self.assertTrue(valid, f"Validation errors: {errors}")
            self.assertEqual(errors, [])

            schema_paths = {item["path"] for item in cm.get_schema()}
            default_paths = set()
            for section, values in ConfigManager.DEFAULT_SETTINGS.items():
                if isinstance(values, dict):
                    for key in values:
                        default_paths.add(f"{section}.{key}")
                else:
                    default_paths.add(section)

            unschematized = sorted(default_paths - schema_paths)
            self.assertEqual(unschematized, [], f"Unschematized keys: {unschematized}")

    def test_visual_analyzer_none_image_returns_desktop_observation(self):
        obs = VisualAnalyzer.analyze_frame(None)
        self.assertIsInstance(obs, VisualObservation)
        self.assertEqual(obs.scene_label, "Desktop")

    async def test_highlight_detector_replay_saved_false_on_obs_failure(self):
        det_dict_fail = HighlightDetector(
            on_save_replay=lambda _m: {"success": False, "error": "OBS disconnected"}
        )
        m1 = det_dict_fail.mark_manual("Manual fail dict")
        self.assertFalse(m1.replay_saved)

        def _raise_err(_m):
            raise RuntimeError("OBS socket closed")

        det_exc = HighlightDetector(on_save_replay=_raise_err)
        m2 = det_exc.mark_manual("Manual exception")
        self.assertFalse(m2.replay_saved)

        async def _async_fail(_m):
            return False

        det_async = HighlightDetector(on_save_replay=_async_fail)
        m3 = det_async.mark_manual("Manual async fail")
        await asyncio.sleep(0)
        self.assertFalse(m3.replay_saved)


if __name__ == "__main__":
    unittest.main()
