# 11 — Performance, Latency & Soak-Test Analysis

**Auditor:** AGENT 8 (`cto-qa`) — QA & Production Reliability Auditor  
**Scope:** End-to-end voice/chat latency budgets, memory & CPU hotspots, asyncio event-loop blocking risks, WebSocket/EventBus throughput, and long-running soak-test risk assessment.

---

## 1. End-to-End Latency Budgets (Observed Architecture)

### Voice / Chat Turn Pipeline (`Chat/Mic -> LLM -> SentenceChunker -> TTS -> Browser/VTS`)
1. **Input Ingestion:**
   - `ChatReceiver` / `YouTubeLiveAdapter` / `Discord` / `/ws` `voice_chunk` -> `EventBus` (`0.1–2ms`).
2. **Semantic Memory Retrieval (`core/memory/embedding.py`):**
   - Local hash fallback: `<1ms`.
   - `_encode_gemini_async()` (`core/memory/embedding.py:320-340`): Creates a **new `aiohttp.ClientSession`** per embedding call rather than reusing a persistent session pool (`[PERF-MED-001]`), adding TCP+TLS handshake overhead (~50–150ms) per memory lookup.
3. **LLM Streaming + Pipelined TTS (`core/tts.py:465-587`):**
   - `SentenceChunker` buffers tokens into sentence boundaries so sentence $N+1$ synthesizes concurrently while sentence $N$ plays (`AudioQueue(maxsize=4)` provides bounded backpressure).
   - **Disk I/O Hotspot (`[PERF-MED-002]`):** `_enqueue_sentence()` (`core/tts.py:503-509`) writes synthesized bytes to a temp `.mp3` file (`Path(out_file).write_bytes(audio_bytes)`) and `_consumer()` (`core/tts.py:561`) reads the entire file back from disk (`Path(file_path).read_bytes()`) even when `output_mode == "browser"` (where `pygame.mixer` disk playback isn't even needed).
4. **WebSocket & Avatar Broadcast (`core/orchestrator.py:368-370`, `run.py:804-813`):**
   - Every `/ws` client registers a wildcard `*` listener on `EventBus`. During TTS lip-sync (`mouth_open`) and streaming `ai_chunk` tokens, `EventBus.publish()` fires at ~10–30+ events/sec across all connected clients.

---

## 2. Event-Loop Blocking & Throughput Hotspots

### `[PERF-HIGH-001]` Sequential `EventBus.publish()` With No Per-Subscriber Timeout (Head-of-Line Blocking)
- **Severity:** High
- **Evidence Classification:** `REPRODUCED` (Chaos Scenario A1)
- **Location:** `core/event_bus.py:193-201`, `run.py:804-813`
- **Symptom:** `EventBus.publish()` iterates `for handler in handlers:` and `await res` **sequentially** without `asyncio.wait_for`.
- **Impact:** Any slow subscriber (e.g., a stalled `/ws` client TCP send buffer in `run.py:809`, a slow plugin `on_event` hook, or a slow async callback) blocks all subsequent subscribers **and** stalls the `await orchestrator.broadcast(...)` caller (freezing TTS lip-sync, barge-in broadcasts, and LLM chunk delivery).
- **Recommended Fix:** Dispatch subscribers concurrently with `asyncio.gather(..., return_exceptions=True)` wrapped in a bounded per-handler timeout (or per-WS-client bounded `asyncio.Queue` with drop-oldest/disconnect on full).

### `[PERF-MED-001]` Per-Call `aiohttp.ClientSession` Allocation in `_encode_gemini_async`
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED` (code inspection `core/memory/embedding.py:328-330`)
- **Location:** `core/memory/embedding.py:320-340`
- **Symptom:** Every async Gemini embedding call instantiates and closes a fresh `aiohttp.ClientSession`, forfeiting HTTP/1.1 keep-alive connection pooling and adding TLS handshake latency.
- **Recommended Fix:** Reuse a lazy, lifecycle-managed `aiohttp.ClientSession` on the embedder instance.

### `[PERF-MED-002]` Synchronous Disk Write/Read Roundtrip on Browser-Only TTS
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED` (code inspection `core/tts.py:503-509, 558-566`)
- **Location:** `core/tts.py:503-509`, `core/tts.py:558-566`
- **Symptom:** `Path(out_file).write_bytes(...)` and `Path(file_path).read_bytes()` execute synchronously on the asyncio event loop for every sentence, even in `output_mode="browser"` where audio is forwarded as bytes via `on_audio_ready`.
- **Recommended Fix:** Pass in-memory `audio_bytes` directly to `on_audio_ready` in `browser` mode, and offload disk writes/reads to `asyncio.to_thread` when `server`/`both` mode requires a file path.

### `[PERF-LOW-001]` Synchronous `urllib.request.urlopen` Fallback in `embedding.py`
- **Severity:** Low (conditional)
- **Evidence Classification:** `VERIFIED` (code inspection `core/memory/embedding.py:303-310`)
- **Location:** `core/memory/embedding.py:297-318`
- **Symptom:** `_encode_gemini_sync()` uses blocking `urllib.request.urlopen(..., timeout=self.timeout)`. Safe if invoked only from sync/worker threads, but will freeze the event loop if called directly from an `async def` coroutine.

### `[PERF-LOW-002]` Unbounded Task Creation in `EventBus.publish_nowait`
- **Severity:** Low
- **Evidence Classification:** `VERIFIED` (code inspection `core/event_bus.py:211-214`, Chaos Scenario A2)
- **Location:** `core/event_bus.py:211-214`
- **Symptom:** `publish_nowait` calls `loop.create_task(self.publish(...))` without tracking or bounding concurrent in-flight tasks. Under sustained high-frequency bursts, task objects accumulate in memory if subscribers are slow.

---

## 3. Soak-Test Risk Assessment (Multi-Hour Live Stream)

| Subsystem | Bounded? | Soak Risk | Mechanism / Observation |
|---|---|---|---|
| `EventBus._history` | **Yes** (`deque(maxlen=200)`) | Low | Ring buffer prevents unbounded event history growth (verified in Scenario A2). |
| `CollabManager.history` | **Yes** (`deque(maxlen=50)`) | Low | Bounded to 50 recent messages. |
| `TTSEngine` temp `.mp3` files | **Yes** (`finally:` cleanup) | Low | Verified `0` disk leftovers after barge-in in Scenario B1. |
| `EventBus._subscribers` (`/ws` listeners) | **Depends on disconnect** | Medium | If a `/ws` client hangs half-open without raising on `send_json`, `publish()` stalls until OS TCP timeout (`[PERF-HIGH-001]`). |
| `MinecraftController` bridge | **No auto-reconnect** | High | A single Node.js bridge drop leaves `connection_status="connected"` indefinitely until manual intervention (`[QA-HIGH-002]`). |
| `PluginRegistry._subprocesses` | **Leaks dead entry on crash** | Medium | Crashed worker entry remains in `_subprocesses` until reload (`[QA-MED-001]`). |
