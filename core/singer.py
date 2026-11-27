import os
import json
import time
import inspect
import asyncio
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List, Set
import edge_tts
import pygame

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

class Singer:
    """
    Karaoke & Singing Engine for Eve.
    Plays instrumental backing tracks while synthesizing melodic vocal lyrics
    with pitch-prosody modulation, real-time lip sync, and subtitle sync.
    """

    def __init__(
        self,
        songs_config_path: str = "config/songs.json",
        voice: str = "en-US-AnaNeural",
        output_mode: str = "both",
        rvc_enabled: bool = False,
        rvc_url: str = "",
        rvc_pitch_shift: int = 0,
        provider: str = "edge-tts",
        fallback_voice: str = "en-US-AriaNeural",
        elevenlabs_voice_id: str = "",
        kokoro_url: str = "",
        custom_tts_url: str = "",
    ):
        self.songs_config_path = Path(songs_config_path)
        self.voice = voice
        self.fallback_voice = str(fallback_voice or "en-US-AriaNeural").strip() or "en-US-AriaNeural"
        mode = str(output_mode or "both").strip().lower()
        self.output_mode = mode if mode in ("server", "browser", "both") else "both"
        self.provider = str(provider or "edge-tts").strip().lower()
        self.elevenlabs_voice_id = str(elevenlabs_voice_id or "").strip()
        self.kokoro_url = str(kokoro_url or "").strip()
        self.custom_tts_url = str(custom_tts_url or "").strip()
        self.rvc_enabled = bool(rvc_enabled)
        self.rvc_url = str(rvc_url or "").strip()
        self.rvc_pitch_shift = int(rvc_pitch_shift)
        self._fallback_provider: EdgeTTSProvider = EdgeTTSProvider()
        self._provider: BaseTTSProvider = self._build_provider()
        self._rvc = RVCVoiceConverter(
            enabled=self.rvc_enabled,
            rvc_url=self.rvc_url,
            pitch_shift=self.rvc_pitch_shift,
        )
        self.songs: Dict[str, Any] = {}
        self.temp_dir = Path(tempfile.gettempdir()) / "maybeai_karaoke"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.is_singing = False
        self._stop_requested = False
        self._active_channel: Any = None
        self.load_songs()

    def _build_provider(self) -> BaseTTSProvider:
        try:
            return create_tts_provider(
                self.provider,
                kokoro_url=self.kokoro_url,
                elevenlabs_voice_id=self.elevenlabs_voice_id,
                custom_tts_url=self.custom_tts_url,
            )
        except ValueError as exc:
            print(f"[Singer Warning] {exc}. Falling back to edge-tts.")
            self.provider = "edge-tts"
            return EdgeTTSProvider()

    def update_config(
        self,
        voice: Optional[str] = None,
        output_mode: Optional[str] = None,
        rvc_enabled: Optional[bool] = None,
        rvc_url: Optional[str] = None,
        rvc_pitch_shift: Optional[int] = None,
        provider: Optional[str] = None,
        fallback_voice: Optional[str] = None,
        elevenlabs_voice_id: Optional[str] = None,
        kokoro_url: Optional[str] = None,
        custom_tts_url: Optional[str] = None,
    ) -> None:
        if voice:
            self.voice = voice.strip()
        if fallback_voice:
            self.fallback_voice = str(fallback_voice).strip()
        if output_mode is not None:
            mode = str(output_mode).strip().lower()
            if mode in ("server", "browser", "both"):
                self.output_mode = mode
        rebuild_provider = False
        if provider is not None:
            self.provider = str(provider or "edge-tts").strip().lower()
            rebuild_provider = True
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

    async def close(self) -> None:
        """Closes persistent HTTP sessions held by TTS provider and RVC converter."""
        for component in (self._provider, self._fallback_provider, self._rvc):
            if component is not None and hasattr(component, "close"):
                try:
                    await component.close()
                except Exception:
                    pass

    async def _synthesize_vocal(
        self,
        text: str,
        rate: str = "+0%",
        pitch: str = "+0Hz",
        emotion: str = "happy",
    ) -> bytes:
        try:
            vocal_bytes = await self._provider.synthesize(
                text=text,
                voice=self.voice,
                rate=rate,
                pitch=pitch,
                emotion=emotion,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not isinstance(self._provider, EdgeTTSProvider):
                fb_voice = self.voice if is_edge_tts_voice(self.voice) else self.fallback_voice
                print(
                    f"[Singer Provider Warning] {self.provider} failed ({exc}); "
                    f"falling back to edge-tts ({fb_voice})."
                )
                vocal_bytes = await self._fallback_provider.synthesize(
                    text=text,
                    voice=fb_voice,
                    rate=rate,
                    pitch=pitch,
                    emotion=emotion,
                )
            else:
                raise

        if self._rvc.enabled and self.rvc_url:
            converted = await self._rvc.convert(vocal_bytes, pitch_shift=self.rvc_pitch_shift)
            if converted:
                vocal_bytes = converted
        return vocal_bytes

    def load_songs(self):
        if self.songs_config_path.exists():
            try:
                with open(self.songs_config_path, "r", encoding="utf-8") as f:
                    self.songs = json.load(f)
            except Exception as e:
                print(f"[Singer] Error loading songs: {e}")

    def get_available_songs(self) -> List[Dict[str, str]]:
        return [
            {"id": k, "title": v.get("title", k), "artist": v.get("artist", "")}
            for k, v in self.songs.items()
        ]

    def stop(self):
        """Immediately aborts current song."""
        self._stop_requested = True
        if self._active_channel is not None:
            try:
                self._active_channel.stop()
            except Exception:
                pass
            self._active_channel = None
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

    @staticmethod
    def _cleanup_vocal_file(file_path: str) -> None:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass

    @staticmethod
    def _get_playback_clock_sec(start_time: float, use_server_audio: bool) -> float:
        """
        Returns the current song playback clock in seconds.
        Anchors to pygame.mixer.music.get_pos() when server BGM is actively playing,
        and falls back to monotonic wall-clock (time.monotonic() - start_time).
        """
        if use_server_audio:
            try:
                if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                    pos_ms = pygame.mixer.music.get_pos()
                    if pos_ms is not None and pos_ms >= 0:
                        return float(pos_ms) / 1000.0
            except Exception:
                pass
        return max(0.0, time.monotonic() - start_time)

    async def _wait_until_clock(
        self,
        target_sec: float,
        start_time: float,
        use_server_audio: bool,
        tick_sec: float = 0.05,
    ) -> None:
        """Sleeps in short slices until the playback clock reaches target_sec."""
        while not self._stop_requested:
            current = self._get_playback_clock_sec(start_time, use_server_audio)
            remaining = target_sec - current
            if remaining <= 0.0:
                break
            await asyncio.sleep(min(tick_sec, remaining))

    async def sing(
        self,
        song_id: str,
        on_lyric_update: Optional[Callable[[str, str], Any]] = None,
        on_mouth_update: Optional[Callable[[float], Any]] = None,
        on_vocal_audio: Optional[Callable[[bytes, str], Any]] = None,
    ) -> bool:
        """
        Executes full karaoke performance:
        Plays BGM + Sings lyric lines in rhythm + updates avatar lip-sync & emotion.
        Cleans up all temporary vocal_*.mp3 files in finally.
        """
        song = self.songs.get(song_id)
        if not song:
            print(f"[Singer] Song '{song_id}' not found in catalog.")
            return False

        self.is_singing = True
        self._stop_requested = False
        created_vocal_files: Set[str] = set()

        bgm_file = song.get("bgm_file") or song.get("bgm")
        bgm_vol = song.get("bgm_volume", 0.3)
        vocal_track = song.get("vocal_track")
        lyrics = song.get("lyrics", [])
        use_server_audio = self.output_mode in ("server", "both")

        try:
            if use_server_audio:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()

                # 1. Start Backing Track (BGM)
                if bgm_file and Path(bgm_file).exists():
                    pygame.mixer.music.load(bgm_file)
                    pygame.mixer.music.set_volume(bgm_vol)
                    pygame.mixer.music.play()
                    print(f"[Singer] Started BGM: {bgm_file} at volume {bgm_vol}")

            song_start_time = time.monotonic()

            # 1b. Pre-separated / RVC-converted full vocal track mode (AI Cover)
            if vocal_track and Path(vocal_track).exists():
                vocal_path = Path(vocal_track)
                vocal_bytes = await asyncio.to_thread(vocal_path.read_bytes)
                if on_vocal_audio and self.output_mode in ("browser", "both") and vocal_bytes:
                    try:
                        cb_res = on_vocal_audio(vocal_bytes, song.get("title", song_id))
                        if inspect.isawaitable(cb_res):
                            await cb_res
                    except Exception:
                        pass

                envelope: List[float] = []
                channel = None
                if use_server_audio:
                    def _load_full_vocal() -> Any:
                        snd = pygame.mixer.Sound(str(vocal_path))
                        snd.set_volume(1.0)
                        env, _ = extract_rms_envelope_from_sound(snd, frame_ms=50)
                        if not env:
                            env, _ = extract_rms_envelope_from_wav(vocal_bytes, frame_ms=50)
                        return snd, env

                    sound, envelope = await asyncio.to_thread(_load_full_vocal)
                    channel = sound.play()
                    self._active_channel = channel
                else:
                    envelope, _ = await asyncio.to_thread(extract_rms_envelope_from_wav, vocal_bytes, 50)

                interval = 0.05
                next_lyric_idx = 0
                sorted_lyrics = sorted(
                    lyrics,
                    key=lambda item: float(
                        item.get("cue_sec", item.get("timestamp_sec", item.get("start_sec", item.get("time", 0.0)))) or 0.0
                    ),
                )
                est_total_sec = max(
                    len(envelope) * interval if envelope else 0.0,
                    float(song.get("duration_sec") or 0.0),
                    1.0,
                )
                step = 0
                while not self._stop_requested:
                    elapsed = self._get_playback_clock_sec(song_start_time, use_server_audio)
                    if use_server_audio:
                        if channel is None or channel.get_busy() not in (True, 1):
                            break
                    elif elapsed >= est_total_sec:
                        break

                    while next_lyric_idx < len(sorted_lyrics):
                        cue_item = sorted_lyrics[next_lyric_idx]
                        cue_t = float(
                            cue_item.get(
                                "cue_sec",
                                cue_item.get("timestamp_sec", cue_item.get("start_sec", cue_item.get("time", 0.0))),
                            )
                            or 0.0
                        )
                        if elapsed >= cue_t:
                            if on_lyric_update:
                                res = on_lyric_update(cue_item.get("text", ""), cue_item.get("emotion", "happy"))
                                if inspect.isawaitable(res):
                                    await res
                            next_lyric_idx += 1
                        else:
                            break

                    if on_mouth_update and envelope:
                        env_idx = min(len(envelope) - 1, int(elapsed / interval))
                        m_res = on_mouth_update(envelope[env_idx])
                        if inspect.isawaitable(m_res):
                            await m_res

                    step += 1
                    next_tick = song_start_time + (step * interval)
                    sleep_for = next_tick - time.monotonic()
                    if sleep_for > 0:
                        await asyncio.sleep(sleep_for)

                self._active_channel = None
                if on_mouth_update:
                    m_res = on_mouth_update(0.0)
                    if inspect.isawaitable(m_res):
                        await m_res
                return not self._stop_requested

            # 2. Iterate through lyrics with audio-clock-locked scheduling
            for idx, line_data in enumerate(lyrics):
                if self._stop_requested:
                    break

                text = line_data.get("text", "")
                pitch = line_data.get("pitch", "+30Hz")
                rate = line_data.get("rate", "-10%")
                delay_before = float(line_data.get("delay_before", 0.5) or 0.0)
                explicit_cue = line_data.get(
                    "cue_sec",
                    line_data.get("timestamp_sec", line_data.get("start_sec", line_data.get("time"))),
                )
                emotion = line_data.get("emotion", "happy")

                # Anchor cue target to absolute BGM timestamp if provided,
                # or clock-locked offset from current playback position.
                if explicit_cue is not None:
                    target_cue_sec = max(0.0, float(explicit_cue))
                else:
                    now_clock = self._get_playback_clock_sec(song_start_time, use_server_audio)
                    target_cue_sec = now_clock + max(0.0, delay_before)

                if target_cue_sec > self._get_playback_clock_sec(song_start_time, use_server_audio):
                    await self._wait_until_clock(target_cue_sec, song_start_time, use_server_audio)

                if self._stop_requested:
                    break

                # Notify subtitle & emotion
                if on_lyric_update:
                    res = on_lyric_update(text, emotion)
                    if inspect.isawaitable(res):
                        await res

                # Generate melodic vocal audio via configured TTS provider + optional RVC
                vocal_bytes = await self._synthesize_vocal(
                    text=text,
                    rate=rate,
                    pitch=pitch,
                    emotion=emotion,
                )

                if on_vocal_audio and self.output_mode in ("browser", "both") and vocal_bytes:
                    try:
                        cb_res = on_vocal_audio(vocal_bytes, text)
                        if inspect.isawaitable(cb_res):
                            await cb_res
                    except Exception:
                        pass

                if use_server_audio and vocal_bytes:
                    _, ext = detect_audio_format(vocal_bytes)
                    vocal_file = str(self.temp_dir / f"vocal_{song_id}_{idx}{ext}")
                    created_vocal_files.add(vocal_file)
                    await asyncio.to_thread(Path(vocal_file).write_bytes, vocal_bytes)

                    def _load_vocal_sound() -> Any:
                        snd = pygame.mixer.Sound(vocal_file)
                        snd.set_volume(1.0)
                        env, _ = extract_rms_envelope_from_sound(snd, frame_ms=50)
                        if not env:
                            env, _ = extract_rms_envelope_from_wav(vocal_bytes, frame_ms=50)
                        return snd, env

                    sound, envelope = await asyncio.to_thread(_load_vocal_sound)
                    channel = sound.play()
                    self._active_channel = channel

                    # Real audio-envelope RMS lip-sync locked to monotonic clock
                    interval = 0.05
                    line_start = time.monotonic()
                    step = 0
                    while channel is not None and channel.get_busy() in (True, 1) and not self._stop_requested:
                        elapsed = max(0.0, time.monotonic() - line_start)
                        if on_mouth_update:
                            if envelope:
                                env_idx = min(len(envelope) - 1, int(elapsed / interval))
                                val = envelope[env_idx]
                            else:
                                val = 0.6 if step % 2 == 0 else 0.2
                            m_res = on_mouth_update(val)
                            if inspect.isawaitable(m_res):
                                await m_res
                        step += 1
                        next_tick = line_start + (step * interval)
                        sleep_for = next_tick - time.monotonic()
                        if sleep_for > 0:
                            await asyncio.sleep(sleep_for)
                    self._active_channel = None
                elif not use_server_audio and on_vocal_audio is None:
                    est_duration = max(1.0, len(text.split()) / 2.6)
                    line_start = time.monotonic()
                    step = 0
                    while not self._stop_requested:
                        elapsed = time.monotonic() - line_start
                        if elapsed >= est_duration:
                            break
                        next_tick = line_start + ((step + 1) * 0.1)
                        sleep_for = min(0.1, max(0.0, next_tick - time.monotonic()))
                        if sleep_for > 0:
                            await asyncio.sleep(sleep_for)
                        if on_mouth_update:
                            val = 0.6 if step % 2 == 0 else 0.1
                            m_res = on_mouth_update(val)
                            if inspect.isawaitable(m_res):
                                await m_res
                        step += 1

                if on_mouth_update:
                    m_res = on_mouth_update(0.0)
                    if inspect.isawaitable(m_res):
                        await m_res

            # Wait a moment for outro
            if not self._stop_requested:
                await asyncio.sleep(1.5)

            # Fade out BGM
            if use_server_audio and pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                pygame.mixer.music.fadeout(1500)
                await asyncio.sleep(1.5)

            return True

        except Exception as e:
            print(f"[Singer Error] {e}")
            return False
        finally:
            self.is_singing = False
            if self._active_channel is not None:
                try:
                    self._active_channel.stop()
                except Exception:
                    pass
                self._active_channel = None
            if use_server_audio:
                try:
                    if pygame.mixer.get_init():
                        pygame.mixer.music.stop()
                except Exception:
                    pass
            for vf in list(created_vocal_files):
                self._cleanup_vocal_file(vf)
            if on_mouth_update:
                try:
                    m_res = on_mouth_update(0.0)
                    if inspect.isawaitable(m_res):
                        await m_res
                except Exception:
                    pass
