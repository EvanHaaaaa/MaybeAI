# MaybeAI — Future Development Roadmap (`strategy/DEVELOPMENT_ROADMAP.md`)

**Owner:** AGENT 12 (`ng-strat-roadmap` — CTO Strategy & Roadmap Manager)  
**Baseline Grounding:** [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md) (`HEAD` `96b7315`) and [audit/00..13](file:///d:/projects/MaybeAI/audit/00_repository_inventory.md)  
**Verification Baseline:** `381` Python `unittest` cases across `43` modules (`380` passed, `1` skipped: Playwright), `node tests/test_guard_runner.js` passed, `node --check` passed on `7` JS files.  
**Estimation Method:** PERT 3-Point Estimation in engineering person-days ($O$ = Optimistic, $M$ = Most Likely, $P$ = Pessimistic, Expected $E = \frac{O + 4M + P}{6}$, Std Dev $\sigma = \frac{P - O}{6}$). Calendar windows assume 2 parallel workstreams unless serialized by a critical-path dependency.

---

## Executive Summary: Completed vs. Planned Horizons

> [!NOTE]
> **Horizons 0–3 are COMPLETE** (`4c4e473`..`1953889`, plus YouTube Karaoke `83298fa` and docs `96b7315`). MaybeAI currently sits at **overall L3.0–L3.5** (**GO** for Supervised Localhost, **CONDITIONAL GO** for Authenticated LAN/Docker, **NO-GO** for Unattended 24/7 Public Internet). This roadmap does **not** restart from Horizon 0; it begins with a focused **Pre-Horizon 4 Remediation Sprint** to clear the remaining §13 blockers, then charts **Horizons 4–8**.

| Phase / Horizon | Strategic Focus | Target Maturity / Verdict | PERT Expected ($E$) | $\sigma$ | Calendar Window (2-Stream) |
|---|---|---|---:|---:|---|
| **Pre-H4 Remediation** | Close §13 P0/P1/P2 audit blockers & test/runtime hygiene | **Unattended 24/7 GO** | **13.5 person-days** | 1.6 | Weeks 1–2 (7–10 days) |
| **Horizon 4** | Cognitive & Companion Intelligence (ANN memory, causal reflection, `promises.md` loop) | **L4 Cognitive Companion** | **21.2 person-days** | 2.4 | Weeks 3–5 (11–14 days) |
| **Horizon 5** | Multimodal & Autonomous Evolution (Vision/Audio fusion, proactive showrunner, FE modularization) | **L4 Multimodal Autonomy** | **24.8 person-days** | 2.8 | Weeks 6–9 (13–17 days) |
| **Horizon 6** | Social & Multi-Agent Ecosystem (N-peer collab, federated plugins, Discord/Twitch/YT depth) | **L4.5 Multi-Agent Ecosystem** | **26.5 person-days** | 3.1 | Weeks 10–13 (14–18 days) |
| **Horizon 7** | Autonomous Content & Digital Presence (VOD/Clip factory, automated scheduling, creator analytics) | **L4.5 Content Studio** | **22.0 person-days** | 2.5 | Weeks 14–16 (11–15 days) |
| **Horizon 8** | Long-Term Digital Companion Ecosystem (Sovereign local-first cluster, SDK, lifelong identity) | **L5 Digital Companion Platform** | **28.5 person-days** | 3.4 | Weeks 17–21 (15–20 days) |
| **Total (Pre-H4 + H4–H8)** | **Post-H3 to L5 Autonomous Digital Companion Platform** | **Full L5 Platform** | **136.5 person-days** | — | **~17–21 Weeks** |

---

## Pre-Horizon 4 — Critical Remediation Sprint (P0 / P1 / P2)

**Objective:** Eliminate all verified §13 blockers from `FINAL_POST_IMPLEMENTATION_AUDIT.md` so MaybeAI achieves **GO for Unattended 24/7 Operation** before any Horizon 4 cognitive or autonomous expansion ships.

### `PH4-01` — WebSocket Subprotocol Auth & Token Storage Hardening (`SEC-GAP-001`) [P0]
- **Objective:** Remove `?token=` from WebSocket URLs and eliminate `localStorage` token persistence.
- **Current Limitation:** `web/shared-client.js` (`CreatorAuth.buildWsUrl()`) appends `?token=...` to `/ws` URLs and persists `maybeai_creator_token` in `localStorage`, exposing credentials in browser history, server logs, and XSS surfaces.
- **Proposed Implementation:** Pass auth via `Sec-WebSocket-Protocol: maybeai.token.<token>` in `shared-client.js`; update `run.py` WS handshake to parse & echo the subprotocol; move client token storage to `sessionStorage` or `HttpOnly` cookie and strip `?token=` via `history.replaceState`.
- **Affected Modules:** `web/shared-client.js`, `run.py`, `web/app.js`, `web/settings.js`, `web/deck.js`.
- **Prerequisites / Dependencies:** None (Horizon 0 `H0-01` complete).
- **PERT:** $O=1.0, M=1.5, P=2.5 \rightarrow E = \mathbf{1.6}$ person-days.
- **Risk:** Medium (browser WS subprotocol negotiation edge cases).
- **Deliverables:** Subprotocol auth in `run.py` + `shared-client.js`; zero `?token=` in WS URLs.
- **Acceptance Criteria:** WS connections authenticate via `Sec-WebSocket-Protocol`; `localStorage.getItem('maybeai_creator_token')` is `null`; `test_websocket_security.py` passes.
- **Regression Tests:** `tests/test_websocket_security.py`, `tests/test_e2e_browser.py`.
- **Rollback Plan:** Temporarily re-enable query-param fallback behind `MAYBEAI_ALLOW_LEGACY_WS_TOKEN=1` env flag if reverse proxies strip `Sec-WebSocket-Protocol`.

### `PH4-02` — Windows OS-Level Plugin Sandbox & `inprocess` Ban (`SEC-GAP-002`) [P0]
- **Objective:** Close the Windows plugin sandbox escape vector.
- **Current Limitation:** `core/plugins/sandbox_worker.py` relies on Python monkeypatches for FS/network isolation on Windows, bypassable via `ctypes` or `subprocess`.
- **Proposed Implementation:** Enforce Windows Restricted Token / AppContainer (`CreateRestrictedToken` / `JobObject` UI & network restrictions) or Docker container isolation; disallow `inprocess` execution for all external plugins in `core/plugins/registry.py`.
- **Affected Modules:** `core/plugins/registry.py`, `core/plugins/sandbox_worker.py`.
- **Prerequisites / Dependencies:** None (Horizon 3 `H3-01` complete).
- **PERT:** $O=1.5, M=2.5, P=4.0 \rightarrow E = \mathbf{2.6}$ person-days.
- **Risk:** High (Windows Win32 API ACL/AppContainer complexity).
- **Deliverables:** OS-enforced Windows sandbox + `inprocess` rejection for untrusted plugins.
- **Acceptance Criteria:** Chaos probe attempting `ctypes` / `subprocess` `.env` read from an external plugin fails with `PermissionError` / access denied.
- **Regression Tests:** `tests/test_collab_and_plugins.py`.
- **Rollback Plan:** Require explicit `plugins.allow_untrusted_windows=false` default-deny (block external plugins on Windows host unless running in Linux/Docker `bwrap`).

### `PH4-03` — VLM/OCR Prompt Injection Sanitization & SSRF/Media Caps (`SEC-GAP-003`, `SEC-GAP-004`, `SEC-GAP-005`) [P0]
- **Objective:** Prevent indirect prompt injection via screen/OCR text and close DNS-rebinding TOCTOU + unbounded `yt-dlp` downloads.
- **Current Limitation:** Raw `obs.summary` / `obs.eve_commentary` enters LLM prompts unsanitized (`SEC-GAP-003`); `validate_outbound_url` resolves DNS separately from `aiohttp` connect (`SEC-GAP-004`); `yt-dlp` lacks `--max-filesize` and concurrent job cap (`SEC-GAP-005`).
- **Proposed Implementation:** Route `obs.summary` and `obs.eve_commentary` through `Moderator.sanitize_metadata()` with untrusted XML/delimiter tags; pin resolved IP in outbound HTTP connector; add `--max-filesize` and `asyncio.Semaphore(2)` in `core/youtube_karaoke.py`.
- **Affected Modules:** `core/conversation/engine.py`, `core/vision/vlm.py`, `core/moderator.py`, `core/youtube_karaoke.py`.
- **Prerequisites / Dependencies:** None.
- **PERT:** $O=1.0, M=1.5, P=2.5 \rightarrow E = \mathbf{1.6}$ person-days.
- **Risk:** Low.
- **Deliverables:** Delimited VLM/OCR context + pinned-IP SSRF guard + bounded `yt-dlp` queue.
- **Acceptance Criteria:** Simulated screen OCR containing `"Ignore previous instructions"` is stripped/escaped; `yt-dlp` rejects oversized media and caps concurrency at 2.
- **Regression Tests:** `tests/test_moderator.py`, `tests/test_youtube_karaoke.py`, `tests/test_security_and_hardening.py`.
- **Rollback Plan:** Disable VLM context injection (`vision.inject_ocr=false`) if sanitization breaks benign game UI reads.

### `PH4-04` — Per-WS Outbound Queue & Streaming Timeouts (`INFRA-MED-001-RES`, `AUDIO-MED-001`, `AUDIO-MED-002/003`) [P1]
- **Objective:** Eliminate 2.0s WebSocket broadcast head-of-line stalls, >1.8s LLM stream truncation, and TTS cancellation/Singer config bugs.
- **Current Limitation:** `_dispatch_to_web_listeners` lacks per-WS outbound `asyncio.Queue(maxsize=64)` (`INFRA-MED-001-RES`); `Brain` uses `ClientTimeout(total=1.8)` (`failover_timeout_sec`) which aborts healthy LLM streams >1.8s (`AUDIO-MED-001`); `TTSEngine.speak()` swallows `CancelledError` (`AUDIO-MED-002`); `reload_settings()` omits neural TTS/fallback fields for `Singer` (`AUDIO-MED-003`).
- **Proposed Implementation:** Add per-WS `asyncio.Queue(maxsize=64)` + dedicated sender task in `run.py`/`core/orchestrator.py` (drop-oldest for telemetry); change `ClientTimeout(total=1.8)` to `ClientTimeout(connect=1.8, sock_read=5.0)` in `core/brain.py`; re-raise `CancelledError` in `TTSEngine.speak()`; forward neural TTS fields to `Singer.update_config()`.
- **Affected Modules:** `run.py`, `core/orchestrator.py`, `core/brain.py`, `core/tts.py`, `core/singer.py`.
- **Prerequisites / Dependencies:** None.
- **PERT:** $O=1.5, M=2.0, P=3.0 \rightarrow E = \mathbf{2.1}$ person-days.
- **Risk:** Medium (WS sender task lifecycle on abrupt disconnect).
- **Deliverables:** Non-blocking WS fan-out + unbroken >1.8s LLM streaming + clean TTS cancellation.
- **Acceptance Criteria:** 1 stalled WS client causes `<5ms` impact on 99 healthy clients; 4s LLM stream completes without timeout; `barge_in()` during `TTSEngine.speak()` cancels immediately.
- **Regression Tests:** `tests/test_event_bus.py`, `tests/test_voice_duplex.py`, `tests/test_brain_failover.py`.
- **Rollback Plan:** Revert to `asyncio.wait_for(..., timeout=2.0)` if per-WS queues leak tasks on disconnect.

### `PH4-05` — Collab Disconnect Floor Reset, `on_hello` Wiring & `promises.md` Hook (`CHAOS-B-001`, `COG-PROMISE-001`) [P1]
- **Objective:** Fix Chaos Scenario B (`disconnect_peer()` stuck `floor_state`) and wire existing `promises.md` archival/fulfillment methods.
- **Current Limitation:** `CollabManager.disconnect_peer()` leaves `floor_state="listening"` and `active_peer` set; `Orchestrator._on_collab_hello` is dead code (`on_hello` unwired in `set_action_callbacks()`); `MemoryDatabase.fulfill_promise()` / `archive_old_promises()` / `sync_promises()` exist but have zero callers.
- **Proposed Implementation:** Reset `self.floor_state = "idle"` and `self.active_peer = None` in `CollabManager.disconnect_peer()`; wire `on_hello` in `set_action_callbacks()`; invoke `sync_promises()` / `archive_old_promises()` on session end and `fulfill_promise()` via conversation/goal completion hook.
- **Affected Modules:** `core/collab/manager.py`, `core/orchestrator.py`, `core/conversation/engine.py`, `core/memory/__init__.py`.
- **Prerequisites / Dependencies:** None.
- **PERT:** $O=1.0, M=1.5, P=2.5 \rightarrow E = \mathbf{1.6}$ person-days.
- **Risk:** Low.
- **Deliverables:** Clean collab disconnect recovery + active `promises.md` lifecycle.
- **Acceptance Criteria:** Chaos Scenario B passes 100% (`floor_state == "idle"` after peer drop); `promises.md` stays `<= 20` completed rows in soak.
- **Regression Tests:** `tests/test_collab_and_plugins.py`, `tests/test_memory_database.py`.
- **Rollback Plan:** Feature-flag `memory.auto_fulfill_promises=false` if false-positive promise completion occurs.

### `PH4-06` — Frontend Guardrails, `ResourceWarning` Cleanup & Structured Logging (`FE-REL-001`, `OPS-001`) [P2]
- **Objective:** Eliminate `app.js` `ws.readyState` `TypeError`s, `aiohttp` `ResourceWarning`s, `asyncio` slow callbacks, and stdout-only logging.
- **Current Limitation:** `web/app.js` has 5 unguarded `ws.readyState` accesses (`L737, 865, 879, 893, 1353`) and incomplete `onopen` re-sync; `web/*.css` has 0 `:focus-visible` / `prefers-reduced-motion` rules; `-W default` shows `aiohttp` `ResourceWarning`s and `0.11s–0.28s` slow callbacks; core uses `print()` without `RotatingFileHandler`; Playwright is missing in CI.
- **Proposed Implementation:** Guard all `ws.readyState` calls with `ws &&`, add `/api/voice/status` + Mood/Chess/MC re-sync to `app.js` `onopen`, add `:focus-visible` + `prefers-reduced-motion` to CSS; close `aiohttp.ClientSession`s in `shutdown()`/tests; offload sync `_ingest_message` I/O to `asyncio.to_thread`; replace `print()` with `logging` + `RotatingFileHandler`; install Playwright in CI.
- **Affected Modules:** `web/app.js`, `web/style.css`, `web/settings.css`, `web/deck.css`, `core/orchestrator.py`, `run.py`, `tests/`.
- **Prerequisites / Dependencies:** `PH4-01`.
- **PERT:** $O=2.5, M=3.8, P=6.0 \rightarrow E = \mathbf{4.0}$ person-days.
- **Risk:** Low.
- **Deliverables:** Zero `ResourceWarning`s under `-W default`, rotating logs, Playwright E2E green.
- **Acceptance Criteria:** `python -W default -m unittest discover tests` reports **0** `ResourceWarning`s and `381/381` passed (including Playwright E2E).
- **Regression Tests:** Full `tests/` suite + `node tests/test_guard_runner.js` + `node --check`.
- **Rollback Plan:** Keep `MAYBEAI_LOG_STDOUT=1` fallback for container log drivers.

---

## Horizon 4 — Cognitive & Companion Intelligence (L3 → L4)

**Objective:** Upgrade Eve from RAG + parametric sliders (`L2/L3`) to genuine **long-horizon learning, hierarchical memory consolidation, causal self-reflection, and resilient 24/7 cognitive continuity (`L4`)**.

### `H4-01` — Indexed ANN Vector Memory (`sqlite-vec` / HNSW)
- **Objective:** Remove the 2,000-row dense vector recall ceiling (`vector_scan_limit=2000`).
- **Current Limitation:** `MemoryDatabase.vector_search()` / `avector_search()` scans at most 2,000 recent rows in Python (`45.32 ms` at 2,000 rows); older memories are invisible to semantic recall.
- **Proposed Implementation:** Integrate `sqlite-vec` (or fallback HNSW index in `data/memory_hnsw.bin`) with dimension-tagged partitions so 100k+ episodic/semantic memories search in `<15 ms`.
- **Affected Modules:** `core/memory/database.py`, `core/memory/embedding.py`, `pyproject.toml`.
- **Prerequisites / Dependencies:** `PH4-05`.
- **PERT:** $O=3.0, M=4.5, P=7.0 \rightarrow E = \mathbf{4.7}$ person-days.
- **Risk:** Medium (native `sqlite-vec` wheel compatibility on Windows/Linux).
- **Deliverables:** Indexed ANN search with automatic backfill migration from SQLite `memories` table.
- **Acceptance Criteria:** Query over 50,000 synthetic memories completes in `<20 ms` p95; dimension-mismatch guard preserved.
- **Regression Tests:** `tests/test_memory_database.py`, `tests/test_memory_benchmark.py` (new).
- **Rollback Plan:** Config toggle `memory.ann_backend="linear"` reverts to `vector_scan_limit=2000` Python cosine scan.

### `H4-02` — Hierarchical Memory Consolidation & Decay Pipeline
- **Objective:** Distill daily episodic logs into structured semantic facts and prune low-importance noise.
- **Current Limitation:** `EpisodicMemoryStore` stores flat rows; `ContextMemory` only keeps 16 turns + 4-snippet string concatenation; no episodic-to-semantic distillation exists.
- **Proposed Implementation:** Background consolidation worker (`core/memory/consolidator.py`) running on idle/post-stream: clusters episodic rows, extracts semantic facts/user preferences via LLM, updates importance/decay weights, and performs bidirectional `promises.md` sync.
- **Affected Modules:** `core/memory/consolidator.py` (new), `core/memory/__init__.py`, `core/memory/markdown_sync.py`, `core/conversation/memory.py`.
- **Prerequisites / Dependencies:** `H4-01`, `PH4-04` (non-blocking streaming timeouts).
- **PERT:** $O=3.5, M=5.0, P=8.0 \rightarrow E = \mathbf{5.3}$ person-days.
- **Risk:** Medium (LLM hallucination during memory summarization).
- **Deliverables:** Scheduled memory consolidator + semantic fact store + provenance links back to source episode IDs.
- **Acceptance Criteria:** 500 episodic rows consolidate into deduplicated semantic facts without overwriting creator-verified facts; `promises.md` bidirectional sync passes round-trip tests.
- **Regression Tests:** `tests/test_memory_consolidation.py` (new), `tests/test_memory_database.py`.
- **Rollback Plan:** Disable `memory.consolidation_enabled=false`; raw episodic rows remain untouched.

### `H4-03` — Causal Self-Reflection & Policy Learning Loop
- **Objective:** Make `Goal.reflection` actionable instead of write-only.
- **Current Limitation:** `StrategyReplanner` uses keyword matching (`"creeper"`, `"habis"`, `"kacang"`, `"blunder"`); `Goal.reflection` is serialized to `goals.json`/`agenda.md` and never read by `GoalDecomposer` or `GoalEngine`.
- **Proposed Implementation:** Feed recent `Goal.reflection` entries and failure traces into `GoalDecomposer` and `StrategyReplanner` as structured lesson-learned priors; replace keyword table with LLM/rule hybrid causal diagnosis + success-rate scoring per strategy.
- **Affected Modules:** `core/planning/replanner.py`, `core/planning/decomposer.py`, `core/planning/executor.py`, `core/planning/models.py`.
- **Prerequisites / Dependencies:** `H4-02`, `PH4-05`.
- **PERT:** $O=3.0, M=4.5, P=7.0 \rightarrow E = \mathbf{4.7}$ person-days.
- **Risk:** Medium (prompt bloat in `GoalDecomposer` if lessons aren't capped).
- **Deliverables:** Closed-loop `reflection` retrieval in `GoalDecomposer` + causal `StrategyReplanner`.
- **Acceptance Criteria:** Simulated repeated mission failure selects a distinct strategy on attempt 2 using stored `reflection` rather than repeating the same failing plan.
- **Regression Tests:** `tests/test_planning_system.py`, `tests/test_causal_reflection.py` (new).
- **Rollback Plan:** Revert `planning.use_causal_reflection=false` to fall back to `MAX_REPLAN_ATTEMPTS=3` keyword replanner.

### `H4-04` — Tokenizer-Exact `ContextBudgetManager` & Dead Config Wiring
- **Objective:** Replace `(len(text)+3)//4` token estimation with model-accurate counting and wire the 4 dead config keys (`INFRA-MED-002`).
- **Current Limitation:** `ContextBudgetManager` uses char/4 heuristic (inaccurate for Indonesian/emoji/code); `system.response_timeout_sec`, `performance.max_concurrent_tasks`, `performance.websocket_ping_interval_sec`, and `performance.audio_buffer_size_kb` are unwired.
- **Proposed Implementation:** Add `tiktoken` / model-family tokenizers (with fast cached fallback) in `core/brain.py`; wire all 4 `INFRA-MED-002` config keys into `run.py` and `Orchestrator`.
- **Affected Modules:** `core/brain.py`, `core/config_manager.py`, `run.py`, `core/orchestrator.py`.
- **Prerequisites / Dependencies:** `PH4-04`.
- **PERT:** $O=2.0, M=3.0, P=4.5 \rightarrow E = \mathbf{3.1}$ person-days.
- **Risk:** Low.
- **Deliverables:** Exact token budgeting + 157/157 config keys actively wired.
- **Acceptance Criteria:** Mixed Indonesian/English/emoji prompts never exceed provider budget by >2%; changing `websocket_ping_interval_sec` or `response_timeout_sec` alters runtime behavior in tests.
- **Regression Tests:** `tests/test_config_manager.py`, `tests/test_brain_failover.py`.
- **Rollback Plan:** Fallback to `(len(text)+3)//4` if `tiktoken` encoding load fails offline.

### `H4-05` — Narrative Affective Memory & Dynamic Personality Synthesis
- **Objective:** Couple `MoodEngine` and `PersonalityEvolutionEngine` to episodic/semantic memories rather than static `experience_matrix` deltas alone.
- **Current Limitation:** `PersonalityEvolutionEngine.record_experience()` and `RelationshipEngine.record_chat_interaction()` are static keyword/float sliders.
- **Proposed Implementation:** Weight retrieved memories by emotional valence (`MoodEngine` state at encoding time) and allow periodic reflection to propose bounded trait/relationship adjustments with audit trail.
- **Affected Modules:** `core/mood/engine.py`, `core/personality/evolution.py`, `core/relationship/engine.py`.
- **Prerequisites / Dependencies:** `H4-02`.
- **PERT:** $O=2.0, M=3.5, P=5.0 \rightarrow E = \mathbf{3.5}$ person-days.
- **Risk:** Low–Medium (personality drift over long runs; mitigated by `[0.05, 0.98]` bounds + creator reset).
- **Deliverables:** Valence-weighted memory recall + auditable trait/relationship evolution log.
- **Acceptance Criteria:** High-valence memories surface preferentially under matching mood; trait bounds `[0.05, 0.98]` remain strictly enforced.
- **Regression Tests:** `tests/test_mood_personality.py`.
- **Rollback Plan:** Lock `personality.dynamic_synthesis=false` to retain deterministic `experience_matrix`.

---

## Horizon 5 — Multimodal & Autonomous Evolution (L4 Multimodal)

**Objective:** Unify real-time vision, audio, avatar expression, and proactive showrunner loops while modernizing the monolithic frontend (`app.js` 5,896 lines) into a cohesive Creator Studio.

### `H5-01` — Unified Frontend Creator Studio & Avatar Module Extraction
- **Objective:** Eliminate duplicated 2D/VRM/Audio code across `app.js` (5,896 lines), `overlay.js`, `settings.js`, and `deck.js`, and unify English/Indonesian UX.
- **Current Limitation:** 4 separate HTML/JS apps; full-page `<a href="/settings">` tears down active WS/AudioWorklet; `web/vrm-avatar.js` was never created; mixed ID/EN copy.
- **Proposed Implementation:** Extract shared ES modules (`web/modules/avatar-renderer.js`, `web/modules/audio-queue.js`, `web/modules/i18n.js`), embed `/settings` as a non-destructive drawer/tab inside Studio while keeping `/overlay` and `/deck` lightweight, and standardize i18n strings.
- **Affected Modules:** `web/index.html`, `web/app.js`, `web/overlay.js`, `web/deck.js`, `web/settings.js`, `web/modules/` (new).
- **Prerequisites / Dependencies:** `PH4-06`.
- **PERT:** $O=4.5, M=6.5, P=10.0 \rightarrow E = \mathbf{6.8}$ person-days.
- **Risk:** Medium–High (regression risk across 4 UI surfaces).
- **Deliverables:** Modular ES frontend with zero WS teardown on settings access and 100% i18n coverage.
- **Acceptance Criteria:** Switching between Live Stage and Settings preserves active `AudioWorklet` mic and WS session; Playwright E2E passes across all 4 routes.
- **Regression Tests:** `tests/test_e2e_browser.py`, `node --check`.
- **Rollback Plan:** Serve legacy `web/settings.html` route alongside embedded drawer until soak-verified.

### `H5-02` — Proactive Showrunner & Game/Media Auto-Reconnect (`startAutonomyLoop` + OBS/MC)
- **Objective:** Activate Eve's autonomous showrunner loop and eliminate manual reconnects for OBS and Mineflayer.
- **Current Limitation:** `startAutonomyLoop()` is uncalled; OBS and Minecraft controllers lack automatic exponential-backoff reconnect; `HighlightDetector` emits `HIGHLIGHT_MARKED` before `replay_saved` finishes; `ClipPipeline`/`VODSummarizer` lack `.get_status()`.
- **Proposed Implementation:** Wire `startAutonomyLoop()` behind creator-configurable pacing policy; add backoff auto-reconnect to `OBSWebSocketClient` and `MinecraftController`; emit `HIGHLIGHT_CLIP_READY` after replay save completes; add `.get_status()` to `ClipPipeline` & `VODSummarizer`.
- **Affected Modules:** `core/orchestrator.py`, `core/desktop/obs_client.py`, `core/minecraft/controller.py`, `core/highlights/detector.py`, `core/highlights/clipper.py`.
- **Prerequisites / Dependencies:** `H4-03`, `PH4-03`.
- **PERT:** $O=3.5, M=5.0, P=7.5 \rightarrow E = \mathbf{5.2}$ person-days.
- **Risk:** Medium (autonomous pacing spamming chat if misconfigured).
- **Deliverables:** Self-healing OBS/MC links + configurable autonomous showrunner + deterministic highlight clip events.
- **Acceptance Criteria:** Killing `bot.js` or OBS triggers automatic reconnect within `<15s`; `startAutonomyLoop()` respects idle/cooldown budgets.
- **Regression Tests:** `tests/test_game_bridges.py`, `tests/test_highlights.py`.
- **Rollback Plan:** Toggle `autonomy.showrunner_enabled=false` via `/deck` or `/api/autonomy/stop`.

### `H5-03` — Sub-500ms Streaming Voice & Expressive Avatar Blending
- **Objective:** Reduce end-to-end voice turn latency and unify `MouthSmile`/`MouthForm` VRM/VTS expression blending.
- **Current Limitation:** `MouthSmile` vs `MouthForm` split in VTS/VRM; duplicate VTS reconnect checks; full-sentence TTS wait on non-streaming providers.
- **Proposed Implementation:** Sentence-clause streaming TTS chunking, unified `AvatarExpressionBlender` (`core/avatar/blender.py`) mapping mood + prosody to VRM/VTS blendshapes, and deduplicated VTS reconnect state machine.
- **Affected Modules:** `core/tts.py`, `core/vts_client.py`, `web/modules/avatar-renderer.js`, `core/orchestrator.py`.
- **Prerequisites / Dependencies:** `PH4-04`, `H5-01`.
- **PERT:** $O=3.5, M=5.0, P=8.0 \rightarrow E = \mathbf{5.3}$ person-days.
- **Risk:** Medium (audio-to-blendshape jitter).
- **Deliverables:** Streaming clause TTS + unified VRM/VTS expression blender.
- **Acceptance Criteria:** First-audio-byte latency `<500 ms` p95 on local Kokoro/EdgeTTS; zero duplicate VTS reconnect loops.
- **Regression Tests:** `tests/test_voice_duplex.py`, `tests/test_vts_client.py`.
- **Rollback Plan:** Disable clause chunking (`tts.clause_streaming=false`) to revert to sentence-level synthesis.

### `H5-04` — Real-Time Multimodal Context Fusion (Vision + Audio + Game State)
- **Objective:** Fuse sanitized VLM screen observations, game telemetry, and acoustic/chat sentiment into a single low-latency context frame.
- **Current Limitation:** VLM, Minecraft telemetry, and chat arrive as separate uncoordinated events; VLM calls are periodic and unthrottled by game/chat activity.
- **Proposed Implementation:** Event-driven `MultimodalContextAggregator` (`core/vision/aggregator.py`) with adaptive VLM frame rate (fast during action/highlights, slow when idle) and strict `SEC-GAP-003` sanitization.
- **Affected Modules:** `core/vision/aggregator.py` (new), `core/vision/vlm.py`, `core/conversation/engine.py`.
- **Prerequisites / Dependencies:** `PH4-03`, `H4-04`.
- **PERT:** $O=3.0, M=4.5, P=6.5 \rightarrow E = \mathbf{4.6}$ person-days.
- **Risk:** Medium (VLM API cost spike if adaptive throttle misbehaves; capped by max calls/min).
- **Deliverables:** Adaptive multimodal context frame + hard VLM rate limiter.
- **Acceptance Criteria:** VLM call rate drops `>=60%` during idle scenes while capturing game events within `2s` of state change.
- **Regression Tests:** `tests/test_vision_aggregator.py` (new).
- **Rollback Plan:** Fixed-interval VLM polling fallback (`vision.adaptive_fusion=false`).

### `H5-05` — Prometheus Metrics & Deep Dependency Health Probes
- **Objective:** Close the L3.0 observability gap (`13_production_readiness.md`) for unattended 24/7 operation.
- **Current Limitation:** `/api/metrics` is JSON-only; `/api/health` is shallow (does not probe SQLite WAL, EventBus lag, or disk space).
- **Proposed Implementation:** Add `/metrics` (Prometheus text exposition), deep `/api/health?deep=1` (SQLite read/write probe, EventBus queue depth, free disk/RSS thresholds), and optional webhook alerting.
- **Affected Modules:** `core/metrics.py`, `run.py`.
- **Prerequisites / Dependencies:** `PH4-06`.
- **PERT:** $O=2.0, M=2.8, P=4.0 \rightarrow E = \mathbf{2.9}$ person-days.
- **Risk:** Low.
- **Deliverables:** Prometheus `/metrics` endpoint + deep health check + alert webhook hook.
- **Acceptance Criteria:** `/api/health?deep=1` returns `503` when SQLite is locked/read-only or disk `<500 MB`; Prometheus scraper parses `/metrics` cleanly.
- **Regression Tests:** `tests/test_metrics_and_health.py`.
- **Rollback Plan:** Keep shallow `/api/health` default for Docker `HEALTHCHECK` while `?deep=1` is opt-in.

---

## Horizon 6 — Social & Multi-Agent Ecosystem (L4.5 Ecosystem)

**Objective:** Scale AI VTuber Collab beyond 2-peer scalar state, complete subsystem auto-sync, and harden a signed third-party plugin ecosystem.

### `H6-01` — N-Peer Mesh Collab & Automatic Subsystem Sync (`duet_sync`, `emote_sync`, `game_move`)
- **Objective:** Upgrade `CollabManager` from 2-peer scalar state to N-peer turn/floor orchestration with live subsystem sync.
- **Current Limitation:** `CollabManager` is 2-peer only (`05_collab_protocol.md`); subsystems (`Singer`, `Avatar`, `Chess`/`MC`) do not auto-emit `duet_sync`/`emote_sync`/`game_move` frames.
- **Proposed Implementation:** Peer registry keyed by `peer_id` with distributed floor-lease token (`owner_peer_id`, `lease_expires_at`), plus EventBus-to-Collab bridge auto-emitting `duet_sync`, `emote_sync`, and `game_move` envelopes.
- **Affected Modules:** `core/collab/manager.py`, `core/collab/protocol.py`, `core/orchestrator.py`.
- **Prerequisites / Dependencies:** `PH4-05`, `H5-03`.
- **PERT:** $O=4.5, M=6.5, P=10.0 \rightarrow E = \mathbf{6.8}$ person-days.
- **Risk:** High (split-brain floor contention across >2 peers).
- **Deliverables:** N-peer `CollabManager` + automatic `EventBus` collab sync bridge.
- **Acceptance Criteria:** 3-peer simulated collab maintains single-speaker floor exclusivity and survives abrupt mid-turn disconnect of any peer.
- **Regression Tests:** `tests/test_collab_and_plugins.py`, `tests/test_collab_n_peer.py` (new).
- **Rollback Plan:** Cap `collab.max_peers=2` via config to run in 2-peer compatibility mode.

### `H6-02` — Signed Plugin Manifests, Capability Quotas & Marketplace Verification
- **Objective:** Enable safe community plugin distribution with cryptographic provenance and resource quotas.
- **Current Limitation:** `PluginRegistry` validates AST + `granted_permissions` locally, but has no author signature verification or CPU/RAM/disk quota enforcement per plugin.
- **Proposed Implementation:** Ed25519 manifest signing (`plugin.sig`), per-plugin cgroup/JobObject memory & CPU caps, and automated sandboxed smoke-test harness for plugin authors.
- **Affected Modules:** `core/plugins/registry.py`, `core/plugins/sandbox_worker.py`, `core/plugins/manifest.py`.
- **Prerequisites / Dependencies:** `PH4-02`.
- **PERT:** $O=4.0, M=6.0, P=9.0 \rightarrow E = \mathbf{6.2}$ person-days.
- **Risk:** Medium (key rotation & developer onboarding friction).
- **Deliverables:** Ed25519 plugin verification + per-plugin resource caps + `maybeai-plugin-check` CLI.
- **Acceptance Criteria:** Unsigned or tampered plugin is rejected when `plugins.require_signature=true`; runaway plugin is killed at memory cap without affecting `Orchestrator`.
- **Regression Tests:** `tests/test_collab_and_plugins.py`.
- **Rollback Plan:** Allow `plugins.require_signature=false` for local creator-authored dev plugins.

### `H6-03` — Multi-Platform Social Graph & Live Audience Co-Play
- **Objective:** Unify user identity and co-play state across Twitch, YouTube Live, Discord, and local Studio.
- **Current Limitation:** `RelationshipEngine` tracks per-platform handles separately; audience participation in Chess/RPG/Karaoke lacks unified queue fairness & anti-abuse throttling.
- **Proposed Implementation:** Cross-platform `IdentityLink` (opt-in verification), fair-share audience request queue (Karaoke/Chess/RPG) with VIP/SuperChat weighting and per-user cooldowns.
- **Affected Modules:** `core/relationship/engine.py`, `core/conversation/chat_curator.py`, `core/youtube_karaoke.py`.
- **Prerequisites / Dependencies:** `H4-05`, `PH4-03`.
- **PERT:** $O=3.5, M=5.0, P=7.5 \rightarrow E = \mathbf{5.2}$ person-days.
- **Risk:** Low–Medium.
- **Deliverables:** Unified audience queue + cross-platform relationship continuity.
- **Acceptance Criteria:** Rapid spam from 1 user across 2 platforms cannot starve the request queue.
- **Regression Tests:** `tests/test_chat_curator.py`, `tests/test_relationship_engine.py`.
- **Rollback Plan:** Disable cross-platform linking (`relationship.cross_platform_merge=false`).

### `H6-04` — Real-Time Collaborative Game & Duet Stage (Minecraft + Chess + Karaoke)
- **Objective:** Turn multi-AI collab into live co-op entertainment (shared Minecraft objectives, AI-vs-AI Chess, synchronized Karaoke duets).
- **Current Limitation:** Game controllers and `YouTubeKaraokeProcessor` are single-agent only.
- **Proposed Implementation:** Shared objective state machine for Minecraft co-op, Collab Chess move relay (`game_move`), and beat-aligned `duet_sync` lyric handoffs.
- **Affected Modules:** `core/minecraft/controller.py`, `core/chess/controller.py`, `core/youtube_karaoke.py`, `core/collab/manager.py`.
- **Prerequisites / Dependencies:** `H6-01`, `H5-02`.
- **PERT:** $O=5.0, M=8.0, P=12.0 \rightarrow E = \mathbf{8.3}$ person-days.
- **Risk:** High (network jitter in duet audio sync).
- **Deliverables:** Co-op MC, AI-vs-AI Chess, and beat-synced Collab Karaoke.
- **Acceptance Criteria:** Two local instances complete a 10-move Collab Chess game and a 2-verse Karaoke duet with `<150 ms` drift.
- **Regression Tests:** `tests/test_collab_games.py` (new).
- **Rollback Plan:** Disable `collab.enable_duet_sync` / `collab.enable_game_sync` independently.

---

## Horizon 7 — Autonomous Content & Digital Presence (L4.5 Content Studio)

**Objective:** Automate post-stream content production (vertical clips, VOD summaries, highlight reels) and give creators actionable analytics with human-in-the-loop publishing gates.

### `H7-01` — Automated Highlight-to-Vertical-Clip Factory & Retention Policy
- **Objective:** End-to-end pipeline from `HighlightDetector` → `ClipPipeline` → captioned 9:16 short-form video with bounded disk retention.
- **Current Limitation:** `data/clips/` lacks automated retention/cleanup (`COST_AND_INFRASTRUCTURE.md` §3); `ClipPipeline` requires manual triggers and lacks auto-caption burn-in.
- **Proposed Implementation:** Whisper/VTT-synced ASS subtitle burn-in in `ClipPipeline`, scheduled post-stream batch export, and configurable LRU disk quota (`clips.max_storage_gb`).
- **Affected Modules:** `core/highlights/clipper.py`, `core/highlights/detector.py`, `core/config_manager.py`.
- **Prerequisites / Dependencies:** `H5-02`, `PH4-03`.
- **PERT:** $O=4.0, M=6.0, P=9.0 \rightarrow E = \mathbf{6.2}$ person-days.
- **Risk:** Medium (`ffmpeg` CPU/GPU contention during live stream; mitigate by deferring batch renders to post-stream idle).
- **Deliverables:** Auto-captioned 9:16 clip pipeline + LRU disk quota enforcement.
- **Acceptance Criteria:** Post-stream job renders captioned clip within `2x` realtime and evicts oldest clips when exceeding `clips.max_storage_gb`.
- **Regression Tests:** `tests/test_highlights.py`.
- **Rollback Plan:** Set `clips.auto_render=false` to keep manual `/deck` clip triggers only.

### `H7-02` — Scheduled Autonomous Presence & Stream Lifecycle Automation
- **Objective:** Enable scheduled Discord/social check-ins, pre-stream warmups, and post-stream VOD summaries with strict creator approval gates.
- **Current Limitation:** `VODSummarizer` and `GoalEngine` run only when triggered manually or during active sessions.
- **Proposed Implementation:** Cron/calendar-backed `PresenceScheduler` (`core/autonomy/scheduler.py`) with dry-run preview, creator approval queue for outbound posts, and automatic post-stream recap generation.
- **Affected Modules:** `core/autonomy/scheduler.py` (new), `core/highlights/vod.py`, `core/orchestrator.py`.
- **Prerequisites / Dependencies:** `H4-02`, `H5-02`.
- **PERT:** $O=4.5, M=6.5, P=9.5 \rightarrow E = \mathbf{6.7}$ person-days.
- **Risk:** High (brand/reputation risk from unapproved autonomous posts; mitigated by mandatory creator approval gate by default).
- **Deliverables:** `PresenceScheduler` + post-stream VOD summary + approval queue UI.
- **Acceptance Criteria:** Scheduled post enters `pending_approval` and never publishes externally unless creator approves or explicitly enables auto-publish.
- **Regression Tests:** `tests/test_presence_scheduler.py` (new).
- **Rollback Plan:** Global kill-switch `autonomy.outbound_posting_enabled=false`.

### `H7-03` — Creator Analytics & Retention Intelligence Dashboard
- **Objective:** Surface token spend, engagement peaks, memory growth, and stream health in the Studio UI.
- **Current Limitation:** `/api/metrics` exposes raw counters/histograms with no historical trend or cost-per-stream attribution.
- **Proposed Implementation:** Lightweight SQLite time-series rollup (`data/telemetry.db`) + Studio Analytics tab showing cost/turn, mood trajectory, top chatters, and highlight engagement.
- **Affected Modules:** `core/metrics.py`, `web/modules/analytics-view.js` (new), `run.py`.
- **Prerequisites / Dependencies:** `H5-01`, `H5-05`.
- **PERT:** $O=3.5, M=5.0, P=7.5 \rightarrow E = \mathbf{5.2}$ person-days.
- **Risk:** Low.
- **Deliverables:** Per-stream cost & engagement dashboard in Studio.
- **Acceptance Criteria:** 12h simulated stream produces `<5 MB` telemetry rollup and renders charts offline in Studio.
- **Regression Tests:** `tests/test_metrics_and_health.py`.
- **Rollback Plan:** Disable `metrics.persist_rollups=false`.

### `H7-04` — Hardware-Accelerated Media Pipeline (NVENC / VAAPI / ONNX-GPU)
- **Objective:** Offload `ffmpeg` clip encoding, `demucs` stem separation, and local STT/TTS from CPU to GPU when available.
- **Current Limitation:** `ClipPipeline` and `YouTubeKaraokeProcessor` default to CPU encoding/separation, competing with live game/OBS workloads.
- **Proposed Implementation:** Auto-detect NVENC/QSV/VAAPI in `ClipPipeline` and CUDA/DirectML in `YouTubeKaraokeProcessor` with graceful CPU fallback.
- **Affected Modules:** `core/highlights/clipper.py`, `core/youtube_karaoke.py`.
- **Prerequisites / Dependencies:** `H7-01`.
- **PERT:** $O=2.5, M=3.8, P=6.0 \rightarrow E = \mathbf{3.9}$ person-days.
- **Risk:** Medium (driver/codec mismatch across Windows/Docker).
- **Deliverables:** Hardware encoder probe + fallback chain.
- **Acceptance Criteria:** Falls back to `libx264` CPU cleanly when NVENC probe fails; `>=3x` faster clip export on RTX GPU.
- **Regression Tests:** `tests/test_highlights.py`, `tests/test_youtube_karaoke.py`.
- **Rollback Plan:** Config `media.hw_accel="cpu"`.

---

## Horizon 8 — Long-Term Digital Companion Ecosystem (L5 Platform)

**Objective:** Deliver a sovereign, multi-node, extensible **L5 Digital Companion Platform** supporting split-node GPU inference, portable lifelong companion identity, and a versioned third-party SDK.

### `H8-01` — Distributed Split-Node Architecture (Control Plane + GPU Inference Workers)
- **Objective:** Decouple heavy ML workers (LLM/VLM, `faster-whisper`, `kokoro`/`RVC`, `demucs`) from the low-latency FastAPI Control Plane so creators can run Eve on a lightweight laptop/VPS backed by a remote GPU node.
- **Current Limitation:** Single-process Python monolith (`run.py` + `Orchestrator`) binds all local ML models to the same host memory/GPU.
- **Proposed Implementation:** gRPC/WebSocket internal worker protocol (`core/workers/client.py`) with health-checked remote STT/TTS/LLM/Karaoke worker registration and automatic local fallback.
- **Affected Modules:** `core/workers/` (new), `core/brain.py`, `core/tts.py`, `core/stt.py`, `run.py`.
- **Prerequisites / Dependencies:** `H5-05`, `H6-01`, `H7-04`.
- **PERT:** $O=6.0, M=9.5, P=15.0 \rightarrow E = \mathbf{9.8}$ person-days.
- **Risk:** High (network latency adding to voice turn budget; mitigated by LAN/WireGuard deployment target).
- **Deliverables:** Remote GPU worker daemon + `Orchestrator` worker router.
- **Acceptance Criteria:** Control Plane runs in `<250 MB` RAM while offloading STT/TTS/LLM to a separate GPU host with `<30 ms` transport overhead on LAN.
- **Regression Tests:** `tests/test_worker_offload.py` (new).
- **Rollback Plan:** Keep `workers.mode="inprocess"` default for single-PC creators.

### `H8-02` — Portable Encrypted Companion Identity & Second Brain Backup (`.maybeai` Bundle)
- **Objective:** Give creators sovereign ownership of Eve's lifelong memories, personality, relationships, and `SecondBrain` in an encrypted, versioned archive.
- **Current Limitation:** State is scattered across `data/memory.db`, `data/second_brain/*.md`, `data/goals/`, and `config/settings.json`.
- **Proposed Implementation:** Schema-versioned export/import (`maybeai export --encrypt` / `maybeai import`) using AES-256-GCM + Argon2id key derivation, with integrity checksums and dry-run diff preview.
- **Affected Modules:** `core/backup/` (new), `core/memory/database.py`, `core/config_manager.py`.
- **Prerequisites / Dependencies:** `H4-02`, `H4-05`.
- **PERT:** $O=3.5, M=5.0, P=8.0 \rightarrow E = \mathbf{5.3}$ person-days.
- **Risk:** Medium (schema migration across versions).
- **Deliverables:** Encrypted `.maybeai` snapshot CLI & Studio UI button.
- **Acceptance Criteria:** Round-trip export → wipe → import restores 100% of episodic/semantic memories, traits, and promises with zero data loss.
- **Regression Tests:** `tests/test_identity_backup.py` (new).
- **Rollback Plan:** Retain direct file-level `data/` + `config/` backup compatibility.

### `H8-03` — Versioned Companion SDK & Real-Time Event/Avatar API (`v1`)
- **Objective:** Publish a stable, versioned SDK (`maybeai-sdk`) for external games, VTuber tools, and community plugins.
- **Current Limitation:** Internal `Events.*` and `/ws` payloads are unversioned and coupled to `Orchestrator` internals.
- **Proposed Implementation:** Versioned `/api/v1` + `/ws/v1` contract schemas (JSON Schema / Pydantic), Python & TypeScript client SDKs, and capability-scoped API keys.
- **Affected Modules:** `sdk/` (new), `run.py`, `core/event_bus.py`.
- **Prerequisites / Dependencies:** `H6-02`, `H5-01`.
- **PERT:** $O=5.0, M=7.5, P=11.0 \rightarrow E = \mathbf{7.7}$ person-days.
- **Risk:** Medium (maintaining backward compatibility with `v0` internal Studio routes).
- **Deliverables:** `maybeai-sdk` (Python + TS) + OpenAPI/AsyncAPI spec.
- **Acceptance Criteria:** External sample app subscribes to `v1` avatar/chat events and triggers a custom skill using a scoped API key.
- **Regression Tests:** `tests/test_sdk_v1_contract.py` (new).
- **Rollback Plan:** Keep `v1` routes behind `api.enable_v1=true` without altering existing Studio `/ws`.

### `H8-04` — Continuous Self-Evaluation & Automated Safety Regression Suite
- **Objective:** Ensure lifelong autonomous evolution never degrades safety, persona consistency, or latency budgets.
- **Current Limitation:** Automated tests check unit/integration contracts, not long-horizon persona drift, prompt-injection resistance, or multi-hour latency regressions.
- **Proposed Implementation:** Nightly/release eval harness (`tests/evals/`) running adversarial prompt-injection suites, persona-consistency rubrics, and automated 8-hour soak benchmarks.
- **Affected Modules:** `tests/evals/` (new), `.github/workflows/` (or CI scripts).
- **Prerequisites / Dependencies:** `H4-03`, `H5-05`, `H7-03`.
- **PERT:** $O=3.5, M=5.5, P=9.0 \rightarrow E = \mathbf{5.7}$ person-days.
- **Risk:** Low–Medium (eval flakiness if tied to live cloud LLMs; use deterministic replay + local judge).
- **Deliverables:** Adversarial safety eval suite + automated 8h soak gate.
- **Acceptance Criteria:** Safety eval blocks release on any prompt-injection bypass or `>15%` p95 latency regression.
- **Regression Tests:** `tests/evals/run_evals.py`.
- **Rollback Plan:** Run evals as non-blocking advisory gate until baseline variance stabilizes.
