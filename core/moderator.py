import re
import json
from pathlib import Path
from typing import Tuple, List

class Moderator:
    def __init__(self, config_path: str = "config/filter_words.json"):
        self.config_path = Path(config_path)
        self.banned_words: List[str] = []
        self.banned_patterns: List[re.Pattern] = []
        self.replacement = "[CENSORED]"
        self.load_rules()

    def load_rules(self):
        if not self.config_path.exists():
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.banned_words = [w.lower() for w in data.get("banned_words", [])]
                self.banned_patterns = [
                    re.compile(p, re.IGNORECASE) for p in data.get("banned_patterns", [])
                ]
                self.replacement = data.get("replacement", "[CENSORED]")
        except Exception as e:
            print(f"[Moderator] Error loading rules: {e}")

    def clean_text(self, text: str) -> Tuple[bool, str]:
        """
        Check and sanitize text.
        Returns: (is_safe: bool, sanitized_text: str)
        """
        if not text:
            return True, ""

        # Limit message length
        if len(text) > 300:
            text = text[:300] + "..."

        is_safe = True
        lowered = text.lower()

        # Check banned words
        for word in self.banned_words:
            if word in lowered:
                is_safe = False
                pattern = re.compile(re.escape(word), re.IGNORECASE)
                text = pattern.sub(self.replacement, text)

        # Check regex patterns
        for pattern in self.banned_patterns:
            if pattern.search(text):
                is_safe = False
                text = pattern.sub(self.replacement, text)

        return is_safe, text
