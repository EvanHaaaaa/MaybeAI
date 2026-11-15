import asyncio
from typing import Optional, Callable

class STTEngine:
    """
    Speech-to-Text engine for voice recognition (e.g. hearing user mic or Discord collab).
    """

    def __init__(self, model_name: str = "base", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self.is_listening = False

    async def transcribe_audio_file(self, file_path: str) -> str:
        """
        Transcribe an audio file. Falls back gracefully if local whisper isn't installed.
        """
        try:
            import whisper
            model = whisper.load_model(self.model_name, device=self.device)
            result = model.transcribe(file_path)
            return result.get("text", "").strip()
        except ImportError:
            return "[STT Mock] Whisper not installed. Install with: pip install openai-whisper"
        except Exception as e:
            return f"[STT Error] {e}"
