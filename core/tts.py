import os
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, Callable
import edge_tts

class TTSEngine:
    """
    Handles speech synthesis and audio playback.
    Default provider: edge-tts (High quality, free, realistic voices).
    """

    def __init__(
        self,
        voice: str = "en-US-AnaNeural",
        rate: str = "+5%",
        pitch: str = "+10Hz",
        enabled: bool = True
    ):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.enabled = enabled
        self.last_error: Optional[str] = None
        self._mixer_initialized: bool = False
        self.temp_dir = Path(tempfile.gettempdir()) / "maybeai_audio"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def update_config(
        self,
        enabled: Optional[bool] = None,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None
    ):
        if enabled is not None:
            self.enabled = bool(enabled)
        if voice:
            self.voice = voice.strip()
        if rate:
            self.rate = rate.strip()
        if pitch:
            self.pitch = pitch.strip()

    def get_status(self) -> dict:
        return {
            "enabled": self.enabled,
            "provider": "edge-tts",
            "voice": self.voice,
            "rate": self.rate,
            "pitch": self.pitch,
            "last_error": self.last_error
        }

    async def speak(self, text: str, on_mouth_update: Optional[Callable[[float], None]] = None) -> Optional[str]:
        """
        Synthesizes text to speech, plays audio, and fires lip-sync mouth updates.
        Returns path to generated audio file.
        """
        if not text.strip():
            return None

        # If TTS is disabled, skip audio synthesis and gracefully simulate mouth flap if needed
        if not self.enabled:
            if on_mouth_update:
                words = len(text.split())
                est_duration = max(0.5, min(3.0, words / 3.0))
                steps = int(est_duration / 0.1)
                for i in range(steps):
                    await asyncio.sleep(0.1)
                    on_mouth_update(0.6 if i % 2 == 0 else 0.1)
                on_mouth_update(0.0)
            return None

        output_file = str(self.temp_dir / f"speech_{asyncio.get_running_loop().time():.2f}.mp3")

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch
            )
            await communicate.save(output_file)

            # Play audio and simulate lip sync
            await self._play_and_lipsync(output_file, text, on_mouth_update)
            self.last_error = None
            return output_file
        except Exception as e:
            self.last_error = str(e)
            print(f"[TTS Error] {e}")
            return None
        finally:
            self._cleanup_audio_file(output_file)

    @staticmethod
    def _cleanup_audio_file(file_path: str):
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass

    async def _play_and_lipsync(self, file_path: str, text: str, on_mouth_update: Optional[Callable[[float], None]]):
        """
        Simulate/Play audio and fire dynamic lip-sync mouth pulses based on text timing.
        """
        # Estimate duration roughly based on word count (approx 150 words/min = 2.5 words/sec)
        words = len(text.split())
        est_duration = max(1.0, words / 2.6)

        try:
            import pygame
            if not self._mixer_initialized:
                if not isinstance(pygame.mixer.get_init(), tuple):
                    pygame.mixer.init()
                self._mixer_initialized = True
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()

            # Dynamic lip sync while music is playing
            interval = 0.08
            elapsed = 0.0
            step = 0
            while pygame.mixer.music.get_busy() or elapsed < est_duration:
                await asyncio.sleep(interval)
                elapsed += interval
                step += 1
                if on_mouth_update:
                    # Rhythmic mouth flap simulation (0.1 to 0.95 amplitude)
                    val = 0.5 + 0.45 * (1 if step % 2 == 0 else 0)
                    on_mouth_update(val)

            if on_mouth_update:
                on_mouth_update(0.0) # Close mouth when done
            pygame.mixer.music.stop()
            if hasattr(pygame.mixer.music, "unload"):
                pygame.mixer.music.unload()
        except Exception:
            # Fallback if pygame audio device isn't available
            steps = int(est_duration / 0.1)
            for i in range(steps):
                await asyncio.sleep(0.1)
                if on_mouth_update:
                    val = 0.6 if i % 2 == 0 else 0.1
                    on_mouth_update(val)
            if on_mouth_update:
                on_mouth_update(0.0)
        finally:
            self._cleanup_audio_file(file_path)
