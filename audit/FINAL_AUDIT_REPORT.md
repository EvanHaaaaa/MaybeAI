# MaybeAI — Comprehensive CTO Technical Audit Report (`FINAL_AUDIT_REPORT.md`)

**Audit Swarm:** Agents 1–8 (`cto-infra`, `cto-audio`, `cto-cognition`, `cto-collab`, `cto-games`, `cto-sec`, `cto-frontend`, `cto-qa`)  
**Repository:** `d:\projects\MaybeAI` (94 Python modules in `core/`, `run.py`, 13 `web/` assets, Node.js `minecraft/` bridge, 35 Python test files + 1 Node test)  
**Audit Standard:** Zero source modifications; all findings verified against live source code, unit tests, and isolated Chaos Scenarios A–E.

---

## 1. Executive Summary & Production Readiness Verdict

MaybeAI is an ambitious, feature-rich autonomous AI VTuber platform with strong foundational architecture: a typed async `EventBus`, streaming LLM-to-`SentenceChunker`-to-TTS pipelining, hybrid SQLite FTS5 + vector Second Brain memory, `python-chess` + Mineflayer + OBS + VTube Studio integrations, and an out-of-process plugin sandbox with clean environment stripping.

However, **MaybeAI is NOT ready for unattended or public-facing production deployment** without targeted hardening:

| Deployment Profile | Verdict | Rationale |
|---|---|---|
| **Unattended / Public / Docker / LAN Stream** | **`NO-GO`** | Unauthenticated `/ws` mutations & `GET /api/*` leaks (`[SEC-CRIT-001]`, `[SEC-HIGH-002]`), broken Docker/LAN Creator WS auth (`[SEC-HIGH-001]`), `/settings` stored DOM XSS (`[UI-HIGH-001]`), Collab replay vulnerability (`[COLLAB-CRIT-001]`), and plugin filesystem/network access (`[SEC-CRIT-002]`). |
| **Supervised Localhost Creator Stream** | **`CONDITIONAL GO`** | Viable for local experimentation once P0 stability/correctness fixes land: `EventBus` slow-subscriber head-of-line blocking (`[PERF-HIGH-001]`), Chess `Board` thread race (`[GAME-CRIT-001]`), barge-in post-cancel side effects (`[AUDIO-CRIT-001]`), and Goal replanning deadlock (`[COG-CRIT-001]`/`[COG-CRIT-002]`). |

---

## 2. Capability Maturity Matrix

| Subsystem | Classification | Verified State |
|---|---|---|
| **Core `EventBus`, FastAPI `lifespan`, `ConfigManager`** | **Current Capability** | Typed pub-sub, atomic config writes, secret masking (6 fields); needs backpressure & LLM key masking. |
| **Browser 16 kHz `AudioWorklet` + `EnergyVAD` + Streaming TTS** | **Current Capability** | 32 ms PCM streaming, `SentenceChunker`, bounded `asyncio.Queue(maxsize=4)` with clean temp-file cleanup. |
| **Hybrid Second Brain Memory & Mood/Personality/Relationships** | **Current Capability** | SQLite FTS5 + cosine vector search + Markdown sync; bounded personality & 5-tier relationships. |
| **Chess, Mini-Games, Storytelling, OBS, Highlights (`ffmpeg`)** | **Current Capability** | Functional engines with offline fallbacks; requires thread-safety (`chess.Board`), `ffmpeg` timeout/confinement, and OBS disconnect detection. |
| **Full-Duplex Barge-In & Multi-Provider TTS/RVC** | **Partially Implemented** | `TTSEngine.stop()` cleans up cleanly, but `speak_stream()` suppresses `CancelledError` on `_stop_requested`, `Singer` BGM isn't stopped, and Edge fallback voice mismatches. |
| **Closed-Loop Autonomous Missions (`AutonomousMissionExecutor`)** | **Partially Implemented** | Loop & approval gate work, but replanned goals never complete, replanning loops infinitely, and 0ms MC polling / disconnected simulation distort progress. |
| **AI-to-AI Collab (`/ws/collab`, `CollabManager`)** | **Partially Implemented** | HMAC-SHA256 works, but lacks replay protection, cooldown auto-recovery (`_refresh_cooldown`), `enabled=False` guard, and bidirectional Singer/VTS/Chess sync. |
| **Out-of-Process Plugin Sandbox (`core/plugins/`)** | **Partially Implemented** | Clean `env` strip (`leaks=[]`) and timeout kill work, but lacks OS filesystem/network jail and shares `hook_timeout_sec` with cold start. |
| **Server-Side Audio-Envelope Lip-Sync & Partial STT** | **Planned Capability** | Server emits a fixed 80 ms square wave (`0.95`/`0.50`) that fights browser `AnalyserNode` RMS; `stt_partial` only sends `"Listening..."`. |
| **Context Window Budgeter & Cross-Provider LLM Failover** | **Planned Capability** | Unbounded prompt concatenation; provider errors drop straight to offline mock text. |

