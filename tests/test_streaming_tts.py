import asyncio
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

try:
    import tests  # noqa: F401  # Ensure tests/__init__.py sets MAYBEAI_LLM_PROVIDER=mock
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

from core.brain import Brain
from core.tts import SentenceChunker, TTSEngine


class _FakeStreamContent:
    def __init__(self, lines):
        self._lines = [
            line.encode("utf-8") if isinstance(line, str) else line
            for line in lines
        ]

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for chunk in self._lines:
            yield chunk


class _FakeStreamResp:
    def __init__(self, status: int, lines=None, text_data: str = ""):
        self.status = status
        self.content = _FakeStreamContent(lines or [])
        self._text_data = text_data

    async def text(self):
        return self._text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestSentenceChunker(unittest.TestCase):
    def test_splits_on_delimiters_and_protects_tags_and_abbreviations(self):
        chunker = SentenceChunker(min_chars=8)
        out = []
        out.extend(chunker.feed("[emotion: hap"))
        self.assertEqual(out, [])

        out.extend(chunker.feed("py] Dr. Strange visited 127.0.0.1 at 3.14! "))
        self.assertEqual(out, ["[emotion: happy] Dr. Strange visited 127.0.0.1 at 3.14!"])

        out.extend(chunker.feed("Second sentence?! [action: wink] Third line~\nFinal tail"))
        self.assertEqual(
            out,
            [
                "[emotion: happy] Dr. Strange visited 127.0.0.1 at 3.14!",
                "Second sentence?!",
                "[action: wink] Third line~",
            ],
        )

        rem = chunker.flush()
        self.assertEqual(rem, "Final tail")
        self.assertIsNone(chunker.flush())

    def test_max_chars_safety_valve_splits_outside_tags(self):
        chunker = SentenceChunker(min_chars=8, max_chars=40)
        long_text = "This is a very long sentence without any punctuation marks at all so it must split safely"
        emitted = chunker.feed(long_text)
        rem = chunker.flush()
        self.assertGreaterEqual(len(emitted), 1)
        combined = " ".join(emitted + ([rem] if rem else []))
        self.assertEqual(" ".join(combined.split()), " ".join(long_text.split()))


