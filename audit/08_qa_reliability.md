# 08 — QA & Production Reliability Audit

**Auditor:** AGENT 8 (`cto-qa`) — QA & Production Reliability Auditor  
**Scope:** Test suite inventory, real vs. mocked coverage gaps, warning/deprecation analysis (`-W default`), regression risks, and production readiness verdict.

---

## 1. Verification Run Summary

| Check | Command | Result | Notes |
|---|---|---|---|
| Python Unit & Integration Suite | `.\.venv\Scripts\python.exe -W default -m unittest discover tests` | **315 tests in 21.277s — FAILED (`errors=1`)** | `test_hard_timeout_kills_infinite_loop_subprocess` errored with `KeyError: 'hang_plugin'` under full-suite CPU load. |
| Isolated Sandbox Plugin Suite | `.\.venv\Scripts\python.exe -W default -m unittest tests.test_sandbox_plugins_cli` | **5 tests in 2.544s — OK** | Passed when run standalone, confirming timing/cold-start flakiness (`[QA-HIGH-001]`). |
| Node.js GuardRunner Tests | `node tests/test_guard_runner.js` | **PASSED (exit 0)** | Verified `start`, `player_hurt` counter-attack, and `stop` lifecycle. |
| Frontend JS Syntax Check | `node --check web/*.js` | **PASSED (exit 0)** | Clean syntax across `app.js`, `audio-worklet-processor.js`, `deck.js`, `overlay.js`, `settings.js`. |

### Side-Effect Hygiene Observation
Running `unittest discover tests` mutated/created tracked and untracked files under `data/` (including `data/memory.db-wal`, `data/memory.db-shm`, `data/desktop/permissions.json`, `data/goals/agenda.md`, `data/minecraft/multiplayer_social.json`, `data/minigames/leaderboard.json`, `data/performance/director.json`, `data/personality/evolution.json`, `data/relationships/relationships.json`, `data/storytelling/campaigns.json`, and `data/second_brain/*`). Several tests write to the workspace `data/` directory rather than `tempfile.TemporaryDirectory()`.

---

## 2. Test Suite Inventory & Real vs. Mocked Coverage

Total Python test files: **35** (`tests/test_*.py`), **315** test cases, plus **1** Node.js test (`tests/test_guard_runner.js`).

