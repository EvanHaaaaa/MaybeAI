import re
import json
from pathlib import Path
from typing import Tuple, List, Optional

class Moderator:
    def __init__(self, config_path: str = "config/filter_words.json", max_message_length: int = 250, strict_mode: bool = True):
        self.config_path = Path(config_path)
        self.max_message_length = max_message_length
        self.strict_mode = strict_mode
        self.banned_words: List[str] = []
        self.banned_patterns: List[re.Pattern] = []
        self.replacement = "[CENSORED]"
        self.load_rules()

    def update_config(self, strict_mode: Optional[bool] = None, max_message_length: Optional[int] = None):
        if strict_mode is not None:
            self.strict_mode = bool(strict_mode)
        if max_message_length is not None:
            self.max_message_length = max(50, min(2000, int(max_message_length)))

    def get_status(self) -> dict:
        return {
            "strict_mode": self.strict_mode,
            "max_message_length": self.max_message_length,
            "banned_words_count": len(self.banned_words),
            "banned_patterns_count": len(self.banned_patterns),
            "replacement": self.replacement
        }

    def test_text(self, text: str) -> dict:
        is_safe, sanitized = self.clean_text(text)
        violations = []
        lowered = text.lower()
        for w in self.banned_words:
            if w in lowered:
                violations.append(f"Keyword: '{w}'")
        for p in self.banned_patterns:
            if p.search(text):
                violations.append(f"Pattern match: '{p.pattern}'")
        if len(text) > self.max_message_length:
            violations.append(f"Exceeded length limit ({len(text)} > {self.max_message_length})")
        return {
            "is_safe": is_safe,
            "sanitized": sanitized,
            "violations": violations
        }

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
        if len(text) > self.max_message_length:
            text = text[:self.max_message_length] + "..."

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
