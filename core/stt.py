import asyncio
import collections
import io
import os
import tempfile
import wave
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Union

import numpy as np


@dataclass
class VADResult:
    """Result from a single EnergyVAD frame evaluation."""

    is_speech: bool
    speech_started: bool
    speech_ended: bool
    rms: float


class EnergyVAD:
    """
    Lightweight pure-Python + NumPy energy-based Voice Activity Detector (VAD)
    with onset hysteresis and hangover smoothing.
    """

    def __init__(
        self,
        energy_threshold: float = 0.02,
        sample_rate: int = 16000,
        min_speech_frames: int = 2,
        hangover_frames: int = 8,
    ):
        self.energy_threshold = max(0.0, float(energy_threshold))
        self.sample_rate = max(1, int(sample_rate))
        self.min_speech_frames = max(1, int(min_speech_frames))
        self.hangover_frames = max(0, int(hangover_frames))

        self._in_speech: bool = False
        self._consecutive_speech: int = 0
        self._silence_frames: int = 0

    def reset(self) -> None:
        """Resets internal VAD state."""
        self._in_speech = False
        self._consecutive_speech = 0
        self._silence_frames = 0

    @staticmethod
    def compute_rms(frame: Union[bytes, bytearray, memoryview, np.ndarray, List[float]]) -> float:
        """Computes normalized [0.0, 1.0+] RMS energy from PCM16 bytes or float/int array."""
        if frame is None:
            return 0.0

        if isinstance(frame, (bytes, bytearray, memoryview)):
            raw = bytes(frame)
            usable = len(raw) - (len(raw) % 2)
            if usable <= 0:
                return 0.0
            samples = np.frombuffer(raw[:usable], dtype=np.int16).astype(np.float32) / 32768.0
        else:
            arr = np.asarray(frame)
            if arr.size == 0:
                return 0.0
            if np.issubdtype(arr.dtype, np.integer):
                info = np.iinfo(arr.dtype)
                scale = float(max(abs(info.min), info.max)) or 32768.0
                samples = arr.astype(np.float32) / scale
            else:
                samples = arr.astype(np.float32)

        if samples.size == 0:
            return 0.0
        rms_val = float(np.sqrt(np.mean(np.square(samples))))
        if not np.isfinite(rms_val):
            return 0.0
        return rms_val

    def process(self, frame: Union[bytes, bytearray, memoryview, np.ndarray, List[float]]) -> VADResult:
        """Evaluates one audio frame and returns VAD state transitions."""
        rms = self.compute_rms(frame)
        above = rms >= self.energy_threshold

        speech_started = False
        speech_ended = False

        if not self._in_speech:
            if above:
                self._consecutive_speech += 1
                if self._consecutive_speech >= self.min_speech_frames:
                    self._in_speech = True
                    self._silence_frames = 0
                    speech_started = True
            else:
                self._consecutive_speech = 0
        else:
            if above:
                self._silence_frames = 0
            else:
                self._silence_frames += 1
                if self._silence_frames >= self.hangover_frames:
                    self._in_speech = False
                    self._consecutive_speech = 0
                    self._silence_frames = 0
                    speech_ended = True

        return VADResult(
            is_speech=self._in_speech,
            speech_started=speech_started,
            speech_ended=speech_ended,
            rms=rms,
        )

    def process_frame(self, frame: Union[bytes, bytearray, memoryview, np.ndarray, List[float]]) -> VADResult:
        """Alias for process()."""
        return self.process(frame)


