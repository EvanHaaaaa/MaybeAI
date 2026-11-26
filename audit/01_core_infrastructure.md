# Core Infrastructure & Distributed Concurrency Audit (`audit/01_core_infrastructure.md`)

**Auditor:** AGENT 1 — Core Infrastructure & Distributed Concurrency Auditor (`cto-infra`)  
**Execution Paths Audited:** `run.py` -> `core/orchestrator.py` -> `core/event_bus.py` -> `core/config_manager.py` -> `core/chat_receiver.py` -> `core/brain.py`  
**Baseline Test Run:** `.venv\Scripts\python.exe -m unittest tests/test_event_bus.py tests/test_configuration.py tests/test_system_integrity.py` -> **29 tests passed in 1.729s** (with asyncio slow-task warnings >100ms observed on `TestEventBusIntegration` and `TestSystemIntegrity` startup/execution).

---

## 1. Capability Maturity Classification

| Area | Classification | Evidence Summary |
|---|---|---|
| Async pub-sub `EventBus` with wildcard `*`, exception isolation, bounded history | **Current Capability** | `core/event_bus.py:124-264`; verified by `test_event_bus.py` |
| FastAPI `lifespan` startup/shutdown & WebSocket/REST routing | **Current Capability** | `run.py:34-40`; `Orchestrator.start()` / `shutdown()` |
| Atomic config save (`os.replace`) & secret masking for 6 fields | **Current Capability** | `core/config_manager.py:248-255, 1582-1588` |
| Hot-reload pipeline for Brain, TTS, VTS, Twitch, Adapters, Missions, OBS, Highlights | **Partially Implemented** | `core/orchestrator.py:712-849` (spawns untracked tasks; some settings ignored) |
| Config schema validation & concurrency-safe writes | **Partially Implemented** | `core/config_manager.py:1484-1612` (validates only 110 schema keys, skips extra `DEFAULT_SETTINGS` & unknown keys, fixed `.tmp` filename) |
| Backpressure, bounded queues, & runtime concurrency limits (`max_concurrent_tasks`, `response_timeout_sec`) | **Planned Capability** | Config keys exist in `DEFAULT_SETTINGS` (`core/config_manager.py:31, 171`) and UI schema (`1148-1168`), but have **0 references** in `run.py` and `core/orchestrator.py` |
| Per-subscriber async dispatch isolation / dead-listener eviction | **Proposed Innovation** | Currently sequential `await` in `EventBus.publish()` and silent `pass` in `_dispatch_to_web_listeners` |

---

## 2. Detailed Findings

