import os
import sys
import types
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.tts import TTSEngine


class TestTTSEngine(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_dir = Path(self._temp_dir_obj.name)
        self.engine = TTSEngine(voice="en-US-AnaNeural", rate="+5%", pitch="+10Hz", enabled=True)
        self.engine.temp_dir = self.temp_dir

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    def test_update_config_and_get_status(self):
        self.engine.update_config(enabled=False, voice=" id-ID-GadisNeural ", rate=" +0% ", pitch=" -5Hz ")
        status = self.engine.get_status()
        self.assertFalse(status["enabled"])
        self.assertEqual(status["voice"], "id-ID-GadisNeural")
        self.assertEqual(status["rate"], "+0%")
        self.assertEqual(status["pitch"], "-5Hz")
        self.assertEqual(status["provider"], "edge-tts")

    async def test_empty_and_disabled_speak(self):
        with patch("core.tts.edge_tts.Communicate") as mock_comm:
            res_empty = await self.engine.speak("   ")
            self.assertIsNone(res_empty)
            mock_comm.assert_not_called()

            self.engine.enabled = False
            mouth_updates = []
            with patch("core.tts.asyncio.sleep", new=AsyncMock()):
                res_disabled = await self.engine.speak("Halo dunia", on_mouth_update=mouth_updates.append)
            self.assertIsNone(res_disabled)
            mock_comm.assert_not_called()
            self.assertGreater(len(mouth_updates), 1)
            self.assertEqual(mouth_updates[-1], 0.0)

    async def test_speak_inits_mixer_once_and_deletes_audio_file(self):
        mixer_state = {"initialized": False}

        def fake_get_init():
            return (44100, -16, 2) if mixer_state["initialized"] else None

        def fake_init():
            mixer_state["initialized"] = True

        fake_channel = MagicMock()
        fake_channel.get_busy.return_value = False
        fake_sound = MagicMock()
        fake_sound.play.return_value = fake_channel
        fake_mixer = MagicMock()
        fake_mixer.get_init.side_effect = fake_get_init
        fake_mixer.init.side_effect = fake_init
        fake_mixer.Sound.return_value = fake_sound

        fake_pygame = types.ModuleType("pygame")
        fake_pygame.mixer = fake_mixer

        created_paths = []

        class FakeCommunicate:
            def __init__(self, text, voice, rate, pitch):
                self.text = text

            async def save(self, out_path):
                Path(out_path).write_bytes(b"fake-mp3-data")
                created_paths.append(out_path)

        mouth_updates = []
        with patch.dict(sys.modules, {"pygame": fake_pygame}), \
             patch("core.tts.edge_tts.Communicate", side_effect=FakeCommunicate), \
             patch("core.tts.asyncio.sleep", new=AsyncMock()):
            out1 = await self.engine.speak("First line", on_mouth_update=mouth_updates.append)
            out2 = await self.engine.speak("Second line", on_mouth_update=mouth_updates.append)

        self.assertIsNotNone(out1)
        self.assertIsNotNone(out2)
        self.assertEqual(fake_mixer.init.call_count, 1)
        self.assertEqual(fake_mixer.Sound.call_count, 2)
        self.assertEqual(fake_sound.play.call_count, 2)
        self.assertEqual(fake_channel.stop.call_count, 2)
        self.assertEqual(mouth_updates[-1], 0.0)
        self.assertTrue(any(v > 0.0 for v in mouth_updates))

        for p in created_paths:
            self.assertFalse(os.path.exists(p), f"Temporary TTS file {p} was not deleted")
        self.assertEqual(list(self.temp_dir.glob("speech_*.mp3")), [])

    async def test_speak_exception_records_last_error_and_cleans_up(self):
        class FailingCommunicate:
            def __init__(self, **kwargs):
                pass

            async def save(self, out_path):
                Path(out_path).write_bytes(b"partial")
                raise RuntimeError("edge-tts network down")

        with patch("core.tts.edge_tts.Communicate", side_effect=FailingCommunicate):
            res = await self.engine.speak("Test failure")

        self.assertIsNone(res)
        self.assertIn("edge-tts network down", self.engine.last_error)
        self.assertEqual(list(self.temp_dir.glob("speech_*.mp3")), [])

    def test_cleanup_audio_file_swallows_remove_errors(self):
        dummy = self.temp_dir / "locked.mp3"
        dummy.write_bytes(b"x")
        with patch("core.tts.os.remove", side_effect=PermissionError("locked")):
            TTSEngine._cleanup_audio_file(str(dummy))


if __name__ == "__main__":
    unittest.main()
