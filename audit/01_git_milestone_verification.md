# Git Milestone Verification & Strategy Execution Matrix (`audit/01_git_milestone_verification.md`)

**Auditor:** AGENT 1 (`ng-infra`) — Core Infrastructure & Distributed Concurrency Auditor  
**Scope:** Verification of git milestone commits (`4c4e473`, `36ba58e`, `a08e435`, `1953889`, `83298fa`, `96b7315`), Strategy Execution Matrix against [FUTURE_DEVELOPMENT_MASTER_PLAN.md](file:///d:/projects/MaybeAI/strategy/FUTURE_DEVELOPMENT_MASTER_PLAN.md) & [DEVELOPMENT_ROADMAP.md](file:///d:/projects/MaybeAI/strategy/DEVELOPMENT_ROADMAP.md), and Documentation Drift analysis.

---

## 1. Git Milestone Commit Verification

| Commit | Date | Message | Diff Stat | Verification Status |
|---|---|---|---|---|
| `4c4e473` (`4c4e4737dd725d8b60e36bcae2b6d03aab7dcbb1`) | 2026-11-26 15:12:52 +0700 | `CTO Audit, Strategy Master Plan & Horizon 0 Security/Concurrency Hardening (H0-01..H0-09)` | 58 files changed, +5,586 / -472 | `VERIFIED` |
| `36ba58e` (`36ba58e6d5fa2f091791b7fca52c532ffaa6eb93`) | 2026-11-26 15:26:46 +0700 | `Horizon 1: Real-Time Audio, Cognitive Loop & Reliability (H1-01..H1-07)` | 26 files changed, +1,929 / -355 | `VERIFIED` |
| `a08e435` (`a08e43505ee69d7ed4c9c8f7412cebceabb71473`) | 2026-11-27 10:15:47 +0700 | `Horizon 2: Companion Intelligence, Observability & UX (H2-01..H2-07)` | 32 files changed, +69,156 / -262 | `VERIFIED` |
| `1953889` (`19538895241dec4d184b8441aa81f17dc7770222`) | 2026-11-27 10:40:45 +0700 | `Horizon 3: Ecosystem, OS Plugin Sandbox, Bidirectional Collab & E2E (H3-01..H3-06)` | 19 files changed, +2,661 / -99 | `VERIFIED` |
| `83298fa` (`83298fa8a89fcc95a91cafa2fc00c0cbd08de4b5`) | 2026-11-27 11:21:15 +0700 | `Feature: YouTube Song Request & AI Cover / Auto-Karaoke Pipeline` | 9 files changed, +812 / -6 | `VERIFIED` |
| `96b7315` (`96b731585ac71233b98456c6c2001a3060796766`) | 2026-11-27 11:27:13 +0700 | `Docs: Update README.md with post-Horizon 3 & YouTube Karaoke progress` | 1 file changed, +83 / -44 | `VERIFIED` |

---

## 2. Strategy Execution Matrix

| Initiative | Original Proposal | Current Status | Evidence | Remaining Gap |
|---|---|---|---|---|
| **H0-01** (`/ws`, `GET /api/*`, Docker/LAN Auth) | Gate mutating `/ws` actions & `GET /api/*`; token-first check for Docker/LAN (`run.py`) | `EXISTING` (`VERIFIED`) | `_is_http_creator_authorized`, `_is_ws_creator_authorized`, `_CREATOR_ONLY_WS_ACTIONS`, `_PRIVATE_WS_EVENTS` in [run.py](file:///d:/projects/MaybeAI/run.py#L98-L170); `tests/test_horizon0_hardening.py` | None in core auth gating (note WS query-param fallback remains for legacy clients alongside Bearer/subprotocol). |
| **H0-02** (`/settings` XSS & Creator Token UI) | Escape dynamic `innerHTML` in `web/settings.js`; add Creator token prompt + `401/403` handling | `EXISTING` (`VERIFIED` in git) | Commit `4c4e473` modified `web/settings.js`, `web/app.js`, `web/index.html`, `web/settings.html` | Delegated to Frontend auditor for deep DOM XSS re-verification. |
| **H0-03** (`ClipPipeline` confinement & `ffmpeg` timeout) | Confine `ClipPipeline` to `data/clips` + `ffmpeg -nostdin`/timeout | `EXISTING` (`VERIFIED` in git) | Commit `4c4e473` modified `core/highlights/clipper.py`, `run.py` | Delegated to Game/Security auditors. |
| **H0-04** (Collab Replay, Loopback & Cooldown Recovery) | `message_id` nonce + `±60s` skew, `urlparse` loopback check, cooldown recovery | `EXISTING` (`VERIFIED` in git) | Commit `4c4e473` modified `core/collab/manager.py`, `core/collab/protocol.py` | Delegated to Collab/Security auditors. |
| **H0-05** (`EventBus` HoL & Task Tracking) | Concurrent `EventBus.publish()`, per-WS bounded `asyncio.Queue(maxsize=64)`, `_spawn_bg_task()`, `_busy_lock` on `perform_song()` | `INCOMPLETE` (`PARTIALLY VERIFIED`) | [core/event_bus.py](file:///d:/projects/MaybeAI/core/event_bus.py#L192-L253) (`asyncio.gather`, `max_pending_tasks=256`); [core/orchestrator.py](file:///d:/projects/MaybeAI/core/orchestrator.py#L288-L295,L427-L443,L1818-L1828) (`_spawn_bg_task`, `_dispatch_to_web_listeners` gather, `perform_song` lock) | **No per-WS outbound `asyncio.Queue(maxsize=64)`** in `run.py:963-971`; `_dispatch_to_web_listeners` still awaits `websocket.send_json()` with `timeout=2.0` per publish. |
| **H0-06** (Barge-In `CancelledError` & `Singer` BGM Stop) | Re-raise `CancelledError` in `speak_stream()`, stop `Singer` BGM on `barge_in()` | `EXISTING` (`VERIFIED` in git) | Commit `4c4e473` modified `core/tts.py`, `core/singer.py`, `core/orchestrator.py` | Delegated to Audio auditor. |
| **H0-07** (Chess Thread Safety & MC/OBS Recovery) | Clone `chess.Board` before `to_thread`, fix MC/OBS disconnect state & `bot.js` timers | `EXISTING` (`VERIFIED` in git) | Commit `4c4e473` modified `core/chess/`, `core/minecraft/controller.py`, `minecraft/bot.js`, `core/desktop/obs_client.py` | Delegated to Game Engines auditor. |
| **H0-08** (Unblock Goals & Cap Replan Attempts) | Exclude `REPLANNED` from progress denominator, cap `MAX_REPLAN_ATTEMPTS=3` | `EXISTING` (`VERIFIED` in git) | Commit `4c4e473` modified `core/planning/executor.py`, `models.py`, `replanner.py` | Delegated to Cognitive auditor. |
| **H0-09** (Plugin Timeout, Eviction & Prompt Injection Gate) | `startup_timeout_sec`, crash eviction, `Moderator.strict_mode`, mask `llm.*_api_key` | `EXISTING` (`VERIFIED`) | `SECRET_MASK_FIELDS` in [core/config_manager.py](file:///d:/projects/MaybeAI/core/config_manager.py#L258-L267); `_ingest_message` in [core/orchestrator.py](file:///d:/projects/MaybeAI/core/orchestrator.py#L1205-L1218) | Plugin sandbox details delegated to Security auditor. |
| **H1-01..H1-07** (Real-Time Audio, Cognitive Loop, `ChatReceiver`, Config Schema) | Non-blocking STT, RMS lip-sync, TTS fallback/MIME, `aiohttp` pooling, `ContextBudgetManager`, `is_creator` plumbing, `ChatReceiver(maxsize=500)`, complete config schema, test hygiene | `INCOMPLETE` (`PARTIALLY VERIFIED`) | Commit `36ba58e`; [core/chat_receiver.py](file:///d:/projects/MaybeAI/core/chat_receiver.py#L26,L37-L40) (`maxsize=500`, `time.monotonic()`); [core/config_manager.py](file:///d:/projects/MaybeAI/core/config_manager.py#L270-L290) (`mkstemp`, 157 schema paths == 157 defaults) | 4 config keys (`response_timeout_sec`, `max_concurrent_tasks`, `websocket_ping_interval_sec`, `audio_buffer_size_kb`) remain unwired; `save_config()` still merges unknown keys; sync `/api/config*` & `_ingest_message()` still cause >100ms asyncio slow-callback warnings in tests. |
| **H2-01..H2-07** (Failover, Mood Sampling, `shared-client.js`, Binary WS, Vendored VRM, Metrics) | `ProviderCircuitBreaker`, mood-modulated sampling, `web/shared-client.js`, binary PCM WS frames, local `web/vendor/` VRM/fonts, `MetricsCollector` (`/api/metrics`) | `EXISTING` (`VERIFIED`) | Commit `a08e435`; [core/metrics.py](file:///d:/projects/MaybeAI/core/metrics.py); [run.py](file:///d:/projects/MaybeAI/run.py#L545,L1125-L1134); `web/shared-client.js`; `web/vendor/` (5 files); `tests/test_horizon2_companion.py` | 4-hour soak test harness status delegated to QA/Perf auditors. |
| **H3-01..H3-06** (OS Plugin Sandbox, SSRF Guard, Bidirectional Collab, Clock-Locked Karaoke, VLM/RPG, Playwright E2E) | `plugins.granted_permissions` default-deny, `validate_outbound_url`, bidirectional `duet_sync`/`emote_sync`/`game_move`, Stockfish UCI, VLM+Storytelling, `tests/test_e2e_browser.py` | `EXISTING` (`VERIFIED`) | Commit `1953889`; [core/security_net.py](file:///d:/projects/MaybeAI/core/security_net.py); `tests/test_horizon3_collab_ssrf.py`, `tests/test_horizon3_ecosystem.py`, `tests/test_e2e_browser.py` | Playwright E2E skips (`1 skipped`) when `playwright` is not installed. |
| **YouTube Song Request & AI Cover** (`83298fa`) | SSRF-safe YouTube download, stem separation, RVC conversion, VTT/SRT lyrics, `POST /api/performance/youtube`, UI controls | `EXISTING` (`VERIFIED`) | [core/youtube_karaoke.py](file:///d:/projects/MaybeAI/core/youtube_karaoke.py); [core/orchestrator.py](file:///d:/projects/MaybeAI/core/orchestrator.py#L1830-L1874); `tests/test_youtube_karaoke.py` | Requires optional `yt-dlp` / `ffmpeg` / `demucs` at runtime (graceful error if absent). |
| **R&D Experiments (`EXP-001`..`EXP-003`)** | Gated experiments for Silero-VAD/kokoro-onnx, `sqlite-vec`+FTS5, 2h Mineflayer soak | `PLANNED` (`NOT VERIFIED`) | `research/experiments/EXP-001.md`..`EXP-003.md` | Not part of H0–H3 commits; benchmark gates remain future R&D. |

---

## 3. Documentation Drift Analysis

| Document / Claim | Observed Reality | Drift Classification |
|---|---|---|
| [README.md](file:///d:/projects/MaybeAI/README.md#L151,L275) — "24 Kategori Pengaturan Lengkap" (`24 section`) | `len(ConfigManager.DEFAULT_SETTINGS)` == **24** sections (`157` leaf keys, `157` schema paths) | `VERIFIED` (No drift) |
| [README.md](file:///d:/projects/MaybeAI/README.md#L15,L354) — "43 modul pengujian ... (381 tests)" / "380 Passed, 1 Skipped" | `tests/test_*.py` == **43** modules; `unittest` discovery == **381** tests | `VERIFIED` (No drift on counts) |
| [README.md](file:///d:/projects/MaybeAI/README.md#L14) — `FastAPI-0.115+` badge | [pyproject.toml](file:///d:/projects/MaybeAI/pyproject.toml#L13) & [requirements.txt](file:///d:/projects/MaybeAI/requirements.txt) specify `fastapi>=0.110.0` | Minor version badge drift |
| [README.md](file:///d:/projects/MaybeAI/README.md#L318) — `data/karaoke_cache/` in directory tree | `data/karaoke_cache/` is created dynamically at runtime, not present in repo tree | Minor runtime-dir drift |
| [strategy/FUTURE_DEVELOPMENT_MASTER_PLAN.md](file:///d:/projects/MaybeAI/strategy/FUTURE_DEVELOPMENT_MASTER_PLAN.md#L11,L25-L40) & [strategy/CURRENT_STATE_ASSESSMENT.md](file:///d:/projects/MaybeAI/strategy/CURRENT_STATE_ASSESSMENT.md) | Still cite pre-H0 baseline ("94 Python modules", "315 Python tests", "NO-GO" verdicts, L1.5–L2.5 scorecard) | **Stale pre-H0 strategic docs** (expected historical snapshot, but superseded by H0–H3) |
| Pre-update `audit/00_repository_inventory.md` & `audit/01_core_infrastructure.md` | Listed 94 `core/` modules, 13 `web/` files, 39 `tests/` files, and pre-H0 findings | Superseded by this post-H3 audit (`audit/00` & `audit/02`) |