### `[INFRA-HIGH-001]` Untracked `asyncio.create_task` Leaks & Post-Barge-In / Post-Shutdown Mouth-Update Races
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/orchestrator.py:749, 751, 759, 925, 1020, 1042, 1446, 1622, 1679, 1734, 1761, 1797, 1857` and `run.py:631`
- **Symptom:** Background tasks spawned during hot-reload (`vts.connect()`, `vts.reconnect()`, `chat.start_twitch_listener()`), on-demand vision (`_speak_visual_commentary`), donations (`minecraft.celebrate`), performance start (`perform_song`), and high-frequency TTS lip-sync (`on_mouth_update`) are not registered in `self._bg_tasks` (`_spawn_bg_task`).
- **Root Cause:** Direct calls to `asyncio.create_task(...)` bypass `Orchestrator._spawn_bg_task()` (`core/orchestrator.py:267-271`). In `shutdown()` (`core/orchestrator.py:425-430`), only `self._bg_tasks` and `self._active_interaction_task` are cancelled. For `on_mouth_update`, each TTS amplitude tick spawns a new untracked task that can execute *after* `barge_in()` or `_speak_response()` resets `mouth_open: 0.0`, and exceptions in untracked tasks are never retrieved.
- **Verification Steps:** Search `core/orchestrator.py` for `asyncio.create_task` (14 occurrences; only lines `268` and `1161` are tracked). Inspect `run.py:631` (`POST /api/performance/start`).
- **Blast Radius:** Zombie background connections (Twitch/VTS) surviving `shutdown()`, lip-sync jitter or stuck open mouth after barge-in, and uncollected task exceptions.
- **Recommended Fix:** Route all long-lived tasks through `_spawn_bg_task()`, track/await `on_mouth_update` tasks (or coalesce via a single lip-sync worker/latest-value slot), and cancel all tracked tasks cleanly in `shutdown()`.

---

### `[INFRA-HIGH-002]` `perform_song()` Bypasses `_busy_lock` When Triggered via API or Autonomous Missions
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `run.py:630-632`, `core/orchestrator.py:156, 1636-1772`
- **Symptom:** Triggering a karaoke performance via `POST /api/performance/start` (`run.py:631`) or `AutonomousMissionExecutor` (`core/orchestrator.py:156`) runs `perform_song()` concurrently with chat interactions (`_execute_interaction`) or `trigger_improv()`.
- **Root Cause:** `_execute_interaction()` acquires `self._busy_lock` before calling `perform_song()` (`core/orchestrator.py:1206`), and `_on_collab_duet_sync()` checks `not self._busy_lock.locked()` (`core/orchestrator.py:585-587`), but `perform_song()` itself does not acquire `self._busy_lock`. Both concurrent flows then contend for `_speech_lock`, mutate `self._current_emotion`, and interleave `ai_response` / `avatar_state` broadcasts.
- **Verification Steps:** Inspect `run.py:631` and `core/orchestrator.py:1636-1772`.
- **Blast Radius:** Overlapping speech/singing state, corrupted `_current_emotion` in TTS audio chunks (`_on_tts_audio_ready`), and VTS expression thrashing.
- **Recommended Fix:** Guard `perform_song()` with `async with self._busy_lock:` (or reject/queue if `_busy_lock.locked()` when called from external triggers, using a re-entrant state flag if called from `_execute_interaction`).

---

### `[INFRA-HIGH-003]` `EventBus.publish()` Sequential Await & Unbounded `publish_nowait()` Lack Backpressure
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/event_bus.py:182-229` and `core/orchestrator.py:357-366`
- **Symptom:** A single slow or stalled subscriber (e.g., a slow WebSocket client in `Orchestrator._dispatch_to_web_listeners`) blocks `EventBus.publish()` and all subsequent subscribers, while `publish_nowait()` creates unbounded `asyncio.Task` objects under event bursts.
- **Root Cause:**
  1. `EventBus.publish()` (`core/event_bus.py:193-201`) loops over `handlers` and `await res` sequentially in the publisher's coroutine.
  2. `Orchestrator._dispatch_to_web_listeners` (`core/orchestrator.py:360-366`) awaits `listener(message)` sequentially for every connected WebSocket client and silently ignores exceptions (`except Exception: pass`) without unregistering dead clients.
  3. `EventBus.publish_nowait()` (`core/event_bus.py:211-214`) calls `loop.create_task(self.publish(...))` with no queue bound, concurrency limit, or task tracking.
- **Verification Steps:** Inspect `core/event_bus.py:193-214` and `core/orchestrator.py:357-366`.
- **Blast Radius:** Head-of-line blocking across the entire real-time pipeline (TTS, VTS, chat loop) if any WebSocket client stalls; unbounded task growth under high-frequency events (`avatar_state` / `stt_partial`).
- **Recommended Fix:** Add per-client bounded send queues (drop-oldest for high-frequency telemetry like `avatar_state`) for WebSocket listeners, evict failing listeners on disconnect/send error, and bound/track `publish_nowait()` tasks.

---

