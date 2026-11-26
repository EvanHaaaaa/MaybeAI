import io
import os
import re
import tempfile
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import aiohttp
import edge_tts


EMOTION_PROSODY_OFFSETS: Dict[str, Tuple[int, int]] = {
    "neutral": (0, 0),
    "happy": (8, 12),
    "excited": (15, 20),
    "smug": (-4, -5),
    "angry": (10, 8),
    "annoyed": (4, -6),
    "sad": (-12, -15),
    "blush": (-5, 8),
    "whisper": (-15, -10),
}

_RATE_RE = re.compile(r"^\s*([+-]?\d+)\s*%\s*$")
_PITCH_RE = re.compile(r"^\s*([+-]?\d+)\s*Hz\s*$", re.IGNORECASE)


def _apply_offset(base_value: str, delta: int, pattern: re.Pattern, unit: str, min_val: int, max_val: int) -> str:
    """Applies an integer offset to a signed prosody string like '+5%' or '+10Hz'."""
    if delta == 0:
        return base_value
    match = pattern.match(str(base_value or ""))
    if not match:
        base_num = 0
    else:
        base_num = int(match.group(1))
    total = max(min_val, min(max_val, base_num + delta))
    sign = "+" if total >= 0 else ""
    return f"{sign}{total}{unit}"


def compute_emotion_prosody(rate: str, pitch: str, emotion: str = "neutral") -> Tuple[str, str]:
    """Returns emotion-adjusted (rate, pitch) strings for Edge-TTS."""
    key = str(emotion or "neutral").strip().lower()
    rate_delta, pitch_delta = EMOTION_PROSODY_OFFSETS.get(key, (0, 0))
    adjusted_rate = _apply_offset(rate, rate_delta, _RATE_RE, "%", -50, 100)
    adjusted_pitch = _apply_offset(pitch, pitch_delta, _PITCH_RE, "Hz", -50, 100)
    return adjusted_rate, adjusted_pitch


def _rate_to_speed_multiplier(rate: str) -> float:
    """Converts a percentage rate string like '+10%' into a float speed multiplier (e.g. 1.1)."""
    match = _RATE_RE.match(str(rate or ""))
    if not match:
        return 1.0
    pct = int(match.group(1))
    return max(0.5, min(2.0, 1.0 + pct / 100.0))


class BaseTTSProvider(ABC):
    """Abstract base class for neural TTS synthesis providers."""

    name: str = "base"

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: str,
        pitch: str,
        emotion: str = "neutral",
        **kwargs: Any,
    ) -> bytes:
        """Synthesizes text to audio bytes (MP3/WAV)."""

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """Returns metadata describing the provider configuration."""


class EdgeTTSProvider(BaseTTSProvider):
    """Default Microsoft Edge-TTS provider with emotion-conditioned prosody offsets."""

    name: str = "edge-tts"

    def __init__(self, **kwargs: Any):
        self.options = kwargs

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: str,
        pitch: str,
        emotion: str = "neutral",
        **kwargs: Any,
    ) -> bytes:
        adj_rate, adj_pitch = compute_emotion_prosody(rate, pitch, emotion)
        fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="edge_tts_")
        os.close(fd)
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=adj_rate,
                pitch=adj_pitch,
            )
            await communicate.save(tmp_path)
            return Path(tmp_path).read_bytes()
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def get_info(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "type": "cloud",
            "supports_emotions": list(EMOTION_PROSODY_OFFSETS.keys()),
        }


