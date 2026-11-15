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

    def __init__(self, voice: str = "en-US-AnaNeural", rate: str = "+5%", pitch: str = "+10Hz"):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.temp_dir = Path(tempfile.gettempdir()) / "maybeai_audio"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def speak(self, text: str, on_mouth_update: Optional[Callable[[float], None]] = None) -> Optional[str]:
        """
        Synthesizes text to speech, plays audio, and fires lip-sync mouth updates.
        Returns path to generated audio file.
        """
        if not text.strip():
            return None

        output_file = str(self.temp_dir / f"speech_{asyncio.get_event_loop().time():.2f}.mp3")

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
            return output_file
        except Exception as e:
            print(f"[TTS Error] {e}")
            return None

    async def _play_and_lipsync(self, file_path: str, text: str, on_mouth_update: Optional[Callable[[float], None]]):
        """
        Simulate/Play audio and fire dynamic lip-sync mouth pulses based on text timing.
        """
        # Estimate duration roughly based on word count (approx 150 words/min = 2.5 words/sec)
        words = len(text.split())
        est_duration = max(1.0, words / 2.6)

        try:
            import pygame
            pygame.mixer.init()
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
