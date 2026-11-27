# MaybeAI — Architecture Decision Records (ADR-001 through ADR-014)

**Document Owner:** Agent 11 (`ng-strat-arch`) — Principal Software & Future Architecture Engineer  
**Target Baseline:** `HEAD` commit `96b7315` (Post-Horizon 0–3 + YouTube Karaoke)  
**Scope:** Historical Horizon 0–3 decisions (`ADR-001`..`ADR-008`, updated with verified implementation status) and Next-Generation Horizon 4–5 decisions (`ADR-009`..`ADR-014`).

---

## Horizon 0–3 ADRs (Verified Post-Implementation Status)

| ADR | Title | Post-H3 Status | Remaining Follow-Up |
|---|---|---|---|
| **ADR-001** | Non-Blocking `EventBus`, Per-Client Bounded WS Queues & `TaskSupervisor` | **Partially Implemented** | Add per-WS outbound `asyncio.Queue(maxsize=64)` (`INFRA-MED-001-RES`), wire/prune 4 dead config keys (`INFRA-MED-002`), offload sync `_ingest_message` (`INFRA-MED-003`). |
| **ADR-002** | Unified Creator Auth, Origin/Token Policy & Read-Only `/ws/overlay` Separation | **Partially Implemented** | Switch frontend `web/shared-client.js` from `?token=` + `localStorage` to `Sec-WebSocket-Protocol` + `sessionStorage` (`SEC-GAP-001`); sanitize `obs.summary` (`SEC-GAP-003`). |
| **ADR-003** | Hardened Out-of-Process Plugin Isolation & Host-Granted Capability Policy | **Partially Implemented** | Replace Windows Python monkeypatches with restricted OS token/AppContainer and disallow `inprocess` for external plugins (`SEC-GAP-002`, see `ADR-012`). |
| **ADR-004** | Audio / Barge-In Cancellation Contract & Server-Side RMS Lip-Sync Envelope | **Partially Implemented** | Fix `ClientTimeout(total=1.8)` stream truncation (`AUDIO-MED-001`), re-raise `CancelledError` in `TTSEngine.speak()` (`AUDIO-MED-002`), forward `Singer` config in `reload_settings()` (`AUDIO-MED-003`). |
| **ADR-005** | Bounded Cognitive Prompt (`ContextBudgetManager`), LLM Failover & Hybrid Memory Store | **Partially Implemented** | Replace `2000`-row linear vector scan with `sqlite-vec` + hierarchical consolidation (`ADR-010`). |
| **ADR-006** | Closed-Loop Mission State Machine, Replan Caps & Async Telemetry Verification | **Implemented (H1–H3)** | Cancel `ChessController._delayed_bot_move` on reset; feed `Goal.reflection` into `GoalDecomposer` (`H5`). |
| **ADR-007** | Collab Replay Protection (`message_id` Nonce + Timestamp Window) & Deterministic Floor Arbitration | **Partially Implemented** | Reset `floor_state="idle"` in `disconnect_peer()` (`CHAOS-B-001`); wire `on_hello`; evolve to multi-peer mesh (`ADR-011`). |
| **ADR-008** | Local-First Frontend Asset Bundling, Shared Auth/WS Client & XSS-Safe Rendering | **Partially Implemented** | Guard 5 `ws.readyState` calls (`FE-REL-001`), complete `app.js` `onopen` re-sync, add `:focus-visible`/`prefers-reduced-motion`, modularize `app.js` (`ADR-013`). |

*(Full text of `ADR-001`–`ADR-008` is preserved in git history at `a08e435` / `1953889`; remaining deltas are superseded and extended by `ADR-009`–`ADR-014` below.)*

---

## ADR-009: Dedicated Inference & Audio Workers (Modular Monolith + Multi-Process Split)

