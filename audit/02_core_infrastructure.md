# Core Infrastructure & Distributed Concurrency Audit (`audit/02_core_infrastructure.md`)

**Auditor:** AGENT 1 (`ng-infra`) — Core Infrastructure & Distributed Concurrency Auditor  
**Scope:** Post-H0/H1/H2/H3 audit of [run.py](file:///d:/projects/MaybeAI/run.py), [core/orchestrator.py](file:///d:/projects/MaybeAI/core/orchestrator.py), [core/event_bus.py](file:///d:/projects/MaybeAI/core/event_bus.py), [core/config_manager.py](file:///d:/projects/MaybeAI/core/config_manager.py), [core/chat_receiver.py](file:///d:/projects/MaybeAI/core/chat_receiver.py), and [core/platforms/](file:///d:/projects/MaybeAI/core/platforms/base.py).  
**Baseline Test Run:** `.\.venv\Scripts\python.exe -m unittest tests/test_event_bus.py tests/test_configuration.py tests/test_system_integrity.py tests/test_horizon0_hardening.py tests/test_chat_receiver.py tests/test_platforms.py tests/test_platforms_v2.py` -> **54 tests passed in 1.814s** (4 asyncio slow-callback warnings `0.110s`–`0.188s` observed).

---

## 1. Post-H0/H1/H2 Remediation Verification Summary

| Prior Finding / Capability | Status | Evidence |
|---|---|---|
| `[INFRA-HIGH-001]` Untracked `asyncio.create_task` leaks in `Orchestrator` | **RESOLVED** (`VERIFIED`) | All background & lip-sync tasks now route through `Orchestrator._spawn_bg_task()` ([core/orchestrator.py](file:///d:/projects/MaybeAI/core/orchestrator.py#L288-L295)). Only `_active_interaction_task` ([line 1329](file:///d:/projects/MaybeAI/core/orchestrator.py#L1329)) uses `create_task` directly and is explicitly cancelled in `shutdown()` ([lines 496-500](file:///d:/projects/MaybeAI/core/orchestrator.py#L496-L500)). |
| `[INFRA-HIGH-002]` `perform_song()` bypassing `_busy_lock` | **RESOLVED** (`VERIFIED`) | `perform_song()` now acquires `self._busy_lock` with `_busy_owner_task` re-entrancy ([core/orchestrator.py](file:///d:/projects/MaybeAI/core/orchestrator.py#L1818-L1828)), and `run.py` routes calls via `_spawn_bg_task` ([run.py](file:///d:/projects/MaybeAI/run.py#L753,L1690)). |
| `[INFRA-HIGH-003]` `EventBus.publish()` sequential await & unbounded `publish_nowait()` | **PARTIALLY RESOLVED** (`PARTIALLY VERIFIED`) | `EventBus.publish()` uses `asyncio.gather` + `handler_timeout=5.0` ([core/event_bus.py](file:///d:/projects/MaybeAI/core/event_bus.py#L192-L224)); `publish_nowait()` bounds pending tasks at `max_pending_tasks=256` ([lines 243-252](file:///d:/projects/MaybeAI/core/event_bus.py#L243-L252)); `_dispatch_to_web_listeners()` uses `asyncio.gather` + `timeout=2.0` + dead-listener eviction ([core/orchestrator.py](file:///d:/projects/MaybeAI/core/orchestrator.py#L434-L443)). **Residual gap:** no per-WS outbound `asyncio.Queue` (see `[INFRA-MED-001-RES]`). |
| `[INFRA-HIGH-004]` Unbounded `ChatReceiver.queue` & `get_event_loop().time()` | **RESOLVED** (`VERIFIED`) | `ChatReceiver.queue` uses `maxsize=500` with drop-oldest overflow ([core/chat_receiver.py](file:///d:/projects/MaybeAI/core/chat_receiver.py#L37-L40,L128-L142)); `ChatMessage` uses `time.monotonic()` ([line 26](file:///d:/projects/MaybeAI/core/chat_receiver.py#L26)). |
| `[INFRA-HIGH-005]` LLM secret masking gap & fixed `.tmp` race | **RESOLVED** (`VERIFIED`) | `SECRET_MASK_FIELDS` now masks all 8 secrets including `llm.gemini_api_key`, `llm.openai_api_key`, and `obs.password` ([core/config_manager.py](file:///d:/projects/MaybeAI/core/config_manager.py#L258-L267)); `_atomic_write_json()` uses `tempfile.mkstemp()` + `os.fsync()` + `os.replace()` ([lines 270-290](file:///d:/projects/MaybeAI/core/config_manager.py#L270-L290)). |
| `[INFRA-MED-001]` Schema coverage vs `DEFAULT_SETTINGS` | **PARTIALLY RESOLVED** (`PARTIALLY VERIFIED`) | `get_schema()` now covers all **157/157** `DEFAULT_SETTINGS` leaf keys across **24** sections. **Residual gap:** `save_config()` still merges unknown keys (see `[INFRA-LOW-001]`). |
| Multi-platform adapters (`core/platforms/`) | **EXISTING** (`VERIFIED`) | `YouTubeLiveAdapter`, `DiscordAdapter`, `TikTokLiveAdapter` inherit `BasePlatformAdapter`, use bounded `_seen_order` (`maxlen=1000`), and push into bounded `ChatReceiver.queue`. |

---

## 2. Residual & Active Findings

### `[INFRA-MED-001-RES]` `_dispatch_to_web_listeners()` Lacks Per-WS Bounded Outbound Queue (`PARTIALLY VERIFIED`)
- **File path:** [core/orchestrator.py](file:///d:/projects/MaybeAI/core/orchestrator.py#L427-L443), [run.py](file:///d:/projects/MaybeAI/run.py#L963-L973)
- **Class/function:** `Orchestrator._dispatch_to_web_listeners`, `websocket_endpoint.listener`
- **Code location:** `core/orchestrator.py:427-443`, `run.py:963-973`
- **Execution path:** `Orchestrator.broadcast()` -> `EventBus.publish()` -> `Orchestrator._dispatch_to_web_listeners()` -> `asyncio.gather(_send_one(l) for l in listeners)` -> `websocket.send_json(event)`.
- **Trigger condition:** One connected WebSocket client stalls on TCP backpressure (e.g., suspended browser tab or slow LAN client) while `EventBus.publish()` is awaited on the hot path (`_ingest_message`, `_speak_response`, `avatar_state`).
- **Expected vs Actual behavior:** Expected (per ADR-001): per-WS bounded `asyncio.Queue(maxsize=64)` decouples `EventBus.publish()` from slow socket writes (<5ms publish). Actual: `EventBus.publish()` awaits `asyncio.gather(..., timeout=2.0)` for the slowest WS client on every broadcast.
- **Root cause:** `run.py` added a bounded `voice_queue = asyncio.Queue(maxsize=64)` for *inbound* audio ([run.py](file:///d:/projects/MaybeAI/run.py#L975)), but `listener()` still calls `await websocket.send_json(event)` directly without an outbound queue/drain task.
- **Impact:** Up to 2.0s head-of-line delay on `Orchestrator.broadcast()` callers when a single WebSocket client stalls.
- **Severity:** Medium
- **Reproduction steps:** Connect two `/ws` clients; pause reading on client A's socket; call `orchestrator.broadcast("chat_received", {...})` and measure elapsed time until `broadcast()` returns (~2.0s).
- **Recommended solution:** Give each `/ws` connection a bounded outbound `asyncio.Queue(maxsize=64)` (drop-oldest for high-frequency `avatar_state` / `stt_partial` frames) drained by a per-connection sender task cancelled in `finally:`.
- **Regression tests:** Add a test in `tests/test_event_bus.py` with a blocked `send_json` mock (sleeping 3s) verifying `orchestrator.broadcast()` returns in `<50ms` while healthy clients receive the event immediately.

---

### `[INFRA-MED-002]` Dead Performance & Timeout Configuration Keys (`VERIFIED`)
- **File path:** [core/config_manager.py](file:///d:/projects/MaybeAI/core/config_manager.py#L31,L180-L182,L1183-L1205,L1558)
- **Class/function:** `ConfigManager.DEFAULT_SETTINGS`, `ConfigManager.get_schema`
- **Code location:** `core/config_manager.py:31` (`system.response_timeout_sec`), `180-182` (`performance.max_concurrent_tasks`, `performance.websocket_ping_interval_sec`, `performance.audio_buffer_size_kb`), `1183-1205`, `1558`
- **Execution path:** `GET /api/config/schema` -> `/settings` UI -> `PUT /api/config` -> `settings.json` -> `Orchestrator.apply_configuration_hot_reload()`.
- **Trigger condition:** Operator modifies any of these 4 settings in `/settings` or `config/settings.json`.
- **Expected vs Actual behavior:** Expected: changing `system.response_timeout_sec` enforces an LLM/interaction timeout; `max_concurrent_tasks` caps concurrent tasks; `websocket_ping_interval_sec` configures WS keepalive. Actual: 0 references exist in `run.py` or `core/orchestrator.py`; changes have zero runtime effect.
- **Root cause:** Keys were defined in `DEFAULT_SETTINGS` and `get_schema()` without corresponding runtime wiring in `Orchestrator` or `run.py`.
- **Impact:** Misleading operator controls; no global `Orchestrator`-level interaction timeout is enforced from `system.response_timeout_sec`.
- **Severity:** Medium
- **Reproduction steps:** Search `run.py` and `core/orchestrator.py` for `max_concurrent_tasks|websocket_ping_interval_sec|audio_buffer_size_kb|response_timeout_sec` -> 0 matches.
- **Recommended solution:** Wire `system.response_timeout_sec` (`asyncio.wait_for` around `_execute_interaction` LLM calls) and `performance.max_concurrent_tasks` / `websocket_ping_interval_sec`, or remove dead controls from `get_schema()`.
- **Regression tests:** Add a test in `tests/test_configuration.py` verifying `system.response_timeout_sec` bounds slow LLM responses in `Orchestrator`.

---

### `[INFRA-MED-003]` Residual Synchronous Disk & Engine I/O on the Asyncio Event Loop (`REPRODUCED`)
- **File path:** [run.py](file:///d:/projects/MaybeAI/run.py#L502-L533), [core/orchestrator.py](file:///d:/projects/MaybeAI/core/orchestrator.py#L1241-L1296)
- **Class/function:** `get_configuration`, `update_configuration`, `validate_configuration`, `reset_configuration`, `Orchestrator._ingest_message`
- **Code location:** `run.py:504, 520, 525, 531`; `core/orchestrator.py:1241, 1256, 1272, 1290`
- **Execution path:** HTTP `GET /api/config`, `POST /api/config/validate`, `POST /api/config/reset` call synchronous `ConfigManager` disk reads/writes directly on the event loop; `_process_chat_loop()` -> `_ingest_message()` calls synchronous `record_incoming_chat()`, `minigames.process_chat_input()`, `storytelling.process_chat_input()`, and `performance.record_audience_cheer()` on the event loop.
- **Trigger condition:** Config reads/resets or chat ingestion triggering SQLite/JSON/Markdown writes.
- **Expected vs Actual behavior:** Expected: zero >100ms event-loop stalls. Actual: running `tests/test_event_bus.py` and `tests/test_system_integrity.py` emits 4 asyncio slow-callback warnings (`0.110s`, `0.125s`, `0.172s`, `0.188s`).
- **Root cause:** While `save_config()` (`run.py:512`) and `vod_summarizer.generate_summary()` (`core/orchestrator.py:527`) were offloaded to `asyncio.to_thread`, `get_public_config()`, `reset_to_defaults()`, and `_ingest_message()` synchronous engine calls remain on the loop.
- **Impact:** Periodic 110–188ms event-loop stalls during chat/memory ingestion or config reads, risking minor audio/lip-sync jitter.
- **Severity:** Medium
- **Reproduction steps:** Run `.\.venv\Scripts\python.exe -m unittest tests/test_event_bus.py tests/test_system_integrity.py` and observe `Executing <Task ...> took 0.172 seconds` warnings.
- **Recommended solution:** Wrap `config_mgr.get_public_config()` and `config_mgr.reset_to_defaults()` in `asyncio.to_thread(...)`, cache `ConfigManager` reads by mtime, and offload heavy `record_incoming_chat()` / Markdown syncs in `_ingest_message()` to `asyncio.to_thread(...)`.
- **Regression tests:** Assert zero asyncio slow-callback warnings (>100ms) in `tests/test_event_bus.py` under `PYTHONASYNCIODEBUG=1`.

---

### `[INFRA-LOW-001]` `ConfigManager.save_config()` Merges Arbitrary Unknown Keys (`VERIFIED`)
- **File path:** [core/config_manager.py](file:///d:/projects/MaybeAI/core/config_manager.py#L2072-L2104)
- **Class/function:** `ConfigManager.save_config`
- **Code location:** `core/config_manager.py:2090-2103`
- **Execution path:** `PUT /api/config` -> `ConfigManager.save_config(payload)`.
- **Trigger condition:** Client sends JSON payload containing unknown top-level sections or unknown keys inside known sections.
- **Expected vs Actual behavior:** Expected: unknown keys are rejected or stripped. Actual: `validate_config()` only validates keys in `get_schema()`, and `save_config()` merges all remaining keys in `payload` into `settings.json`.
- **Root cause:** No allowlist check against `DEFAULT_SETTINGS` keys in `validate_config()` or `save_config()`.
- **Impact:** Arbitrary unvalidated data can be persisted into `config/settings.json`.
- **Severity:** Low
- **Reproduction steps:** Call `ConfigManager().save_config({"unknown_sec": {"foo": "bar"}})` -> returns `(True, [], False)` and writes `unknown_sec` to `settings.json`.
- **Recommended solution:** Reject or strip keys not present in `DEFAULT_SETTINGS` (plus `"character"`, `"filters"`, `"api_keys"`).
- **Regression tests:** Add a test in `tests/test_configuration.py` asserting unknown keys are rejected or stripped by `save_config()`.

---

### `[INFRA-LOW-002]` `_idle_banter_loop()` TOCTOU & Unsynchronized `_current_emotion` Mutation (`VERIFIED`)
- **File path:** [core/orchestrator.py](file:///d:/projects/MaybeAI/core/orchestrator.py#L667,L1019-L1029)
- **Class/function:** `Orchestrator._on_collab_emote_sync`, `Orchestrator._idle_banter_loop`
- **Code location:** `core/orchestrator.py:667`, `core/orchestrator.py:1019-1029`
- **Execution path:** `_idle_banter_loop()` checks `not self._busy_lock.locked()` (`line 1019`), mutates `goals` and `mood` (`lines 1022-1028`), then calls `trigger_improv()` which re-checks `_busy_lock`. Separately, `_on_collab_emote_sync()` mutates `self._current_emotion` (`line 667`) when `_busy_lock` is not locked, outside `_speech_lock`.
- **Trigger condition:** Chat message arrives between `line 1019` and `trigger_improv()`, or collab emote arrives concurrently with TTS chunk emission.
- **Expected vs Actual behavior:** Expected: idle mood/goal mutation only occurs if improv actually acquires `_busy_lock`; `_current_emotion` is guarded. Actual: mood/goal state is mutated even if `trigger_improv()` aborts on lock contention.
- **Root cause:** Check-then-act outside `async with self._busy_lock`.
- **Impact:** Minor state desync on rare race conditions.
- **Severity:** Low
- **Reproduction steps:** Inspect `core/orchestrator.py:1019-1029`.
- **Recommended solution:** Move idle goal/mood mutation inside `_run_improv()` under `self._busy_lock`.
- **Regression tests:** Unit test `_idle_banter_loop` / `_run_improv` with `_busy_lock` held.

---

### `[INFRA-LOW-003]` `voice_worker_task` Created Outside `Orchestrator._spawn_bg_task` (`VERIFIED`)
- **File path:** [run.py](file:///d:/projects/MaybeAI/run.py#L1107-L1112,L1842-L1849)
- **Class/function:** `websocket_endpoint._enqueue_voice_pcm`
- **Code location:** `run.py:1111`
- **Execution path:** Incoming binary/JSON voice chunk -> `_enqueue_voice_pcm()` -> `asyncio.create_task(_voice_worker())`.
- **Trigger condition:** WebSocket `/ws` receives voice audio chunks.
- **Expected vs Actual behavior:** Expected: all server tasks visible in `bg_tasks_active` metric. Actual: `voice_worker_task` is properly cleaned up in `finally:` (`run.py:1842-1849`), so it does not leak, but is omitted from `Orchestrator._bg_tasks` / `bg_tasks_active`.
- **Root cause:** Per-connection task spawned locally in `run.py`.
- **Impact:** Informational / observability gap only (cleanup is sound).
- **Severity:** Low
- **Reproduction steps:** Inspect `run.py:1111` and `run.py:1842-1849`.
- **Recommended solution:** Optional: track active `voice_worker_task` count in `MetricsCollector` or keep local per-WS lifecycle.
- **Regression tests:** Existing `tests/test_audioworklet_deck.py` covers `/ws` voice worker lifecycle.

---

## 3. Infrastructure L0–L5 Maturity Score

| Dimension | Pre-H0 Score | Post-H3 Score | Rationale |
|---|---|---|---|
| **Core Infrastructure & Distributed Concurrency** | **L2.5** | **L3.5** | **L3.0 (Hardened Single-Node)** achieved via concurrent `EventBus.publish()`, bounded `publish_nowait` (`256`) & `ChatReceiver.queue` (`500`), `_spawn_bg_task()` supervision, `perform_song()` lock, `mkstemp` atomic config, 8-field secret masking, and 157/157 schema coverage. **+0.5 (L3.5)** for `MetricsCollector` (`/api/metrics`) & multi-platform adapter isolation. Blocked from **L4.0** by missing per-WS outbound `asyncio.Queue`, 4 unwired performance/timeout config keys, and residual sync I/O on the event loop. |
