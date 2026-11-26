# 09 — Cross-Agent Review & Root-Cause Synthesis

**Author:** AGENT 8 (`cto-qa`) — Audit Lead Synthesizer  
**Scope:** Cross-domain verification, deduplication, discrepancy resolution, and systemic root-cause clustering across `audit/00`–`08`, `10`, and `11`.

---

## 1. Cross-Agent Consistency & Discrepancy Resolution

1. **Test Inventory Count (`00` vs `08`):**
   - `00_repository_inventory.md` listed 39 entries in `tests/`. Direct enumeration in `08_qa_reliability.md` verified **35** `tests/test_*.py` files (**315** Python `unittest` cases), **1** `tests/__init__.py`, and **1** Node.js test (`tests/test_guard_runner.js`).
   - Full-suite execution (`-W default`) reported **315 tests in 21.277s — FAILED (`errors=1`)** due to `[QA-HIGH-001]` (`test_hard_timeout_kills_infinite_loop_subprocess` timing out on cold start under CPU load, while passing 5/5 standalone).
2. **TTS Barge-In Cleanup vs. Orchestrator Post-Cancel Side Effects (`02` vs `10`):**
   - Chaos Scenario B (`10_chaos_testing.md`) `VERIFIED` that `TTSEngine.stop()` and `speak_stream()` cleanly cancel inner tasks, reset `is_speaking=False` and `mouth_open=0.0`, and leave `0` temp `.mp3` files on disk.
   - `02_realtime_audio.md` (`[AUDIO-CRIT-001]`) `VERIFIED` a distinct higher-level race: because `speak_stream()` returns partial `raw_parts` instead of re-raising `CancelledError` when `_stop_requested` is `True`, `Orchestrator._execute_interaction()` can still broadcast `ai_response` and dispatch Minecraft/Discord replies if `_active_interaction_task` has not hit another `await`.
3. **Collab Replay & EventBus Blocking (`01`, `04`, `06`, `10`, `11`):**
   - Independently identified and `REPRODUCED` by Agents 4, 6, and 8 (`[COLLAB-CRIT-001]` = `[SEC-HIGH-005]` = `[QA-CRIT-001]`) and Agents 1 and 8 (`[INFRA-HIGH-003]` = `[PERF-HIGH-001]`).

---

## 2. Deduplicated Cross-Domain Root-Cause Clusters

### Cluster A — Security, Auth & XSS Escalation Chain
- **Member Findings:** `[SEC-CRIT-001]`, `[SEC-HIGH-001]`, `[SEC-HIGH-002]`, `[UI-HIGH-001]`, `[UI-HIGH-002]`, `[SEC-MED-002]`, `[UI-LOW-002]`, `[INFRA-HIGH-005]`
- **Systemic Root Cause:** Authentication and escaping are applied inconsistently across HTTP/WS/UI boundaries:
  - `/ws` gates 9 actions in `_CREATOR_ONLY_WS_ACTIONS` but leaves `memory_action`, `mood_action`, `relationship_action`, `minigame_action`, `story_action`, and `trigger_improv` unauthenticated (`[SEC-CRIT-001]`), while `_is_ws_creator_authorized()` breaks Docker/LAN Creator auth by checking `_LOOPBACK_HOSTS` before `MAYBEAI_CREATOR_TOKEN` (`[SEC-HIGH-001]`).
  - `/settings` interpolates config/diagnostics into `innerHTML` unescaped (`[UI-HIGH-001]`), creating a direct chain to steal `localStorage.maybeai_creator_token` (`[UI-LOW-002]`).
  - `ConfigManager.SECRET_MASK_FIELDS` omits `llm.gemini_api_key` and `llm.openai_api_key` (`[INFRA-HIGH-005]`).