* **Status:** Proposed (Horizon 4-B)
* **Context:** MaybeAI runs as a single-process `asyncio` FastAPI + `EventBus` monolith (`run.py` + `Orchestrator`) using `asyncio.to_thread()` for CPU/GPU tasks. Audit `02_core_infrastructure.md` and `03_realtime_audio.md` show `0.109s–0.282s` event-loop slow-callback warnings from sync I/O/DB work, and local neural ML (`faster-whisper`, `kokoro-onnx`, `RVC`, `demucs`, `sentence-transformers`, VLM) shares the main Python GIL and heap/VRAM when enabled.
* **Problem:** Heavy local ML inference or native C++/CUDA OOMs in the main process risk audio/lip-sync jitter or crashing the entire live stream (`/ws`, OBS, Twitch chat, `MemoryDatabase`).
* **Decision:** Keep the **Modular Monolith** (`run.py` + `Orchestrator` + `EventBus`) as the control plane, and introduce optional/auto-managed **Dedicated Local Worker Processes** (`inference_worker` for STT/Embeddings/VLM and `audio_worker` for TTS/RVC/Demucs/RMS extraction) communicating over typed local IPC (stdio JSON-RPC / Unix socket / Windows named pipe + binary PCM frames), supervised by `Orchestrator` like `minecraft/bot.js` and `sandbox_worker.py`.
* **Alternatives:**
  1. *Status quo (`asyncio.to_thread` only):* Rejected for local GPU setups due to shared GIL and OOM blast radius.
  2. *Full Microservices (Docker Compose per subsystem):* Rejected as premature operational complexity for single-creator studios.
* **Trade-offs:** Adds `1–3ms` local IPC serialization overhead and child-process lifecycle management in exchange for full GIL/VRAM isolation and crash-resilient streaming.
* **Migration:**
  1. Define `InferenceWorkerClient` and `AudioWorkerClient` behind existing `STTEngine`, `EmbeddingEngine`, and `TTSEngine` interfaces.
  2. Support `runtime.worker_mode = "inprocess" | "subprocess"` (default `"inprocess"` for lightweight cloud-API setups; `"subprocess"` when local neural models are enabled).
* **Backward Compatibility:** Cloud-API users (`OpenAI`/`Gemini`/`Edge-TTS`) experience zero config or deployment changes; `inprocess` remains valid for minimal environments.
* **Risks:** Zombie worker processes on abrupt host kill (mitigated via `--die-with-parent` / `_WindowsJobObject` `KILL_ON_JOB_CLOSE`).

---

## ADR-010: Hierarchical Memory & Schema Versioning

* **Status:** Proposed (Horizon 4-A / 4-B)
* **Context:** `MemoryDatabase` (`core/memory/database.py`) uses SQLite WAL + FTS5 + a Python `for`-loop cosine scan bounded by `vector_scan_limit=2000` (`45.32ms` at 2,000 rows). Memories older than the 2,000th row are invisible to dense vector search (`04_cognitive_memory.md`), `promises.md` fulfillment/archival methods are unwired, `Goal.reflection` is write-only, and `data/memory.db` has no formal `schema_version` migration framework.
* **Problem:** Long-running 24/7 streams will silently lose older episodic memories from semantic recall, accumulate un-distilled noise, and risk schema drift across upgrades.
* **Decision:**
  1. Add `PRAGMA user_version` schema versioning and idempotent forward migrations in `MemoryDatabase`.
  2. Integrate `sqlite-vec` ANN/KNN indexing (with graceful fallback to NumPy scan if the extension is unavailable) and single-connection RRF (Reciprocal Rank Fusion) combining FTS5 + vector similarity + recency/importance decay.
  3. Add a background **Hierarchical Consolidation Pipeline** (episodic turns → daily summaries → semantic facts/user dossiers) and wire `fulfill_promise()` / `archive_old_promises()` bidirectionally into `ConversationEngine` and `AutonomousMissionExecutor`.
* **Alternatives:** Migrating to external `Qdrant`/`Chroma` + `Neo4j` — rejected for H4 to preserve single-file `data/memory.db` portability and zero-daemon backups (see `research/architecture_proposals.md`).
* **Trade-offs:** Adds `sqlite-vec` wheel dependency (with fallback) and periodic background LLM/summarization token cost during off-peak consolidation.
* **Migration:** Run automatic `PRAGMA user_version` migration on startup (`backup memory.db` before alter), backfill `sqlite-vec` virtual table from existing non-null embedding blobs in batches.
* **Backward Compatibility:** Preserves `data/second_brain/*.md` Markdown export format and existing `MemoryRetriever` public API.
* **Risks:** Embedding dimension changes across models (mitigated by existing `_can_persist_reencoded_embedding()` dimension guard and model-tag column).

---

## ADR-011: Multi-Peer Collab Mesh

