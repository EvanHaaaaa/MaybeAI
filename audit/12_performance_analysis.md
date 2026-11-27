# Post-Implementation Audit — 12: Performance & Scalability Analysis

**Auditor:** `ng-qa` (Agent 8)  
**Scope:** Latency budgets, EventBus/WS fan-out bottlenecks, memory/SQLite/vector scan scaling, and 8–12h stream soak feasibility.

---

## 1. Latency Budgets & Runtime Instrumentation

[MetricsCollector](file:///d:/projects/MaybeAI/core/metrics.py#L110-L197) tracks `tts_latency_ms` and `stt_latency_ms` via bounded `_HistogramTracker` (`max_samples=1000`), alongside `event_bus_published`, `event_bus_errors`, `llm_requests`, `llm_failovers`, `active_ws_clients`, `bg_tasks_active`, and `rss_mb`.

| Stage | Target Budget (Interactive VTuber) | Observed / Guardrail |
|---|---|---|
| Moderation (`Moderator.clean_text`) | `< 5 ms` | `0.006 ms/msg` (`3.19 ms` for 500 messages in probe). |
| Vector Memory Recall (`MemoryDatabase.vector_search`) | `< 50 ms` | `13.54 ms` (N=100) to `45.32 ms` (N=2000) (`vector_scan_limit=2000`). |
| EventBus + WS Fan-Out (`_dispatch_to_web_listeners`) | `< 10 ms` | `0.074 ms` (10 clients) to `2.159 ms` (500 clients) in-process. Per-client send timeout is `2.0s` ([orchestrator.py](file:///d:/projects/MaybeAI/core/orchestrator.py#L438)). |
| TTS Synthesis (`_speak_with_metrics`) | `< 800 ms` (streaming) | Instrumented in `tts_latency_ms`; Kokoro/EdgeTTS network-dependent. |
| Plugin Command/Hook | `<= 5.0s` | Enforced by `hook_timeout_sec=5.0` in [PluginRegistry](file:///d:/projects/MaybeAI/core/plugins/registry.py#L553). |

---

## 2. EventBus & WebSocket Fan-Out Scaling

Measured in isolated async probe (`20` broadcasts of `Events.AI_RESPONSE` via `EventBus.publish` + `asyncio.gather`):

| Concurrent WS Listeners | 20 Broadcasts Total (ms) | Per-Broadcast Avg (ms) | Delivered Events |
|---:|---:|---:|---:|
| 10 | `1.48` | `0.074` | `200` |
| 50 | `3.11` | `0.155` | `1,000` |
| 100 | `5.23` | `0.262` | `2,000` |
| 500 | `43.18` | `2.159` | `10,000` |

- **Bottleneck Analysis:** [Orchestrator._dispatch_to_web_listeners](file:///d:/projects/MaybeAI/core/orchestrator.py#L427-L443) uses `asyncio.gather(*(_send_one(l) for l in listeners), return_exceptions=True)` with `timeout=2.0` per listener and auto-discards failing listeners. Because `EventBus.publish` awaits all subscribers concurrently with `handler_timeout=5.0`, a single slow WS client will not block other clients beyond `2.0s`, though high-frequency `avatar_state` / `audio_chunk` broadcasts at 500+ connected browsers would saturate single-process JSON serialization and event-loop CPU. (In typical VTuber deployments, WS clients are 1–5 local/OBS overlays, not 500 browsers.)

---

## 3. SQLite & Vector Scan Scaling

Measured on `MemoryDatabase` (`PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`, `vector_scan_limit=2000`):

| Stored Episodic Memories (N) | `vector_search` Latency (ms) |
|---:|---:|
| 100 | `13.54` |
| 500 | `14.89` |
| 1,000 | `23.08` |
| 2,000 | `45.32` |

- **Scaling Verdict:** Linear `O(min(N, vector_scan_limit))` brute-force cosine scan in Python/NumPy stays under `50 ms` up to the default `vector_scan_limit=2000` cap ([database.py](file:///d:/projects/MaybeAI/core/memory/database.py#L24)). Beyond 2,000 memories, older entries are excluded from dense vector scan (though still searchable via SQLite FTS5 `fts_memories`).

---

## 4. 8–12 Hour Stream Soak Feasibility

| Subsystem | Soak Mechanism | Risk Level | Assessment |
|---|---|---|---|
| `EventBus` | `deque(maxlen=200)`, `max_pending_tasks=256` | **LOW** | Bounded memory; drops excess `publish_nowait` tasks instead of OOMing. |
| `MetricsCollector` | `_HistogramTracker(maxlen=1000)` | **LOW** | Fixed memory footprint over 12h. |
| `ConversationEngine` | `ContextMemory(max_buffer_turns=16)`, `ChatCurator(max_buffer_size=50)` | **LOW** | Bounded in-memory turn/chat buffers. |
| `TTSEngine` temp audio | `_cleanup_audio_file()` in `try/finally` & queue drain ([tts.py](file:///d:/projects/MaybeAI/core/tts.py#L642-L656)) | **LOW–MEDIUM** | Cleans up `maybeai_audio` temp files on normal/error paths; abrupt `SIGKILL` can leave orphans in OS temp dir. |
| `MemoryDatabase` (SQLite) | WAL mode, `timeout=10.0`, `vector_scan_limit=2000` | **LOW** | Per-call `sqlite3.connect` avoids long-lived connection lock contention; WAL checkpointing is automatic. |
| Logging | `print()` to stdout (no `RotatingFileHandler`) | **MEDIUM** | Redirecting stdout to a file for 12h+ without external `logrotate`/Docker log driver caps can grow disk usage unboundedly. |
| `aiohttp` / Subprocess Lifecycle | `ResourceWarning`s observed in test suite | **MEDIUM** | If external adapters reconnect repeatedly over 12h without closing old `ClientSession`s, file descriptors can accumulate. |

**Soak Verdict:** **Feasible for 8–12h supervised streams** with Docker log rotation (`max-size`/`max-file`) and `Orchestrator.shutdown()` cleanup, provided `aiohttp` session cleanup warnings are monitored via `/api/metrics` (`rss_mb`, `bg_tasks_active`).