class KokoroTTSProvider(BaseTTSProvider):
    """
    Low-latency Kokoro-82M TTS provider.
    Supports remote HTTP inference via `kokoro_url` (OpenAI-compatible `/v1/audio/speech`
    or direct endpoint) and local inference via `kokoro_onnx` or `kokoro`.
    """

    name: str = "kokoro"

    def __init__(
        self,
        kokoro_url: str = "",
        lang_code: str = "a",
        default_voice: str = "af_heart",
        timeout: float = 15.0,
        **kwargs: Any,
    ):
        self.kokoro_url = str(kokoro_url or "").strip()
        self.lang_code = lang_code
        self.default_voice = default_voice
        self.timeout = float(timeout)
        self._local_pipeline: Any = None
        self._local_backend: Optional[str] = None

    def _resolve_endpoint(self) -> str:
        parsed = urlparse(self.kokoro_url)
        if not parsed.path or parsed.path == "/":
            return self.kokoro_url.rstrip("/") + "/v1/audio/speech"
        return self.kokoro_url

    @staticmethod
    def _pcm_to_wav_bytes(samples: Any, sample_rate: int = 24000) -> bytes:
        import numpy as np

        arr = np.asarray(samples, dtype=np.float32)
        arr = np.clip(arr, -1.0, 1.0)
        pcm = (arr * 32767.0).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())
        return buf.getvalue()

    def _synthesize_local_sync(self, text: str, voice: str, speed: float) -> bytes:
        if self._local_pipeline is None:
            try:
                from kokoro import KPipeline  # type: ignore

                self._local_pipeline = KPipeline(lang_code=self.lang_code)
                self._local_backend = "kokoro"
            except ImportError:
                try:
                    import kokoro_onnx  # type: ignore

                    model_path = os.getenv("KOKORO_MODEL_PATH", "kokoro-v1.0.onnx")
                    voices_path = os.getenv("KOKORO_VOICES_PATH", "voices-v1.0.bin")
                    self._local_pipeline = kokoro_onnx.Kokoro(model_path, voices_path)
                    self._local_backend = "kokoro_onnx"
                except ImportError as exc:
                    raise RuntimeError(
                        "Neither 'kokoro' nor 'kokoro_onnx' is installed and 'kokoro_url' is not configured."
                    ) from exc

        target_voice = voice if (voice and "-" not in voice) else self.default_voice
        if self._local_backend == "kokoro_onnx":
            samples, sample_rate = self._local_pipeline.create(text, voice=target_voice, speed=speed)
            return self._pcm_to_wav_bytes(samples, int(sample_rate))

        import numpy as np

        chunks = []
        for _, _, audio in self._local_pipeline(text, voice=target_voice, speed=speed):
            chunks.append(np.asarray(audio, dtype=np.float32))
        if not chunks:
            raise RuntimeError("Kokoro local pipeline produced no audio.")
        combined = np.concatenate(chunks)
        return self._pcm_to_wav_bytes(combined, 24000)

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: str,
        pitch: str,
        emotion: str = "neutral",
        **kwargs: Any,
    ) -> bytes:
        speed = _rate_to_speed_multiplier(rate)
        if self.kokoro_url:
            endpoint = self._resolve_endpoint()
            target_voice = kwargs.get("kokoro_voice") or (
                voice if (voice and "-" not in voice) else self.default_voice
            )
            payload = {
                "model": "kokoro",
                "input": text,
                "voice": target_voice,
                "speed": speed,
                "response_format": "mp3",
                "emotion": emotion,
            }
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, json=payload) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        raise RuntimeError(f"Kokoro HTTP {resp.status}: {err_text[:200]}")
                    data = await resp.read()
                    if not data:
                        raise RuntimeError("Kokoro HTTP returned empty audio.")
                    return data

        import asyncio

        return await asyncio.to_thread(self._synthesize_local_sync, text, voice, speed)

    def get_info(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "type": "http" if self.kokoro_url else "local",
            "kokoro_url": self.kokoro_url,
            "default_voice": self.default_voice,
        }


class ElevenLabsTTSProvider(BaseTTSProvider):
    """Streaming REST TTS provider for ElevenLabs."""

    name: str = "elevenlabs"

    def __init__(
        self,
        api_key: str = "",
        elevenlabs_voice_id: str = "",
        model_id: str = "eleven_multilingual_v2",
        timeout: float = 20.0,
        **kwargs: Any,
    ):
        self.api_key = str(api_key or os.getenv("ELEVENLABS_API_KEY", "")).strip()
        self.voice_id = str(
            elevenlabs_voice_id or kwargs.get("voice_id", "") or os.getenv("ELEVENLABS_VOICE_ID", "")
        ).strip()
        self.model_id = model_id
        self.timeout = float(timeout)

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: str,
        pitch: str,
        emotion: str = "neutral",
        **kwargs: Any,
    ) -> bytes:
        api_key = str(kwargs.get("api_key") or self.api_key or os.getenv("ELEVENLABS_API_KEY", "")).strip()
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not configured.")

        voice_id = str(kwargs.get("elevenlabs_voice_id") or self.voice_id or "").strip()
        if not voice_id and voice and not voice.endswith("Neural"):
            voice_id = voice.strip()
        if not voice_id:
            raise RuntimeError("elevenlabs_voice_id is not configured.")

        style = 0.35 if emotion in ("happy", "excited", "angry", "smug") else 0.15
        stability = 0.4 if emotion in ("excited", "angry") else 0.55

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        headers = {
            "xi-api-key": api_key,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": 0.75,
                "style": style,
                "use_speaker_boost": True,
            },
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    raise RuntimeError(f"ElevenLabs HTTP {resp.status}: {err_text[:200]}")
                chunks = []
                async for chunk in resp.content.iter_chunked(4096):
                    if chunk:
                        chunks.append(chunk)
                data = b"".join(chunks)
                if not data:
                    raise RuntimeError("ElevenLabs returned empty audio stream.")
                return data

    def get_info(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "type": "cloud",
            "voice_id": self.voice_id,
            "model_id": self.model_id,
            "api_key_configured": bool(self.api_key or os.getenv("ELEVENLABS_API_KEY", "")),
        }