* **Status:** Proposed (Horizon 4-B / 5)
* **Context:** `CollabManager` (`core/collab/manager.py`) has hardened 2-peer wire security (HMAC-SHA256, `±60s` skew, `1024`-nonce LRU, SSRF guard), but uses scalar peer state (`_ws_client`, `connected_peer`, `peer_capabilities`), global `floor_state`/`turn_count`, and inbound-only subsystem wiring (`05_collab_protocol.md`). Moreover, `disconnect_peer()` leaves `floor_state="listening"` (`CHAOS-B-001`), and `on_hello` is dead code.
* **Problem:** A 2-peer scalar model cannot support 3+ AI VTuber collaborations without split-brain outbound routing, reply collisions, or `sender_id` spoofing across peers.
* **Decision:**
  1. *Pre-H4 Immediate:* Fix `disconnect_peer()` to reset `floor_state="idle"` and clear `active_peer`; add `on_hello` to `set_action_callbacks()`.
  2. *H4-B Mesh Refactor:* Replace scalar peer fields with `self.peers: Dict[str, PeerSession]` (`peer_id`, transport handle, `capabilities`, `protocol_version`, `is_loopback`, `last_seen`), add `target_id` / `room_id` to `CollabEnvelope`, bind `env.sender_id` to the authenticated `PeerSession`, extract `RoomFloorArbitrator` (supporting host/round-robin turn queues for `N >= 3`), and wire automatic outbound `duet_sync`/`emote_sync`/`game_move` hooks from `Singer`, `VTSClient`, and `ChessController`.
* **Alternatives:** External message broker (NATS/Redis) for multi-agent rooms — rejected to keep `/ws/collab` peer-to-peer over standard WebSockets.
* **Trade-offs:** Slightly more complex `CollabEnvelope` routing and floor arbitration state machine; requires explicit `room_id` coordination on multi-peer hosts.
* **Migration:** Default `target_id="*"` when only 1 peer is connected so 2-peer sessions remain wire-compatible.
* **Backward Compatibility:** Legacy 2-peer `/ws/collab` handshakes continue to function by auto-creating a single `PeerSession` entry.
* **Risks:** Clock skew across 3+ distributed hosts (mitigated by existing `±60s` skew window and clear `timestamp_skew_exceeded` diagnostics).

---

## ADR-012: Indirect Prompt Injection & OS Sandbox Hardening

* **Status:** Proposed (Pre-Horizon 4 — P0 Priority)
* **Context:** `07_security.md` identifies three high/medium security gaps blocking unattended 24/7 exposure: `SEC-GAP-001` (`web/shared-client.js` sends `?token=` in WS URLs and stores tokens in `localStorage`), `SEC-GAP-002` (Windows plugin sandbox relies on bypassable Python monkeypatches), and `SEC-GAP-003` (`core/conversation/engine.py` injects raw `obs.summary` from VLM/OCR into the system prompt). Additionally, `SEC-GAP-004` notes a DNS-rebinding TOCTOU window in `validate_outbound_url()`.
* **Problem:** Any XSS exposes `localStorage` tokens, a malicious Windows plugin can read `.env` via `ctypes`/`subprocess`, and adversarial on-screen text can hijack Eve's LLM behavior.
* **Decision:**
  1. Update `CreatorAuth` / `ReconnectingWebSocket` to authenticate `/ws` via `Sec-WebSocket-Protocol: maybeai.token.<token>`, remove `?token=` from `buildWsUrl()`, and move tokens to `sessionStorage` (or `HttpOnly` cookie).
  2. Pass `obs.summary` and `obs.eve_commentary` through `Moderator.sanitize_metadata()` + injection pattern checks and wrap in `<visual_observation_data>` untrusted-data delimiters with explicit system instructions to ignore embedded directives.
  3. On Windows, launch external plugin workers under a restricted OS token / AppContainer (`CreateRestrictedToken`) with ACL-isolated scratch directories (matching Linux `bwrap`), and disallow `sandbox_mode="inprocess"` for external `plugins_dir` plugins.
  4. Return pinned IP / custom `aiohttp.TCPConnector` from `validate_outbound_url()` to close DNS-rebinding TOCTOU (`SEC-GAP-004`).
* **Alternatives:** Running every plugin in its own Docker container — rejected due to Docker socket escalation risk and Windows desktop friction.
* **Trade-offs:** Windows restricted-token/AppContainer setup requires careful ACL handling for Python stdlib paths; `sessionStorage` requires re-entering token on new browser tab unless `HttpOnly` cookie is used.
* **Migration:** Deprecate `?token=` on `/ws` with a logged warning for one minor release before hard removal; migrate `plugins/` ACLs automatically on startup.
* **Backward Compatibility:** `/ws/overlay` remains read-only and requires no Creator token.
* **Risks:** Third-party plugins relying on `ctypes` or unrestricted filesystem reads will fail cleanly with `PermissionError` (desired security behavior).

