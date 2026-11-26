import os
import re
import uuid
import inspect
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, Callable, AsyncIterator, List, Tuple, Any, Set
import edge_tts

from core.actions import ActionParser
from core.tts_providers import (
    BaseTTSProvider,
    EdgeTTSProvider,
    RVCVoiceConverter,
    create_tts_provider,
    detect_audio_format,
    extract_rms_envelope_from_sound,
    extract_rms_envelope_from_wav,
    is_edge_tts_voice,
)


class SentenceChunker:
    """
    Buffers streaming LLM text chunks and flushes complete sentences/clauses
    on '.', '!', '?', '\\n', '~' while avoiding mid-tag splits (e.g. '[emotion: happy]'),
    common abbreviations, and decimal numbers.
    """

    DELIMITERS = {".", "!", "?", "\n", "~"}
    ABBREVIATIONS = {
        "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs",
        "etc", "no", "rp", "e.g", "i.e", "a.m", "p.m",
    }
    _TAG_STRIP_RE = re.compile(r"\[(?:emotion|action):\s*[a-zA-Z0-9_\-]+\]", re.IGNORECASE)

    def __init__(self, min_chars: int = 8, max_chars: int = 240):
        self.min_chars = max(1, int(min_chars))
        self.max_chars = max(self.min_chars, int(max_chars))
        self._buffer: str = ""

    @classmethod
    def _visible_length(cls, text: str) -> int:
        stripped = cls._TAG_STRIP_RE.sub("", text)
        return len(" ".join(stripped.split()))

    def _is_abbreviation(self, text: str, dot_idx: int) -> bool:
        prefix = text[:dot_idx].rstrip()
        if not prefix:
            return False
        token = re.split(r"[\s(\[\"'“‘]+", prefix)[-1].lower()
        return token in self.ABBREVIATIONS

    def _find_split_index(self) -> Optional[int]:
        buf = self._buffer
        n = len(buf)
        bracket_depth = 0
        i = 0

        while i < n:
            ch = buf[i]
            if ch == "[":
                bracket_depth += 1
                i += 1
                continue
            if ch == "]":
                if bracket_depth > 0:
                    bracket_depth -= 1
                i += 1
                continue

            if bracket_depth == 0 and ch in self.DELIMITERS:
                if ch == ".":
                    # Avoid splitting decimal numbers or hostnames/domains (e.g. 3.14, 127.0.0.1, example.com)
                    if i + 1 < n and buf[i + 1].isalnum():
                        i += 1
                        continue
                    if self._is_abbreviation(buf, i):
                        i += 1
                        continue

                # Consume consecutive sentence punctuation (e.g. '...', '!!', '?!')
                end = i + 1
                while end < n and buf[end] in {".", "!", "?", "~"}:
                    end += 1

                # Include immediately trailing closing quotes/parentheses
                while end < n and buf[end] in {'"', "'", ")", "”", "’"}:
                    end += 1

                candidate = buf[:end]
                if self._visible_length(candidate) >= self.min_chars:
                    return end
                i = end
                continue

            i += 1

        # Safety valve: force-split overly long buffers at a clean whitespace boundary outside tags
        if n >= self.max_chars:
            bracket_depth = 0
            last_space = -1
            for idx, ch in enumerate(buf):
                if ch == "[":
                    bracket_depth += 1
                elif ch == "]" and bracket_depth > 0:
                    bracket_depth -= 1
                elif bracket_depth == 0 and ch.isspace():
                    if self._visible_length(buf[:idx]) >= self.min_chars:
                        last_space = idx + 1
            if last_space > 0:
                return last_space

        return None

    def feed(self, chunk: str) -> List[str]:
        """Feeds an incoming text chunk and returns any complete sentences ready to flush."""
        if not chunk:
            return []
        self._buffer += chunk
        emitted: List[str] = []

        while True:
            split_idx = self._find_split_index()
            if split_idx is None:
                break
            sentence = self._buffer[:split_idx].strip()
            self._buffer = self._buffer[split_idx:].lstrip()
            if sentence:
                emitted.append(sentence)

        return emitted

    def flush(self) -> Optional[str]:
        """Flushes any remaining buffered text at end of stream."""
        rem = self._buffer.strip()
        self._buffer = ""
        return rem if rem else None