---

## 3. Severity-Ranked Findings Register (Deduplicated)

### Critical (7 Findings)
1. **`[SEC-CRIT-001]`** (`VERIFIED`) — Unauthenticated `/ws` state-mutating actions (`memory_action`, `mood_action`, `relationship_action`, `minigame_action`, `story_action`, `trigger_improv`) & pre-auth sensitive state push (`run.py:780-790, 815-921, 927-1604`).
2. **`[SEC-CRIT-002]`** (`VERIFIED`) — Plugin subprocess sandbox lacks filesystem/network/RLIMIT isolation, trusts self-declared manifest permissions, executes top-level code at discovery, and allows `inprocess` mode (`core/plugins/registry.py:63-73, 372-383, 448-452`).
3. **`[COLLAB-CRIT-001]` / `[QA-CRIT-001]` / `[SEC-HIGH-005]`** (`REPRODUCED`) — Zero replay protection on signed `CollabEnvelope` (no `message_id` nonce cache or `timestamp` skew check; `core/collab/manager.py:470-488`).
4. **`[AUDIO-CRIT-001]`** (`VERIFIED`) — `TTSEngine.speak_stream()` swallows `CancelledError` when `_stop_requested=True`, allowing `Orchestrator._execute_interaction()` to emit `ai_response` / Minecraft / Discord replies after barge-in (`core/tts.py:588-600`, `core/orchestrator.py:1531-1567`).
5. **`[AUDIO-CRIT-002]`** (`VERIFIED`) — Server lip-sync is a synthetic 80 ms square wave (`0.95`/`0.50`) that collides with browser `AnalyserNode` RMS in `output_mode="both"` (`core/tts.py:646-685`, `web/overlay.js:219-221`, `web/app.js:449-450`).
6. **`[COG-CRIT-001]`** (`REPRODUCED`) — Replanned goals can never reach `COMPLETED` because `Goal.recalculate_progress()` includes `REPLANNED` subtasks in the denominator (`core/planning/models.py:107-112`).
7. **`[COG-CRIT-002]`** (`VERIFIED`) — Infinite 25s replan loop and unbounded `goals.json`/`agenda.md` growth (`attempts` never capped in `core/planning/executor.py:568-603` or `replanner.py`).
8. **`[GAME-CRIT-001]`** (`VERIFIED`) — Unsynchronized `chess.Board` mutation between `asyncio.to_thread(alpha_beta)` and event-loop handlers (`core/chess/controller.py:197-206`, `chess_engine.py:184-207`).
9. **`[GAME-CRIT-002]` / `[QA-HIGH-002]`** (`REPRODUCED`) — `MinecraftController` has no Node.js bridge crash recovery, leaves `connection_status="connected"` on drop, and `minecraft/bot.js` leaks `setInterval` timers & swallows `uncaughtException` (`core/minecraft/controller.py:340-343`, `minecraft/bot.js:6-9, 417-432`).

