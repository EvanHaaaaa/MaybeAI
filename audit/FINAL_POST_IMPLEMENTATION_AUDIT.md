# MaybeAI — Post-Implementation Technical Audit (`FINAL_POST_IMPLEMENTATION_AUDIT.md`)

**Lead Synthesizer:** `ng-qa` (Agent 8)  
**Audit Team:** 8-Agent Swarm (`ng-infra`, `ng-audio`, `ng-cognition`, `ng-collab`, `ng-games`, `ng-sec`, `ng-frontend`, `ng-qa`)  
**Target Baseline:** `d:\projects\MaybeAI` at `HEAD` commit `96b7315` (Post-Horizon 0–3 + YouTube Karaoke)  
**Source Reports:** [00_repository_inventory.md](file:///d:/projects/MaybeAI/audit/00_repository_inventory.md) through [13_production_readiness.md](file:///d:/projects/MaybeAI/audit/13_production_readiness.md)

---

## 1. Executive Summary

Following the Horizon 0–3 hardening sprints (`4c4e473` through `1953889`) and the YouTube Song Request / Auto-Karaoke release (`83298fa`), MaybeAI has progressed from an unhardened L1.5–L2.5 prototype to a **hardened, modular single-node AI VTuber platform (overall L3.0–L3.5)**.

- **Verification Baseline:** `381` Python `unittest` cases across `43` test modules (`380` passed, `1` skipped: Playwright browser E2E because `playwright` is not installed), `node tests/test_guard_runner.js` passed, and `node --check` passed on all `7` JS/Worklet/Bot files.
- **Major Wins Delivered:** Origin + token-first Creator authentication on mutating/sensitive HTTP & WS endpoints, `EventBus` concurrent dispatch + bounded `publish_nowait` (`256`) & `ChatReceiver.queue` (`500`), `ProviderCircuitBreaker` cross-provider LLM failover, full-duplex `AudioWorklet` 16 kHz binary PCM + `EnergyVAD` barge-in, `HMAC-SHA256` + SSRF-guarded 2-peer Collab protocol, OS-isolated plugin subprocesses (`bwrap` / `_WindowsJobObject`) with default-deny permissions, and offline vendored Three-VRM (`web/vendor/`).
- **Primary Blockers Before Unattended 24/7 / Horizon 4:**
  1. Frontend `web/shared-client.js` still passes `?token=` in WS URLs and stores tokens in `localStorage` (`SEC-GAP-001`).
  2. Windows plugin sandbox relies on bypassable Python monkeypatches (`SEC-GAP-002`).
  3. Indirect VLM/OCR prompt injection via raw `obs.summary` (`SEC-GAP-003`).
  4. Missing per-WS outbound `asyncio.Queue(maxsize=64)` (`INFRA-MED-001-RES`), `ClientTimeout(total=1.8)` truncating >1.8s LLM streams (`AUDIO-MED-001`), and `CollabManager.disconnect_peer()` not resetting `floor_state` from `"listening"` to `"idle"` (Chaos Scenario B).

---

## 2. Repository Inventory Summary

Verified in [00_repository_inventory.md](file:///d:/projects/MaybeAI/audit/00_repository_inventory.md):
- **Core Python (`core/`):** `97` `.py` files (`14` top-level + `83` across `18` subpackages), anchored by `run.py` (`1,935` lines), `core/orchestrator.py` (`2,197` lines), `core/config_manager.py` (`2,317` lines, `24` sections, `157` leaf keys), and `core/brain.py` (`1,239` lines).
- **Web Frontend (`web/`):** `19` files across 4 entry points (`/`, `/settings`, `/overlay`, `/deck`) + `5` offline-vendored files in `web/vendor/` (zero CDN dependencies).
- **Minecraft Bridge (`minecraft/`):** `bot.js`, `casual.js`, `guard.js`, `speedrun.js`, `config.json`, bundled `node/` & `node_modules/`.
- **Tests (`tests/`):** `43` Python test modules (`381` test cases) + `__init__.py` + `tests/test_guard_runner.js`.
- **Containerization:** `Dockerfile` (`python:3.12-slim`, `ffmpeg`, non-root `maybeai`, `HEALTHCHECK` on `/api/health`) and `docker-compose.yml`.

---

## 3. Git & Milestone Verification (`4c4e473`..`96b7315`)

Verified in [01_git_milestone_verification.md](file:///d:/projects/MaybeAI/audit/01_git_milestone_verification.md):

| Commit | Milestone | Scope Verified |
|---|---|---|
| `4c4e473` | **Horizon 0** (`H0-01..H0-09`) | Auth gating, XSS neutralization, `ClipPipeline` confinement, Collab replay/SSRF, `EventBus`/`_spawn_bg_task`/`_busy_lock`, `barge_in` `CancelledError`, Chess `board.copy()`, Goal `REPLANNED` & retry cap, `llm.*_api_key` masking. |
| `36ba58e` | **Horizon 1** (`H1-01..H1-07`) | Non-blocking STT, RMS lip-sync, TTS fallback/MIME, `ContextBudgetManager`, `is_creator` plumbing, `ChatReceiver(maxsize=500)`, 157/157 config schema, atomic `mkstemp` writes. |
| `a08e435` | **Horizon 2** (`H2-01..H2-07`) | `ProviderCircuitBreaker`, mood-modulated sampling, `web/shared-client.js`, binary PCM WS frames, local `web/vendor/`, `MetricsCollector` (`/api/metrics`). |
| `1953889` | **Horizon 3** (`H3-01..H3-06`) | OS plugin sandbox + `granted_permissions`, `validate_outbound_url`, bidirectional collab sync, Stockfish UCI, VLM/RPG showrunner hooks, `tests/test_e2e_browser.py`. |
| `83298fa` | **YouTube Karaoke** | `core/youtube_karaoke.py` SSRF-safe `yt-dlp`/`demucs`/`ffmpeg`/RVC pipeline, VTT/SRT parser, `/api/performance/youtube`, Studio UI bar. |
| `96b7315` | **Docs** | `README.md` updated (`24` config sections, `381` tests). Minor drift: `FastAPI-0.115+` badge vs `>=0.110.0` in `pyproject.toml`; `strategy/` docs remain pre-H0 historical snapshots. |

---

## 4. Current Architecture

MaybeAI operates as a **single-process async FastAPI + EventBus monolith** (`run.py` + `core/orchestrator.py`) with isolated subprocesses for untrusted plugins (`core/plugins/sandbox_worker.py`), external media tools (`yt-dlp`, `ffmpeg`, `demucs`), and the Node.js Mineflayer bridge (`minecraft/bot.js`).
- **Control & Event Plane:** Typed async `EventBus` (`core/event_bus.py`) bridges internal subsystems to `/ws` web listeners (`_dispatch_to_web_listeners`).
- **Cognitive & Memory Plane:** `ConversationEngine` + `Brain` (`ContextBudgetManager`, `ProviderCircuitBreaker`) backed by SQLite WAL + FTS5 + dense vector scan (`MemoryDatabase`, `vector_scan_limit=2000`) and Markdown Second Brain sync.
- **Real-Time Media Plane:** `AudioWorklet` 16 kHz binary PCM → bounded `voice_queue` → `STTEngine`/`EnergyVAD` → `TTSEngine` (`edge-tts`/`kokoro`/`elevenlabs`/`custom` + `RVCVoiceConverter`) → 50ms RMS lip-sync + browser `AnalyserNode` arbitration (`isLocalAudioPlaying`).

---

## 5. 8-Agent Audit Results & L0–L5 Maturity Scorecard

| Domain | Auditor | Score | Key Verified Strengths | Key Remaining Gaps |
|---|---|---|---|---|
| **Core Infrastructure** | `ng-infra` | **L3.5** | `_spawn_bg_task`, `_busy_lock`, `ChatReceiver(500)`, `mkstemp` atomic config, 157/157 schema | Missing per-WS outbound queue; 4 dead config keys; sync disk/engine I/O on event loop (`0.11s–0.19s` slow callbacks) |
| **Voice & Real-Time Audio** | `ng-audio` | **L3.5** | 16 kHz binary PCM, `EnergyVAD` barge-in, `speak_stream()` `CancelledError`, `ProviderCircuitBreaker` | `ClientTimeout(total=1.8)` truncates >1.8s streams; `TTSEngine.speak()` swallows `CancelledError`; `Singer` missing provider config in `reload_settings` |
| **Avatar & Lip-Sync** | `ng-audio` | **L3.5** | 50ms RMS envelope, `isLocalAudioPlaying` arbitration, VTS token persistence & reconnect | `MouthSmile` vs `MouthForm` split; duplicate VTS reconnect check |
| **Memory & Cognition** | `ng-cognition` | **L2 / L3** | `ContextBudgetManager`, `is_creator` plumbing, `MoodEngine` temp modifier (**L3**), `MAX_REPLAN_ATTEMPTS=3` | 2000-row linear vector scan; `Goal.reflection` write-only; `promises.md` fulfillment unwired; RAG + sliders (no causal learning) |
| **AI Collaboration** | `ng-collab` | **L2.5** | HMAC-SHA256, `±60s` skew, 1024-nonce LRU, `NaN` rejection, SSRF guard, Bearer/subprotocol auth | Subsystems don't auto-emit sync frames; `on_hello` dead code; `disconnect_peer()` leaves `floor_state="listening"`; 2-peer only |
| **Games, Vision & Entertainment** | `ng-games` | **L3** | Chess `board.copy()` + Stockfish fallback, `bot.js` timer cleanup, `ClipPipeline` confinement, `YouTubeKaraokeProcessor` | Missing host binaries (`yt-dlp`/`ffmpeg`/`demucs`/`stockfish`/`obsws-python`) prevent live media E2E; `startAutonomyLoop()` uncalled; no OBS/MC auto-reconnect |
| **Security & OT** | `ng-sec` | **L3** | Origin + Creator auth gating, AST plugin manifest + default-deny, `Moderator` injection drop, 8/8 secret masking | Frontend `?token=` & `localStorage` (`SEC-GAP-001`); Windows Python monkeypatch sandbox (`SEC-GAP-002`); raw `obs.summary` prompt injection (`SEC-GAP-003`) |
| **Frontend & Avatar UX** | `ng-frontend` | **L3** (DX **L2**) | `MaybeAIClient`, `/settings` XSS neutralization + `401/403` UI, `/overlay` re-sync, offline `web/vendor/` | 4 separate apps with duplicated boilerplate; 5 unguarded `ws.readyState` calls in `app.js`; 0 `:focus-visible`/`prefers-reduced-motion` rules |
| **QA, Reliability & Observability** | `ng-qa` | **L3.5 / L3.0** | `380/381` Python tests + `GuardRunner` + `node --check` pass; `/api/health`, `/api/metrics` | Playwright E2E skipped; `ResourceWarning`s & slow callbacks; no `RotatingFileHandler` |

---

## 6. Cross-Module Integration Summary

Traced in full in [10_cross_module_integration.md](file:///d:/projects/MaybeAI/audit/10_cross_module_integration.md) (Flows **A–G**):
- **Strong Seams:** `EventBus` exception/timeout isolation, `Orchestrator._busy_lock` + `barge_in()` cancellation, `Moderator` ingress filtering, and `PluginRegistry` AST + JSON-RPC timeout isolation.
- **Weak Seams:** Synchronous `_ingest_message` disk/DB calls on the event loop; `CollabManager` inbound-only subsystem wiring & stale `floor_state` on disconnect; `HighlightDetector` async replay callback updating `replay_saved` after `HIGHLIGHT_MARKED` is emitted.

---

## 7. Security Assessment

Verified in [07_security.md](file:///d:/projects/MaybeAI/audit/07_security.md) (**Overall: L3**):
- **Remediated:** Mutating/sensitive HTTP & WS routes gated by Origin + token-first Creator auth; `ClipPipeline` confined via `is_relative_to()` + filtergraph escaping; `YouTubeKaraokeProcessor` canonicalizes URLs & checks SSRF; `ConfigManager` masks all 8 secret fields.
- **Open Gaps:** `SEC-GAP-001` (`?token=` + `localStorage`), `SEC-GAP-002` (Windows plugin FS/net monkeypatch bypassable via `ctypes`/`subprocess`), `SEC-GAP-003` (indirect VLM/OCR prompt injection via `obs.summary`), `SEC-GAP-004` (`validate_outbound_url` DNS-rebinding TOCTOU), `SEC-GAP-005` (`yt-dlp` missing `--max-filesize` & concurrent job cap).

---

## 8. Chaos Testing Summary (Scenarios A–H)

Executed in isolated temp/in-memory probes ([11_chaos_testing.md](file:///d:/projects/MaybeAI/audit/11_chaos_testing.md)):
- **PASS:** **A** (50 msgs + SuperChat + Karaoke + Barge-in on `EventBus` in `0.28ms`, `0` errors), **C** (`Moderator` blocks prompt injection & strips control/delimiter metadata), **D** (`MemoryDatabase` preserves `[384]*5` vectors on 128-d hash query without crash), **F** (`PluginRegistry` `os_isolated`/`windows_job_object` + timeout/exception isolation), **G** (`ProviderCircuitBreaker` `closed` → `open` → `half_open` → `closed`), **H** (500-listener fan-out `2.159ms`/broadcast, 2000-row vector scan `45.32ms`).
- **PARTIAL:** **B** (`CollabManager.disconnect_peer()` leaves `floor_state="listening"`), **E** (stdout-only `print()` + `aiohttp` `ResourceWarning`s).

---

## 9. Performance & Soak Analysis

Detailed in [12_performance_analysis.md](file:///d:/projects/MaybeAI/audit/12_performance_analysis.md):
- **WS Fan-Out:** `0.074ms` (10 clients) → `0.262ms` (100) → `2.159ms` (500) per broadcast; single stalled client caps at `2.0s` due to missing per-WS outbound queue.
- **Vector Scan:** `13.54ms` (100 rows) → `45.32ms` (2000 rows), bounded by `vector_scan_limit=2000`.
- **8–12h Soak:** **Feasible** under supervision with Docker log rotation (`max-size`/`max-file`) and `Orchestrator.shutdown()` cleanup; watch `rss_mb` and `bg_tasks_active` via `/api/metrics`.

---

## 10. Test Coverage & Gaps

Verified in [09_qa_reliability.md](file:///d:/projects/MaybeAI/audit/09_qa_reliability.md):
- `381` `unittest` cases (`380` passed, `1` skipped: `TestPlaywrightBrowserE2E` due to missing `playwright`), `node tests/test_guard_runner.js` passed, `node --check` passed on all `7` JS files, `git status --short data/` clean.
- **Warnings (`-W default`):** Multiple `asyncio` slow callbacks (`0.109s–0.282s`) and `ResourceWarning`s (unclosed `aiohttp.ClientSession`/connector, socket/ProactorSocketTransport, subprocess).

---

## 11. Technical Debt Register

1. **Dead Config Keys (`INFRA-MED-002`):** `system.response_timeout_sec`, `performance.max_concurrent_tasks`, `performance.websocket_ping_interval_sec`, `performance.audio_buffer_size_kb` unwired in `run.py`/`Orchestrator`.
2. **Monolithic Frontend (`08_frontend_ux.md`):** 4 separate HTML/JS apps; `web/app.js` (`5,896` lines) + `web/overlay.js` duplicate 2D/VRM/audio code and have 5 unguarded `ws.readyState` accesses.
3. **Unwired Cognitive Loops (`04_cognitive_memory.md`):** `Goal.reflection` write-only; `promises.md` fulfillment/archival methods uncalled; `StrategyReplanner` keyword-templated.
4. **Collab Asymmetric Wiring (`05_collab_protocol.md`):** Subsystems never auto-emit `duet_sync`/`emote_sync`/`game_move`; `Orchestrator._on_collab_hello` is dead code; 2-peer scalar state.
5. **Runtime Hygiene:** `print()` instead of `logging` + `RotatingFileHandler`; test teardown `ResourceWarning`s; `ClipPipeline`/`VODSummarizer` missing `.get_status()`.

---

## 12. Production Readiness Verdict

Verified in [13_production_readiness.md](file:///d:/projects/MaybeAI/audit/13_production_readiness.md):

| Deployment Profile | Verdict | Key Conditions / Blockers |
|---|---|---|
| **Supervised Localhost** (`127.0.0.1:7860`) | **GO** | Origin + Creator token controls, graceful offline degradation, `<50ms` DB/moderation latency. |
| **Authenticated LAN / Docker** (`MAYBEAI_HEADLESS=1`) | **CONDITIONAL GO** | Require strong `MAYBEAI_CREATOR_TOKEN`, Docker log rotation (`max-size`/`max-file`), container memory limits, and minimal `granted_permissions`. |
| **Unattended 24/7 Public Internet** | **NO-GO** | Blocked by `SEC-GAP-001`/`002`/`003`, `CollabManager.disconnect_peer()` stuck `floor_state`, `aiohttp` `ResourceWarning`s, and lack of structured log rotation / deep health checks. |

---

## 13. Critical Remediation Plan (Pre-Horizon 4)

| Priority | ID | Action | Target Files |
|---|---|---|---|
| **P0** | `SEC-GAP-001` | Switch frontend WS auth to `Sec-WebSocket-Protocol: maybeai.token.<token>`, remove `?token=` from `buildWsUrl()`, and move token from `localStorage` to `sessionStorage`/cookie. | `web/shared-client.js`, `run.py` |
| **P0** | `SEC-GAP-002` | Replace Python-level Windows plugin monkeypatches with restricted OS token/AppContainer or container isolation; disallow `inprocess` for external plugins. | `core/plugins/registry.py`, `core/plugins/sandbox_worker.py` |
| **P0** | `SEC-GAP-003` | Sanitize `obs.summary` / `obs.eve_commentary` via `Moderator.sanitize_metadata()` + untrusted-data delimiters before prompt injection. | `core/conversation/engine.py`, `core/vision/vlm.py` |
| **P1** | `INFRA-MED-001-RES` | Add per-WS bounded outbound `asyncio.Queue(maxsize=64)` + sender task in `run.py` to eliminate 2.0s broadcast HoL stalls. | `run.py`, `core/orchestrator.py` |
| **P1** | `AUDIO-MED-001` | Replace `ClientTimeout(total=1.8)` with `ClientTimeout(connect=1.8, sock_read=5.0)` so healthy LLM streams >1.8s are not truncated. | `core/brain.py` |
| **P1** | `AUDIO-MED-002/003` | Re-raise `CancelledError` in `TTSEngine.speak()`; forward neural TTS/fallback fields to `Singer.update_config()` in `reload_settings()`. | `core/tts.py`, `core/orchestrator.py` |
| **P1** | `CHAOS-B-001` | Reset `self.floor_state = "idle"` and clear `self.active_peer` in `CollabManager.disconnect_peer()`; wire `on_hello` in `set_action_callbacks()`. | `core/collab/manager.py` |
| **P2** | `FE-REL-001` | Guard all 5 `ws.readyState` calls in `web/app.js` with `ws &&`, complete `app.js` `onopen` re-sync, and add `:focus-visible` / `prefers-reduced-motion`. | `web/app.js`, `web/style.css` |
| **P2** | `OPS-001` | Add `RotatingFileHandler` structured logging, close `aiohttp` sessions cleanly in tests/teardown to eliminate `ResourceWarning`s, and install `playwright` in CI. | `core/`, `run.py`, `tests/` |