### `[INFRA-HIGH-004]` Unbounded `ChatReceiver.queue` & `ChatMessage` Event-Loop Deprecation Hazard
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/chat_receiver.py:25, 38`
- **Symptom:** Chat floods from Twitch/YouTube/TikTok/WebSocket can grow `ChatReceiver.queue` without limit; instantiating `ChatMessage` outside a running event loop fails on Python 3.12+.
- **Root Cause:** `self.queue: asyncio.Queue[ChatMessage] = asyncio.Queue()` (`core/chat_receiver.py:38`) uses `maxsize=0` (unbounded). `ChatMessage.__init__` (`core/chat_receiver.py:25`) calls `asyncio.get_event_loop().time()`, which raises `RuntimeError: There is no current event loop in thread` when no loop is running.
- **Verification Steps:** Inspect `core/chat_receiver.py:25, 38`.
- **Blast Radius:** Unbounded memory growth during chat raids/spam floods; `RuntimeError` if `ChatMessage` is constructed in sync worker threads or tests without a running loop.
- **Recommended Fix:** Set a bounded `maxsize` (e.g., 500) with overflow shedding/prioritization, and replace `asyncio.get_event_loop().time()` with `time.monotonic()`.

---

### `[INFRA-HIGH-005]` `ConfigManager` Secret Masking Gap for LLM API Keys & Fixed `.tmp` Race
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/config_manager.py:248-255, 1584, 1630` and `core/orchestrator.py:956-961`
- **Symptom:**
  1. `Orchestrator._visual_perception_loop` reads `llm.gemini_api_key` and `llm.openai_api_key` from `settings` (`core/orchestrator.py:956-961`), but `ConfigManager.SECRET_MASK_FIELDS` (`core/config_manager.py:248-255`) does not include them. If stored in `settings.json`, `GET /api/config` and `configuration_updated` WebSocket broadcasts expose them in plaintext.
  2. `save_config()` (`line 1584, 1595, 1605`) and `reset_to_defaults()` (`line 1630`) use a deterministic `.tmp` suffix (`settings.tmp`) rather than `tempfile.mkstemp()` (unlike `Brain._atomic_write_settings` at `core/brain.py:125`), and do not clean up `.tmp` on `json.dump` failure.
- **Root Cause:** Incomplete `SECRET_MASK_FIELDS` tuple and non-unique temporary file path in `ConfigManager`.
- **Verification Steps:** Compare `core/config_manager.py:248-255, 1584-1590` with `core/orchestrator.py:956-961` and `core/brain.py:121-136`.
- **Blast Radius:** Potential API key leakage over `/api/config` or WebSocket if keys are saved in `settings.json`; temp-file collision if `Brain.set_provider` / `save_config` / `reset_to_defaults` overlap across threads/processes.
- **Recommended Fix:** Add `("llm", "gemini_api_key", ...)` and `("llm", "openai_api_key", ...)` to `SECRET_MASK_FIELDS` (or forbid storing them in `settings.json`), and use `tempfile.mkstemp(dir=...)` with cleanup on error.

---

### `[INFRA-MED-001]` `ConfigManager.validate_config()` Skips Unschematized Settings & Allows Arbitrary Keys
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/config_manager.py:21-217, 1484-1565, 1614-1626`
- **Symptom:** Dozens of `DEFAULT_SETTINGS` keys (e.g., `system.response_timeout_sec`, `llm.context_window_turns`, `llm.fallback_provider`, `llm.retry_attempts`, `personality.curiosity`, `personality.roasting_level`, `memory.retrieval_limit`, `memory.similarity_threshold`, `moderator.spam_rate_limit`, `performance.audio_buffer_size_kb`) are absent from `get_schema()`. `validate_config()` ignores them and also ignores unknown keys, allowing arbitrary unvalidated data into `settings.json`. `reset_to_defaults(category)` similarly skips unschematized keys in that category.
- **Root Cause:** Validation and category reset iterate only over `self.get_schema()` (110 paths) rather than the full `DEFAULT_SETTINGS` contract, and `save_config()` merges arbitrary `payload` keys (`lines 1552-1565`).
- **Verification Steps:** Compare `DEFAULT_SETTINGS` (`core/config_manager.py:21-217`) against `get_schema()` (`lines 306-1482`, 110 `"path"` entries) and `validate_config()` (`lines 1484-1532`).
- **Blast Radius:** Invalid types/ranges for unschematized settings can reach runtime engines without rejection; category resets leave stale values behind.
- **Recommended Fix:** Derive validation and category resets from a single complete schema/Pydantic model covering 100% of `DEFAULT_SETTINGS`, and reject or strip unknown keys.

---

### `[INFRA-MED-002]` Dead Performance/Timeout Configuration Keys (`max_concurrent_tasks`, `response_timeout_sec`, `websocket_ping_interval_sec`)
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/config_manager.py:31, 170-174, 1148-1168`
- **Symptom:** Settings exposed to users in `/settings` (`performance.max_concurrent_tasks`, `performance.websocket_ping_interval_sec`, `performance.audio_buffer_size_kb`, `system.response_timeout_sec`) have no runtime effect.
- **Root Cause:** `Select-String` across `run.py` and `core/orchestrator.py` confirms zero references to these 4 keys.
- **Verification Steps:** Run `Select-String -Path run.py,core\orchestrator.py -Pattern "max_concurrent_tasks|websocket_ping_interval_sec|audio_buffer_size_kb|response_timeout_sec"` -> 0 matches.
- **Blast Radius:** Misleading operator controls; no global LLM/interaction timeout is enforced by `Orchestrator` from `system.response_timeout_sec`.
- **Recommended Fix:** Wire `response_timeout_sec` (`asyncio.wait_for` around LLM/interaction execution), WebSocket keepalive pings, and task concurrency semaphores, or remove unused controls from the schema.

