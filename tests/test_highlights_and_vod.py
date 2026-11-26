import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import tests  # noqa: F401  # Ensure tests/__init__.py sets MAYBEAI_LLM_PROVIDER=mock
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

import run
from core.event_bus import (
    CHAT_RECEIVED,
    DONATION_RECEIVED,
    EventBus,
    HIGHLIGHT_MARKED,
    VOD_SUMMARY_READY,
)
from core.highlights.detector import GOAL_COMPLETED
from core.highlights import ClipPipeline, HighlightDetector, VODSummarizer


async def _run_asgi_request(
    method: str,
    path: str,
    body: bytes = b"",
    headers=None,
    client=("127.0.0.1", 50300),
):
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": raw_headers,
        "client": client,
        "server": ("127.0.0.1", 7860),
    }
    sent = []
    delivered = False
    done_event = asyncio.Event()

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await done_event.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            done_event.set()

    await run.app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    resp_body = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    resp_headers = {
        k.decode("latin-1").lower(): v.decode("latin-1")
        for k, v in start.get("headers", [])
    }
    return start["status"], resp_headers, resp_body


class TestHighlightDetector(unittest.IsolatedAsyncioTestCase):
    async def test_burst_donation_goal_triggers_and_cooldown(self):
        bus = EventBus()
        replays = []
        marked_events = []
        bus.subscribe(HIGHLIGHT_MARKED, lambda _ev, pl: marked_events.append(pl))

        detector = HighlightDetector(
            event_bus=bus,
            on_save_replay=lambda marker: replays.append(marker.id),
            chat_burst_threshold=4,
            burst_window_sec=10.0,
            cooldown_sec=60.0,
        )

        # 1. Chat velocity burst triggers 1 highlight
        for idx in range(4):
            await bus.publish(CHAT_RECEIVED, {"user": f"Viewer{idx}", "text": "POG!", "source": "twitch"})
        await asyncio.sleep(0)

        self.assertEqual(len(detector.get_highlights()), 1)
        self.assertEqual(detector.get_highlights()[0]["category"], "chat_burst")
        self.assertEqual(len(replays), 1)
        self.assertEqual(len(marked_events), 1)

        # 2. Donation within cooldown is deduplicated
        await bus.publish(DONATION_RECEIVED, {"user": "Whale", "amount": "$20", "currency": "USD"})
        self.assertEqual(len(detector.get_highlights()), 1)

        # 3. Manual highlight bypasses cooldown
        manual = detector.mark_manual(reason="Epic clutch", user="Creator")
        self.assertEqual(manual.category, "manual")
        self.assertEqual(len(detector.get_highlights()), 2)

        # 4. Reset cooldown -> donation and goal triggers fire
        detector.update_config(cooldown_sec=0.0)
        await bus.publish(DONATION_RECEIVED, {"user": "Supporter", "amount": "$5", "currency": "USD"})
        await bus.publish(GOAL_COMPLETED, {"title": "Beat Ender Dragon", "goal_completed": True})

        categories = [h["category"] for h in detector.get_highlights()]
        self.assertIn("donation", categories)
        self.assertIn("goal_completed", categories)


