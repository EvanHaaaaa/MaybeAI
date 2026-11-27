import io
import json
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.config_manager import ConfigManager
from core.singer import Singer
from core.youtube_karaoke import (
    YouTubeKaraokeError,
    YouTubeKaraokeProcessor,
    extract_youtube_video_id,
    parse_captions_to_lyrics,
)


def _make_tone_wav_bytes(duration_sec: float = 0.25, sample_rate: int = 16000) -> bytes:
    num_samples = int(duration_sec * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            val = int(12000 * math.sin(2.0 * math.pi * 440.0 * i / sample_rate))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(bytes(frames))
    return buf.getvalue()


class TestYouTubeKaraoke(unittest.IsolatedAsyncioTestCase):
    def test_extract_youtube_video_id_valid_and_blocked(self):
        self.assertEqual(
            extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ?t=42"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            extract_youtube_video_id("https://music.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            extract_youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )
        for bad_url in (
            "",
            "http://127.0.0.1:8000/watch?v=dQw4w9WgXcQ",
            "http://169.254.169.254/latest/meta-data/",
            "https://evil.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=bad",
        ):
            with self.assertRaises(YouTubeKaraokeError):
                extract_youtube_video_id(bad_url)

    def test_parse_captions_to_lyrics_vtt(self):
        vtt = (
            "WEBVTT\n\n"
            "00:00:01.200 --> 00:00:03.500\n"
            "<c>Hello</c> world\n\n"
            "00:00:03.500 --> 00:00:05.000\n"
            "Hello world\n\n"
            "00:00:05.500 --> 00:00:08.000\n"
            "Sing along!\n"
        )
        cues = parse_captions_to_lyrics(vtt)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0]["time"], 1.2)
        self.assertEqual(cues[0]["text"], "Hello world")
        self.assertEqual(cues[1]["time"], 5.5)
        self.assertEqual(cues[1]["text"], "Sing along!")

    async def test_prepare_song_ai_cover_with_rvc_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "karaoke_cache"
            rvc_mock = MagicMock()
            rvc_mock.enabled = True
            rvc_mock.rvc_url = "http://127.0.0.1:7865"
            rvc_mock.pitch_shift = 2
            converted_wav = _make_tone_wav_bytes(0.2)
            rvc_mock.convert = AsyncMock(return_value=converted_wav)

            proc = YouTubeKaraokeProcessor(cache_dir=cache_dir, max_duration_sec=600, rvc_converter=rvc_mock)
            vid = "dQw4w9WgXcQ"
            song_dir = cache_dir / vid
            wav_bytes = _make_tone_wav_bytes(0.2)

            async def fake_run_exec(*args, timeout=120.0):
                cmd = args[0]
                if cmd == "yt-dlp" and "--dump-single-json" in args:
                    return 0, json.dumps({"title": "Test Song", "uploader": "Tester", "duration": 180}), ""
                if cmd == "yt-dlp":
                    song_dir.mkdir(parents=True, exist_ok=True)
                    (song_dir / "source.wav").write_bytes(wav_bytes)
                    (song_dir / "source.en.vtt").write_text(
                        "WEBVTT\n\n00:00:00.100 --> 00:00:01.000\nLa la la\n",
                        encoding="utf-8",
                    )
                    return 0, "ok", ""
                if cmd == "ffmpeg":
                    (song_dir / "instrumental.wav").write_bytes(wav_bytes)
                    return 0, "ok", ""
                return 1, "", "unexpected"

            statuses = []
            with (
                patch.object(YouTubeKaraokeProcessor, "tools_available", return_value={"yt_dlp": True, "ffmpeg": True, "demucs": False}),
                patch.object(proc, "_run_exec", side_effect=fake_run_exec),
            ):
                entry = await proc.prepare_song(
                    f"https://www.youtube.com/watch?v={vid}",
                    mode="ai_cover",
                    on_status=lambda s, d: statuses.append(s),
                )
                self.assertEqual(entry["id"], f"yt_{vid}")
                self.assertEqual(entry["title"], "Test Song")
                self.assertTrue(Path(entry["bgm"]).exists())
                self.assertTrue(Path(entry["vocal_track"]).exists())
                self.assertEqual(entry["lyrics"][0]["text"], "La la la")
                self.assertIn("converting_rvc", statuses)
                self.assertEqual(statuses[-1], "ready")
                rvc_mock.convert.assert_awaited_once()

                # Second call hits cache without running yt-dlp/RVC again
                rvc_mock.convert.reset_mock()
                cached_entry = await proc.prepare_song(f"https://youtu.be/{vid}", mode="ai_cover")
                self.assertEqual(cached_entry["id"], f"yt_{vid}")
                rvc_mock.convert.assert_not_awaited()

    async def test_prepare_song_rejects_excessive_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = YouTubeKaraokeProcessor(cache_dir=Path(tmp), max_duration_sec=120)

            async def fake_meta(*args, timeout=120.0):
                return 0, json.dumps({"title": "Too Long", "duration": 999}), ""

            with (
                patch.object(YouTubeKaraokeProcessor, "tools_available", return_value={"yt_dlp": True, "ffmpeg": True, "demucs": False}),
                patch.object(proc, "_run_exec", side_effect=fake_meta),
            ):
                with self.assertRaises(YouTubeKaraokeError):
                    await proc.prepare_song("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    async def test_singer_plays_vocal_track_in_browser_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            vocal_path = Path(tmp) / "eve_vocals.wav"
            vocal_path.write_bytes(_make_tone_wav_bytes(0.15))
            singer = Singer(songs_config_path=str(Path(tmp) / "missing.json"), output_mode="browser")
            singer.songs["yt_test"] = {
                "title": "YT Cover",
                "bgm": str(Path(tmp) / "missing_bgm.wav"),
                "vocal_track": str(vocal_path),
                "duration_sec": 0.15,
                "lyrics": [{"time": 0.0, "text": "Hello Stage", "emotion": "happy"}],
            }

            lyrics_seen = []
            audio_seen = []
            mouth_vals = []

            ok = await singer.sing(
                "yt_test",
                on_lyric_update=lambda t, e: lyrics_seen.append((t, e)),
                on_mouth_update=lambda v: mouth_vals.append(v),
                on_vocal_audio=lambda b, t: audio_seen.append((len(b), t)),
            )
            self.assertTrue(ok)
            self.assertEqual(lyrics_seen, [("Hello Stage", "happy")])
            self.assertEqual(len(audio_seen), 1)
            self.assertEqual(mouth_vals[-1], 0.0)
            self.assertTrue(any(v > 0.0 for v in mouth_vals))

    def test_config_schema_validates_with_youtube_keys(self):
        cfg = ConfigManager()
        ok, errors = cfg.validate_config(cfg.DEFAULT_SETTINGS)
        self.assertTrue(ok, f"Unexpected config validation errors: {errors}")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