class TestBrainStreaming(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_dir = Path(self._temp_dir_obj.name)
        self.settings_path = self.temp_dir / "settings.json"
        self.settings_path.write_text(
            json.dumps({
                "llm": {
                    "provider": "gemini",
                    "gemini_model": "gemini-3-flash-preview",
                    "model": "gpt-4o-mini",
                    "ollama_model": "llama3.2",
                    "streaming_enabled": True,
                    "temperature": 0.7,
                    "max_tokens": 120,
                }
            }),
            encoding="utf-8",
        )

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    async def test_mock_stream_yields_chunks_and_records_turn(self):
        brain = Brain(settings_path=str(self.settings_path), character_path="config/character.json")
        try:
            self.assertTrue(brain.is_streaming_enabled())
            chunks = []
            with patch.dict(os.environ, {"MAYBEAI_LLM_PROVIDER": "mock"}, clear=False):
                async for c in brain.generate_response_stream("Viewer", "Halo Eve! Cerita dong!"):
                    chunks.append(c)

            self.assertGreaterEqual(len(chunks), 1)
            full_text = "".join(chunks).strip()
            self.assertTrue(len(full_text) > 0)
            self.assertEqual(brain.history[-1]["content"], full_text)
        finally:
            await brain.close()

    async def test_gemini_sse_stream(self):
        brain = Brain(settings_path=str(self.settings_path), character_path="config/character.json")
        captured = {}

        sse_lines = [
            'data: {"candidates":[{"content":{"parts":[{"text":"[emotion: happy] Halo "}]}}]}\n',
            "\n",
            'data: {"candidates":[{"content":{"parts":[{"text":"dari Gemini SSE!"}]}}]}\n',
            "data: [DONE]\n",
        ]

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            return _FakeStreamResp(status=200, lines=sse_lines)

        fake_session = MagicMock()
        fake_session.post = fake_post

        try:
            chunks = []
            with patch.dict(
                os.environ,
                {"MAYBEAI_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "gem-stream-key"},
                clear=False,
            ), patch.object(brain, "_get_session", new=AsyncMock(return_value=fake_session)):
                async for c in brain.generate_response_stream("Viewer", "Tes Gemini stream"):
                    chunks.append(c)

            self.assertEqual(chunks, ["[emotion: happy] Halo ", "dari Gemini SSE!"])
            self.assertIn("streamGenerateContent?alt=sse", captured["url"])
            self.assertNotIn("?key=", captured["url"])
            self.assertEqual(captured["headers"].get("x-goog-api-key"), "gem-stream-key")
            self.assertEqual(brain.history[-1]["content"], "[emotion: happy] Halo dari Gemini SSE!")
        finally:
            await brain.close()

    async def test_openai_sse_stream(self):
        brain = Brain(settings_path=str(self.settings_path), character_path="config/character.json")
        captured = {}

        sse_lines = [
            'data: {"choices":[{"delta":{"content":"[emotion: smug] OpenAI "}}]}\n',
            'data: {"choices":[{"delta":{"content":"streaming works!"}}]}\n',
            "data: [DONE]\n",
        ]

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["payload"] = json
            return _FakeStreamResp(status=200, lines=sse_lines)

        fake_session = MagicMock()
        fake_session.post = fake_post

        try:
            chunks = []
            with patch.dict(
                os.environ,
                {"MAYBEAI_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "sk-test-stream"},
                clear=False,
            ), patch.object(brain, "_get_session", new=AsyncMock(return_value=fake_session)):
                async for c in brain.generate_response_stream("Viewer", "Tes OpenAI stream"):
                    chunks.append(c)

            self.assertEqual(chunks, ["[emotion: smug] OpenAI ", "streaming works!"])
            self.assertTrue(captured["payload"]["stream"])
            self.assertEqual(captured["headers"].get("Authorization"), "Bearer sk-test-stream")
        finally:
            await brain.close()

    async def test_ollama_ndjson_stream(self):
        brain = Brain(settings_path=str(self.settings_path), character_path="config/character.json")
        captured = {}

        ndjson_lines = [
            '{"message":{"content":"[emotion: happy] Local "},"done":false}\n',
            '{"message":{"content":"Ollama rocks!"},"done":true}\n',
        ]

        def fake_post(url, json=None, timeout=None):
            captured["url"] = url
            captured["payload"] = json
            return _FakeStreamResp(status=200, lines=ndjson_lines)

        fake_session = MagicMock()
        fake_session.post = fake_post

        try:
            chunks = []
            with patch.dict(os.environ, {"MAYBEAI_LLM_PROVIDER": "ollama"}, clear=False), \
                 patch.object(brain, "_get_session", new=AsyncMock(return_value=fake_session)):
                async for c in brain.generate_response_stream("Viewer", "Tes Ollama stream"):
                    chunks.append(c)

            self.assertEqual(chunks, ["[emotion: happy] Local ", "Ollama rocks!"])
            self.assertTrue(captured["payload"]["stream"])
        finally:
            await brain.close()

    async def test_stream_error_falls_back_to_mock(self):
        brain = Brain(settings_path=str(self.settings_path), character_path="config/character.json")
        fake_session = MagicMock()
        fake_session.post = MagicMock(return_value=_FakeStreamResp(status=500, text_data="Internal Error"))

        try:
            chunks = []
            with patch.dict(
                os.environ,
                {"MAYBEAI_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "gem-test"},
                clear=False,
            ), patch.object(brain, "_get_session", new=AsyncMock(return_value=fake_session)):
                async for c in brain.generate_response_stream("Viewer", "Halo fallback"):
                    chunks.append(c)

            self.assertGreaterEqual(len(chunks), 1)
            self.assertTrue("".join(chunks).strip())
        finally:
            await brain.close()


class TestTTSEngineStreaming(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_dir = Path(self._temp_dir_obj.name)
        self.engine = TTSEngine(voice="en-US-AnaNeural", enabled=True)
        self.engine.temp_dir = self.temp_dir

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    def _make_fake_pygame(self):
        mixer_state = {"initialized": False}

        def fake_get_init():
            return (44100, -16, 2) if mixer_state["initialized"] else None

        def fake_init():
            mixer_state["initialized"] = True

        fake_music = MagicMock()
        fake_music.get_busy.return_value = False
        fake_mixer = MagicMock()
        fake_mixer.get_init.side_effect = fake_get_init
        fake_mixer.init.side_effect = fake_init
        fake_mixer.music = fake_music

        fake_pygame = types.ModuleType("pygame")
        fake_pygame.mixer = fake_mixer
        return fake_pygame, fake_mixer, fake_music

    async def test_speak_stream_pipelines_synthesis_parses_tags_and_cleans_up(self):
        fake_pygame, fake_mixer, fake_music = self._make_fake_pygame()
        synthesized_texts = []
        created_files = []

        class FakeCommunicate:
            def __init__(self, text, voice, rate, pitch):
                synthesized_texts.append(text)

            async def save(self, out_path):
                Path(out_path).write_bytes(b"mp3-bytes")
                created_files.append(out_path)

        async def chunk_gen():
            for part in [
                "[emotion: happy] Halo ",
                "semuanya! ",
                "[action: wink] Ini kalimat ",
                "streaming kedua.",
            ]:
                await asyncio.sleep(0)
                yield part

        tags_seen = []
        sentences_started = []
        mouth_values = []

        async def on_tag(emotions, actions):
            tags_seen.append((emotions, actions))

        async def on_sentence_start(sentence):
            sentences_started.append(sentence)

        with patch.dict(sys.modules, {"pygame": fake_pygame}), \
             patch("core.tts.edge_tts.Communicate", side_effect=FakeCommunicate), \
             patch("core.tts.asyncio.sleep", new=AsyncMock()):
            full_raw = await self.engine.speak_stream(
                chunk_gen(),
                on_mouth_update=mouth_values.append,
                on_sentence_start=on_sentence_start,
                on_tag=on_tag,
            )

        self.assertIn("[emotion: happy]", full_raw)
        self.assertEqual(synthesized_texts, ["Halo semuanya!", "Ini kalimat streaming kedua."])
        self.assertEqual(sentences_started, ["Halo semuanya!", "Ini kalimat streaming kedua."])
        self.assertEqual(tags_seen, [(["happy"], []), ([], ["wink"])])
        self.assertEqual(fake_mixer.init.call_count, 1)
        self.assertEqual(fake_music.play.call_count, 2)
        self.assertEqual(mouth_values[-1], 0.0)
        for fp in created_files:
            self.assertFalse(os.path.exists(fp), f"Temp file not deleted: {fp}")
        self.assertEqual(list(self.temp_dir.glob("speech_*.mp3")), [])

    async def test_speak_stream_disabled_simulates_mouth_flap_and_tags(self):
        self.engine.enabled = False
        tags_seen = []
        sentences = []
        mouth_vals = []

        async def chunk_gen():
            yield "[emotion: smug] Streaming tanpa audio aktif!"

        with patch("core.tts.edge_tts.Communicate") as mock_comm, \
             patch("core.tts.asyncio.sleep", new=AsyncMock()):
            raw = await self.engine.speak_stream(
                chunk_gen(),
                on_mouth_update=mouth_vals.append,
                on_sentence_start=sentences.append,
                on_tag=lambda e, a: tags_seen.append((e, a)),
            )

        mock_comm.assert_not_called()
        self.assertIn("Streaming tanpa audio aktif!", raw)
        self.assertEqual(tags_seen, [(["smug"], [])])
        self.assertEqual(sentences, ["Streaming tanpa audio aktif!"])
        self.assertEqual(mouth_vals[-1], 0.0)

    async def test_speak_stream_cancellation_cleans_up_temp_files(self):
        fake_pygame, _, _ = self._make_fake_pygame()
        started_play = asyncio.Event()
        mouth_vals = []

        class FakeCommunicate:
            def __init__(self, text, voice, rate, pitch):
                pass

            async def save(self, out_path):
                Path(out_path).write_bytes(b"mp3-bytes")

        async def slow_chunks():
            yield "Kalimat pertama yang akan dipotong!"
            await asyncio.sleep(5.0)
            yield "Kalimat kedua tidak sempat."

        orig_play = self.engine._play_and_lipsync

        async def blocking_play(file_path, text, on_mouth_update):
            started_play.set()
            try:
                await asyncio.sleep(10.0)
            finally:
                self.engine._cleanup_audio_file(file_path)

        with patch.dict(sys.modules, {"pygame": fake_pygame}), \
             patch("core.tts.edge_tts.Communicate", side_effect=FakeCommunicate), \
             patch.object(self.engine, "_play_and_lipsync", side_effect=blocking_play):
            task = asyncio.create_task(
                self.engine.speak_stream(slow_chunks(), on_mouth_update=mouth_vals.append)
            )
            await asyncio.wait_for(started_play.wait(), timeout=2.0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.assertEqual(list(self.temp_dir.glob("speech_*.mp3")), [])
        self.assertEqual(mouth_vals[-1], 0.0)
        self.assertIsNotNone(orig_play)


class TestOrchestratorStreamingMode(unittest.IsolatedAsyncioTestCase):
    async def test_orchestrator_streaming_mode_broadcasts_chunks_and_final_response(self):
        from core.orchestrator import Orchestrator
        from core.conversation.chat_curator import ChatInteraction, LiveChatMessage

        orch = Orchestrator()
        orch.tts.enabled = False
        orch.brain.settings.setdefault("llm", {})["streaming_enabled"] = True

        events = []
        orch.register_listener(lambda msg: events.append(msg))

        async def fake_stream(*args, **kwargs):
            yield "[emotion: happy] Halo penonton! "
            yield "Streaming aktif nih!"

        msg = LiveChatMessage(user="Viewer1", text="Halo Eve!", source="web", is_creator=False)
        interaction = ChatInteraction(
            primary_message=msg,
            interaction_type="single",
            related_messages=[],
        )

        try:
            with patch.object(orch.brain, "generate_response_stream", side_effect=fake_stream), \
                 patch("core.tts.asyncio.sleep", new=AsyncMock()):
                await orch._execute_interaction(interaction)
        finally:
            await orch.brain.close()

        types_emitted = [e["type"] for e in events]
        self.assertIn("ai_chunk", types_emitted)
        self.assertIn("ai_response", types_emitted)
        ai_resp = next(e["data"] for e in events if e["type"] == "ai_response")
        self.assertTrue(ai_resp.get("streamed"))
        self.assertIn("Halo penonton!", ai_resp["speech"])
        self.assertIn("happy", ai_resp["emotions"])


if __name__ == "__main__":
    unittest.main()