class TestClipPipelineAndVODSummarizer(unittest.IsolatedAsyncioTestCase):
    async def test_ffmpeg_argv_generation_and_no_shell_true(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
            pipeline = ClipPipeline(clips_dir=tmp_dir)
            cmd = pipeline.build_vertical_clip_cmd(
                input_path="C:/videos/replay.mp4",
                output_path=os.path.join(tmp_dir, "out.mp4"),
                start_sec=12.5,
                duration_sec=25.0,
                subtitle_path="C:/subs/eve's_clip.srt",
            )
            self.assertEqual(cmd[0], "ffmpeg")
            self.assertIn("-vf", cmd)
            vf_arg = cmd[cmd.index("-vf") + 1]
            self.assertIn("scale=1080:1920:force_original_aspect_ratio=increase", vf_arg)
            self.assertIn("crop=1080:1920", vf_arg)
            self.assertIn("subtitles=", vf_arg)

            # Verify create_vertical_clip fails gracefully when ffmpeg is missing
            with patch("core.highlights.clipper.shutil.which", return_value=None):
                res = await pipeline.create_vertical_clip(input_path="replay.mp4")
            self.assertFalse(res["success"])
            self.assertIn("ffmpeg", res["error"].lower())

            # Ensure source code uses create_subprocess_exec and never create_subprocess_shell
            clipper_src = Path("core/highlights/clipper.py").read_text(encoding="utf-8")
            self.assertIn("create_subprocess_exec", clipper_src)
            self.assertNotIn("create_subprocess_shell", clipper_src)

    def test_vod_summarizer_markdown_and_unique_suffix(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
            bus = EventBus()
            ready_events = []
            bus.subscribe(VOD_SUMMARY_READY, lambda _ev, pl: ready_events.append(pl))

            vod = VODSummarizer(streams_dir=tmp_dir, event_bus=bus)
            vod.start_session(title="Evening Variety Stream", start_time=1700000000.0)
            vod.record_chat("Alice", "hi!")
            vod.record_chat("Alice", "lol")
            vod.record_donation("Bob", "$10", "USD", "Keep it up!")
            vod.record_goal_completed("Win 1 Chess Game")
            vod.record_song("Digital World", "Eve Maybe")
            vod.record_highlight({"category": "manual", "reason": "Funny moment", "user": "Creator"})

            first = vod.generate_summary(end_time=1700003600.0)
            second = vod.generate_summary(end_time=1700003605.0)

            p1 = Path(first["path"])
            p2 = Path(second["path"])
            self.assertTrue(p1.exists())
            self.assertTrue(p2.exists())
            self.assertNotEqual(p1, p2)
            self.assertTrue(p2.name.endswith("_2.md"))
            self.assertIn("# VOD Summary: Evening Variety Stream", first["markdown"])
            self.assertIn("Alice", first["markdown"])
            self.assertIn("Digital World", first["markdown"])
            self.assertEqual(len(ready_events), 2)


class TestDockerAndHighlightAsgiRoutes(unittest.IsolatedAsyncioTestCase):
    def test_docker_files_exist_with_headless_healthcheck(self):
        root = Path(".")
        dockerfile = root / "Dockerfile"
        compose = root / "docker-compose.yml"
        dockerignore = root / ".dockerignore"
        self.assertTrue(dockerfile.exists())
        self.assertTrue(compose.exists())
        self.assertTrue(dockerignore.exists())

        df_text = dockerfile.read_text(encoding="utf-8")
        self.assertIn("MAYBEAI_HEADLESS=1", df_text)
        self.assertIn("/api/health", df_text)
        self.assertIn("ffmpeg", df_text)

    async def test_health_and_highlights_asgi_routes(self):
        h_status, _, h_body = await _run_asgi_request("GET", "/api/health")
        self.assertEqual(h_status, 200)
        self.assertEqual(json.loads(h_body.decode("utf-8")), {"status": "ok"})

        st_code, headers, st_body = await _run_asgi_request("GET", "/api/highlights/status")
        self.assertEqual(st_code, 200)
        self.assertIn("application/json", headers.get("content-type", ""))
        st_data = json.loads(st_body.decode("utf-8"))
        self.assertIn("highlights", st_data)
        self.assertIn("clipper", st_data)
        self.assertIn("vod_summarizer", st_data)

        with patch.dict(os.environ, {"MAYBEAI_CREATOR_TOKEN": "creator-tok"}):
            deny_code, _, _ = await _run_asgi_request(
                "POST",
                "/api/highlights/action",
                body=json.dumps({"action": "status"}).encode("utf-8"),
                headers={"content-type": "application/json"},
                client=("192.0.2.60", 50301),
            )
            self.assertEqual(deny_code, 401)

            ok_code, _, ok_body = await _run_asgi_request(
                "POST",
                "/api/highlights/action",
                body=json.dumps({"action": "status"}).encode("utf-8"),
                headers={
                    "content-type": "application/json",
                    "x-creator-token": "creator-tok",
                },
                client=("192.0.2.60", 50302),
            )
            self.assertEqual(ok_code, 200)
            self.assertTrue(json.loads(ok_body.decode("utf-8")).get("success"))


if __name__ == "__main__":
    unittest.main()
