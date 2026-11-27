# MaybeAI — Experiment Results & Verified Baseline (`research/EXPERIMENT_RESULTS.md`)

**Owner:** AGENT 10 (`ng-strat-research`) — AI Research & Emerging Technology Architect  
**Grounding Baseline:** Post-Horizon 3 + YouTube Karaoke (`HEAD 96b7315`) — [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md), [11_chaos_testing.md](file:///d:/projects/MaybeAI/audit/11_chaos_testing.md), [12_performance_analysis.md](file:///d:/projects/MaybeAI/audit/12_performance_analysis.md)

> [!IMPORTANT]
> **Measurement Discipline:** Section 1 and Section 2 record **directly observed measurements** from the post-H3 audit and chaos/performance probes. Section 3 records **pending target gates** (estimates/acceptance thresholds) for Horizons 4–8 experiments `EXP-004`–`EXP-006`.

---

## 1. Verified Post-H3 Baseline Measurements (`HEAD 96b7315`)

### 1.1 Automated Test & Static Check Baseline
- **Python `unittest` Suite:** `381` test cases across `43` modules — **`380` passed, `1` skipped** (`TestPlaywrightBrowserE2E` skipped because `playwright` is not installed) in `34.964s` (`audit/09_qa_reliability.md`).
- **JavaScript / Node Checks:** `node tests/test_guard_runner.js` **PASS**; `node --check` on all `7` JS/Worklet/Bot files **PASS**.
- **Runtime Warnings (`-W default`):** Multiple `asyncio` slow callbacks (`0.109s–0.282s`) and `ResourceWarning`s (unclosed `aiohttp.ClientSession`/connector, socket/ProactorSocketTransport, subprocess in test teardowns).

### 1.2 WebSocket Fan-Out Scaling (Observed Probe)
Measured in isolated async probe (`20` broadcasts of `Events.AI_RESPONSE` via `EventBus.publish` + `asyncio.gather`, `audit/12_performance_analysis.md`):

| Concurrent WS Listeners | 20 Broadcasts Total (ms) | Per-Broadcast Avg (ms) | Delivered Events | Bottleneck Note (Observed) |
|---:|---:|---:|---:|---|
| `10` | `1.48` | **`0.074`** | `200` | — |
| `50` | `3.11` | **`0.155`** | `1,000` | — |
| `100` | `5.23` | **`0.262`** | `2,000` | — |
| `500` | `43.18` | **`2.159`** | `10,000` | Single stalled client caps at `2.0s` (`orchestrator.py:438`) due to missing per-WS outbound `asyncio.Queue(64)`. |

### 1.3 SQLite & Vector Scan Scaling (Observed Probe)
Measured on `MemoryDatabase` (`PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`, `vector_scan_limit=2000`, `audit/12_performance_analysis.md`):

| Stored Episodic Memories (N) | `vector_search` Latency (ms) | Scaling Behavior |
|---:|---:|---|
| `100` | **`13.54`** | Brute-force Python/NumPy cosine scan |
| `500` | **`14.89`** | Brute-force Python/NumPy cosine scan |
| `1,000` | **`23.08`** | Brute-force Python/NumPy cosine scan |
| `2,000` | **`45.32`** | Hits `vector_scan_limit=2000` cap; rows `>2,000` invisible to dense vector scan |

### 1.4 Subsystem Microbenchmarks & Chaos Probes (Scenarios A–H)
Verified in `audit/11_chaos_testing.md` and `audit/12_performance_analysis.md`:
- **Scenario A (EventBus Storm & Interruption):** `50` rapid Twitch messages + `DONATION_RECEIVED` + `SONG_STARTED` + `VOICE_BARGE_IN` processed in **`0.28 ms`** with `0` handler errors (`history_len: 53`, `max_pending_tasks=256`). **PASS**.
- **Scenario B (Collab Disconnect):** `CollabManager.disconnect_peer()` cleanly closes `_ws_client`/`_http_session`, but **leaves `floor_state="listening"` and `active_peer` non-null** (`REPRODUCED` gap). **PARTIAL**.
- **Scenario C (Malicious Viewer & Metadata):** `Moderator.clean_text` averaged **`0.006 ms/msg`** (`3.19 ms` for `500` messages); blocked prompt injection (`3` violations) and stripped `<|im_start|>`/control chars in `sanitize_metadata()`. **PASS**.
- **Scenario D (Embedding Switch Mid-Stream):** Querying 128-d `hash` against 384-d stored vectors returned `0` vector hits without crashing and preserved all `[384, 384, 384, 384, 384]` blobs. **PASS**.
- **Scenario E (8–12h Stream Soak):** Bounded buffers (`EventBus(200)`, `MetricsCollector(1000)`, `ContextMemory(16)`, `ChatCurator(50)`) confirmed; stdout-only `print()` (no `RotatingFileHandler`) and `aiohttp` `ResourceWarning`s remain. **PARTIAL** (Feasible with Docker log rotation).
- **Scenario F (Plugin Failure):** External `ChaosPlugin` ran in `os_isolated` (`windows_job_object`), rejected invalid `fs:read` permission, timed out `!slow`/`!hang` at `0.1s`/`0.3s`, and isolated `!boom` `RuntimeError`. **PASS**.
- **Scenario G (Provider Circuit Breaker):** `ProviderCircuitBreaker` transitioned `closed` -> `open` (3 failures) -> `half_open` -> `closed` cleanly. **PASS**.
- **Scenario H (High Audience Load):** `500`-listener WS fan-out `2.159 ms`/broadcast; `2,000`-row vector scan `45.32 ms`. **PASS**.

---

## 2. Post-H3 Status of Earlier R&D (`EXP-001`..`EXP-003`)

| Experiment | Landed in H1–H3 (`VERIFIED`) | Remaining Gaps (`INCOMPLETE` / `EXPERIMENTAL`) |
|---|---|---|
| **EXP-001** (Duplex Voice & Lip-Sync) | 16 kHz `AudioWorklet` binary PCM, non-blocking `_voice_worker`, `EnergyVAD` barge-in, `speak_stream()` `CancelledError`, 50ms RMS envelope + browser `isLocalAudioPlaying` arbitration, `ProviderCircuitBreaker`. | `faster-whisper`, `kokoro_onnx`, `silero-vad` absent in `.venv` (`EXPERIMENTAL`); `StreamingSTTSession` emits hardcoded `"Listening..."` partials; `ClientTimeout(total=1.8)` truncates >1.8s LLM streams (`AUDIO-MED-001`); `TTSEngine.speak()` swallows `CancelledError` (`AUDIO-MED-002`). |
| **EXP-002** (Memory & Prompt Budgeting) | `ContextBudgetManager` (`1600–1800` tokens), `is_creator` end-to-end plumbing, `MoodEngine.get_temperature_modifier()`, shared `EmbeddingEngine`, 128-d overwrite guard (`Chaos D`), SQLite FTS5. | `vector_scan_limit=2000` linear scan (`45.32 ms`) still active (no `sqlite-vec`/`hnswlib` ANN); `promises.md` fulfillment/archival methods uncalled; no hierarchical consolidation. |
| **EXP-003** (Closed-Loop Agency) | `Goal.recalculate_progress()` excludes `REPLANNED`, `MAX_REPLAN_ATTEMPTS=3`, `approval_timeout_sec=300`, `bot.js` timer cleanup + `EADDRINUSE` exit, `MinecraftController` disconnect reset. | `Goal.reflection` write-only; `StrategyReplanner` keyword-templated; `startAutonomyLoop()` uncalled; no MC/OBS auto-reconnect loop. |

---

## 3. Pending Gate Criteria for Next-Gen Experiments (`EXP-004`–`EXP-006`)

All thresholds below are **Target Gates (Estimates)** to be measured in isolated harnesses before promoting to `core/`:

| Experiment | Target Domain | Key Pending Gate Criteria |
|---|---|---|
| **EXP-004** | Hierarchical Memory & Causal Reflection | `Recall@5 >= 0.80` on aged rows (`>2000`); `arecall() <= 15 ms` p95 at `10,000` rows (vs `45.32 ms` @ `2,000` baseline); `>= 25%` reduction in repeated failed strategies via `Goal.reflection`; `100%` `promises.md` lifecycle closure. |
| **EXP-005** | Multi-Peer Agent Orchestration (`N<=4`) | `0` stuck `floor_state` across `50` forced peer disconnects (vs `Chaos B` fail); `<20 ms` LAN sync frame propagation; `<= 1%` turn-collision rate across `3`-peer `30`-min soak; automated `duet_sync`/`emote_sync`/`game_move` emission. |
| **EXP-006** | Dedicated Inference Worker | `0` main event-loop slow callbacks `>50 ms` (vs `0.109s–0.282s` baseline); `/ws` ack p99 `<= 15 ms` during concurrent STT+TTS+Embedding burst; worker crash auto-recovery `<= 3 s` with `0` dropped `/ws` clients. |