---

## ADR-013: Unified Frontend Studio State

* **Status:** Proposed (Pre-Horizon 4 → Horizon 4-B)
* **Context:** `08_frontend_ux.md` reports that `web/` consists of 4 separate HTML/JS apps (`/`, `/settings`, `/overlay`, `/deck`) with `web/app.js` at `5,896` lines, duplicated 2D/VRM/Web Audio boilerplate, `5` unguarded `ws.readyState` accesses (`TypeError` on reconnect), incomplete `app.js` `onopen` re-sync, mixed English/Indonesian copy, and `0` `:focus-visible` / `prefers-reduced-motion` accessibility rules.
* **Problem:** Full-page navigation (`/` ↔ `/settings`) tears down active WebSockets and `AudioWorklet` mic streams, while monolithic `app.js` and duplicated renderers slow down feature velocity and cause state-sync bugs.
* **Decision:**
  1. *Pre-H4 Immediate:* Guard all `ws.readyState` calls with `ws &&`, complete `app.js` `onopen` re-sync (`/api/voice/status`, Mood, Chess, Minecraft), and add `:focus-visible` + `@media (prefers-reduced-motion: reduce)` CSS rules.
  2. *H4-B Modularization:* Keep vanilla ES modules (zero Node build step), extract shared `web/modules/avatar-renderer.js`, `web/modules/audio-player.js`, and `web/modules/studio-store.js` (single reactive state store), and embed `/settings` as an in-app drawer/panel inside `/` (retaining `/settings` route as an alias) so configuration edits never tear down live audio/WS sessions.
* **Alternatives:** Full React + Vite + TypeScript SPA rewrite — rejected (see `research/architecture_proposals.md`) due to build-pipeline overhead and regression risk.
* **Trade-offs:** Vanilla ES module state management requires discipline around DOM event cleanup, but preserves instant `node --check` validation and zero-build Docker/Windows deployment.
* **Migration:** Extract one module at a time (`audio-player.js` → `avatar-renderer.js` → `studio-store.js`) while keeping `test_e2e_browser.py` green.
* **Backward Compatibility:** `/overlay` and `/deck` remain standalone lightweight entry points importing the shared ES modules.
* **Risks:** Browser ES module caching during local dev (mitigated by FastAPI cache-control headers or versioned query tags).

---

## ADR-014: Continuous Review Governance

* **Status:** Proposed (Pre-Horizon 4 → Horizon 5)
* **Context:** `09_qa_reliability.md` and `13_production_readiness.md` show `380/381` Python `unittest` cases passing, with `TestPlaywrightBrowserE2E` skipped due to missing `playwright`, multiple `asyncio` slow-callback warnings (`0.109s–0.282s`), `aiohttp` `ResourceWarning`s under `-W default`, and stdout-only `print()` logging without `RotatingFileHandler`.
* **Problem:** Without automated CI gates for browser E2E, `ResourceWarning`s, slow callbacks, and structured log rotation, regressions and FD/memory leaks can slip into unattended 24/7 releases.
* **Decision:**
  1. Replace `print()` in `run.py` and `core/` with structured JSON `logging` + `RotatingFileHandler` (`data/logs/maybeai.log`, bounded size/backups).
  2. Close all `aiohttp.ClientSession` / connectors cleanly in `Orchestrator.shutdown()` and test `asyncTearDown`s so `-W default` produces zero `ResourceWarning`s.
  3. Establish mandatory CI gates: `unittest` full suite (`0` failures), `node tests/test_guard_runner.js`, `node --check`, Playwright E2E (`TestPlaywrightBrowserE2E` enabled in CI), `PYTHONASYNCIODEBUG=1` slow-callback budget check, and periodic 8h soak/chaos runs.
* **Alternatives:** Ad-hoc manual pre-release audits — rejected because manual checks do not scale with H4/H5 velocity.
* **Trade-offs:** Slightly longer CI runtime (Playwright + strict warning flags) in exchange for deterministic production readiness.
* **Migration:** Add `.github/workflows/ci.yml` (or local `scripts/verify_all.ps1`) running unit + JS + Playwright + `-W default` gates.
* **Backward Compatibility:** Zero runtime breaking changes; log format configurable (`json` vs `text`) for local developer readability.
* **Risks:** Flaky timing in Playwright E2E under loaded CI runners (mitigated by deterministic `ws` readiness hooks and bounded retries).