class CustomNeuralTTSProvider(BaseTTSProvider):
    """Generic HTTP POST provider for GPT-SoVITS, Fish Speech, and custom neural TTS servers."""

    name: str = "custom"

    def __init__(
        self,
        custom_tts_url: str = "",
        backend: str = "gpt_sovits",
        timeout: float = 20.0,
        **kwargs: Any,
    ):
        self.custom_tts_url = str(custom_tts_url or "").strip()
        self.backend = str(backend or "gpt_sovits").strip().lower()
        self.name = self.backend if self.backend in ("gpt_sovits", "fish_speech") else "custom"
        self.timeout = float(timeout)

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: str,
        pitch: str,
        emotion: str = "neutral",
        **kwargs: Any,
    ) -> bytes:
        url = str(kwargs.get("custom_tts_url") or self.custom_tts_url).strip()
        if not url:
            raise RuntimeError(f"custom_tts_url is not configured for {self.backend}.")

        payload = {
            "text": text,
            "voice": voice,
            "rate": rate,
            "pitch": pitch,
            "emotion": emotion,
            "backend": self.backend,
            "speed": _rate_to_speed_multiplier(rate),
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    raise RuntimeError(f"Custom TTS ({self.backend}) HTTP {resp.status}: {err_text[:200]}")
                data = await resp.read()
                if not data:
                    raise RuntimeError(f"Custom TTS ({self.backend}) returned empty audio.")
                return data

    def get_info(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "backend": self.backend,
            "type": "http",
            "custom_tts_url": self.custom_tts_url,
        }


def create_tts_provider(provider_name: str = "edge-tts", **kwargs: Any) -> BaseTTSProvider:
    """Factory returning a configured BaseTTSProvider instance."""
    normalized = str(provider_name or "edge-tts").strip().lower()
    if normalized in ("", "edge", "edge-tts", "edge_tts"):
        return EdgeTTSProvider(**kwargs)
    if normalized in ("kokoro", "kokoro-tts", "kokoro_tts"):
        return KokoroTTSProvider(**kwargs)
    if normalized in ("elevenlabs", "eleven-labs", "eleven_labs"):
        return ElevenLabsTTSProvider(**kwargs)
    if normalized in ("gpt_sovits", "gpt-sovits", "fish_speech", "fish-speech", "custom", "custom_neural"):
        backend = normalized.replace("-", "_")
        return CustomNeuralTTSProvider(backend=backend, **kwargs)
    raise ValueError(f"Unsupported TTS provider: {provider_name}")


class RVCVoiceConverter:
    """
    Post-processing Retrieval-based Voice Conversion (RVC) client.
    Posts synthesized audio bytes to an RVC inference endpoint and falls back
    cleanly to the original audio bytes when disabled, unconfigured, or offline.
    """

    def __init__(
        self,
        enabled: bool = False,
        rvc_url: str = "",
        pitch_shift: int = 0,
        timeout: float = 20.0,
    ):
        self.enabled = bool(enabled)
        self.rvc_url = str(rvc_url or "").strip()
        self.pitch_shift = int(pitch_shift)
        self.timeout = float(timeout)
        self.last_error: Optional[str] = None

    def update_config(
        self,
        enabled: Optional[bool] = None,
        rvc_url: Optional[str] = None,
        pitch_shift: Optional[int] = None,
    ) -> None:
        if enabled is not None:
            self.enabled = bool(enabled)
        if rvc_url is not None:
            self.rvc_url = str(rvc_url).strip()
        if pitch_shift is not None:
            self.pitch_shift = int(pitch_shift)

    async def convert(self, audio_bytes: bytes, pitch_shift: Optional[int] = None) -> bytes:
        if not self.enabled or not self.rvc_url or not audio_bytes:
            return audio_bytes

        shift = self.pitch_shift if pitch_shift is None else int(pitch_shift)
        form = aiohttp.FormData()
        form.add_field("audio", audio_bytes, filename="input.mp3", content_type="audio/mpeg")
        form.add_field("pitch_shift", str(shift))

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.rvc_url, data=form) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        self.last_error = f"RVC HTTP {resp.status}: {err_text[:200]}"
                        print(f"[RVC Warning] {self.last_error}. Using original audio.")
                        return audio_bytes
                    converted = await resp.read()
                    if not converted:
                        self.last_error = "RVC returned empty audio."
                        print(f"[RVC Warning] {self.last_error}. Using original audio.")
                        return audio_bytes
                    self.last_error = None
                    return converted
        except Exception as exc:
            self.last_error = str(exc)
            print(f"[RVC Warning] RVC conversion failed ({exc}). Using original audio.")
            return audio_bytes

    def get_info(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "rvc_url": self.rvc_url,
            "pitch_shift": self.pitch_shift,
            "last_error": self.last_error,
        }
