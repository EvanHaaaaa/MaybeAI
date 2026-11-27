import hashlib
import hmac
import json
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


PROTOCOL_VERSION = "1.0"

VALID_COLLAB_EVENT_TYPES: Tuple[str, ...] = (
    "hello",
    "turn_utterance",
    "turn_yield",
    "duet_sync",
    "game_move",
    "emote_sync",
    "ping",
    "bye",
)

DEFAULT_COLLAB_CAPABILITIES: Tuple[str, ...] = (
    "turn_utterance",
    "turn_yield",
    "duet_sync",
    "emote_sync",
    "game_move",
)

NON_UTTERANCE_EVENT_TYPES: Tuple[str, ...] = (
    "hello",
    "duet_sync",
    "emote_sync",
    "game_move",
    "ping",
)


@dataclass
class CollabEnvelope:
    """
    Signed wire-protocol envelope exchanged between cooperating AI VTubers.
    Supports HMAC-SHA256 authentication with constant-time verification.
    """

    protocol_version: str = PROTOCOL_VERSION
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    sender_id: str = ""
    sender_name: str = ""
    event_type: str = "turn_utterance"
    speech: str = ""
    emotion: str = "neutral"
    topic: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    turn_index: int = 0
    timestamp: float = field(default_factory=time.time)
    signature: str = ""

    def __post_init__(self) -> None:
        if self.event_type not in VALID_COLLAB_EVENT_TYPES:
            raise ValueError(
                f"Unsupported collab event_type '{self.event_type}'. "
                f"Expected one of {VALID_COLLAB_EVENT_TYPES}."
            )
        if not isinstance(self.payload, dict):
            raise ValueError("CollabEnvelope.payload must be a dict.")
        if not self.message_id:
            self.message_id = uuid.uuid4().hex

    def _canonical_bytes(self) -> bytes:
        canonical = {
            "protocol_version": str(self.protocol_version),
            "message_id": str(self.message_id),
            "sender_id": str(self.sender_id),
            "sender_name": str(self.sender_name),
            "event_type": str(self.event_type),
            "speech": str(self.speech),
            "emotion": str(self.emotion),
            "topic": str(self.topic),
            "payload": self.payload,
            "turn_index": int(self.turn_index),
            "timestamp": float(self.timestamp),
        }
        return json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    def sign(self, secret: str) -> str:
        """
        Signs the envelope using HMAC-SHA256 when `secret` is non-empty.
        When `secret` is empty, clears `signature` and returns "".
        """
        if not secret:
            self.signature = ""
            return ""
        digest = hmac.new(
            secret.encode("utf-8"),
            self._canonical_bytes(),
            hashlib.sha256,
        ).hexdigest()
        self.signature = digest
        return digest

    def verify(self, secret: str, allow_unsigned: bool = False) -> bool:
        """
        Verifies the envelope signature using constant-time `hmac.compare_digest`.
        When `secret` is empty, unsigned frames are accepted only if `allow_unsigned` is True.
        """
        if not secret:
            return bool(allow_unsigned) and not bool(self.signature)
        if not self.signature or not isinstance(self.signature, str):
            return False
        expected = hmac.new(
            secret.encode("utf-8"),
            self._canonical_bytes(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(self.signature, expected)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "event_type": self.event_type,
            "speech": self.speech,
            "emotion": self.emotion,
            "topic": self.topic,
            "payload": dict(self.payload),
            "turn_index": int(self.turn_index),
            "timestamp": float(self.timestamp),
            "signature": self.signature,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @staticmethod
    def _validate_finite_floats(value: Any, field_name: str = "payload") -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"Non-finite float (NaN/Infinity) is not allowed in '{field_name}'.")
        if isinstance(value, dict):
            for k, v in value.items():
                CollabEnvelope._validate_finite_floats(v, f"{field_name}.{k}")
        elif isinstance(value, (list, tuple)):
            for idx, item in enumerate(value):
                CollabEnvelope._validate_finite_floats(item, f"{field_name}[{idx}]")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CollabEnvelope":
        if not isinstance(data, dict):
            raise ValueError("Collab envelope payload must be a JSON object.")
        event_type = str(data.get("event_type", "")).strip()
        if event_type not in VALID_COLLAB_EVENT_TYPES:
            raise ValueError(
                f"Invalid collab event_type '{event_type}'. "
                f"Expected one of {VALID_COLLAB_EVENT_TYPES}."
            )
        payload = data.get("payload")
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise ValueError("Collab envelope 'payload' must be an object.")
        cls._validate_finite_floats(payload, "payload")

        raw_ts = data.get("timestamp")
        if raw_ts is None:
            timestamp = time.time()
        else:
            if isinstance(raw_ts, bool):
                raise ValueError("Collab envelope 'timestamp' must be a finite number.")
            timestamp = float(raw_ts)
            if not math.isfinite(timestamp):
                raise ValueError("Collab envelope 'timestamp' must be finite (NaN/Infinity rejected).")

        raw_turn = data.get("turn_index")
        if raw_turn is None:
            turn_index = 0
        else:
            if isinstance(raw_turn, bool):
                raise ValueError("Collab envelope 'turn_index' must be an integer.")
            if isinstance(raw_turn, float) and not math.isfinite(raw_turn):
                raise ValueError("Collab envelope 'turn_index' must be finite.")
            turn_index = int(raw_turn)

        return cls(
            protocol_version=str(data.get("protocol_version", PROTOCOL_VERSION)),
            message_id=str(data.get("message_id") or uuid.uuid4().hex),
            sender_id=str(data.get("sender_id", "")),
            sender_name=str(data.get("sender_name", "")),
            event_type=event_type,
            speech=str(data.get("speech", "")),
            emotion=str(data.get("emotion", "neutral")),
            topic=str(data.get("topic", "")),
            payload=dict(payload),
            turn_index=turn_index,
            timestamp=timestamp,
            signature=str(data.get("signature", "")),
        )