class TTSEngine:
    """
    Handles speech synthesis and audio playback.
    Default provider: edge-tts (High quality, free, realistic voices).
    Supports both single-shot speak() and pipelined streaming speak_stream().
    """

    _VALID_OUTPUT_MODES = ("server", "browser", "both")

    def __init__(
        self,
        voice: str = "en-US-AnaNeural",
        rate: str = "+5%",
        pitch: str = "+10Hz",
        enabled: bool = True,
        interruptible: bool = True,
        output_mode: str = "both",
        on_audio_ready: Optional[Callable[[bytes, str, str], Any]] = None,
        provider: str = "edge-tts",
        emotion: str = "neutral",
        rvc_enabled: bool = False,
        rvc_url: str = "",
        rvc_pitch_shift: int = 0,
        elevenlabs_voice_id: str = "",
        kokoro_url: str = "",
        custom_tts_url: str = "",
        fallback_voice: str = "en-US-AriaNeural",
    ):
        self.voice = voice
        self.fallback_voice = str(fallback_voice or "en-US-AriaNeural").strip() or "en-US-AriaNeural"
        self.rate = rate
        self.pitch = pitch
        self.enabled = enabled
        self.interruptible = interruptible
        mode = str(output_mode or "both").strip().lower()
        self.output_mode = mode if mode in self._VALID_OUTPUT_MODES else "both"
        self.on_audio_ready = on_audio_ready
        self.provider = str(provider or "edge-tts").strip().lower()
        self.emotion = str(emotion or "neutral").strip().lower()
        self.rvc_enabled = bool(rvc_enabled)
        self.rvc_url = str(rvc_url or "").strip()
        self.rvc_pitch_shift = int(rvc_pitch_shift)
        self.elevenlabs_voice_id = str(elevenlabs_voice_id or "").strip()
        self.kokoro_url = str(kokoro_url or "").strip()
        self.custom_tts_url = str(custom_tts_url or "").strip()
        self.last_error: Optional[str] = None
        self._fallback_provider: EdgeTTSProvider = EdgeTTSProvider()
        self._provider: BaseTTSProvider = self._build_provider()
        self._rvc: RVCVoiceConverter = RVCVoiceConverter(
            enabled=self.rvc_enabled,
            rvc_url=self.rvc_url,
            pitch_shift=self.rvc_pitch_shift,
        )
        self._mixer_initialized: bool = False
        self._tts_channel: Any = None
        self._tts_sound: Any = None
        self._is_speaking: bool = False
        self._was_interrupted: bool = False
        self._stop_requested: bool = False
        self._stop_reason: Optional[str] = None
        self._active_speak_task: Optional[asyncio.Task] = None
        self._active_stream_tasks: List[asyncio.Task] = []
        self._active_stream_interruptible: bool = True
        self._active_temp_files: Set[str] = set()
        self._active_mouth_callback: Optional[Callable[[float], Any]] = None
        self.temp_dir = Path(tempfile.gettempdir()) / "maybeai_audio"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    @property
    def was_interrupted(self) -> bool:
        return self._was_interrupted

    def _build_provider(self) -> BaseTTSProvider:
        try:
            return create_tts_provider(
                self.provider,
                kokoro_url=self.kokoro_url,
                elevenlabs_voice_id=self.elevenlabs_voice_id,
                custom_tts_url=self.custom_tts_url,
            )
        except ValueError as exc:
            self.last_error = str(exc)
            print(f"[TTS Warning] {exc}. Falling back to edge-tts.")
            self.provider = "edge-tts"
            return EdgeTTSProvider()

    def update_config(
        self,
        enabled: Optional[bool] = None,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
        interruptible: Optional[bool] = None,
        output_mode: Optional[str] = None,
        provider: Optional[str] = None,
        emotion: Optional[str] = None,
        rvc_enabled: Optional[bool] = None,
        rvc_url: Optional[str] = None,
        rvc_pitch_shift: Optional[int] = None,
        elevenlabs_voice_id: Optional[str] = None,
        kokoro_url: Optional[str] = None,
        custom_tts_url: Optional[str] = None,
        fallback_voice: Optional[str] = None,
    ):
        if enabled is not None:
            self.enabled = bool(enabled)
        if voice:
            self.voice = voice.strip()
        if fallback_voice:
            self.fallback_voice = str(fallback_voice).strip()
        if rate:
            self.rate = rate.strip()
        if pitch:
            self.pitch = pitch.strip()
        if interruptible is not None:
            self.interruptible = bool(interruptible)
        if output_mode is not None:
            mode = str(output_mode).strip().lower()
            if mode in self._VALID_OUTPUT_MODES:
                self.output_mode = mode

        rebuild_provider = False
        if provider is not None:
            self.provider = str(provider or "edge-tts").strip().lower()
            rebuild_provider = True
        if emotion is not None:
            self.emotion = str(emotion or "neutral").strip().lower()
        if elevenlabs_voice_id is not None:
            self.elevenlabs_voice_id = str(elevenlabs_voice_id).strip()
            rebuild_provider = True
        if kokoro_url is not None:
            self.kokoro_url = str(kokoro_url).strip()
            rebuild_provider = True
        if custom_tts_url is not None:
            self.custom_tts_url = str(custom_tts_url).strip()
            rebuild_provider = True
        if rebuild_provider:
            self._provider = self._build_provider()

        if rvc_enabled is not None:
            self.rvc_enabled = bool(rvc_enabled)
        if rvc_url is not None:
            self.rvc_url = str(rvc_url).strip()
        if rvc_pitch_shift is not None:
            self.rvc_pitch_shift = int(rvc_pitch_shift)
        self._rvc.update_config(
            enabled=self.rvc_enabled,
            rvc_url=self.rvc_url,
            pitch_shift=self.rvc_pitch_shift,
        )

    def get_status(self) -> dict:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "voice": self.voice,
            "rate": self.rate,
            "pitch": self.pitch,
            "emotion": self.emotion,
            "interruptible": self.interruptible,
            "output_mode": self.output_mode,
            "rvc_enabled": self.rvc_enabled,
            "rvc_url": self.rvc_url,
            "rvc_pitch_shift": self.rvc_pitch_shift,
            "elevenlabs_voice_id": self.elevenlabs_voice_id,
            "kokoro_url": self.kokoro_url,
            "custom_tts_url": self.custom_tts_url,
            "is_speaking": self._is_speaking,
            "was_interrupted": self._was_interrupted,
            "last_error": self.last_error,
        }

    async def close(self) -> None:
        """Closes persistent HTTP sessions held by providers and RVC converter."""
        for component in (self._provider, self._fallback_provider, self._rvc):
            if component is not None and hasattr(component, "close"):
                try:
                    await component.close()
                except Exception:
                    pass

    async def _synthesize_audio(self, text: str, emotion: Optional[str] = None) -> bytes:
        active_emotion = str(emotion or self.emotion or "neutral").strip().lower()
        try:
            audio_bytes = await self._provider.synthesize(
                text=text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch,
                emotion=active_emotion,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not isinstance(self._provider, EdgeTTSProvider):
                fb_voice = self.voice if is_edge_tts_voice(self.voice) else self.fallback_voice
                print(
                    f"[TTS Provider Warning] {self.provider} failed ({exc}); "
                    f"falling back to edge-tts ({fb_voice})."
                )
                audio_bytes = await self._fallback_provider.synthesize(
                    text=text,
                    voice=fb_voice,
                    rate=self.rate,
                    pitch=self.pitch,
                    emotion=active_emotion,
                )
            else:
                raise

        if self._rvc.enabled:
            audio_bytes = await self._rvc.convert(audio_bytes)
        return audio_bytes

    def _make_temp_audio_path(self, ext: str = ".mp3") -> str:
        ts_ms = int(asyncio.get_running_loop().time() * 1000)
        suffix = ext if ext.startswith(".") else f".{ext}"
        return str(self.temp_dir / f"speech_{ts_ms}_{uuid.uuid4().hex[:6]}{suffix}")

    @staticmethod
    async def _invoke_callback(cb: Optional[Callable], *args):
        if cb is None:
            return
        result = cb(*args)
        if inspect.isawaitable(result):
            await result

    def stop(self, reason: str = "barge_in") -> bool:
        """
        Interrupts active single-shot or streaming TTS playback if interruptible is enabled.
        Returns True if an active speech task or audio stream was signalled to stop.
        """
        if self._active_stream_tasks and not self._active_stream_interruptible:
            return False
        if not self.interruptible:
            return False

        self._stop_requested = True
        self._was_interrupted = True
        self._stop_reason = reason
        stopped = False

        if self._active_speak_task is not None and not self._active_speak_task.done():
            self._active_speak_task.cancel()
            stopped = True

        for task in list(self._active_stream_tasks):
            if not task.done():
                task.cancel()
                stopped = True

        try:
            if self._tts_channel is not None:
                if self._tts_channel.get_busy():
                    stopped = True
                self._tts_channel.stop()
                self._tts_channel = None
            self._tts_sound = None
        except Exception:
            pass

        for temp_path in list(self._active_temp_files):
            self._cleanup_audio_file(temp_path)
            self._active_temp_files.discard(temp_path)

        return stopped

    async def speak(self, text: str, on_mouth_update: Optional[Callable[[float], Any]] = None) -> Optional[str]:
        """
        Synthesizes text to speech, plays audio, and fires lip-sync mouth updates.
        Returns path to generated audio file (or None if disabled, failed, or interrupted via stop()).
        """
        if not text.strip():
            return None

        self._is_speaking = True
        self._was_interrupted = False
        self._stop_requested = False
        self._stop_reason = None
        self._active_mouth_callback = on_mouth_update
        output_file: Optional[str] = None

        async def _run_speak() -> Optional[str]:
            nonlocal output_file
            audio_bytes = await self._synthesize_audio(text, emotion=self.emotion)
            if self.on_audio_ready is not None and self.output_mode in ("browser", "both") and audio_bytes:
                await self._invoke_callback(self.on_audio_ready, audio_bytes, text, self.voice)

            if self.output_mode == "browser":
                if self.on_audio_ready is None:
                    await self._simulate_mouth_flap(text, on_mouth_update)
                self.last_error = None
                return None

            _, ext = detect_audio_format(audio_bytes)
            out_path = self._make_temp_audio_path(ext=ext)
            output_file = out_path
            self._active_temp_files.add(out_path)
            await asyncio.to_thread(Path(out_path).write_bytes, audio_bytes)
            await self._play_and_lipsync(out_path, text, on_mouth_update)
            self.last_error = None
            return out_path

        try:
            if not self.enabled:
                task = asyncio.create_task(self._simulate_mouth_flap(text, on_mouth_update))
                self._active_speak_task = task
                await task
                return None

            task = asyncio.create_task(_run_speak())
            self._active_speak_task = task
            return await task
        except asyncio.CancelledError:
            if self._active_speak_task is not None and not self._active_speak_task.done():
                self._active_speak_task.cancel()
                await asyncio.gather(self._active_speak_task, return_exceptions=True)
            if on_mouth_update:
                try:
                    await self._invoke_callback(on_mouth_update, 0.0)
                except Exception:
                    pass
            if self._stop_requested:
                return None
            raise
        except Exception as e:
            self.last_error = str(e)
            print(f"[TTS Error] {e}")
            return None
        finally:
            self._is_speaking = False
            self._active_speak_task = None
            self._active_mouth_callback = None
            if output_file:
                self._cleanup_audio_file(output_file)
                self._active_temp_files.discard(output_file)

    async def speak_stream(
        self,
        text_chunks: AsyncIterator[str],
        on_mouth_update: Optional[Callable[[float], Any]] = None,
        on_sentence_start: Optional[Callable[[str], Any]] = None,
        on_tag: Optional[Callable[[List[str], List[str]], Any]] = None,
        interruptible: Optional[bool] = None,
    ) -> str:
        """
        Pipelined streaming TTS: buffers incoming text chunks into sentences via
        SentenceChunker, synthesizes sentence N+1 via Edge-TTS concurrently while
        sentence N is playing, strips [emotion:...]/[action:...] tags before synthesis
        (invoking on_tag), and cleans up every temporary speech_*.mp3 file in finally.
        Returns the full accumulated raw text from the stream.
        """
        is_interruptible = self.interruptible if interruptible is None else bool(interruptible)
        self._active_stream_interruptible = is_interruptible
        self._is_speaking = True
        self._was_interrupted = False
        self._stop_requested = False
        self._stop_reason = None
        self._active_mouth_callback = on_mouth_update

        chunker = SentenceChunker()
        audio_queue: asyncio.Queue[Optional[Tuple[Optional[str], Optional[bytes], str, List[str], List[str]]]] = (
            asyncio.Queue(maxsize=4)
        )
        pending_files: Set[str] = set()
        raw_parts: List[str] = []

        async def _enqueue_sentence(sentence: str):
            clean_text, emotions, actions = ActionParser.parse(sentence)
            if not clean_text and not emotions and not actions:
                return

            if not clean_text:
                await audio_queue.put((None, None, "", emotions, actions))
                return

            if not self.enabled:
                await audio_queue.put((None, None, clean_text, emotions, actions))
                return

            out_file: Optional[str] = None
            audio_bytes: Optional[bytes] = None
            sentence_emotion = emotions[-1] if emotions else self.emotion
            try:
                audio_bytes = await self._synthesize_audio(clean_text, emotion=sentence_emotion)
                if self.output_mode in ("server", "both") and audio_bytes:
                    _, ext = detect_audio_format(audio_bytes)
                    out_file = self._make_temp_audio_path(ext=ext)
                    pending_files.add(out_file)
                    self._active_temp_files.add(out_file)
                    await asyncio.to_thread(Path(out_file).write_bytes, audio_bytes)
                self.last_error = None
            except asyncio.CancelledError:
                if out_file:
                    self._cleanup_audio_file(out_file)
                    pending_files.discard(out_file)
                    self._active_temp_files.discard(out_file)
                raise
            except Exception as e:
                self.last_error = str(e)
                print(f"[TTS Stream Error] {e}")
                if out_file:
                    self._cleanup_audio_file(out_file)
                    pending_files.discard(out_file)
                    self._active_temp_files.discard(out_file)
                out_file = None
                audio_bytes = None

            await audio_queue.put((out_file, audio_bytes, clean_text, emotions, actions))

        async def _producer():
            try:
                async for chunk in text_chunks:
                    if not chunk:
                        continue
                    raw_parts.append(chunk)
                    for sentence in chunker.feed(chunk):
                        await _enqueue_sentence(sentence)

                rem = chunker.flush()
                if rem:
                    await _enqueue_sentence(rem)
            finally:
                try:
                    await audio_queue.put(None)
                except asyncio.CancelledError:
                    pass

        async def _consumer():
            while True:
                item = await audio_queue.get()
                if item is None:
                    audio_queue.task_done()
                    break

                file_path, audio_bytes, clean_text, emotions, actions = item
                try:
                    if emotions or actions:
                        await self._invoke_callback(on_tag, emotions, actions)

                    if clean_text:
                        await self._invoke_callback(on_sentence_start, clean_text)
                        if audio_bytes and self.on_audio_ready is not None and self.output_mode in ("browser", "both"):
                            try:
                                await self._invoke_callback(
                                    self.on_audio_ready, audio_bytes, clean_text, self.voice
                                )
                            except Exception:
                                pass
                        if self.output_mode in ("server", "both") and file_path:
                            await self._play_and_lipsync(file_path, clean_text, on_mouth_update)
                        elif self.output_mode == "browser" and audio_bytes and self.on_audio_ready is not None:
                            pass
                        else:
                            await self._simulate_mouth_flap(clean_text, on_mouth_update)
                finally:
                    if file_path:
                        self._cleanup_audio_file(file_path)
                        pending_files.discard(file_path)
                        self._active_temp_files.discard(file_path)
                    audio_queue.task_done()

        producer_task = asyncio.create_task(_producer())
        consumer_task = asyncio.create_task(_consumer())
        self._active_stream_tasks = [producer_task, consumer_task]

        try:
            await asyncio.gather(producer_task, consumer_task)
            return "".join(raw_parts).strip()
        except asyncio.CancelledError:
            for t in (producer_task, consumer_task):
                if not t.done():
                    t.cancel()
            await asyncio.gather(producer_task, consumer_task, return_exceptions=True)
            if on_mouth_update:
                try:
                    await self._invoke_callback(on_mouth_update, 0.0)
                except Exception:
                    pass
            raise
        finally:
            self._is_speaking = False
            self._active_stream_tasks = []
            self._active_mouth_callback = None
            if self._tts_channel is not None:
                try:
                    self._tts_channel.stop()
                except Exception:
                    pass
                self._tts_channel = None
            self._tts_sound = None
            # Drain any unconsumed items in the queue and clean up all temp files
            while not audio_queue.empty():
                try:
                    queued = audio_queue.get_nowait()
                    if queued and queued[0]:
                        self._cleanup_audio_file(queued[0])
                        pending_files.discard(queued[0])
                        self._active_temp_files.discard(queued[0])
                except asyncio.QueueEmpty:
                    break
            for leftover in list(pending_files):
                self._cleanup_audio_file(leftover)
                pending_files.discard(leftover)
                self._active_temp_files.discard(leftover)

    @staticmethod
    def _cleanup_audio_file(file_path: str):
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass

    async def _simulate_mouth_flap(self, text: str, on_mouth_update: Optional[Callable[[float], Any]]):
        if not on_mouth_update:
            return
        words = len(text.split())
        est_duration = max(0.5, min(3.0, words / 3.0))
        steps = max(1, int(est_duration / 0.1))
        try:
            for i in range(steps):
                await asyncio.sleep(0.1)
                await self._invoke_callback(on_mouth_update, 0.6 if i % 2 == 0 else 0.1)
            await self._invoke_callback(on_mouth_update, 0.0)
        except asyncio.CancelledError:
            try:
                await self._invoke_callback(on_mouth_update, 0.0)
            except Exception:
                pass
            raise

    async def _play_and_lipsync(self, file_path: str, text: str, on_mouth_update: Optional[Callable[[float], Any]]):
        """
        Play audio via dedicated pygame.mixer.Sound channel and drive lip-sync from
        the real per-frame RMS audio envelope, stopping immediately when playback ends.
        """
        if self.output_mode == "browser":
            if self.on_audio_ready is None:
                await self._simulate_mouth_flap(text, on_mouth_update)
            self._cleanup_audio_file(file_path)
            return

        channel = None

        try:
            import pygame

            def _load_sound_and_envelope() -> Tuple[Any, List[float]]:
                if not self._mixer_initialized:
                    if not isinstance(pygame.mixer.get_init(), tuple):
                        pygame.mixer.init()
                    self._mixer_initialized = True
                snd = pygame.mixer.Sound(file_path)
                env, _ = extract_rms_envelope_from_sound(snd, frame_ms=50)
                if not env:
                    try:
                        env, _ = extract_rms_envelope_from_wav(Path(file_path).read_bytes(), frame_ms=50)
                    except Exception:
                        env = []
                return snd, env

            sound, envelope = await asyncio.to_thread(_load_sound_and_envelope)
            self._tts_sound = sound
            channel = sound.play()
            self._tts_channel = channel

            # Real audio-envelope RMS lip sync while dedicated TTS channel is playing
            interval = 0.05
            elapsed = 0.0
            step = 0
            while channel is not None and channel.get_busy() in (True, 1):
                if on_mouth_update:
                    if envelope:
                        idx = min(len(envelope) - 1, int(elapsed / interval))
                        val = envelope[idx]
                    else:
                        val = 0.6 if step % 2 == 0 else 0.2
                    await self._invoke_callback(on_mouth_update, val)
                await asyncio.sleep(interval)
                elapsed += interval
                step += 1

            if on_mouth_update:
                await self._invoke_callback(on_mouth_update, 0.0)
        except asyncio.CancelledError:
            if on_mouth_update:
                try:
                    await self._invoke_callback(on_mouth_update, 0.0)
                except Exception:
                    pass
            raise
        except Exception:
            # Fallback if pygame audio device isn't available: use WAV RMS envelope if available
            envelope: List[float] = []
            try:
                envelope, _ = extract_rms_envelope_from_wav(Path(file_path).read_bytes(), frame_ms=50)
            except Exception:
                envelope = []
            if envelope:
                for val in envelope:
                    await asyncio.sleep(0.05)
                    if on_mouth_update:
                        await self._invoke_callback(on_mouth_update, val)
                if on_mouth_update:
                    await self._invoke_callback(on_mouth_update, 0.0)
            else:
                await self._simulate_mouth_flap(text, on_mouth_update)
        finally:
            if channel is not None:
                try:
                    channel.stop()
                except Exception:
                    pass
            self._tts_channel = None
            self._tts_sound = None
            self._cleanup_audio_file(file_path)
