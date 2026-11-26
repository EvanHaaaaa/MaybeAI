import os
import json
import inspect
import asyncio
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List, Set
import edge_tts
import pygame

from core.tts_providers import RVCVoiceConverter

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
    ):
        self.songs_config_path = Path(songs_config_path)
        self.voice = voice
        mode = str(output_mode or "both").strip().lower()
        self.output_mode = mode if mode in ("server", "browser", "both") else "both"
        self.rvc_enabled = bool(rvc_enabled)
        self.rvc_url = str(rvc_url or "").strip()
        self.rvc_pitch_shift = int(rvc_pitch_shift)
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

    def update_config(
        self,
        voice: Optional[str] = None,
        output_mode: Optional[str] = None,
        rvc_enabled: Optional[bool] = None,
        rvc_url: Optional[str] = None,
        rvc_pitch_shift: Optional[int] = None,
    ) -> None:
        if voice:
            self.voice = voice.strip()
        if output_mode is not None:
            mode = str(output_mode).strip().lower()
            if mode in ("server", "browser", "both"):
                self.output_mode = mode
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

        bgm_file = song.get("bgm_file")
        bgm_vol = song.get("bgm_volume", 0.3)
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

            # 2. Iterate through lyrics
            for idx, line_data in enumerate(lyrics):
                if self._stop_requested:
                    break

                text = line_data.get("text", "")
                pitch = line_data.get("pitch", "+30Hz")
                rate = line_data.get("rate", "-10%")
                delay_before = line_data.get("delay_before", 0.5)
                emotion = line_data.get("emotion", "happy")

                # Wait rhythmic intro/pause before line
                if delay_before > 0:
                    await asyncio.sleep(delay_before)

                if self._stop_requested:
                    break

                # Notify subtitle & emotion
                if on_lyric_update:
                    res = on_lyric_update(text, emotion)
                    if inspect.isawaitable(res):
                        await res

                # Generate melodic vocal file
                vocal_file = str(self.temp_dir / f"vocal_{song_id}_{idx}.mp3")
                created_vocal_files.add(vocal_file)
                comm = edge_tts.Communicate(
                    text=text,
                    voice=self.voice,
                    pitch=pitch,
                    rate=rate
                )
                await comm.save(vocal_file)

                if self._rvc.enabled and self.rvc_url:
                    raw_vocal_bytes = Path(vocal_file).read_bytes()
                    converted_vocal_bytes = await self._rvc.convert(
                        raw_vocal_bytes, pitch_shift=self.rvc_pitch_shift
                    )
                    if converted_vocal_bytes and converted_vocal_bytes != raw_vocal_bytes:
                        Path(vocal_file).write_bytes(converted_vocal_bytes)

                if on_vocal_audio and self.output_mode in ("browser", "both"):
                    try:
                        audio_bytes = Path(vocal_file).read_bytes()
                        if audio_bytes:
                            cb_res = on_vocal_audio(audio_bytes, text)
                            if inspect.isawaitable(cb_res):
                                await cb_res
                    except Exception:
                        pass

                if use_server_audio:
                    # Play vocal on dedicated channel so BGM keeps playing simultaneously
                    sound = pygame.mixer.Sound(vocal_file)
                    sound.set_volume(1.0)
                    channel = sound.play()
                    self._active_channel = channel

                    # Dynamic lip-sync while vocal line plays
                    step = 0
                    while channel is not None and channel.get_busy() and not self._stop_requested:
                        await asyncio.sleep(0.08)
                        step += 1
                        if on_mouth_update:
                            val = 0.7 if step % 2 == 0 else 0.2
                            m_res = on_mouth_update(val)
                            if inspect.isawaitable(m_res):
                                await m_res
                    self._active_channel = None
                else:
                    est_duration = max(1.0, len(text.split()) / 2.6)
                    steps = max(1, int(est_duration / 0.1))
                    for step in range(steps):
                        if self._stop_requested:
                            break
                        await asyncio.sleep(0.1)
                        if on_mouth_update:
                            val = 0.7 if step % 2 == 0 else 0.2
                            m_res = on_mouth_update(val)
                            if inspect.isawaitable(m_res):
                                await m_res

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