| Test File | Lines | Tests | Mock Refs | Coverage Type |
|---|---:|---:|---:|---|
| `test_audioworklet_deck.py` | 114 | 3 | 4 | Mocked WS/STT audio chunking & EventBus emission |
| `test_autonomous_missions.py` | 302 | 8 | 10 | Mocked LLM/executor mission decomposition & replanning |
| `test_avatar_vts_and_telemetry.py` | 140 | 4 | 9 | Mocked VTS + MC telemetry callbacks |
| `test_brain.py` | 139 | 4 | 6 | Mocked HTTP/LLM provider calls (`Gemini`, etc.) |
| `test_chat_receiver.py` | 65 | 4 | 3 | Unit tests for chat queue & priority |
| `test_chess.py` | 186 | 9 | 3 | Real `python-chess` engine + mocked orchestrator speech |
| `test_collab_and_plugins.py` | 493 | 9 | 1 | Real `CollabEnvelope`/`CollabManager` + `PluginRegistry` (in-process) |
| `test_configuration.py` | 234 | 11 | 0 | Real `ConfigManager` / FastAPI settings routes |
| `test_desktop_companion.py` | 306 | 22 | 9 | Mocked OS/Win32 volume/app/notification actions |
| `test_event_bus.py` | 217 | 8 | 3 | Real `EventBus` + mocked orchestrator/conversation |
| `test_fase1_hardening.py` | 366 | 9 | 13 | Mocked audio/TTS/lifecycle shutdown |
| `test_goals.py` | 173 | 16 | 2 | Real goal/agenda state (mutates `data/goals/agenda.md`) |
| `test_guard_mode.py` | 90 | 3 | 5 | Mocked Minecraft guard bridge events |
| `test_highlights_and_vod.py` | 235 | 5 | 2 | Mocked `ffmpeg` clip export & VOD summarizer |
| `test_memory.py` | 185 | 9 | 0 | Real SQLite memory DB |
| `test_minigames.py` | 245 | 14 | 0 | Real minigame state (mutates `data/minigames/leaderboard.json`) |
| `test_mood.py` | 143 | 10 | 0 | Real mood engine |
| `test_multiplayer_social.py` | 282 | 21 | 0 | Real social engine (mutates `data/minecraft/multiplayer_social.json`) |
| `test_neural_tts_rvc.py` | 213 | 6 | 15 | Mocked Kokoro/ElevenLabs/RVC HTTP endpoints |
| `test_obs_showrunner.py` | 250 | 5 | 9 | Mocked `obsws_python.ReqClient` |
| `test_overlay_route.py` | 105 | 4 | 0 | Real FastAPI `TestClient` route checks |
| `test_performance.py` | 162 | 8 | 0 | Real `PerformanceDirector` (mutates `data/performance/director.json`) |
| `test_personality.py` | 146 | 9 | 0 | Real personality evolution (mutates `data/personality/evolution.json`) |
| `test_platforms.py` | 288 | 9 | 9 | Mocked Twitch/YouTube/Discord adapters |
| `test_platforms_v2.py` | 225 | 4 | 3 | Mocked `aiohttp` / Discord gateway |
| `test_relationships.py` | 218 | 17 | 0 | Real relationship engine (mutates `data/relationships/`) |
| `test_sandbox_plugins_cli.py` | 287 | 5 | 1 | **Real subprocess** `sandbox_worker` + CLI tests |
| `test_semantic_memory.py` | 210 | 6 | 4 | Mocked Gemini embedding REST + local hash fallback |
| `test_storytelling.py` | 186 | 7 | 0 | Real campaign engine (mutates `data/storytelling/campaigns.json`) |
| `test_streaming_tts.py` | 438 | 11 | 24 | Mocked Edge-TTS / LLM SSE stream |
| `test_system_integrity.py` | 168 | 10 | 10 | Mocked end-to-end orchestrator priority/guardrails |
| `test_tts.py` | 121 | 5 | 14 | Mocked `edge_tts` / `pygame.mixer` |
| `test_vision.py` | 174 | 17 | 0 | Pure unit tests for vision analyzer/models |
| `test_voice_duplex.py` | 410 | 11 | 9 | Mocked VAD/STT/TTS barge-in flow |
| `test_vts_client.py` | 124 | 6 | 12 | Mocked `websockets` VTube Studio RPC |
| `test_websocket_security.py` | 215 | 6 | 1 | Real FastAPI WS origin/auth/action-guard checks |

### Critical Coverage Gaps
1. **Live External Integrations (100% Mocked):** Zero contract/smoke tests against real OBS Studio (`obsws-python`), VTube Studio (`ws://127.0.0.1:8001`), Mineflayer `minecraft/bot.js` over live WebSocket, `ffmpeg` binary execution, `edge-tts`, or live LLM SSE endpoints.
2. **Frontend Runtime / Browser E2E (0% Covered):** `node --check` verifies syntax only. There are no DOM, WebSocket, AudioWorklet, or VRM 3D rendering tests for `web/app.js`, `web/overlay.js`, `web/deck.js`, or `web/settings.js`.
3. **Long-Running Soak & Concurrency Stress:** No multi-hour soak tests, WebSocket slow-client backpressure tests, or `EventBus` subscriber-stall tests exist in `tests/`.
4. **Collab Security Edge Cases:** `test_collab_and_plugins.py` tests valid/invalid HMAC signatures and `max_collab_turns`, but has **zero tests** for replay attacks (reused `message_id` / stale `timestamp`) or non-`turn_utterance` flood (`emote_sync`/`duet_sync`).

---

## 3. Warning & Deprecation Analysis (`-W default`)