### High (21 Deduplicated Findings)
- **Infrastructure & Performance:** `[INFRA-HIGH-001]` (12+ untracked `asyncio.create_task` leaks), `[INFRA-HIGH-002]` (`perform_song()` bypasses `_busy_lock`), `[INFRA-HIGH-003]` / `[PERF-HIGH-001]` (`REPRODUCED` sequential `EventBus.publish()` head-of-line blocking & unbounded `publish_nowait`), `[INFRA-HIGH-004]` (unbounded `ChatReceiver.queue` & `get_event_loop().time()`), `[INFRA-HIGH-005]` (`SECRET_MASK_FIELDS` omits `llm.gemini_api_key`/`openai_api_key` & fixed `.tmp` filename).
- **Audio & Real-Time:** `[AUDIO-HIGH-001]` (`transcribe_wav_bytes` blocks WS receive loop), `[AUDIO-HIGH-002]` (barge-in does not stop `Singer` BGM), `[AUDIO-HIGH-003]` (Edge fallback voice mismatch, hardcoded `audio/mpeg` MIME, `Singer` provider bypass), `[AUDIO-HIGH-004]` (double temp-file disk I/O & unpooled `aiohttp` sessions).
- **Cognition & Memory:** `[COG-HIGH-001]` (0ms MC inventory polling vs. fabricated offline progress), `[COG-HIGH-002]` (unbounded prompt assembly & mismatched `max_tokens`), `[COG-HIGH-003]` (`is_creator` dropped on live LLM paths & fallbacks), `[COG-HIGH-004]` (duplicate `EmbeddingEngine` in `EpisodicMemoryStore`), `[COG-HIGH-005]` (vector search capped at 300 rows & unsafe hash overwrite).
- **Collab:** `[COLLAB-HIGH-001]` (`REPRODUCED` `_is_loopback_url` substring spoofing), `[COLLAB-HIGH-002]` (WS query-string secrets & global `shared_secret` mutation race), `[COLLAB-HIGH-003]` (`REPRODUCED` permanent `"cooldown"` deadlock in `_refresh_cooldown()`), `[COLLAB-HIGH-004]` (concurrent collab reply task storm).
- **Games / OBS / Vision / Clips:** `[GAME-HIGH-001]` (`VisualAnalyzer` `TypeError` on `detected_label`), `[GAME-HIGH-002]` / `[QA-HIGH-003]` (`REPRODUCED` `OBSWebSocketClient` leaves `is_connected=True` on failure), `[GAME-HIGH-003]` (`replay_saved=True` set before async OBS save), `[GAME-HIGH-004]` (`ffmpeg` missing `-nostdin`, timeout, & cleanup), `[GAME-HIGH-005]` (`Singer` cumulative TTS drift & blocking `pygame`).
- **Security & Frontend & QA:** `[SEC-HIGH-001]` (`_is_ws_creator_authorized` breaks Docker/LAN Creator auth), `[SEC-HIGH-002]` (unauthenticated `GET /api/*` routes), `[SEC-HIGH-003]` (arbitrary file overwrite `ffmpeg -y` & filtergraph injection), `[SEC-HIGH-004]` (non-blocking `Moderator`, dead `strict_mode`/`prompt_injection_filter`, unsanitized `user`/`donation_amount`), `[UI-HIGH-001]` (stored DOM XSS in `/settings`), `[UI-HIGH-002]` (`/` & `/settings` missing token UI & crash on `401/403`), `[UI-HIGH-003]` (2s WS reconnect storm, missing `overlay.js` `onopen` re-sync, `deck.js` double-WS race), `[QA-HIGH-001]` (`REPRODUCED` flaky subprocess plugin cold-start timeout).

### Medium & Low Highlights
- **Medium:** Dead config keys (`[INFRA-MED-002]`, `[COG-MED-004]`, `[AUDIO-MED-002]`, `[AUDIO-MED-003]`), sync disk/SQLite I/O on event loop (`[INFRA-MED-003]`, `[COG-MED-003]`, `[PERF-MED-001]`, `[PERF-MED-002]`), SSRF via unvalidated outbound URLs (`[SEC-MED-001]`), Docker/LAN hardening (`[SEC-MED-004]`), `collab.enabled=False` not enforced (`[COLLAB-MED-001]`), non-utterance collab flood (`[COLLAB-MED-002]` / `[QA-MED-002]`), AudioWorklet resampler/tail-frame bug (`[UI-MED-002]`), external CDN VRM/fonts (`[UI-MED-004]`), dead plugin entry retained after crash (`[QA-MED-001]`), tests mutating `data/` (`[QA-MED-003]`).
- **Low:** `stt_partial` dead path (`[AUDIO-LOW-001]`), `promises.md` append-only (`[COG-LOW-002]`), static `/settings` status pill (`[UI-LOW-001]`), `localStorage` token + `?token=` exposure (`[UI-LOW-002]` / `[SEC-MED-002]`).

---

## 4. Test & Chaos Verification Summary