### Cluster B — Autonomous Mission + Minecraft Bridge Failure Cascade
- **Member Findings:** `[GAME-CRIT-002]`, `[QA-HIGH-002]`, `[COG-CRIT-001]`, `[COG-CRIT-002]`, `[COG-HIGH-001]`, `[GAME-MED-003]`, `[GAME-MED-004]`
- **Systemic Root Cause:** Lack of closed-loop state synchronization between external runtimes and the planner:
  1. `MinecraftController._listen_bridge()` leaves `connection_status="connected"` after bridge WS drops (`[GAME-CRIT-002]` / `[QA-HIGH-002]`).
  2. `AutonomousMissionExecutor._execute_minecraft()` checks `get_inventory_count()` 0ms after sending `toggle_wander()` (`[COG-HIGH-001]`), failing every tick (`observed_delta <= 0`) when connected—or fabricating `simulated: True` progress when disconnected.
  3. Repeated failures trigger `StrategyReplanner` indefinitely (`[COG-CRIT-002]`), and any replanned goal is permanently barred from `COMPLETED` by `Goal.recalculate_progress()` (`[COG-CRIT-001]`).

### Cluster C — Asyncio Concurrency, Event-Loop Blocking & Lifecycle Leaks
- **Member Findings:** `[INFRA-HIGH-001]`, `[INFRA-HIGH-002]`, `[INFRA-HIGH-003]`, `[PERF-HIGH-001]`, `[AUDIO-CRIT-001]`, `[AUDIO-CRIT-002]`, `[AUDIO-HIGH-001]`, `[AUDIO-HIGH-002]`, `[AUDIO-HIGH-004]`, `[AUDIO-MED-001]`, `[AUDIO-MED-003]`, `[GAME-CRIT-001]`, `[GAME-HIGH-005]`, `[COG-MED-003]`, `[PERF-MED-001]`, `[PERF-MED-002]`
- **Systemic Root Cause:**
  - `EventBus.publish()` awaits subscribers sequentially (`[INFRA-HIGH-003]` / `[PERF-HIGH-001]`).
  - 12+ untracked `asyncio.create_task()` calls bypass `_bg_tasks` (`[INFRA-HIGH-001]`, `[AUDIO-MED-001]`), and `perform_song()` bypasses `_busy_lock` (`[INFRA-HIGH-002]`).
  - Blocking I/O (`transcribe_wav_bytes` in WS loop, `pygame.mixer`, `sqlite3`, `ffmpeg` without timeout, `write_bytes`/`read_bytes` on browser TTS, and `chess.Board` shared mutation in `to_thread`) causes >100ms event-loop stalls and race conditions (`[GAME-CRIT-001]`, `[GAME-HIGH-004]`, `[GAME-HIGH-005]`, `[AUDIO-HIGH-001]`, `[INFRA-MED-003]`).

### Cluster D — Collab Protocol & Plugin Sandbox Trust Boundaries
- **Member Findings:** `[COLLAB-CRIT-001]`, `[SEC-HIGH-005]`, `[QA-CRIT-001]`, `[COLLAB-HIGH-001]`, `[COLLAB-HIGH-002]`, `[COLLAB-HIGH-003]`, `[COLLAB-HIGH-004]`, `[COLLAB-MED-001]`, `[QA-MED-002]`, `[SEC-CRIT-002]`, `[QA-HIGH-001]`, `[QA-MED-001]`
- **Systemic Root Cause:** Both boundaries implement cryptographic/process primitives (HMAC-SHA256, subprocess `env` stripping) without full lifecycle/state enforcement:
  - Collab lacks nonce/timestamp replay protection, hostname-parsed loopback checks, cooldown turn reset (`_refresh_cooldown()` dead code), and `enabled=False` enforcement.
  - Plugin sandbox strips `os.environ` (`leaks=[]` verified) and kills CPU loops (`[QA-HIGH-001]` aside), but runs as the same OS user in `REPO_ROOT` with full read/write access to `.env`/`config/`/`data/` and trusts self-declared manifest permissions (`[SEC-CRIT-002]`).

### Cluster E — Dead Configuration & Incomplete Integrations
- **Member Findings:** `[INFRA-MED-002]`, `[SEC-HIGH-004]`, `[AUDIO-MED-002]`, `[AUDIO-MED-003]`, `[COG-MED-004]`, `[COLLAB-MED-004]`, `[GAME-MED-004]`, `[GAME-LOW-001]`, `[UI-LOW-001]`
- **Summary:** Multiple UI-exposed settings (`max_concurrent_tasks`, `response_timeout_sec`, `websocket_ping_interval_sec`, `strict_mode`, `prompt_injection_filter`, `vts.auto_reconnect`, `tts.volume`, `karaoke.vocal_volume`, `MoodEngine.get_temperature_modifier`) have zero runtime effect.
