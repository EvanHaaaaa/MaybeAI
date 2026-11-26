"""Async ffmpeg vertical clip pipeline (16:9 -> 9:16 1080x1920)."""

import asyncio
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _escape_ffmpeg_filter_path(path_str: str) -> str:
    """Escape a filesystem path for ffmpeg's subtitles filter."""
    normalized = str(path_str).replace("\\", "/")
    normalized = normalized.replace(":", r"\:")
    normalized = normalized.replace("'", r"\'")
    return normalized


class ClipPipeline:
    """Converts horizontal stream recordings into 9:16 vertical Shorts/TikTok clips."""

    def __init__(self, clips_dir: str = "data/clips"):
        self.clips_dir = Path(clips_dir)

    def build_vertical_clip_cmd(
        self,
        input_path: str,
        output_path: str,
        start_sec: float = 0.0,
        duration_sec: float = 30.0,
        subtitle_path: Optional[str] = None,
    ) -> List[str]:
        """
        Build a safe ffmpeg argument list (never using shell=True) that crops and
        scales 16:9 footage into 1080x1920 (9:16) vertical format with optional
        burned-in subtitles.
        """
        start = max(0.0, float(start_sec))
        duration = max(0.1, float(duration_sec))

        vf_parts = [
            "scale=1080:1920:force_original_aspect_ratio=increase",
            "crop=1080:1920",
        ]
        if subtitle_path:
            escaped_sub = _escape_ffmpeg_filter_path(str(subtitle_path))
            vf_parts.append(f"subtitles='{escaped_sub}'")

        vf_filter = ",".join(vf_parts)

        return [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(input_path),
            "-t",
            f"{duration:.3f}",
            "-vf",
            vf_filter,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]

    async def create_vertical_clip(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        start_sec: float = 0.0,
        duration_sec: float = 30.0,
        subtitle_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute ffmpeg asynchronously via create_subprocess_exec (no shell=True)
        and return structured result metadata.
        """
        in_path = Path(input_path)
        if output_path is None:
            self.clips_dir.mkdir(parents=True, exist_ok=True)
            stamp = int(time.time())
            out_path = self.clips_dir / f"{in_path.stem}_vertical_{stamp}.mp4"
        else:
            out_path = Path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = self.build_vertical_clip_cmd(
            input_path=str(in_path),
            output_path=str(out_path),
            start_sec=start_sec,
            duration_sec=duration_sec,
            subtitle_path=subtitle_path,
        )

        if not shutil.which("ffmpeg"):
            return {
                "success": False,
                "output_path": str(out_path),
                "command": cmd,
                "error": "ffmpeg executable not found in PATH",
            }

        if not in_path.exists():
            return {
                "success": False,
                "output_path": str(out_path),
                "command": cmd,
                "error": f"Input file not found: {in_path}",
            }

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err_text = stderr.decode("utf-8", errors="replace").strip()
                return {
                    "success": False,
                    "output_path": str(out_path),
                    "command": cmd,
                    "error": err_text or f"ffmpeg exited with code {proc.returncode}",
                }
            return {
                "success": True,
                "output_path": str(out_path),
                "command": cmd,
                "error": None,
            }
        except Exception as exc:
            return {
                "success": False,
                "output_path": str(out_path),
                "command": cmd,
                "error": str(exc),
            }
