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
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.enabled = enabled
        self.interruptible = interruptible
        mode = str(output_mode or "both").strip().lower()
        self.output_mode = mode if mode in self._VALID_OUTPUT_MODES else "both"
        self.on_audio_ready = on_audio_ready
        self.last_error: Optional[str] = None
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

    def update_config(
        self,
        enabled: Optional[bool] = None,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
        interruptible: Optional[bool] = None,
        output_mode: Optional[str] = None,
    ):
        if enabled is not None:
            self.enabled = bool(enabled)
        if voice:
            self.voice = voice.strip()
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

    def get_status(self) -> dict:
        return {
            "enabled": self.enabled,
            "provider": "edge-tts",
            "voice": self.voice,
            "rate": self.rate,
            "pitch": self.pitch,
            "interruptible": self.interruptible,
            "output_mode": self.output_mode,
            "is_speaking": self._is_speaking,
            "was_interrupted": self._was_interrupted,
            "last_error": self.last_error
        }

    def _make_temp_audio_path(self) -> str:
        ts_ms = int(asyncio.get_running_loop().time() * 1000)
        return str(self.temp_dir / f"speech_{ts_ms}_{uuid.uuid4().hex[:6]}.mp3")

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

        async def _emit_browser_audio(out_path: str, spoken_text: str) -> None:
            if self.on_audio_ready is None or self.output_mode not in ("browser", "both"):
                return
            try:
                audio_bytes = Path(out_path).read_bytes()
            except Exception:
                return
            if audio_bytes:
                await self._invoke_callback(self.on_audio_ready, audio_bytes, spoken_text, self.voice)

        async def _run_speak(out_path: str) -> str:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch
            )
            await communicate.save(out_path)
            await _emit_browser_audio(out_path, text)
            if self.output_mode in ("server", "both"):
                await self._play_and_lipsync(out_path, text, on_mouth_update)
            else:
                await self._simulate_mouth_flap(text, on_mouth_update)
            self.last_error = None
            return out_path

        try:
            if not self.enabled:
                task = asyncio.create_task(self._simulate_mouth_flap(text, on_mouth_update))
                self._active_speak_task = task
                await task
                return None

            output_file = self._make_temp_audio_path()
            self._active_temp_files.add(output_file)
            task = asyncio.create_task(_run_speak(output_file))
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
        audio_queue: asyncio.Queue[Optional[Tuple[Optional[str], str, List[str], List[str]]]] = asyncio.Queue(maxsize=4)
        pending_files: Set[str] = set()
        raw_parts: List[str] = []

        async def _enqueue_sentence(sentence: str):
            clean_text, emotions, actions = ActionParser.parse(sentence)
            if not clean_text and not emotions and not actions:
                return

            if not clean_text:
                await audio_queue.put((None, "", emotions, actions))
                return

            if not self.enabled:
                await audio_queue.put((None, clean_text, emotions, actions))
                return

            out_file = self._make_temp_audio_path()
            pending_files.add(out_file)
            self._active_temp_files.add(out_file)
            try:
                communicate = edge_tts.Communicate(
                    text=clean_text,
                    voice=self.voice,
                    rate=self.rate,
                    pitch=self.pitch,
                )
                await communicate.save(out_file)
                self.last_error = None
            except asyncio.CancelledError:
                self._cleanup_audio_file(out_file)
                pending_files.discard(out_file)
                self._active_temp_files.discard(out_file)
                raise
            except Exception as e:
                self.last_error = str(e)
                print(f"[TTS Stream Error] {e}")
                self._cleanup_audio_file(out_file)
                pending_files.discard(out_file)
                self._active_temp_files.discard(out_file)
                out_file = None

            await audio_queue.put((out_file, clean_text, emotions, actions))

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

                file_path, clean_text, emotions, actions = item
                try:
                    if emotions or actions:
                        await self._invoke_callback(on_tag, emotions, actions)

                    if clean_text:
                        await self._invoke_callback(on_sentence_start, clean_text)
                        if file_path:
                            if self.on_audio_ready is not None and self.output_mode in ("browser", "both"):
                                try:
                                    audio_bytes = Path(file_path).read_bytes()
                                    if audio_bytes:
                                        await self._invoke_callback(
                                            self.on_audio_ready, audio_bytes, clean_text, self.voice
                                        )
                                except Exception:
                                    pass
                            if self.output_mode in ("server", "both"):
                                await self._play_and_lipsync(file_path, clean_text, on_mouth_update)
                            else:
                                await self._simulate_mouth_flap(clean_text, on_mouth_update)
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
            if self._stop_requested:
                return "".join(raw_parts).strip()
            raise
        finally:
            self._is_speaking = False
            self._active_stream_tasks = []
            self._active_mouth_callback = None
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
        Simulate/Play audio via dedicated pygame.mixer.Sound channel and fire dynamic lip-sync mouth pulses.
        """
        if self.output_mode == "browser":
            await self._simulate_mouth_flap(text, on_mouth_update)
            self._cleanup_audio_file(file_path)
            return

        # Estimate duration roughly based on word count (approx 150 words/min = 2.5 words/sec)
        words = len(text.split())
        est_duration = max(1.0, words / 2.6)
        channel = None

        try:
            import pygame
            if not self._mixer_initialized:
                if not isinstance(pygame.mixer.get_init(), tuple):
                    pygame.mixer.init()
                self._mixer_initialized = True
            sound = pygame.mixer.Sound(file_path)
            self._tts_sound = sound
            channel = sound.play()
            self._tts_channel = channel

            # Dynamic lip sync while dedicated TTS channel is playing
            interval = 0.08
            elapsed = 0.0
            step = 0
            while (channel is not None and channel.get_busy() in (True, 1)) or elapsed < est_duration:
                await asyncio.sleep(interval)
                elapsed += interval
                step += 1
                if on_mouth_update:
                    # Rhythmic mouth flap simulation (0.1 to 0.95 amplitude)
                    val = 0.5 + 0.45 * (1 if step % 2 == 0 else 0)
                    await self._invoke_callback(on_mouth_update, val)

            if on_mouth_update:
                await self._invoke_callback(on_mouth_update, 0.0)  # Close mouth when done
        except asyncio.CancelledError:
            if on_mouth_update:
                try:
                    await self._invoke_callback(on_mouth_update, 0.0)
                except Exception:
                    pass
            raise
        except Exception:
            # Fallback if pygame audio device isn't available
            steps = int(est_duration / 0.1)
            for i in range(steps):
                await asyncio.sleep(0.1)
                if on_mouth_update:
                    val = 0.6 if i % 2 == 0 else 0.1
                    await self._invoke_callback(on_mouth_update, val)
            if on_mouth_update:
                await self._invoke_callback(on_mouth_update, 0.0)
        finally:
            if channel is not None:
                try:
                    channel.stop()
                except Exception:
                    pass
            self._tts_channel = None
            self._tts_sound = None
            self._cleanup_audio_file(file_path)
