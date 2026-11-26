import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

try:
    import tests  # noqa: F401
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

from core.singer import Singer
from core.stt import STTEngine
from core.tts import TTSEngine
from core.tts_providers import (
    BaseTTSProvider,
    CustomNeuralTTSProvider,
    EdgeTTSProvider,
    ElevenLabsTTSProvider,
    KokoroTTSProvider,
    RVCVoiceConverter,
    compute_emotion_prosody,
    create_tts_provider,
    detect_audio_format,
    extract_rms_envelope_from_wav,
)


class _FakeResponse:
    def __init__(self, status: int = 200, body: bytes = b"AUDIO_BYTES", text_body: str = ""):
        self.status = status
        self._body = body
        self._text_body = text_body
        self.content = self._ChunkedContent(body)

    class _ChunkedContent:
        def __init__(self, data: bytes):
            self._data = data

        async def iter_chunked(self, size: int):
            if self._data:
                yield self._data

    async def read(self) -> bytes:
        return self._body

    async def text(self) -> str:
        return self._text_body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, response: _FakeResponse, capture: list):
        self._response = response
        self._capture = capture

    def post(self, url, **kwargs):
        self._capture.append((url, kwargs))
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestNeuralTTSProvidersAndRVC(unittest.IsolatedAsyncioTestCase):
    def test_emotion_prosody_and_factory(self):
        rate, pitch = compute_emotion_prosody("+5%", "+10Hz", "excited")
        self.assertEqual(rate, "+20%")
        self.assertEqual(pitch, "+30Hz")

        sad_rate, sad_pitch = compute_emotion_prosody("+0%", "+0Hz", "sad")
        self.assertEqual(sad_rate, "-12%")
        self.assertEqual(sad_pitch, "-15Hz")

        self.assertIsInstance(create_tts_provider("edge-tts"), BaseTTSProvider)
        self.assertIsInstance(create_tts_provider("kokoro", kokoro_url="http://localhost:8880"), KokoroTTSProvider)
        self.assertIsInstance(create_tts_provider("elevenlabs", api_key="k", elevenlabs_voice_id="v"), ElevenLabsTTSProvider)
        self.assertIsInstance(create_tts_provider("gpt_sovits", custom_tts_url="http://localhost:9880"), CustomNeuralTTSProvider)
        with self.assertRaises(ValueError):
            create_tts_provider("unknown_provider")

    async def test_edge_tts_provider_applies_emotion_prosody(self):
        captured = {}

        class _FakeCommunicate:
            def __init__(self, text, voice, rate, pitch):
                captured["text"] = text
                captured["voice"] = voice
                captured["rate"] = rate
                captured["pitch"] = pitch

            async def save(self, path):
                Path(path).write_bytes(b"FAKE_EDGE_MP3")

        provider = EdgeTTSProvider()
        with patch("core.tts_providers.edge_tts.Communicate", _FakeCommunicate):
            audio = await provider.synthesize("Hello!", "en-US-AnaNeural", "+5%", "+10Hz", emotion="happy")

        self.assertEqual(audio, b"FAKE_EDGE_MP3")
        self.assertEqual(captured["rate"], "+13%")
        self.assertEqual(captured["pitch"], "+22Hz")

    async def test_kokoro_elevenlabs_and_custom_providers_mocked_http(self):
        calls = []

        # Kokoro HTTP
        kokoro = KokoroTTSProvider(kokoro_url="http://127.0.0.1:8880")
        with patch("core.tts_providers.aiohttp.ClientSession", return_value=_FakeSession(_FakeResponse(200, b"KOKORO_MP3"), calls)):
            k_audio = await kokoro.synthesize("Test kokoro", "en-US-AnaNeural", "+10%", "+0Hz", emotion="happy")
        self.assertEqual(k_audio, b"KOKORO_MP3")
        self.assertTrue(calls[-1][0].endswith("/v1/audio/speech"))

        # ElevenLabs streaming REST
        el = ElevenLabsTTSProvider(api_key="el_test_key", elevenlabs_voice_id="voice_123")
        with patch("core.tts_providers.aiohttp.ClientSession", return_value=_FakeSession(_FakeResponse(200, b"EL_MP3"), calls)):
            el_audio = await el.synthesize("Test eleven", "en-US-AnaNeural", "+0%", "+0Hz", emotion="excited")
        self.assertEqual(el_audio, b"EL_MP3")
        self.assertIn("voice_123", calls[-1][0])

        # CustomNeuralTTSProvider (fish_speech)
        custom = CustomNeuralTTSProvider(custom_tts_url="http://127.0.0.1:9999/tts", backend="fish_speech")
        with patch("core.tts_providers.aiohttp.ClientSession", return_value=_FakeSession(_FakeResponse(200, b"CUSTOM_WAV"), calls)):
            c_audio = await custom.synthesize("Test custom", "eve", "+0%", "+0Hz", emotion="smug")
        self.assertEqual(c_audio, b"CUSTOM_WAV")
        self.assertEqual(calls[-1][1]["json"]["backend"], "fish_speech")

    async def test_rvc_converter_and_fallback(self):
        # Disabled -> passthrough
        rvc_off = RVCVoiceConverter(enabled=False, rvc_url="http://127.0.0.1:7890/convert")
        self.assertEqual(await rvc_off.convert(b"ORIG"), b"ORIG")

        # Enabled -> HTTP conversion
        calls = []
        rvc_on = RVCVoiceConverter(enabled=True, rvc_url="http://127.0.0.1:7890/convert", pitch_shift=3)
        with patch("core.tts_providers.aiohttp.ClientSession", return_value=_FakeSession(_FakeResponse(200, b"RVC_OUT"), calls)):
            self.assertEqual(await rvc_on.convert(b"ORIG"), b"RVC_OUT")

        # HTTP 500 -> clean fallback to original bytes
        with patch("core.tts_providers.aiohttp.ClientSession", return_value=_FakeSession(_FakeResponse(500, b"", "boom"), calls)):
            self.assertEqual(await rvc_on.convert(b"ORIG"), b"ORIG")
        self.assertIn("500", rvc_on.last_error or "")

    async def test_tts_engine_edge_fallback_and_rvc_postprocess(self):
        captured_audio = []

        async def _on_audio(audio_bytes: bytes, text: str, *args):
            captured_audio.append((audio_bytes, text))

        engine = TTSEngine(
            provider="kokoro",
            kokoro_url="http://127.0.0.1:8880",
            rvc_enabled=True,
            rvc_url="http://127.0.0.1:7890/convert",
            output_mode="browser",
            on_audio_ready=_on_audio,
        )
        engine._provider.synthesize = AsyncMock(side_effect=RuntimeError("kokoro offline"))
        engine._fallback_provider.synthesize = AsyncMock(return_value=b"EDGE_FALLBACK")
        engine._rvc.convert = AsyncMock(return_value=b"EDGE_PLUS_RVC")

        with patch.object(engine, "_simulate_mouth_flap", AsyncMock()):
            await engine.speak("[emotion: happy] Hello stream!")

        engine._fallback_provider.synthesize.assert_awaited_once()
        engine._rvc.convert.assert_awaited_once_with(b"EDGE_FALLBACK")
        self.assertEqual(captured_audio, [(b"EDGE_PLUS_RVC", "[emotion: happy] Hello stream!")])

    async def test_singer_rvc_integration_and_cleanup(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            songs_path = Path(tmpdir) / "songs.json"
            songs_path.write_text(
                '{"test_song": {"title": "Test", "artist": "Eve", "lyrics": [{"text": "La la la", "emotion": "happy", "pitch": "+5Hz", "rate": "+0%", "pause_after": 0.0}]}}',
                encoding="utf-8",
            )
            singer = Singer(
                songs_config_path=str(songs_path),
                output_mode="browser",
                rvc_enabled=True,
                rvc_url="http://127.0.0.1:7890/convert",
                rvc_pitch_shift=2,
            )
            singer.temp_dir = Path(tmpdir) / "karaoke_tmp"
            singer.temp_dir.mkdir(parents=True, exist_ok=True)
            singer._rvc.convert = AsyncMock(return_value=b"SINGER_RVC_AUDIO")

            class _FakeSingerComm:
                def __init__(self, text, voice, pitch, rate):
                    pass

                async def save(self, path):
                    Path(path).write_bytes(b"RAW_VOCAL")

            emitted_vocals = []

            async def _on_vocal(audio_bytes: bytes, text: str):
                emitted_vocals.append((audio_bytes, text))

            with patch("core.singer.edge_tts.Communicate", _FakeSingerComm):
                ok = await singer.sing("test_song", on_vocal_audio=_on_vocal)

            self.assertTrue(ok)
            singer._rvc.convert.assert_awaited_once_with(b"RAW_VOCAL", pitch_shift=2)
            self.assertEqual(emitted_vocals, [(b"SINGER_RVC_AUDIO", "La la la")])
            self.assertEqual(list(singer.temp_dir.glob("vocal_*.mp3")), [])

    async def test_h1_03_fallback_voice_dynamic_mime_and_singer_provider(self):
        # 1. detect_audio_format and RVC dynamic WAV upload
        import io
        import wave
        import numpy as np

        buf = io.BytesIO()
        t = np.linspace(0, 0.2, int(16000 * 0.2), endpoint=False)
        samples = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(samples.tobytes())
        wav_bytes = buf.getvalue()

        self.assertEqual(detect_audio_format(wav_bytes), ("audio/wav", ".wav"))
        self.assertEqual(detect_audio_format(b"ID3\x03\x00"), ("audio/mpeg", ".mp3"))

        calls = []
        rvc = RVCVoiceConverter(enabled=True, rvc_url="http://127.0.0.1:7890/convert")
        with patch("core.tts_providers.aiohttp.ClientSession", return_value=_FakeSession(_FakeResponse(200, b"OUT"), calls)):
            await rvc.convert(wav_bytes)
        form_data = calls[-1][1]["data"]
        field_headers = form_data._fields[0][1]
        self.assertEqual(field_headers.get("Content-Type"), "audio/wav")

        # 2. TTSEngine fallback uses valid Edge voice instead of Kokoro voice 'af_heart'
        engine = TTSEngine(
            provider="kokoro",
            voice="af_heart",
            fallback_voice="en-US-AriaNeural",
            output_mode="browser",
        )
        engine._provider.synthesize = AsyncMock(side_effect=RuntimeError("kokoro down"))
        engine._fallback_provider.synthesize = AsyncMock(return_value=b"EDGE_OK")
        await engine.speak("Testing fallback voice")
        self.assertEqual(engine._fallback_provider.synthesize.call_args.kwargs["voice"], "en-US-AriaNeural")

        # 3. Singer routes through create_tts_provider
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            songs_path = Path(tmpdir) / "songs.json"
            songs_path.write_text(
                '{"s1": {"title": "T", "lyrics": [{"text": "Sing!", "delay_before": 0.0}]}}',
                encoding="utf-8",
            )
            singer = Singer(
                songs_config_path=str(songs_path),
                provider="kokoro",
                kokoro_url="http://127.0.0.1:8880",
                voice="af_heart",
                output_mode="browser",
            )
            self.assertIsInstance(singer._provider, KokoroTTSProvider)
            singer._provider.synthesize = AsyncMock(return_value=wav_bytes)
            vocals = []

            async def _on_vocal(b, txt):
                vocals.append((b, txt))

            ok = await singer.sing("s1", on_vocal_audio=_on_vocal)
            self.assertTrue(ok)
            self.assertEqual(vocals, [(wav_bytes, "Sing!")])

    async def test_h1_02_real_rms_envelope_and_immediate_stop(self):
        import io
        import wave
        import numpy as np

        buf = io.BytesIO()
        t = np.linspace(0, 0.15, int(16000 * 0.15), endpoint=False)
        samples = (np.sin(2 * np.pi * 440 * t) * 20000).astype(np.int16)
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(samples.tobytes())
        wav_bytes = buf.getvalue()

        env, dur = extract_rms_envelope_from_wav(wav_bytes, frame_ms=50)
        self.assertGreater(len(env), 0)
        self.assertGreater(dur, 0.1)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in env))
        self.assertTrue(any(v > 0.2 for v in env))

        # Verify _play_and_lipsync stops immediately when channel.get_busy() turns False
        # even for a long-word sentence where est_duration would have been > 1s
        fake_channel = MagicMock()
        fake_channel.get_busy.side_effect = [True, False]
        fake_sound = MagicMock()
        fake_sound.play.return_value = fake_channel
        fake_sound.get_length.return_value = 0.15

        fake_mixer = MagicMock()
        fake_mixer.get_init.return_value = (16000, -16, 1)
        fake_mixer.Sound.return_value = fake_sound

        import types
        import sys

        fake_pygame = types.ModuleType("pygame")
        fake_pygame.mixer = fake_mixer

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            wav_path = Path(tmpdir) / "test.wav"
            wav_path.write_bytes(wav_bytes)
            engine = TTSEngine(output_mode="server")
            mouth_vals = []
            with patch.dict(sys.modules, {"pygame": fake_pygame}), \
                 patch("core.tts.asyncio.sleep", new=AsyncMock()):
                await engine._play_and_lipsync(str(wav_path), "one two three four five six seven", mouth_vals.append)
            # Only 1 busy tick + final 0.0 close (not 10+ ticks from est_duration)
            self.assertEqual(len(mouth_vals), 2)
            self.assertGreater(mouth_vals[0], 0.2)
            self.assertEqual(mouth_vals[-1], 0.0)

    async def test_h1_01_stt_persistent_session_and_close(self):
        stt = STTEngine(api_key="sk-test")
        sess1 = stt._get_session()
        sess2 = stt._get_session()
        self.assertIs(sess1, sess2)
        self.assertFalse(sess1.closed)
        await stt.close()
        self.assertTrue(sess1.closed)
        self.assertIsNone(stt._session)


if __name__ == "__main__":
    unittest.main()
