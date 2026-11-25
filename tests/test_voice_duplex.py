import asyncio
import base64
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

try:
    import tests  # noqa: F401
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

import run
from core.orchestrator import Orchestrator
from core.stt import EnergyVAD, STTEngine, StreamingSTTSession
from core.tts import TTSEngine


def _pcm16_frame(amplitude: int, num_samples: int = 320) -> bytes:
    """Generates a mono PCM16 frame with constant sample amplitude."""
    clamped = max(-32768, min(32767, int(amplitude)))
    return struct.pack(f"<{num_samples}h", *([clamped] * num_samples))


class TestEnergyVAD(unittest.TestCase):
    def test_onset_hangover_and_silence_transitions(self):
        vad = EnergyVAD(
            energy_threshold=0.05,
            sample_rate=16000,
            min_speech_frames=2,
            hangover_frames=3,
        )
        quiet = _pcm16_frame(100)   # ~0.003 RMS
        loud = _pcm16_frame(8000)   # ~0.244 RMS

        # Initial silence
        r0 = vad.process(quiet)
        self.assertFalse(r0.is_speech)
        self.assertFalse(r0.speech_started)
        self.assertFalse(r0.speech_ended)

        # Single loud frame is below min_speech_frames=2 (onset hysteresis)
        r1 = vad.process(loud)
        self.assertFalse(r1.is_speech)
        self.assertFalse(r1.speech_started)

        # Second loud frame triggers speech_started
        r2 = vad.process(loud)
        self.assertTrue(r2.is_speech)
        self.assertTrue(r2.speech_started)
        self.assertFalse(r2.speech_ended)

        # Two quiet frames stay in speech during hangover_frames=3
        h1 = vad.process(quiet)
        h2 = vad.process(quiet)
        self.assertTrue(h1.is_speech)
        self.assertTrue(h2.is_speech)
        self.assertFalse(h2.speech_ended)

        # Third quiet frame ends speech
        h3 = vad.process(quiet)
        self.assertFalse(h3.is_speech)
        self.assertFalse(h3.speech_started)
        self.assertTrue(h3.speech_ended)

        # Subsequent silence stays quiet
        r_after = vad.process(quiet)
        self.assertFalse(r_after.is_speech)
        self.assertFalse(r_after.speech_ended)

    def test_compute_rms_handles_empty_and_reset(self):
        self.assertEqual(EnergyVAD.compute_rms(b""), 0.0)
        self.assertEqual(EnergyVAD.compute_rms(b"\x01"), 0.0)
        vad = EnergyVAD(energy_threshold=0.05, min_speech_frames=1, hangover_frames=5)
        self.assertTrue(vad.process(_pcm16_frame(8000)).speech_started)
        vad.reset()
        self.assertFalse(vad.process(_pcm16_frame(100)).is_speech)


class TestStreamingSTTSession(unittest.IsolatedAsyncioTestCase):
    async def test_chunking_and_offline_transcription(self):
        stt = STTEngine(model_name="base", device="cpu", enabled=True, vad_energy_threshold=0.05)
        vad = EnergyVAD(energy_threshold=0.05, sample_rate=16000, min_speech_frames=2, hangover_frames=2)
        session = StreamingSTTSession(stt_engine=stt, vad=vad, sample_rate=16000, pre_roll_frames=1)

        quiet = _pcm16_frame(50)
        loud = _pcm16_frame(10000)

        res_pre = await session.feed_pcm_chunk(quiet)
        self.assertFalse(res_pre["speech_started"])
        self.assertIsNone(res_pre["transcript"])

        res_1 = await session.feed_pcm_chunk(loud)
        self.assertFalse(res_1["speech_started"])

        res_2 = await session.feed_pcm_chunk(loud)
        self.assertTrue(res_2["speech_started"])
        self.assertTrue(res_2["is_speech"])

        # Hangover 1 -> still buffering
        res_h1 = await session.feed_pcm_chunk(quiet)
        self.assertFalse(res_h1["speech_ended"])
        self.assertIsNone(res_h1["transcript"])

        # Hangover 2 -> utterance ends & offline mock transcribes WAV bytes
        res_h2 = await session.feed_pcm_chunk(quiet)
        self.assertTrue(res_h2["speech_ended"])
        self.assertGreater(res_h2["wav_bytes_len"], 44)
        self.assertIsNotNone(res_h2["transcript"])
        self.assertIn("[STT Mock]", res_h2["transcript"])
        self.assertEqual(session.utterances_transcribed, 1)

    async def test_flush_transcribes_active_buffer(self):
        stt = STTEngine(enabled=True, vad_energy_threshold=0.05)
        vad = EnergyVAD(energy_threshold=0.05, sample_rate=16000, min_speech_frames=1, hangover_frames=10)
        session = StreamingSTTSession(stt_engine=stt, vad=vad, sample_rate=16000)

        await session.feed_pcm_chunk(_pcm16_frame(12000))
        transcript = await session.flush()
        self.assertIsNotNone(transcript)
        self.assertIn("[STT Mock]", transcript)
        self.assertIsNone(await session.flush())


