import re
import json
from pathlib import Path
from typing import Any, Tuple, List, Optional


_PROMPT_INJECTION_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"\b(?:ignore|disregard|forget)\s+(?:all\s+|previous\s+|above\s+|prior\s+|your\s+)*(?:instructions|prompts|rules)\b", re.IGNORECASE),
    re.compile(r"\b(?:new\s+system\s+prompt|override\s+system|you\s+are\s+now)\b", re.IGNORECASE),
    re.compile(r"(?:<\|(?:im_start|im_end|system|assistant|user)\|>|\[(?:SYSTEM|INST)\])", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*(?:###\s*)?(?:system|instruction)\s*:", re.IGNORECASE),
)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]+")
_INJECTION_TOKENS_RE = re.compile(r"<\|[^|>]+\|>|\[(?:SYSTEM|INST|/INST)\]", re.IGNORECASE)
_VISUAL_DELIMITER_RE = re.compile(r"</?visual_observation_data>", re.IGNORECASE)


class Moderator:
    def __init__(
        self,
        config_path: str = "config/filter_words.json",
        max_message_length: int = 250,
        strict_mode: bool = True,
        prompt_injection_filter: bool = True,
    ):
        self.config_path = Path(config_path)
        self.max_message_length = max_message_length
        self.strict_mode = bool(strict_mode)
        self.prompt_injection_filter = bool(prompt_injection_filter)
        self.banned_words: List[str] = []
        self.banned_patterns: List[re.Pattern] = []
        self.replacement = "[CENSORED]"
        self.load_rules()

    def update_config(
        self,
        strict_mode: Optional[bool] = None,
        max_message_length: Optional[int] = None,
        prompt_injection_filter: Optional[bool] = None,
    ):
        if strict_mode is not None:
            self.strict_mode = bool(strict_mode)
        if max_message_length is not None:
            self.max_message_length = max(50, min(2000, int(max_message_length)))
        if prompt_injection_filter is not None:
            self.prompt_injection_filter = bool(prompt_injection_filter)

    def get_status(self) -> dict:
        return {
            "strict_mode": self.strict_mode,
            "prompt_injection_filter": self.prompt_injection_filter,
            "max_message_length": self.max_message_length,
            "banned_words_count": len(self.banned_words),
            "banned_patterns_count": len(self.banned_patterns),
            "replacement": self.replacement,
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
        if self.prompt_injection_filter:
            for p in _PROMPT_INJECTION_PATTERNS:
                if p.search(text):
                    violations.append(f"Prompt injection pattern: '{p.pattern}'")
        if len(text) > self.max_message_length:
            violations.append(f"Exceeded length limit ({len(text)} > {self.max_message_length})")
        is_blocked = bool(self.strict_mode and not is_safe)
        return {
            "is_safe": is_safe,
            "is_blocked": is_blocked,
            "sanitized": sanitized,
            "violations": violations,
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

    @staticmethod
    def sanitize_metadata(value: Any, max_len: int = 64) -> str:
        """Sanitize metadata fields (user, donation_amount, visual OCR) against control chars and injection delimiters."""
        if value is None:
            return ""
        cleaned = _CONTROL_CHARS_RE.sub(" ", str(value))
        cleaned = _INJECTION_TOKENS_RE.sub("", cleaned)
        cleaned = _VISUAL_DELIMITER_RE.sub("", cleaned)
        for pattern in _PROMPT_INJECTION_PATTERNS:
            cleaned = pattern.sub("[FILTERED]", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if max_len > 0 and len(cleaned) > max_len:
            cleaned = cleaned[:max_len].rstrip()
        return cleaned

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

        # Check prompt-injection patterns
        if self.prompt_injection_filter:
            for pattern in _PROMPT_INJECTION_PATTERNS:
                if pattern.search(text):
                    is_safe = False
                    text = pattern.sub(self.replacement, text)

        return is_safe, text

    def should_drop(self, text: str) -> bool:
        """Return True when strict_mode is enabled and the message is flagged unsafe."""
        is_safe, _ = self.clean_text(text)
        return bool(self.strict_mode and not is_safe)

    def moderate_message(
        self,
        text: str,
        user: Any = "",
        donation_amount: Any = "",
    ) -> dict:
        """Evaluate message safety and sanitize user/donation metadata."""
        is_safe, sanitized = self.clean_text(text)
        is_blocked = bool(self.strict_mode and not is_safe)
        return {
            "is_safe": is_safe,
            "is_blocked": is_blocked,
            "should_drop": is_blocked,
            "sanitized_text": "" if is_blocked else sanitized,
            "user": self.sanitize_metadata(user, max_len=64),
            "donation_amount": self.sanitize_metadata(donation_amount, max_len=32),
        }
