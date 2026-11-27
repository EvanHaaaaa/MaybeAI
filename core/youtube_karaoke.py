"""YouTube Song Request & AI Cover / Auto-Karaoke Pipeline for MaybeAI.

Fetches audio + captions from validated YouTube URLs via ``yt-dlp``, separates
vocals/instrumental (via ``demucs`` when installed, or ``ffmpeg`` center-channel
reduction fallback), optionally converts extracted vocals through Eve's RVC
pipeline, and produces a ``Singer``-compatible song entry cached under
``data/karaoke_cache/<video_id>/``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from core.security_net import SSRFValidationError, validate_outbound_url

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_VTT_TIMESTAMP_RE = re.compile(
    r"(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})"
)
_TAG_RE = re.compile(r"<[^>]+>")


class YouTubeKaraokeError(ValueError):
    """Raised when a YouTube song request fails validation or processing."""


def _default_cache_root() -> Path:
    data_dir = os.environ.get("MAYBEAI_DATA_DIR", "").strip()
    base = Path(data_dir) if data_dir else Path("data")
    return base / "karaoke_cache"


def extract_youtube_video_id(url: str) -> str:
    """Validate a YouTube URL (including SSRF checks) and return its 11-char video ID."""
    raw = str(url or "").strip()
    if not raw:
        raise YouTubeKaraokeError("YouTube URL is required.")
    try:
        validate_outbound_url(raw, allowed_schemes=("https", "http"), allow_private=False)
    except SSRFValidationError as exc:
        raise YouTubeKaraokeError(f"Blocked URL: {exc}") from exc

    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        raise YouTubeKaraokeError(f"Unsupported host '{host}'. Only youtube.com and youtu.be are allowed.")

    video_id = ""
    path_parts = [p for p in parsed.path.split("/") if p]
    if host in ("youtu.be", "www.youtu.be"):
        if path_parts:
            video_id = path_parts[0]
    else:
        if parsed.path == "/watch":
            video_id = (parse_qs(parsed.query).get("v") or [""])[0]
        elif len(path_parts) >= 2 and path_parts[0] in ("shorts", "embed", "live"):
            video_id = path_parts[1]

    if not _VIDEO_ID_RE.match(video_id):
        raise YouTubeKaraokeError("Could not extract a valid 11-character YouTube video ID.")
    return video_id


def parse_captions_to_lyrics(caption_text: str) -> List[Dict[str, Any]]:
    """Parse WebVTT or SRT caption text into Singer-compatible timed lyric cues."""
    if not caption_text:
        return []

    cues: List[Dict[str, Any]] = []
    lines = caption_text.replace("\r\n", "\n").split("\n")
    idx = 0
    last_text = ""

    while idx < len(lines):
        line = lines[idx].strip()
        match = _VTT_TIMESTAMP_RE.search(line)
        if not match:
            idx += 1
            continue

        h1 = int(match.group(1) or 0)
        m1 = int(match.group(2))
        s1 = int(match.group(3))
        ms1 = int(match.group(4))
        start_sec = round(h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0, 2)

        idx += 1
        text_parts: List[str] = []
        while idx < len(lines) and lines[idx].strip():
            cleaned = _TAG_RE.sub("", lines[idx]).strip()
            if cleaned and not cleaned.isdigit():
                text_parts.append(cleaned)
            idx += 1

        lyric_text = " ".join(text_parts).strip()
        # Deduplicate rolling auto-caption lines
        if lyric_text and lyric_text != last_text:
            cues.append(
                {
                    "time": start_sec,
                    "text": lyric_text,
                    "emotion": "happy",
                    "pitch": "+0Hz",
                    "rate": "+0%",
                }
            )
            last_text = lyric_text
        idx += 1

    return cues


class YouTubeKaraokeProcessor:
    """Downloads, separates, RVC-converts, and caches YouTube songs for Singer."""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        max_duration_sec: int = 600,
        rvc_converter: Any = None,
        max_filesize: str = "150M",
        max_concurrent_jobs: int = 2,
    ):
        self.cache_dir = Path(cache_dir) if cache_dir else _default_cache_root()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_duration_sec = max(30, int(max_duration_sec))
        self.rvc_converter = rvc_converter
        self.max_filesize = str(max_filesize or "150M").strip() or "150M"
        self._job_semaphore = asyncio.Semaphore(max(1, int(max_concurrent_jobs)))

    @staticmethod
    def tools_available() -> Dict[str, bool]:
        """Report which external media tools are installed on PATH / Python env."""
        demucs_ok = False
        try:
            import importlib.util

            demucs_ok = importlib.util.find_spec("demucs") is not None
        except Exception:
            demucs_ok = False
        return {
            "yt_dlp": shutil.which("yt-dlp") is not None,
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "demucs": demucs_ok,
        }

    async def _run_exec(self, *args: str, timeout: float = 120.0) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            raise YouTubeKaraokeError(f"Command '{args[0]}' timed out after {timeout}s.") from exc
        return (
            int(proc.returncode or 0),
            stdout_b.decode("utf-8", errors="replace"),
            stderr_b.decode("utf-8", errors="replace"),
        )

    async def prepare_song(
        self,
        url: str,
        mode: str = "ai_cover",
        on_status: Optional[Callable[[str, str], Awaitable[None] | None]] = None,
    ) -> Dict[str, Any]:
        """Prepare a YouTube URL into a Singer-compatible song dictionary."""
        async with self._job_semaphore:
            return await self._prepare_song_impl(url=url, mode=mode, on_status=on_status)

    async def _prepare_song_impl(
        self,
        url: str,
        mode: str = "ai_cover",
        on_status: Optional[Callable[[str, str], Awaitable[None] | None]] = None,
    ) -> Dict[str, Any]:
        norm_mode = str(mode or "ai_cover").strip().lower()
        if norm_mode not in ("ai_cover", "auto_karaoke"):
            norm_mode = "ai_cover"

        async def _emit(stage: str, detail: str) -> None:
            if on_status is not None:
                res = on_status(stage, detail)
                if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                    await res

        await _emit("validating", "Validating YouTube URL...")
        video_id = extract_youtube_video_id(url)
        canonical_url = f"https://www.youtube.com/watch?v={video_id}"
        song_dir = self.cache_dir / video_id
        song_dir.mkdir(parents=True, exist_ok=True)
        meta_path = song_dir / "meta.json"

        # Return cached entry if already prepared for this mode
        if meta_path.exists():
            try:
                cached = json.loads(meta_path.read_text(encoding="utf-8"))
                bgm_ok = bool(cached.get("bgm")) and Path(cached["bgm"]).exists()
                vocal_ok = norm_mode == "auto_karaoke" or (
                    bool(cached.get("vocal_track")) and Path(cached["vocal_track"]).exists()
                )
                if bgm_ok and vocal_ok and cached.get("mode") == norm_mode:
                    await _emit("ready", f"Loaded cached song: {cached.get('title', video_id)}")
                    return cached
            except Exception:
                pass

        tools = self.tools_available()
        if not tools["yt_dlp"]:
            raise YouTubeKaraokeError("yt-dlp is not installed on PATH.")
        if not tools["ffmpeg"]:
            raise YouTubeKaraokeError("ffmpeg is not installed on PATH.")

        await _emit("fetching_metadata", f"Fetching metadata for {video_id}...")
        rc, out, err = await self._run_exec(
            "yt-dlp",
            "--dump-single-json",
            "--no-playlist",
            "--no-warnings",
            canonical_url,
            timeout=30.0,
        )
        if rc != 0:
            raise YouTubeKaraokeError(f"yt-dlp metadata fetch failed: {err.strip() or out.strip()}")

        try:
            info = json.loads(out)
        except json.JSONDecodeError as exc:
            raise YouTubeKaraokeError("Failed to parse yt-dlp metadata JSON.") from exc

        duration = float(info.get("duration") or 0.0)
        if duration > self.max_duration_sec:
            raise YouTubeKaraokeError(
                f"Video duration ({int(duration)}s) exceeds limit ({self.max_duration_sec}s)."
            )

        title = str(info.get("title") or video_id).strip()
        artist = str(info.get("uploader") or info.get("channel") or "YouTube").strip()

        source_wav = song_dir / "source.wav"
        if not source_wav.exists():
            await _emit("downloading", f"Downloading audio for '{title}'...")
            out_tpl = str(song_dir / "source.%(ext)s")
            rc, out, err = await self._run_exec(
                "yt-dlp",
                "-x",
                "--audio-format",
                "wav",
                "--audio-quality",
                "0",
                "--max-filesize",
                self.max_filesize,
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs",
                "en.*,id.*,ja.*",
                "--sub-format",
                "vtt/srt/best",
                "--no-playlist",
                "--no-warnings",
                "-o",
                out_tpl,
                canonical_url,
                timeout=180.0,
            )
            if rc != 0 or not source_wav.exists():
                raise YouTubeKaraokeError(f"yt-dlp audio download failed: {err.strip() or out.strip()}")

        # Parse any downloaded captions
        lyrics: List[Dict[str, Any]] = []
        for sub_file in sorted(list(song_dir.glob("*.vtt")) + list(song_dir.glob("*.srt"))):
            try:
                parsed = parse_captions_to_lyrics(sub_file.read_text(encoding="utf-8", errors="replace"))
                if parsed:
                    lyrics = parsed
                    break
            except Exception:
                continue

        instrumental_wav = song_dir / "instrumental.wav"
        vocals_wav = song_dir / "vocals.wav"
        eve_vocals_wav = song_dir / "eve_vocals.wav"

        if norm_mode == "ai_cover" and tools["demucs"]:
            if not instrumental_wav.exists() or not vocals_wav.exists():
                await _emit("separating", "Separating vocals & instrumental via Demucs...")
                demucs_out = song_dir / "demucs_out"
                rc, _, err = await self._run_exec(
                    sys.executable,
                    "-m",
                    "demucs",
                    "--two-stems=vocals",
                    "-o",
                    str(demucs_out),
                    str(source_wav),
                    timeout=300.0,
                )
                if rc != 0:
                    raise YouTubeKaraokeError(f"Demucs separation failed: {err.strip()}")
                found_no_vocals = list(demucs_out.rglob("no_vocals.wav"))
                found_vocals = list(demucs_out.rglob("vocals.wav"))
                if not found_no_vocals or not found_vocals:
                    raise YouTubeKaraokeError("Demucs did not produce vocals/no_vocals stems.")
                shutil.copy2(found_no_vocals[0], instrumental_wav)
                shutil.copy2(found_vocals[0], vocals_wav)
        else:
            if not instrumental_wav.exists():
                await _emit("separating", "Creating karaoke instrumental via ffmpeg center-cancel...")
                rc, _, err = await self._run_exec(
                    "ffmpeg",
                    "-y",
                    "-nostdin",
                    "-i",
                    str(source_wav),
                    "-af",
                    "pan=stereo|c0=c0-c1|c1=c1-c0",
                    str(instrumental_wav),
                    timeout=120.0,
                )
                if rc != 0 or not instrumental_wav.exists():
                    raise YouTubeKaraokeError(f"ffmpeg instrumental creation failed: {err.strip()}")
            if norm_mode == "ai_cover" and not vocals_wav.exists():
                # Fallback when demucs is unavailable: keep source as vocal guide
                shutil.copy2(source_wav, vocals_wav)

        vocal_track_path: Optional[str] = None
        if norm_mode == "ai_cover" and vocals_wav.exists():
            if self.rvc_converter is not None and getattr(self.rvc_converter, "enabled", False) and getattr(self.rvc_converter, "rvc_url", ""):
                if not eve_vocals_wav.exists():
                    await _emit("converting_rvc", "Converting vocals to Eve's voice via RVC...")
                    raw_vocals = await asyncio.to_thread(vocals_wav.read_bytes)
                    converted = await self.rvc_converter.convert(
                        raw_vocals,
                        pitch_shift=int(getattr(self.rvc_converter, "pitch_shift", 0)),
                    )
                    if converted:
                        await asyncio.to_thread(eve_vocals_wav.write_bytes, converted)
                vocal_track_path = str(eve_vocals_wav if eve_vocals_wav.exists() else vocals_wav)
            else:
                vocal_track_path = str(vocals_wav)

        if not lyrics:
            lyrics = [
                {
                    "time": 0.5,
                    "text": f"♪ {title} ♪",
                    "emotion": "happy",
                    "pitch": "+0Hz",
                    "rate": "+0%",
                }
            ]

        song_entry: Dict[str, Any] = {
            "id": f"yt_{video_id}",
            "video_id": video_id,
            "source": "youtube",
            "url": canonical_url,
            "mode": norm_mode,
            "title": title,
            "artist": artist,
            "duration_sec": duration,
            "bgm": str(instrumental_wav),
            "vocal_track": vocal_track_path,
            "lyrics": lyrics,
        }
        await asyncio.to_thread(meta_path.write_text, json.dumps(song_entry, indent=2), "utf-8")
        await _emit("ready", f"Ready: {title}")
        return song_entry
