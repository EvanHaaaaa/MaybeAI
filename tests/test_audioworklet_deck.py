import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

try:
    import tests  # noqa: F401
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

import run
from core.event_bus import EventBus, Events
from core.orchestrator import Orchestrator


async def _run_http_get(path: str, query_string: str = "", headers=None):
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query_string.encode("ascii"),
        "headers": raw_headers,
        "client": ("127.0.0.1", 50110),
        "server": ("127.0.0.1", 7860),
    }
    sent = []
    delivered = False
    done_event = asyncio.Event()

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await done_event.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            done_event.set()

    await run.app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    resp_body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    resp_headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in start.get("headers", [])}
    return start["status"], resp_headers, resp_body


class TestAudioWorkletAndDeck(unittest.IsolatedAsyncioTestCase):
    async def test_get_deck_returns_200_html_with_stream_deck_controls(self):
        status, headers, body = await _run_http_get("/deck")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("content-type", ""))
        html = body.decode("utf-8")
        self.assertIn('id="btn-deck-barge-in"', html)
        self.assertIn('id="btn-deck-mic"', html)
        self.assertIn("/static/deck.js", html)

    async def test_deck_and_audioworklet_assets_exist_and_have_expected_symbols(self):
        root = Path(__file__).resolve().parent.parent
        worklet_js = (root / "web" / "audio-worklet-processor.js").read_text(encoding="utf-8")
        deck_js = (root / "web" / "deck.js").read_text(encoding="utf-8")

        self.assertIn("MaybeAIPCMProcessor", worklet_js)
        self.assertIn('registerProcessor("maybeai-pcm-processor"', worklet_js)
        self.assertIn("16000", worklet_js)

        self.assertIn("audioWorklet.addModule", deck_js)
        self.assertIn("voice_audio_chunk", deck_js)
        self.assertIn("X-Creator-Token", deck_js)

    async def test_process_voice_chunk_emits_stt_partial_and_final_on_event_bus(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            bus = EventBus()
            partials = []
            finals = []
            bus.subscribe(Events.STT_PARTIAL, lambda _evt, p: partials.append(p))
            bus.subscribe(Events.STT_FINAL, lambda _evt, p: finals.append(p))

            with patch.object(Orchestrator, "_configure_platform_adapters", lambda self, settings=None: None):
                orch = Orchestrator(event_bus=bus)
            try:
                orch.voice_session.feed_pcm_chunk = AsyncMock(
                    return_value={
                        "is_speech": True,
                        "speech_started": True,
                        "speech_ended": False,
                        "rms": 0.42,
                        "partial_transcript": "halo eve",
                        "transcript": "halo eve apa kabar",
                    }
                )
                orch.chat.put_message = AsyncMock()

                res = await orch.process_voice_chunk(b"\x01\x00" * 320, user="Creator")
                self.assertEqual(res["transcript"], "halo eve apa kabar")
                self.assertTrue(len(partials) >= 1)
                self.assertEqual(partials[0]["text"], "halo eve")
                self.assertTrue(len(finals) >= 1)
                self.assertEqual(finals[0]["text"], "halo eve apa kabar")
            finally:
                await orch.shutdown()


if __name__ == "__main__":
    unittest.main()