Running with `.\.venv\Scripts\python.exe -W default -m unittest discover tests` produced:
- **Zero Python `DeprecationWarning` or `ResourceWarning` tracebacks** in stdout/stderr across all 315 tests.
- **13+ `asyncio` slow-callback warnings** (`Executing <Task ...> took 0.109–0.172 seconds`) from `asyncio` debug mode/slow-callback threshold (100ms), notably in:
  - `test_audioworklet_deck.py:80` (`0.109s`)
  - `test_brain.py:85` (`0.125s`)
  - `test_chess.py:125` (`0.140s–0.156s`)
  - `test_event_bus.py:188,196` (`0.125s–0.172s`)
  - `test_fase1_hardening.py:358` (`0.125s`)
  - `test_streaming_tts.py:124` (`0.109s`)
  - `test_system_integrity.py:84,108,133` (`0.109s–0.141s`)
  - **Root cause:** Heavy synchronous setup (e.g., `pygame.mixer` init, SQLite schema/disk I/O, or `FastAPI`/module imports) executing inside `async def` test/setup coroutines on the event loop.

---

## 4. Key QA & Reliability Findings

### `[QA-CRIT-001]` Missing Replay Protection on Signed `CollabEnvelope` Messages
- **Severity:** Critical
- **Evidence Classification:** `REPRODUCED` (verified in Chaos Scenario D3)
- **Location:** `core/collab/protocol.py:92-106`, `core/collab/manager.py:470-488`
- **Symptom:** An attacker or misbehaving peer replaying a previously captured valid `CollabEnvelope` (identical `message_id`, identical `signature`, `timestamp` 1 hour stale) is accepted repeatedly and advances `turn_count` each time.
- **Root Cause:** `CollabEnvelope.verify()` checks HMAC-SHA256 only. `CollabManager.handle_incoming_envelope()` has no `message_id` nonce cache and no `timestamp` freshness window check.
- **Recommended Fix:** Maintain a bounded TTL/LRU cache of seen `message_id` values in `CollabManager` and reject envelopes with `abs(time.time() - env.timestamp) > max_clock_skew_sec` (e.g., 60s) or duplicate `message_id`.

### `[QA-HIGH-001]` Flaky Subprocess Plugin Discovery Under CPU Load (`hook_timeout_sec` Shared with Cold Start)
- **Severity:** High
- **Evidence Classification:** `REPRODUCED` (failed in full `unittest discover tests` run, passed in isolated `tests.test_sandbox_plugins_cli` run)
- **Location:** `core/plugins/registry.py:541-555` (`_probe_sandbox_manifest`), `tests/test_sandbox_plugins_cli.py:202-207`
- **Symptom:** `test_hard_timeout_kills_infinite_loop_subprocess` errors with `KeyError: 'hang_plugin'` during full-suite execution; log shows `[PluginRegistry] Failed discovering sandboxed plugin '...hang_plugin.py': ` (empty `TimeoutError` string).
- **Root Cause:** `_probe_sandbox_manifest` reuses `self.hook_timeout_sec` (0.3s in test) as the timeout for spawning a fresh Python subprocess + importing modules + returning the `manifest` RPC. Under CPU contention, Windows subprocess cold-start exceeds 0.3s.
- **Recommended Fix:** Separate `startup_timeout_sec` (e.g., `max(5.0, self.hook_timeout_sec)`) for `_probe_sandbox_manifest` and `on_load`, keeping `hook_timeout_sec` strictly for runtime `on_command` / `on_event` hooks.

### `[QA-HIGH-002]` `MinecraftController._listen_bridge()` Leaves Stale `"connected"` State on Bridge Disconnect
- **Severity:** High
- **Evidence Classification:** `REPRODUCED` (verified in Chaos Scenario E1)
- **Location:** `core/minecraft/controller.py:340-343`
- **Symptom:** When the Node.js Mineflayer WebSocket bridge drops (`ConnectionError` / abnormal closure 1006), `_listen_bridge()` breaks and sets `self.bridge_ws = None`, but `self.connection_status` remains `"connected"` and `self.is_active` remains `True`, with no automatic reconnect or state broadcast.
- **Recommended Fix:** In `_listen_bridge()`'s `finally:` block, reset `connection_status = "disconnected"`, `is_active = False`, `viewer_url = None`, emit state change, and optionally schedule bounded-backoff reconnect if `bot_process` is still alive or restartable.