class STTEngine:
    """
    Speech-to-Text engine for voice recognition (creator mic or collab).
    Supports faster-whisper, openai-whisper, OpenAI Whisper REST API,
    and deterministic offline mock fallback.
    """

    def __init__(
        self,
        model_name: str = "base",
        device: str = "cpu",
        enabled: bool = True,
        vad_enabled: bool = True,
        vad_energy_threshold: float = 0.02,
        barge_in_enabled: bool = True,
        api_key: Optional[str] = None,
    ):
        self.model_name = model_name
        self.device = device
        self.enabled = bool(enabled)
        self.vad_enabled = bool(vad_enabled)
        self.vad_energy_threshold = float(vad_energy_threshold)
        self.barge_in_enabled = bool(barge_in_enabled)
        self.api_key = api_key
        self.is_listening = False
        self.last_error: Optional[str] = None
        self._whisper_model = None
        self._faster_whisper_model = None
        self._last_backend: str = "mock"
        self._session: Any = None

    def _get_session(self) -> Any:
        import aiohttp

        if self._session is None or getattr(self._session, "closed", True) is not False:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self._session

    async def close(self) -> None:
        """Closes persistent HTTP session if open."""
        if self._session is not None:
            if getattr(self._session, "closed", True) is False and hasattr(self._session, "close"):
                await self._session.close()
            self._session = None

    def update_config(
        self,
        enabled: Optional[bool] = None,
        model: Optional[str] = None,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        vad_enabled: Optional[bool] = None,
        vad_energy_threshold: Optional[float] = None,
        barge_in_enabled: Optional[bool] = None,
    ) -> None:
        if enabled is not None:
            self.enabled = bool(enabled)
        chosen_model = model if model is not None else model_name
        if chosen_model:
            cleaned = str(chosen_model).strip()
            if cleaned and cleaned != self.model_name:
                self.model_name = cleaned
                self._whisper_model = None
                self._faster_whisper_model = None
        if device:
            cleaned_dev = str(device).strip()
            if cleaned_dev and cleaned_dev != self.device:
                self.device = cleaned_dev
                self._whisper_model = None
                self._faster_whisper_model = None
        if vad_enabled is not None:
            self.vad_enabled = bool(vad_enabled)
        if vad_energy_threshold is not None:
            self.vad_energy_threshold = max(0.0, float(vad_energy_threshold))
        if barge_in_enabled is not None:
            self.barge_in_enabled = bool(barge_in_enabled)

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "model": self.model_name,
            "model_name": self.model_name,
            "device": self.device,
            "vad_enabled": self.vad_enabled,
            "vad_energy_threshold": self.vad_energy_threshold,
            "barge_in_enabled": self.barge_in_enabled,
            "is_listening": self.is_listening,
            "backend": self._last_backend,
            "last_error": self.last_error,
        }

    @staticmethod
    def _is_mock_mode() -> bool:
        return os.getenv("MAYBEAI_LLM_PROVIDER", "").strip().lower() == "mock"

    def _transcribe_with_faster_whisper_sync(self, file_path: str, language: Optional[str] = None) -> str:
        from faster_whisper import WhisperModel

        if self._faster_whisper_model is None:
            compute_type = "float16" if self.device == "cuda" else "int8"
            self._faster_whisper_model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=compute_type,
            )
        kwargs: Dict[str, Any] = {}
        if language:
            kwargs["language"] = language.split("-")[0]
        segments, _ = self._faster_whisper_model.transcribe(file_path, **kwargs)
        text = " ".join(seg.text.strip() for seg in segments if getattr(seg, "text", "").strip())
        self._last_backend = "faster-whisper"
        self.last_error = None
        return text.strip()

    def _transcribe_with_openai_whisper_sync(self, file_path: str, language: Optional[str] = None) -> str:
        import whisper

        if self._whisper_model is None:
            self._whisper_model = whisper.load_model(self.model_name, device=self.device)
        kwargs: Dict[str, Any] = {}
        if language:
            kwargs["language"] = language.split("-")[0]
        result = self._whisper_model.transcribe(file_path, **kwargs)
        self._last_backend = "openai-whisper"
        self.last_error = None
        return str(result.get("text", "")).strip()

    async def _transcribe_with_openai_api(self, wav_bytes: bytes, language: Optional[str] = None) -> Optional[str]:
        api_key = (self.api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        if not api_key or self._is_mock_mode():
            return None

        import aiohttp

        form = aiohttp.FormData()
        form.add_field("file", wav_bytes, filename="speech.wav", content_type="audio/wav")
        form.add_field("model", "whisper-1")
        if language:
            form.add_field("language", language.split("-")[0])

        headers = {"Authorization": f"Bearer {api_key}"}
        session = self._get_session()
        async with session.post(
            "https://api.openai.com/v1/audio/transcriptions",
            data=form,
            headers=headers,
        ) as resp:
            if resp.status != 200:
                err_body = await resp.text()
                raise RuntimeError(f"OpenAI Whisper API error ({resp.status}): {err_body[:200]}")
            payload = await resp.json()
            self._last_backend = "openai-api"
            self.last_error = None
            return str(payload.get("text", "")).strip()

    async def transcribe_audio_file(self, file_path: str, language: Optional[str] = None) -> str:
        """
        Transcribe an audio file. Supports faster-whisper, openai-whisper,
        OpenAI Whisper API (when configured and not in mock mode), and clean offline mock fallback.
        """
        if not file_path or not os.path.exists(file_path):
            return ""

        # 1. Try faster-whisper if installed (unless explicitly mocked without local package)
        try:
            return await asyncio.to_thread(self._transcribe_with_faster_whisper_sync, file_path, language)
        except ImportError:
            pass
        except Exception as e:
            self.last_error = str(e)
            return f"[STT Error] {e}"

        # 2. Try openai-whisper if installed
        try:
            return await asyncio.to_thread(self._transcribe_with_openai_whisper_sync, file_path, language)
        except ImportError:
            pass
        except Exception as e:
            self.last_error = str(e)
            return f"[STT Error] {e}"

        # 3. Try OpenAI Whisper API when configured and not in mock mode
        try:
            def _read_file_bytes(path: str) -> bytes:
                with open(path, "rb") as f:
                    return f.read()

            data = await asyncio.to_thread(_read_file_bytes, file_path)
            api_text = await self._transcribe_with_openai_api(data, language=language)
            if api_text is not None:
                return api_text
        except Exception as e:
            self.last_error = str(e)
            return f"[STT Error] {e}"

        self._last_backend = "mock"
        return "[STT Mock] Whisper not installed. Install with: pip install openai-whisper"

    async def transcribe_wav_bytes(self, wav_bytes: bytes, language: Optional[str] = None) -> str:
        """
        Transcribe in-memory WAV bytes cleanly without leaking temp files.
        Never makes network calls when MAYBEAI_LLM_PROVIDER == "mock".
        """
        if not wav_bytes:
            return ""

        if self._is_mock_mode():
            # Allow mocked local whisper if injected in tests, otherwise fast offline mock
            try:
                import faster_whisper  # noqa: F401
                has_fw = True
            except ImportError:
                has_fw = False
            try:
                import whisper  # noqa: F401
                has_w = True
            except ImportError:
                has_w = False

            if not has_fw and not has_w:
                self._last_backend = "mock"
                self.last_error = None
                return f"[STT Mock] Captured offline voice segment ({len(wav_bytes)} bytes)"

        tmp_path: Optional[str] = None
        try:
            def _write_temp_wav(data: bytes) -> str:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp.write(data)
                    return tmp.name

            tmp_path = await asyncio.to_thread(_write_temp_wav, wav_bytes)

            # Try local backends first
            try:
                return await asyncio.to_thread(self._transcribe_with_faster_whisper_sync, tmp_path, language)
            except ImportError:
                pass
            except Exception as e:
                self.last_error = str(e)
                return f"[STT Error] {e}"

            try:
                return await asyncio.to_thread(self._transcribe_with_openai_whisper_sync, tmp_path, language)
            except ImportError:
                pass
            except Exception as e:
                self.last_error = str(e)
                return f"[STT Error] {e}"

            # Cloud OpenAI Whisper API fallback (skipped in mock mode)
            api_text = await self._transcribe_with_openai_api(wav_bytes, language=language)
            if api_text is not None:
                return api_text

            self._last_backend = "mock"
            return f"[STT Mock] Captured offline voice segment ({len(wav_bytes)} bytes)"
        except Exception as e:
            self.last_error = str(e)
            return f"[STT Error] {e}"
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass


class StreamingSTTSession:
    """
    Full-duplex streaming STT session:
    - Evaluates incoming PCM16 audio chunks via EnergyVAD
    - Signals `speech_started` immediately on voice onset (for instant barge-in)
    - Buffers active speech frames (+ short pre-roll) into in-memory WAV bytes
    - Transcribes on `speech_ended` or `flush()` via STTEngine
    """

    def __init__(
        self,
        stt_engine: Optional[STTEngine] = None,
        vad: Optional[EnergyVAD] = None,
        sample_rate: int = 16000,
        pre_roll_frames: int = 2,
        max_buffer_seconds: float = 30.0,
    ):
        self.stt = stt_engine or STTEngine()
        self.sample_rate = max(1, int(sample_rate))
        self.vad = vad or EnergyVAD(
            energy_threshold=self.stt.vad_energy_threshold,
            sample_rate=self.sample_rate,
        )
        self._pre_roll: Deque[bytes] = collections.deque(maxlen=max(0, int(pre_roll_frames)))
        self._speech_frames: List[bytes] = []
        self._in_utterance: bool = False
        self._max_buffer_bytes = int(max(1.0, float(max_buffer_seconds)) * self.sample_rate * 2)
        self._buffered_bytes: int = 0

        self.total_chunks: int = 0
        self.utterances_transcribed: int = 0

    def reset(self) -> None:
        """Clears buffered frames and resets VAD state."""
        self._pre_roll.clear()
        self._speech_frames.clear()
        self._in_utterance = False
        self._buffered_bytes = 0
        self.vad.reset()

    def _pcm_to_wav_bytes(self, pcm_chunks: List[bytes]) -> bytes:
        pcm_data = b"".join(pcm_chunks)
        usable = len(pcm_data) - (len(pcm_data) % 2)
        if usable <= 0:
            return b""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_data[:usable])
        return buf.getvalue()

    async def feed_pcm_chunk(self, pcm_bytes: bytes, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Feeds a raw PCM16 mono chunk, runs VAD, buffers speech, and transcribes
        when the utterance ends (or hits max_buffer_seconds).
        """
        self.total_chunks += 1
        chunk = bytes(pcm_bytes or b"")

        if not self._in_utterance and chunk:
            self._pre_roll.append(chunk)

        vad_res = self.vad.process(chunk)
        transcript: Optional[str] = None
        wav_len = 0

        if vad_res.speech_started:
            self._in_utterance = True
            self._speech_frames = list(self._pre_roll)
            self._pre_roll.clear()
            if not self._speech_frames and chunk:
                self._speech_frames.append(chunk)
            self._buffered_bytes = sum(len(c) for c in self._speech_frames)
        elif self._in_utterance and vad_res.is_speech and chunk:
            self._speech_frames.append(chunk)
            self._buffered_bytes += len(chunk)

        hit_max = self._in_utterance and self._buffered_bytes >= self._max_buffer_bytes
        if (vad_res.speech_ended or hit_max) and self._speech_frames:
            frames_to_decode = self._speech_frames
            self._speech_frames = []
            self._buffered_bytes = 0
            self._in_utterance = False
            if hit_max:
                self.vad.reset()

            wav_bytes = self._pcm_to_wav_bytes(frames_to_decode)
            wav_len = len(wav_bytes)
            if wav_bytes:
                transcript = await self.stt.transcribe_wav_bytes(wav_bytes, language=language)
                self.utterances_transcribed += 1

        return {
            "is_speech": vad_res.is_speech,
            "speech_started": vad_res.speech_started,
            "speech_ended": vad_res.speech_ended or hit_max,
            "rms": vad_res.rms,
            "transcript": transcript,
            "wav_bytes_len": wav_len,
        }

    async def flush(self, language: Optional[str] = None) -> Optional[str]:
        """Forces transcription of any buffered speech frames and resets session state."""
        frames = self._speech_frames
        self._speech_frames = []
        self._buffered_bytes = 0
        self._in_utterance = False
        self._pre_roll.clear()
        self.vad.reset()

        if not frames:
            return None
        wav_bytes = self._pcm_to_wav_bytes(frames)
        if not wav_bytes:
            return None
        transcript = await self.stt.transcribe_wav_bytes(wav_bytes, language=language)
        self.utterances_transcribed += 1
        return transcript

    def get_status(self) -> Dict[str, Any]:
        return {
            "in_speech": self._in_utterance,
            "buffered_bytes": self._buffered_bytes,
            "total_chunks": self.total_chunks,
            "utterances_transcribed": self.utterances_transcribed,
            "sample_rate": self.sample_rate,
            "energy_threshold": self.vad.energy_threshold,
            "min_speech_frames": self.vad.min_speech_frames,
            "hangover_frames": self.vad.hangover_frames,
        }
