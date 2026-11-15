import os
import json
import asyncio
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
import edge_tts
import pygame

class Singer:
    """
    Karaoke & Singing Engine for Eve.
    Plays instrumental backing tracks while synthesizing melodic vocal lyrics
    with pitch-prosody modulation, real-time lip sync, and subtitle sync.
    """

    def __init__(self, songs_config_path: str = "config/songs.json", voice: str = "en-US-AnaNeural"):
        self.songs_config_path = Path(songs_config_path)
        self.voice = voice
        self.songs: Dict[str, Any] = {}
        self.temp_dir = Path(tempfile.gettempdir()) / "maybeai_karaoke"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.is_singing = False
        self._stop_requested = False
        self.load_songs()

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
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.stop()
        except Exception:
            pass

    async def sing(
        self,
        song_id: str,
        on_lyric_update: Optional[Callable[[str, str], None]] = None,
        on_mouth_update: Optional[Callable[[float], None]] = None
    ) -> bool:
        """
        Executes full karaoke performance:
        Plays BGM + Sings lyric lines in rhythm + updates avatar lip-sync & emotion.
        """
        song = self.songs.get(song_id)
        if not song:
            print(f"[Singer] Song '{song_id}' not found in catalog.")
            return False

        self.is_singing = True
        self._stop_requested = False

        bgm_file = song.get("bgm_file")
        bgm_vol = song.get("bgm_volume", 0.3)
        lyrics = song.get("lyrics", [])

        try:
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
                    if asyncio.iscoroutine(res):
                        await res

                # Generate melodic vocal file
                vocal_file = str(self.temp_dir / f"vocal_{song_id}_{idx}.mp3")
                comm = edge_tts.Communicate(
                    text=text,
                    voice=self.voice,
                    pitch=pitch,
                    rate=rate
                )
                await comm.save(vocal_file)

                # Play vocal on dedicated channel so BGM keeps playing simultaneously
                sound = pygame.mixer.Sound(vocal_file)
                sound.set_volume(1.0)
                channel = sound.play()

                # Dynamic lip-sync while vocal line plays
                step = 0
                while channel.get_busy() and not self._stop_requested:
                    await asyncio.sleep(0.08)
                    step += 1
                    if on_mouth_update:
                        val = 0.7 if step % 2 == 0 else 0.2
                        on_mouth_update(val)

                if on_mouth_update:
                    on_mouth_update(0.0)

            # Wait a moment for outro
            await asyncio.sleep(1.5)

            # Fade out BGM
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.fadeout(1500)
                await asyncio.sleep(1.5)

            return True

        except Exception as e:
            print(f"[Singer Error] {e}")
            return False
        finally:
            self.is_singing = False
            if on_mouth_update:
                on_mouth_update(0.0)