### `[QA-HIGH-003]` `OBSWebSocketClient` Leaves `is_connected=True` After Transport Failure
- **Severity:** High
- **Evidence Classification:** `REPRODUCED` (verified in Chaos Scenario E2)
- **Location:** `core/desktop/obs_client.py:144-168`
- **Symptom:** When `set_current_program_scene` raises `ConnectionError`, `switch_scene()` returns `{"success": False, "connected": True, ...}` and leaves `self.is_connected = True` and `self._client` populated. Subsequent callers believe OBS is still connected.
- **Recommended Fix:** On connection/transport exceptions in `OBSWebSocketClient` RPC methods, set `self.is_connected = False`, clear `self._client`, and attempt lazy reconnect or surface `connected: False`.

### `[QA-MED-001]` Dead Plugin Subprocess Entry Retained in `_subprocesses` After Worker Crash
- **Severity:** Medium
- **Evidence Classification:** `REPRODUCED` (verified in Chaos Scenario C3)
- **Location:** `core/plugins/registry.py:151-155`, `core/plugins/registry.py:620-642`
- **Symptom:** When a sandboxed plugin crashes (`os._exit(42)`), `dispatch_command` catches `EOFError`, increments `error_count`, but leaves the dead `_SandboxPluginClient` in `self._subprocesses`. Calling `reload_plugin()` then logs `on_unload error ... ConnectionResetError: Connection lost` before spawning a replacement.
- **Recommended Fix:** Evict dead clients (`not client.is_running`) from `self._subprocesses` and mark `meta["loaded"] = False` immediately on `EOFError` / `ConnectionResetError`.

### `[QA-MED-002]` Non-Utterance Collab Events Bypass `max_collab_turns` and `cooldown`
- **Severity:** Medium
- **Evidence Classification:** `REPRODUCED` (verified in Chaos Scenario D5)
- **Location:** `core/collab/manager.py:508-516`
- **Symptom:** `duet_sync`, `emote_sync`, and `game_move` envelopes are processed and invoke callbacks even when `floor_state == "cooldown"` and `turn_count >= max_collab_turns`.
- **Recommended Fix:** Apply per-peer rate limiting for sync/game events inside `CollabManager.handle_incoming_envelope()`.

### `[QA-MED-003]` Unit Tests Mutate Tracked Workspace `data/` Files
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED` (observed via `git status --short` after `unittest discover tests`)
- **Location:** `tests/test_goals.py`, `tests/test_minigames.py`, `tests/test_multiplayer_social.py`, `tests/test_performance.py`, `tests/test_personality.py`, `tests/test_relationships.py`, `tests/test_storytelling.py`
- **Symptom:** Running the test suite dirties `git status` with 25+ modified/untracked files under `data/`.
- **Recommended Fix:** Isolate test fixtures using `tempfile.TemporaryDirectory()` so CI and local runs remain idempotent.

---

## 5. Production Readiness Verdict

**Verdict: `CONDITIONAL NO-GO` for unattended/public production streams; `CONDITIONAL GO` for supervised local creator streams** once `[QA-CRIT-001]` (Collab replay protection if Collab is enabled) and `[PERF-HIGH-001]` (EventBus slow-subscriber isolation) are addressed.

- **Strengths:** Strong unit-test discipline (315 Python tests + Node GuardRunner + JS syntax checks), clean env isolation in plugin subprocesses (`leaks=[]`), solid TTS barge-in cleanup (zero temp file leaks), and clean `-W default` deprecation posture.
- **Blockers for Unattended Production:** Flaky plugin cold-start timeout (`[QA-HIGH-001]`), Collab replay vulnerability (`[QA-CRIT-001]`), stale disconnect states in Minecraft/OBS (`[QA-HIGH-002]`, `[QA-HIGH-003]`), and sequential `EventBus` / WebSocket broadcast head-of-line blocking (`[PERF-HIGH-001]`).
