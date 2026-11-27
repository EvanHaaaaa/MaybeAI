import asyncio
import hashlib
import json
import math
import os
import re
import urllib.request
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "it", "its", "this", "that", "these", "those", "and", "or", "but",
    "yang", "di", "ke", "dari", "dan", "atau", "ini", "itu", "ya", "aja",
})


class EmbeddingEngine:
    """
    Multi-backend dense vector embedding engine for MaybeAI Episodic Memory.

    Supported providers:
    - "auto":   local (sentence-transformers / fastembed) -> gemini -> openai -> hash
                (skips remote cloud calls when MAYBEAI_LLM_PROVIDER == "mock")
    - "local":  sentence-transformers or fastembed if installed, else falls back to hash
    - "gemini": Google Gemini text-embedding-004 via REST (x-goog-api-key header)
    - "openai": OpenAI text-embedding-3-small via REST
    - "hash":   Deterministic semantic-normalized multi-scale feature hashing (offline, zero deps)

    Supports both synchronous `encode(text)` (with LRU cache) and async `aencode(text)`.
    """

    DIMENSION = 128
    VALID_PROVIDERS = ("auto", "local", "gemini", "openai", "hash")

    def __init__(
        self,
        dimension: int = 128,
        provider: str = "auto",
        model_name: Optional[str] = None,
        cache_size: int = 512,
        timeout: float = 10.0,
    ):
        self.dimension = int(dimension)
        self.requested_provider = (provider or "auto").lower().strip()
        if self.requested_provider not in self.VALID_PROVIDERS:
            self.requested_provider = "auto"
        self.model_name = model_name
        self.cache_size = max(16, int(cache_size))
        self.timeout = float(timeout)

        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache_hits = 0
        self._cache_misses = 0

        self._local_model: Any = None
        self._local_kind: Optional[str] = None  # "sentence_transformers" | "fastembed"
        self.active_backend: str = "hash"
        self.last_encode_was_fallback: bool = False
        self._session: Any = None

        self._resolve_backend()

    async def _get_session(self):
        """Lazily creates and reuses a shared aiohttp ClientSession on the active event loop."""
        import aiohttp

        loop = asyncio.get_running_loop()
        if self._session is not None and getattr(self._session, "closed", False) is not True:
            session_loop = getattr(self._session, "_loop", None)
            if session_loop is not None and (session_loop.is_closed() or session_loop is not loop):
                try:
                    await self._session.close()
                except Exception:
                    pass
                self._session = None
        if self._session is None or getattr(self._session, "closed", False) is True:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Closes the shared aiohttp ClientSession if it is open."""
        if self._session is not None and getattr(self._session, "closed", False) is not True:
            await self._session.close()
        self._session = None

    async def aclose(self) -> None:
        """Async alias for close()."""
        await self.close()

    def _is_mock_llm_mode(self) -> bool:
        return os.getenv("MAYBEAI_LLM_PROVIDER", "").lower().strip() == "mock"

    def _try_init_local(self) -> bool:
        if self._local_model is not None:
            return True

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            model_id = self.model_name or "all-MiniLM-L6-v2"
            self._local_model = SentenceTransformer(model_id)
            self._local_kind = "sentence_transformers"
            dim = getattr(self._local_model, "get_sentence_embedding_dimension", lambda: None)()
            if isinstance(dim, int) and dim > 0:
                self.dimension = dim
            return True
        except Exception:
            pass

        try:
            from fastembed import TextEmbedding  # type: ignore

            model_id = self.model_name or "BAAI/bge-small-en-v1.5"
            self._local_model = TextEmbedding(model_name=model_id)
            self._local_kind = "fastembed"
            self.dimension = 384
            return True
        except Exception:
            pass

        return False

    def _resolve_backend(self) -> None:
        env_override = os.getenv("MAYBEAI_EMBEDDING_PROVIDER", "").lower().strip()
        choice = self.requested_provider
        if choice == "auto" and env_override in self.VALID_PROVIDERS:
            choice = env_override

        if choice == "hash":
            self.active_backend = "hash"
            return

        if choice == "local":
            if self._try_init_local():
                self.active_backend = "local"
            else:
                self.active_backend = "hash"
            return

        if choice == "gemini":
            if os.getenv("GEMINI_API_KEY"):
                self.active_backend = "gemini"
            else:
                self.active_backend = "hash"
            return

        if choice == "openai":
            if os.getenv("OPENAI_API_KEY"):
                self.active_backend = "openai"
            else:
                self.active_backend = "hash"
            return

        # "auto" resolution: local -> gemini -> openai -> hash
        if self._try_init_local():
            self.active_backend = "local"
            return

        # Never make cloud embedding calls in mock LLM mode unless explicitly requested
        if not self._is_mock_llm_mode():
            if os.getenv("GEMINI_API_KEY"):
                self.active_backend = "gemini"
                return
            if os.getenv("OPENAI_API_KEY"):
                self.active_backend = "openai"
                return

        self.active_backend = "hash"

    def set_provider(self, provider: str) -> str:
        """Hot-reloads the embedding backend and clears the vector cache."""
        p = (provider or "auto").lower().strip()
        if p not in self.VALID_PROVIDERS:
            p = "auto"
        self.requested_provider = p
        self._resolve_backend()
        self.clear_cache()
        return self.active_backend

    def get_status(self) -> Dict[str, Any]:
        return {
            "requested_provider": self.requested_provider,
            "active_backend": self.active_backend,
            "dimension": self.dimension,
            "cache_entries": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
        }

    def clear_cache(self) -> None:
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    def _cache_get(self, key: str) -> Optional[np.ndarray]:
        vec = self._cache.get(key)
        if vec is not None:
            self._cache.move_to_end(key)
            self._cache_hits += 1
            return vec.copy()
        self._cache_misses += 1
        return None

    def _cache_put(self, key: str, vec: np.ndarray) -> None:
        self._cache[key] = vec.copy()
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    # --- Normalization & Feature Hashing Backend ---

    @staticmethod
    def _l2_normalize(vec: np.ndarray) -> np.ndarray:
        arr = np.asarray(vec, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(arr))
        if norm > 1e-6:
            arr = arr / norm
        return arr

    def _clean_and_tokenize(self, text: str) -> List[str]:
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        tokens = [t for t in cleaned.split() if len(t) > 1]
        return tokens

    def _extract_weighted_features(self, text: str) -> List[Tuple[str, float]]:
        tokens = self._clean_and_tokenize(text)
        if not tokens:
            return []

        content_tokens = [t for t in tokens if t not in _STOP_WORDS] or tokens
        features: List[Tuple[str, float]] = []

        # 1. Word unigrams (content words weighted higher than stopwords)
        for token in tokens:
            weight = 2.0 if token not in _STOP_WORDS else 0.35
            features.append((f"w:{token}", weight))
            # Basic morphological stem prefix for longer words (helps inflectional matching)
            if len(token) >= 5 and token not in _STOP_WORDS:
                features.append((f"s:{token[:5]}", 0.8))

        # 2. Word bigrams over content tokens
        for i in range(len(content_tokens) - 1):
            features.append((f"b:{content_tokens[i]}_{content_tokens[i+1]}", 1.4))

        # 3. Subword character trigrams for morphology & typo tolerance
        for token in content_tokens:
            if len(token) >= 3:
                for j in range(len(token) - 2):
                    features.append((f"#{token[j:j+3]}", 0.55))

        return features

    def _extract_features(self, text: str) -> List[str]:
        """Backwards-compatible feature list helper."""
        return [feat for feat, _ in self._extract_weighted_features(text)]

    def _encode_hash(self, text: str) -> np.ndarray:
        self.last_encode_was_fallback = True
        vec = np.zeros(self.dimension, dtype=np.float32)
        if not text or not text.strip():
            return vec

        weighted_features = self._extract_weighted_features(text)
        if not weighted_features:
            return vec

        # Sublinear TF accumulation per feature before signed projection
        counts: Dict[str, Tuple[int, float]] = {}
        for feat, w in weighted_features:
            if feat in counts:
                c, prev_w = counts[feat]
                counts[feat] = (c + 1, prev_w)
            else:
                counts[feat] = (1, w)

        for feat, (cnt, weight) in counts.items():
            tf = 1.0 + math.log(cnt)
            digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
            h = int.from_bytes(digest, "little")
            idx = (h >> 1) % self.dimension
            sign = 1.0 if (h & 1) else -1.0
            vec[idx] += sign * weight * tf

        return self._l2_normalize(vec)

    # --- Local ML Backend ---

    def _encode_local(self, text: str) -> np.ndarray:
        if not self._try_init_local():
            return self._encode_hash(text)
        try:
            if self._local_kind == "sentence_transformers":
                raw = self._local_model.encode(text, normalize_embeddings=True)
                vec = self._l2_normalize(raw)
                self.dimension = int(vec.shape[0])
                return vec
            elif self._local_kind == "fastembed":
                raw = next(iter(self._local_model.embed([text])))
                vec = self._l2_normalize(raw)
                self.dimension = int(vec.shape[0])
                return vec
        except Exception:
            pass
        return self._encode_hash(text)

    # --- Gemini REST Backend ---

    def _gemini_request_parts(self, text: str) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        model = self.model_name or "text-embedding-004"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }
        payload = {
            "model": f"models/{model}",
            "content": {"parts": [{"text": text}]},
        }
        return url, headers, payload

    def _encode_gemini_sync(self, text: str) -> np.ndarray:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            return self._encode_hash(text)
        url, headers, payload = self._gemini_request_parts(text)
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            values = data.get("embedding", {}).get("values")
            if values:
                vec = self._l2_normalize(np.array(values, dtype=np.float32))
                self.dimension = int(vec.shape[0])
                return vec
        except Exception:
            pass
        return self._encode_hash(text)

    async def _encode_gemini_async(self, text: str) -> np.ndarray:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            return self._encode_hash(text)
        url, headers, payload = self._gemini_request_parts(text)
        try:
            session = await self._get_session()
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    values = data.get("embedding", {}).get("values")
                    if values:
                        vec = self._l2_normalize(np.array(values, dtype=np.float32))
                        self.dimension = int(vec.shape[0])
                        return vec
        except Exception:
            pass
        return self._encode_hash(text)

    # --- OpenAI REST Backend ---

    def _openai_request_parts(self, text: str) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = self.model_name or "text-embedding-3-small"
        url = "https://api.openai.com/v1/embeddings"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "input": text,
        }
        return url, headers, payload

    def _encode_openai_sync(self, text: str) -> np.ndarray:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return self._encode_hash(text)
        url, headers, payload = self._openai_request_parts(text)
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = data.get("data", [])
            if items and "embedding" in items[0]:
                vec = self._l2_normalize(np.array(items[0]["embedding"], dtype=np.float32))
                self.dimension = int(vec.shape[0])
                return vec
        except Exception:
            pass
        return self._encode_hash(text)

    async def _encode_openai_async(self, text: str) -> np.ndarray:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return self._encode_hash(text)
        url, headers, payload = self._openai_request_parts(text)
        try:
            session = await self._get_session()
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    items = data.get("data", [])
                    if items and "embedding" in items[0]:
                        vec = self._l2_normalize(np.array(items[0]["embedding"], dtype=np.float32))
                        self.dimension = int(vec.shape[0])
                        return vec
        except Exception:
            pass
        return self._encode_hash(text)

    # --- Public Encode APIs ---

    def encode(self, text: str) -> np.ndarray:
        """
        Synchronously encodes text into an L2-normalized float32 dense vector with LRU caching.
        """
        if not text or not text.strip():
            return np.zeros(self.dimension, dtype=np.float32)

        cache_key = f"{self.active_backend}:{text}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if self.active_backend == "local":
            self.last_encode_was_fallback = False
            vec = self._encode_local(text)
        elif self.active_backend == "gemini":
            self.last_encode_was_fallback = False
            vec = self._encode_gemini_sync(text)
        elif self.active_backend == "openai":
            self.last_encode_was_fallback = False
            vec = self._encode_openai_sync(text)
        else:
            self.last_encode_was_fallback = True
            vec = self._encode_hash(text)

        self._cache_put(cache_key, vec)
        return vec

    async def aencode(self, text: str) -> np.ndarray:
        """
        Asynchronously encodes text into an L2-normalized float32 dense vector with LRU caching.
        """
        if not text or not text.strip():
            return np.zeros(self.dimension, dtype=np.float32)

        cache_key = f"{self.active_backend}:{text}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if self.active_backend == "local":
            self.last_encode_was_fallback = False
            vec = await asyncio.to_thread(self._encode_local, text)
        elif self.active_backend == "gemini":
            self.last_encode_was_fallback = False
            vec = await self._encode_gemini_async(text)
        elif self.active_backend == "openai":
            self.last_encode_was_fallback = False
            vec = await self._encode_openai_async(text)
        else:
            self.last_encode_was_fallback = True
            vec = self._encode_hash(text)

        self._cache_put(cache_key, vec)
        return vec

    def cosine_similarity(self, vec_a: Optional[np.ndarray], vec_b: Optional[np.ndarray]) -> float:
        """
        Calculates cosine similarity between two vectors.
        Returns 0.0 safely on None, zero-norm, or mismatched vector dimensions.
        """
        if vec_a is None or vec_b is None:
            return 0.0
        a = np.asarray(vec_a, dtype=np.float32).reshape(-1)
        b = np.asarray(vec_b, dtype=np.float32).reshape(-1)
        if a.size == 0 or b.size == 0 or a.shape != b.shape:
            return 0.0
        norm_a = float(np.linalg.norm(a))
        norm_b = float(np.linalg.norm(b))
        if norm_a < 1e-6 or norm_b < 1e-6:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def serialize(self, vec: np.ndarray) -> bytes:
        """Serializes vector into binary bytes for SQLite BLOB storage."""
        return np.asarray(vec, dtype=np.float32).tobytes()

    def deserialize(self, blob: bytes) -> np.ndarray:
        """Deserializes SQLite BLOB bytes into a float32 NumPy vector."""
        if not blob:
            return np.zeros(self.dimension, dtype=np.float32)
        if len(blob) % 4 != 0:
            return np.zeros(self.dimension, dtype=np.float32)
        return np.frombuffer(blob, dtype=np.float32).copy()