---

### `[INFRA-MED-003]` Synchronous Disk I/O & Engine Calls on the Asyncio Event Loop
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/orchestrator.py:450, 897, 1075, 1090, 1106, 1124` and `run.py:406-407, 414-415, 497`
- **Symptom:** Synchronous disk reads/writes and SQLite/Markdown operations execute directly on the FastAPI/Orchestrator event loop, causing >100ms event-loop stalls (observed in test output: `Task-28 took 0.235 seconds`, `Task-61 took 0.172 seconds`, `Task-75 took 0.187 seconds`).
- **Root Cause:**
  - `ConfigManager.get_public_config()` (`run.py:407`) synchronously reads and parses `settings.json`, `character.json`, and `filter_words.json` on every `GET /api/config`.
  - `Orchestrator._ingest_message()` (`core/orchestrator.py:1075-1125`) calls synchronous `record_incoming_chat()`, `minigames.process_chat_input()`, `storytelling.process_chat_input()`, and `performance.record_audience_cheer()`.
  - `Orchestrator.shutdown()` (`core/orchestrator.py:450`) calls synchronous `self.vod_summarizer.generate_summary(...)` on the loop.
- **Verification Steps:** Observed asyncio slow-task warnings (`0.110s`–`0.235s`) during `unittest` run of `test_event_bus.py` and `test_system_integrity.py`.
- **Blast Radius:** Audio/lip-sync jitter and delayed WebSocket heartbeats under heavy disk/SQLite I/O.
- **Recommended Fix:** Offload blocking file/SQLite operations to `asyncio.to_thread(...)` and cache `ConfigManager` reads with mtime/in-memory invalidation.

---

### `[INFRA-LOW-001]` Shared Mutable `_current_emotion` & TOCTOU in `_idle_banter_loop`
- **Severity:** Low
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/orchestrator.py:219, 304, 591, 865-875`
- **Symptom:** `self._current_emotion` is mutated outside `_speech_lock` by `_on_collab_emote_sync` (`line 591`), while `_idle_banter_loop` (`lines 865-875`) checks `not self._busy_lock.locked()`, mutates mood/goals, and only then calls `trigger_improv()`.
- **Root Cause:** Unsynchronized shared attribute access and check-then-act outside `_busy_lock`.
- **Verification Steps:** Inspect `core/orchestrator.py:591, 865-875`.
- **Blast Radius:** Occasional emotion tag mismatch on `audio_chunk` payloads during collab emotes; minor mood/goal update even if `_busy_lock` is acquired between `line 865` and `line 881`.
- **Recommended Fix:** Pass emotion explicitly to `_on_tts_audio_ready` or guard `_current_emotion` under `_speech_lock`; move idle mood/goal mutation inside `_run_improv()` under `_busy_lock`.