- **Python Suite (`-W default`):** 315 tests in 21.277s — **1 Error** (`test_hard_timeout_kills_infinite_loop_subprocess` failed under load due to `[QA-HIGH-001]`; passed 5/5 standalone). Zero `DeprecationWarning`/`ResourceWarning` tracebacks; 13+ `asyncio` slow-callback warnings (`0.109s–0.235s`).
- **Node.js & Frontend Checks:** `node tests/test_guard_runner.js` **PASSED**; `node --check web/*.js` **PASSED** on all 5 files.
- **Chaos Scenarios A–E (`audit/10_chaos_testing.md`):**
  - **A (`EventBus`):** Exception isolation `VERIFIED`; sequential `publish()` stall `REPRODUCED` (`0.207s` on 200ms sub).
  - **B (`TTSEngine` Barge-In):** Clean task cancellation, `mouth=0.0`, and `0` temp-file leftovers `VERIFIED`.
  - **C (Plugin Sandbox):** Zero env secret leakage `VERIFIED` (`leaks=[]`); infinite loop killed at `0.811s`; dead crash entry retention `REPRODUCED`.
  - **D (`CollabManager`):** Invalid HMAC & unsigned-with-secret rejected; replay of 1h-old envelope accepted twice (`REPRODUCED`); `emote_sync` bypasses cooldown (`REPRODUCED`).
  - **E (Adapters):** `MinecraftController` and `OBSWebSocketClient` stale connected states `REPRODUCED`; `YouTubeLiveAdapter` HTTP 500 -> 200 recovery `VERIFIED`.

---

## 5. Top 10 Immediate Hardening Priorities

1. **Lock Down `/ws` & `GET /api/*` + Fix Docker/LAN Auth (`[SEC-CRIT-001]`, `[SEC-HIGH-001]`, `[SEC-HIGH-002]`)** — Gate all mutating/private WS actions & `GET /api/*` routes; check `MAYBEAI_CREATOR_TOKEN` before loopback in `_is_ws_creator_authorized()`.
2. **Fix `/settings` Stored DOM XSS & Add Creator Token UI (`[UI-HIGH-001]`, `[UI-HIGH-002]`)** — Escape all interpolated values in `web/settings.js` and add token prompt + `401/403` handling to `/` and `/settings`.
3. **Confine `ClipPipeline` Paths & Add `ffmpeg` Timeout (`[SEC-HIGH-003]`, `[GAME-HIGH-004]`)** — Restrict paths to `data/clips`, escape filtergraph chars, add `-nostdin` and `asyncio.wait_for`.
4. **Add Collab Replay Protection & Fix Cooldown Deadlock (`[COLLAB-CRIT-001]`, `[COLLAB-HIGH-001]`, `[COLLAB-HIGH-003]`)** — Enforce `message_id` nonce cache + `timestamp` window, fix `_is_loopback_url`, and reset `turn_count` in `_refresh_cooldown()`.
5. **Eliminate `EventBus` Head-of-Line Blocking & Track Async Tasks (`[PERF-HIGH-001]`, `[INFRA-HIGH-001]`, `[INFRA-HIGH-002]`)** — Per-WS bounded queues + concurrent `EventBus` dispatch, route all tasks through `_spawn_bg_task()`, and guard `perform_song()` with `_busy_lock`.
6. **Fix Barge-In `CancelledError` Propagation & `Singer` Stop (`[AUDIO-CRIT-001]`, `[AUDIO-HIGH-002]`, `[AUDIO-HIGH-001]`)** — Prevent post-barge-in broadcasts/replies, stop `pygame.mixer.music` on barge-in, and offload `transcribe_wav_bytes()`.
7. **Fix Chess Thread Safety & Minecraft/OBS Disconnect Recovery (`[GAME-CRIT-001]`, `[GAME-CRIT-002]`, `[GAME-HIGH-002]`)** — Clone `chess.Board` before `to_thread`, reset `connection_status`/`is_connected` on socket drop, and clear leaked timers in `bot.js`.
8. **Unblock Autonomous Goals & Cap Replan Attempts (`[COG-CRIT-001]`, `[COG-CRIT-002]`, `[COG-HIGH-001]`)** — Exclude `REPLANNED` subtasks from completion denominator, enforce `MAX_REPLAN_ATTEMPTS`, and replace 0ms MC polling.
9. **Harden Plugin Sandbox & Cold-Start Timeout (`[SEC-CRIT-002]`, `[QA-HIGH-001]`, `[QA-MED-001]`)** — Separate `startup_timeout_sec` from `hook_timeout_sec`, evict crashed workers, and enforce host-approved plugin permissions.
10. **Enforce Prompt Injection Filtering & Mask LLM Keys (`[SEC-HIGH-004]`, `[INFRA-HIGH-005]`)** — Wire `strict_mode` / `prompt_injection_filter` to drop flagged chat, sanitize `user`/`donation_amount`, and mask `llm.*_api_key` in `ConfigManager`.