class TestTTSEngineInterrupt(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.audio_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    async def test_stop_interrupts_speak_and_cleans_temp_files(self):
        tts = TTSEngine(enabled=True, interruptible=True)
        tts.temp_dir = self.audio_dir
        mouth_values = []
        playback_started = asyncio.Event()

        class FakeCommunicate:
            def __init__(self, text, voice, rate, pitch):
                self.text = text

            async def save(self, out_path):
                Path(out_path).write_bytes(b"FAKE_MP3")

        async def slow_play(file_path, text, on_mouth_update):
            playback_started.set()
            try:
                await asyncio.sleep(5.0)
            finally:
                tts._cleanup_audio_file(file_path)

        with patch("core.tts.edge_tts.Communicate", FakeCommunicate), \
             patch.object(tts, "_play_and_lipsync", side_effect=slow_play):
            speak_task = asyncio.create_task(
                tts.speak("Halo semuanya ini kalimat panjang banget!", on_mouth_update=mouth_values.append)
            )
            await asyncio.wait_for(playback_started.wait(), timeout=2.0)
            self.assertTrue(tts.is_speaking)

            stopped = tts.stop(reason="barge_in")
            self.assertTrue(stopped)
            result = await asyncio.wait_for(speak_task, timeout=2.0)

        self.assertIsNone(result)
        self.assertFalse(tts.is_speaking)
        self.assertTrue(tts.was_interrupted)
        self.assertEqual(mouth_values[-1], 0.0)
        self.assertEqual(list(self.audio_dir.glob("speech_*.mp3")), [])

    async def test_stop_interrupts_speak_stream_and_cleans_temp_files(self):
        tts = TTSEngine(enabled=True, interruptible=True)
        tts.temp_dir = self.audio_dir
        mouth_values = []
        playback_started = asyncio.Event()

        class FakeCommunicate:
            def __init__(self, text, voice, rate, pitch):
                self.text = text

            async def save(self, out_path):
                Path(out_path).write_bytes(b"FAKE_MP3")

        async def slow_play(file_path, text, on_mouth_update):
            playback_started.set()
            try:
                await asyncio.sleep(5.0)
            finally:
                tts._cleanup_audio_file(file_path)

        async def chunk_gen():
            yield "Kalimat pertama yang panjang banget. "
            await asyncio.sleep(0.05)
            yield "Kalimat kedua tidak boleh selesai."
            await asyncio.sleep(5.0)

        with patch("core.tts.edge_tts.Communicate", FakeCommunicate), \
             patch.object(tts, "_play_and_lipsync", side_effect=slow_play):
            stream_task = asyncio.create_task(
                tts.speak_stream(chunk_gen(), on_mouth_update=mouth_values.append)
            )
            await asyncio.wait_for(playback_started.wait(), timeout=2.0)
            self.assertTrue(tts.is_speaking)

            stopped = tts.stop(reason="creator_vad")
            self.assertTrue(stopped)
            raw_out = await asyncio.wait_for(stream_task, timeout=2.0)

        self.assertIn("Kalimat pertama", raw_out)
        self.assertFalse(tts.is_speaking)
        self.assertTrue(tts.was_interrupted)
        self.assertEqual(mouth_values[-1], 0.0)
        self.assertEqual(list(self.audio_dir.glob("speech_*.mp3")), [])

    async def test_non_interruptible_tts_ignores_stop(self):
        tts = TTSEngine(enabled=False, interruptible=False)
        stopped = tts.stop(reason="barge_in")
        self.assertFalse(stopped)
        self.assertFalse(tts.was_interrupted)


async def _run_http_get(path: str):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 50200),
        "server": ("127.0.0.1", 7860),
    }
    sent = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await run.app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], json.loads(body.decode("utf-8"))


async def _run_ws(client_host: str = "127.0.0.1", origin: str = "http://127.0.0.1:7860", query_string: str = "", incoming_json=None):
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/ws",
        "raw_path": b"/ws",
        "query_string": query_string.encode("latin-1"),
        "headers": [(b"origin", origin.encode("latin-1"))],
        "client": (client_host, 50201),
        "server": ("127.0.0.1", 7860),
        "subprotocols": [],
    }
    queue = [{"type": "websocket.connect"}]
    for item in incoming_json or []:
        queue.append({"type": "websocket.receive", "text": json.dumps(item)})
    queue.append({"type": "websocket.disconnect", "code": 1000})

    sent = []

    async def receive():
        if queue:
            return queue.pop(0)
        await asyncio.sleep(0)
        return {"type": "websocket.disconnect", "code": 1000}

    async def send(message):
        sent.append(message)

    await run.app(scope, receive, send)
    return sent


