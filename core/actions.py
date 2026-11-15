import re
from typing import Dict, Any, Tuple, List

class ActionParser:
    """
    Parses emotions and actions from AI response text.
    Example: "[emotion: smug] You really thought you could beat me? [action: giggle]"
    Output:
      clean_speech: "You really thought you could beat me?"
      emotions: ["smug"]
      actions: ["giggle"]
    """
    EMOTION_REGEX = re.compile(r"\[emotion:\s*([a-zA-Z0-9_\-]+)\]", re.IGNORECASE)
    ACTION_REGEX = re.compile(r"\[action:\s*([a-zA-Z0-9_\-]+)\]", re.IGNORECASE)

    @classmethod
    def parse(cls, raw_text: str) -> Tuple[str, List[str], List[str]]:
        emotions = cls.EMOTION_REGEX.findall(raw_text)
        actions = cls.ACTION_REGEX.findall(raw_text)

        # Remove emotion and action tags for spoken text
        clean = cls.EMOTION_REGEX.sub("", raw_text)
        clean = cls.ACTION_REGEX.sub("", clean)
        clean = " ".join(clean.split()).strip()

        return clean, emotions, actions