class TestOrchestratorAndVoiceRoutes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._orig_security = dict(run.config_mgr.settings.get("security", {}))
        while not run.orchestrator.chat.queue.empty():
            run.orchestrator.chat.queue.get_nowait()

    async def asyncTearDown(self):
        run.config_mgr.settings["security"] = self._orig_security
        while not run.orchestrator.chat.queue.empty():
            run.orchestrator.chat.queue.get_nowait()

    async def test_orchestrator_barge_in_preempts_active_interaction_without_deadlock(self):
        orch = Orchestrator()
        events = []
        orch.event_bus.subscribe("*", lambda name, data: events.append((name, data)))

        entered_lock = asyncio.Event()

        async def slow_interaction():
            async with orch._busy_lock:
                orch.tts._is_speaking = True
                entered_lock.set()
                try:
                    await asyncio.sleep(5.0)
                finally:
                    orch.tts._is_speaking = False

        orch._active_interaction_task = asyncio.create_task(slow_interaction())
        await asyncio.wait_for(entered_lock.wait(), timeout=2.0)
        self.assertTrue(orch.is_busy)

        res = await asyncio.wait_for(orch.barge_in(source="creator", reason="vad"), timeout=2.0)
        self.assertTrue(res["interrupted"])
        self.assertTrue(res["task_cancelled"])
        self.assertEqual(res["barge_in_count"], 1)
        self.assertFalse(orch.is_busy)
        self.assertTrue(any(ev == "voice.barge_in" for ev, _ in events))
        self.assertTrue(any(ev == "avatar.state" and d.get("mouth_open") == 0.0 for ev, d in events))

    async def test_orchestrator_process_voice_chunk_triggers_barge_in_and_queues_mic(self):
        orch = Orchestrator()
        orch.stt.update_config(enabled=True, vad_enabled=True, vad_energy_threshold=0.05)
        orch.voice_session = StreamingSTTSession(
            stt_engine=orch.stt,
            vad=EnergyVAD(energy_threshold=0.05, sample_rate=16000, min_speech_frames=1, hangover_frames=1),
            sample_rate=16000,
        )
        orch.tts._is_speaking = True
        barge_mock = AsyncMock(return_value={"interrupted": True, "barge_in_count": 1})
        orch.barge_in = barge_mock

        res1 = await orch.process_voice_chunk(_pcm16_frame(10000), user="Creator")
        self.assertTrue(res1["speech_started"])
        barge_mock.assert_awaited_once_with(source="creator", reason="vad")

        res2 = await orch.process_voice_chunk(_pcm16_frame(50), user="Creator")
        self.assertTrue(res2["speech_ended"])
        queued = await orch.chat.get_next_message()
        self.assertEqual(queued.source, "mic")
        self.assertTrue(queued.is_creator)
        self.assertIn("[STT Mock]", queued.text)

    async def test_ws_barge_in_and_voice_chunk_creator_only_enforcement(self):
        run.config_mgr.settings["security"] = {"creator_token": "", "allowed_origins": []}
        chunk_b64 = base64.b64encode(_pcm16_frame(9000)).decode("ascii")

        # 1. Non-loopback client must be rejected on barge_in & voice_audio_chunk
        with patch.object(run.orchestrator, "barge_in", AsyncMock()) as mock_barge, \
             patch.object(run.orchestrator, "process_voice_chunk", AsyncMock()) as mock_chunk:
            sent_non_creator = await _run_ws(
                client_host="198.51.100.42",
                incoming_json=[
                    {"type": "barge_in", "reason": "spoof"},
                    {"type": "voice_audio_chunk", "audio_b64": chunk_b64},
                ],
            )
            mock_barge.assert_not_awaited()
            mock_chunk.assert_not_awaited()

        err_msgs = [
            json.loads(m["text"])
            for m in sent_non_creator
            if m["type"] == "websocket.send" and json.loads(m["text"]).get("type") == "error"
        ]
        self.assertEqual(len(err_msgs), 2)
        self.assertTrue(all(e["data"]["code"] == "forbidden" for e in err_msgs))

        # 2. Authorized loopback creator is allowed
        with patch.object(run.orchestrator, "barge_in", AsyncMock(return_value={"interrupted": True})) as mock_barge_ok, \
             patch.object(run.orchestrator, "process_voice_chunk", AsyncMock(return_value={"is_speech": True, "rms": 0.3})) as mock_chunk_ok:
            sent_creator = await _run_ws(
                client_host="127.0.0.1",
                incoming_json=[
                    {"type": "barge_in", "reason": "creator_vad"},
                    {"type": "voice_audio_chunk", "audio_b64": chunk_b64, "user": "Creator"},
                ],
            )
            mock_barge_ok.assert_awaited_once_with(source="creator", reason="creator_vad")
            mock_chunk_ok.assert_awaited_once()

        acks = [
            json.loads(m["text"])
            for m in sent_creator
            if m["type"] == "websocket.send" and json.loads(m["text"]).get("type") == "voice_chunk_ack"
        ]
        self.assertEqual(len(acks), 1)
        self.assertTrue(acks[0]["data"]["is_speech"])

    async def test_get_api_voice_status(self):
        status, data = await _run_http_get("/api/voice/status")
        self.assertEqual(status, 200)
        for key in ("stt", "voice_session", "tts", "barge_in_count", "busy"):
            self.assertIn(key, data)
        self.assertIn("vad_enabled", data["stt"])
        self.assertIn("interruptible", data["tts"])


if __name__ == "__main__":
    unittest.main()
