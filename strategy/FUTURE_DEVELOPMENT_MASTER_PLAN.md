# MaybeAI — Future Development Master Plan (`strategy/FUTURE_DEVELOPMENT_MASTER_PLAN.md`)

**Document ID:** Document D — Next-Generation CTO Master Plan  
**Owner:** AGENT 12 (`ng-strat-roadmap` — CTO Strategy & Roadmap Manager)  
**Synthesized From:**  
- Audit Baseline: [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md) (`HEAD` `96b7315`, Post-Horizon 0–3 + YouTube Karaoke `83298fa`)  
- Product & Backlog: [PRODUCT_VISION.md](file:///d:/projects/MaybeAI/strategy/PRODUCT_VISION.md), [INNOVATION_PORTFOLIO.md](file:///d:/projects/MaybeAI/strategy/INNOVATION_PORTFOLIO.md), [FEATURE_BACKLOG.md](file:///d:/projects/MaybeAI/strategy/FEATURE_BACKLOG.md), [SUCCESS_METRICS.md](file:///d:/projects/MaybeAI/strategy/SUCCESS_METRICS.md)  
- Architecture & Governance: [CURRENT_STATE_ASSESSMENT.md](file:///d:/projects/MaybeAI/strategy/CURRENT_STATE_ASSESSMENT.md), [FUTURE_STATE_ARCHITECTURE.md](file:///d:/projects/MaybeAI/strategy/FUTURE_STATE_ARCHITECTURE.md), [ARCHITECTURE_DECISIONS.md](file:///d:/projects/MaybeAI/strategy/ARCHITECTURE_DECISIONS.md)  
- Research & Radar: [TECHNOLOGY_RADAR.md](file:///d:/projects/MaybeAI/strategy/TECHNOLOGY_RADAR.md), [EXPERIMENT_BACKLOG.md](file:///d:/projects/MaybeAI/research/EXPERIMENT_BACKLOG.md), [EXPERIMENT_RESULTS.md](file:///d:/projects/MaybeAI/research/EXPERIMENT_RESULTS.md)  
- Roadmap & Ops: [DEVELOPMENT_ROADMAP.md](file:///d:/projects/MaybeAI/strategy/DEVELOPMENT_ROADMAP.md), [DEPENDENCY_GRAPH.md](file:///d:/projects/MaybeAI/strategy/DEPENDENCY_GRAPH.md), [COST_AND_RESOURCE_PLAN.md](file:///d:/projects/MaybeAI/strategy/COST_AND_RESOURCE_PLAN.md), [RISK_REGISTER.md](file:///d:/projects/MaybeAI/strategy/RISK_REGISTER.md), [RELEASE_STRATEGY.md](file:///d:/projects/MaybeAI/strategy/RELEASE_STRATEGY.md)

---

## 1. Executive Roadmap Overview (Pre-Horizon 4 + Horizons 4–8)

> [!IMPORTANT]
> **Horizons 0–3 are COMPLETE** (`4c4e473`..`1953889`, plus YouTube Karaoke `83298fa` and docs `96b7315`). MaybeAI does **not** restart from Horizon 0. Execution begins with a focused **Pre-Horizon 4 Remediation Sprint (`PH4-01..PH4-06`)** to clear §13 P0/P1/P2 blockers and unlock **`GO` for Unattended 24/7 Operation**, followed by **Horizons 4–8** (`136.5` total PERT person-days across ~17–21 calendar weeks with 2 parallel streams).

| Phase / Horizon | Strategic Focus | Target Verdict / Maturity | PERT $E$ (days) | $\sigma$ | Calendar (2-Stream) |
|---|---|---|---:|---:|---|
| **Pre-H4 Remediation** | Close §13 P0/P1/P2 blockers (`SEC-GAP-001..005`, `INFRA-MED-001-RES`, `AUDIO-MED-001..003`, `CHAOS-B-001`, `FE-REL-001`, `OPS-001`) | **Unattended 24/7 `GO`** | **13.5** | 1.6 | Weeks 1–2 |
| **Horizon 4** | **Cognitive & Companion Intelligence** (`H4-01..H4-05`: ANN memory, hierarchical consolidation, causal reflection, exact `ContextBudgetManager`, valence memory) | **L4 Cognitive Companion** | **21.2** | 2.4 | Weeks 3–5 |
| **Horizon 5** | **Multimodal & Autonomous Evolution** (`H5-01..H5-05`: Unified Studio ES modules, `startAutonomyLoop` + OBS/MC reconnect, <500ms clause TTS, VLM fusion, `/metrics`) | **L4 Multimodal Autonomy** | **24.8** | 2.8 | Weeks 6–9 |
| **Horizon 6** | **Social & Multi-Agent Ecosystem** (`H6-01..H6-04`: N-peer `PeerSession` mesh, signed plugins + quotas, audience graph, collab games/duets) | **L4.5 Ecosystem** | **26.5** | 3.1 | Weeks 10–13 |
| **Horizon 7** | **Autonomous Content & Digital Presence** (`H7-01..H7-04`: Captioned 9:16 clip factory, `PresenceScheduler` w/ approval gate, analytics, NVENC/CUDA) | **L4.5 Content Studio** | **22.0** | 2.5 | Weeks 14–16 |
| **Horizon 8** | **Long-Term Digital Companion Ecosystem** (`H8-01..H8-04`: Split-node Control Plane + GPU workers, encrypted `.maybeai` backup, SDK v1, continuous evals) | **L5 Digital Companion Platform** | **28.5** | 3.4 | Weeks 17–21 |
| **Total** | **Post-H3 (`L3.0–L3.5`) $\rightarrow$ `L5` Autonomous Digital Companion** | **Full L5 Platform** | **136.5** | — | **~17–21 Weeks** |

---

## 2. Current State & L0–L5 Maturity Summary (`HEAD` `96b7315`)

Verified in [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md) across `97` `core/` Python files, `19` `web/` files (`+5` offline `web/vendor/`), `minecraft/`, and `381` Python `unittest` cases (`380` passed, `1` skipped: Playwright E2E because `playwright` is not installed), plus `node tests/test_guard_runner.js` and `node --check` on `7` JS files:

| Domain | Maturity | Verified Strengths | Primary Remaining Gaps |
|---|---|---|---|
| **Core Infrastructure** | **L3.5** | `_spawn_bg_task`, `_busy_lock`, `ChatReceiver(500)`, atomic `mkstemp`, 157/157 config schema | Missing per-WS outbound queue (`INFRA-MED-001-RES`); 4 dead config keys (`INFRA-MED-002`); `0.11s–0.28s` slow callbacks |
| **Voice & Avatar** | **L3.5** | 16 kHz `AudioWorklet` binary PCM, `EnergyVAD` barge-in, 50ms RMS lip-sync, `isLocalAudioPlaying` arbitration | `ClientTimeout(total=1.8)` truncates >1.8s LLM streams (`AUDIO-MED-001`); `TTSEngine.speak()` swallows `CancelledError` (`AUDIO-MED-002`); `Singer` config reload gap (`AUDIO-MED-003`) |
| **Memory & Cognition** | **L2 / L3** | `ContextBudgetManager`, `ProviderCircuitBreaker`, `MoodEngine` temp coupling (**L3**), `MAX_REPLAN_ATTEMPTS=3` | 2,000-row linear vector scan (`45.32 ms`); `Goal.reflection` write-only; `promises.md` fulfillment unwired; RAG + scalar sliders (no causal learning) |
| **AI Collaboration** | **L2.5** | HMAC-SHA256, `±60s` skew, 1024-nonce LRU, SSRF guard | `disconnect_peer()` leaves `floor_state="listening"` (`CHAOS-B-001`); `on_hello` dead code; subsystems don't auto-emit sync; 2-peer only |
| **Games, Vision & Media** | **L3** | Thread-safe Chess (+ Stockfish), `bot.js` timer cleanup, `ClipPipeline` confinement, `YouTubeKaraokeProcessor` | Missing host binaries (`yt-dlp`/`ffmpeg`/`demucs`/`stockfish`/`obsws-python`) in `.venv`; `startAutonomyLoop()` uncalled; no OBS/MC auto-reconnect |
| **Security & OT** | **L3** | Origin + token-first Creator auth, AST plugin manifest + default-deny, `Moderator` injection drop, 8/8 secret masking | `?token=` + `localStorage` (`SEC-GAP-001`); Windows Python monkeypatch sandbox (`SEC-GAP-002`); raw `obs.summary` injection (`SEC-GAP-003`); DNS TOCTOU (`SEC-GAP-004`); `yt-dlp` bounds (`SEC-GAP-005`) |
| **Frontend & UX** | **L3** (DX **L2**) | `web/shared-client.js`, `/settings` XSS neutralization, `/overlay` re-sync, offline `web/vendor/` | 4 separate apps; `app.js` (`5,896` lines) has 5 unguarded `ws.readyState` nulls (`FE-REL-001`); 0 `:focus-visible`/`prefers-reduced-motion` rules |
| **QA & Observability** | **L3.5 / L3.0** | `380/381` tests + `GuardRunner` + `/api/health` + `/api/metrics` | Playwright E2E skipped; `ResourceWarning`s under `-W default`; stdout `print()` without `RotatingFileHandler` (`OPS-001`) |

**Current Production Readiness Verdict (`13_production_readiness.md`):**
- **Supervised Localhost (`127.0.0.1:7860`):** **`GO`**
- **Authenticated LAN / Docker (`MAYBEAI_HEADLESS=1`):** **`CONDITIONAL GO`**
- **Unattended 24/7 Public Internet:** **`NO-GO`** (until Pre-H4 Remediation `PH4-01..PH4-06` passes)

---

## 3. Target Architecture Evolution, ADRs & Governance Categories 1–5

### 3.1 Three-Horizon Architectural Progression (`FUTURE_STATE_ARCHITECTURE.md`)
- **Near-Term (Pre-H4):** Close `SEC-GAP-001..005`, add per-WS bounded outbound `asyncio.Queue(maxsize=64)`, fix `ClientTimeout(connect=1.8, sock_read=5.0)`, offload sync `_ingest_message` to `asyncio.to_thread()`, reset `floor_state="idle"` on collab disconnect, add `RotatingFileHandler`, and eliminate all `ResourceWarning`s.
- **Mid-Term (Horizon 4–5):** Evolve into a **Modular Monolith + Dedicated Inference & Audio Workers** (`ADR-009`), upgrade `MemoryDatabase` with `sqlite-vec` ANN + `PRAGMA user_version` + nightly consolidation (`ADR-010`), modularize `web/` into zero-build ES modules (`ADR-013`), and enforce CI/soak governance (`ADR-014`).
- **Long-Term (Horizon 6–8):** Scale `CollabManager` to an N-peer `PeerSession` mesh + `RoomFloorArbitrator` (`ADR-011`), close the causal self-reflection loop, and enable split-node Control Plane + remote GPU Worker offload (`H8-01`).

### 3.2 Architecture Decision Records (`ADR-009`..`ADR-014`)
- **`ADR-009`:** Dedicated Inference & Audio Workers (Modular Monolith + Multi-Process Split over typed local IPC).
- **`ADR-010`:** Hierarchical Memory & Schema Versioning (`PRAGMA user_version`, `sqlite-vec` + FTS5 RRF, bidirectional `promises.md`).
- **`ADR-011`:** Multi-Peer Collab Mesh (`PeerSession` registry, `RoomFloorArbitrator`, automatic outbound subsystem sync).
- **`ADR-012`:** Indirect Prompt Injection & OS Sandbox Hardening (`Sec-WebSocket-Protocol`, `<visual_observation_data>` delimiters, Windows Restricted Token/AppContainer, pinned-IP SSRF).
- **`ADR-013`:** Unified Frontend Studio State (zero-build ES modules `studio-store.js`, `avatar-renderer.js`, `audio-player.js`, embedded `/settings` drawer).
- **`ADR-014`:** Continuous Review Governance (structured JSON `RotatingFileHandler`, zero `ResourceWarning`s, mandatory Playwright E2E + soak/chaos gates).

### 3.3 Security, Ethics & Autonomy Governance (Categories 1–5)
1. **Category 1 — Passive & Read-Only (Low / Auto-Allow):** Memory/Metrics reads, VLM screen observation (must sanitize via `Moderator.sanitize_metadata()` + `<visual_observation_data>`).
2. **Category 2 — Ephemeral Stage Expression (Low / Auto-Allow, Bounded):** TTS, Singing, VTS rig, `/ws/overlay`, Chess/MiniGames (serialized by `_busy_lock`, `<1ms` `barge_in()` cancellation).
3. **Category 3 — Persistent Local State & Media (Medium / Auto-Allow w/ Caps):** SQLite memories, `goals.json`, `VODSummarizer`, `ClipPipeline` (`is_relative_to()` + `clips.max_storage_gb`), `yt-dlp` (`--max-filesize` + `<=600s`).
4. **Category 4 — External Social & Collab Dispatch (Medium-High / Rate-Limited + Allowlisted):** Chat platforms, `bot.js`, `/ws/collab` (`PeerSession` + HMAC), outbound plugin HTTP (`plugins.granted_permissions` + pinned-IP SSRF).
5. **Category 5 — High-Risk OT, Stream & System Control (High / Explicit Creator Approval):** OBS stream start/stop, `DesktopCompanionEngine` OS actions, `PUT /api/config`, plugin installs (`PermissionManager` `approval_timeout_sec=300s`, Creator-only auth, `shell=False`).

---

## 4. Scored `FUT-001`..`FUT-015` Innovation & Backlog Summary

Using the §10 7-criterion weighted rubric (`0.20*UV + 0.20*SA + 0.15*FE + 0.15*DF + 0.15*LP + 0.10*CE + 0.05*MS`, max `10.00` — [FEATURE_BACKLOG.md](file:///d:/projects/MaybeAI/strategy/FEATURE_BACKLOG.md)):

| Rank | ID | Feature Name | Score | Bucket | Roadmap Mapping |
|---:|---|---|---:|---|---|
| 1 | `FUT-003` | Hierarchical Episodic-to-Semantic Consolidation & Promise Loop | **8.70** | Strategic Differentiation | `PH4-05`, `H4-02` |
| 2 | `FUT-001` | Causal Self-Reflection & Experience-Driven Replanner | **8.60** | Strategic Differentiation | `H4-03` |
| 3 | `FUT-008` | Autonomy L2–L3 Goal Supervisor & Telemetry-Verified Agency | **8.35** | Core Evolution | `H5-02` |
| 4 | `FUT-015` | Per-WS Bounded Outbound Queues & Structured Telemetry Ops | **8.30** | Quick Wins | `PH4-04`, `PH4-06`, `H4-04`, `H5-05` |
| 5 | `FUT-006` | Sanitized Scene-Change VLM Ring Buffer & Live Commentary | **8.25** | Quick Wins | `PH4-03`, `H5-04` |
| 6 | `FUT-014` | Unified Creator Studio Shell & Hardened Session Auth | **8.25** | Core Evolution | `PH4-01`, `PH4-06`, `H5-01` |
| 7 | `FUT-012` | OS-Enforced Plugin Capability Jail & Typed `PluginSDK` | **8.25** | Core Evolution | `PH4-02`, `H6-02`, `H8-03` |
| 8 | `FUT-010` | Unified Showrunner & Multi-Modal Stage Sync (Karaoke + Games) | **8.20** | Core Evolution | `PH4-03`, `PH4-04`, `H5-02` |
| 9 | `FUT-013` | Multi-Peer `PeerSession` Mesh & `RoomFloorArbitrator` | **8.15** | Strategic Differentiation | `PH4-05`, `H6-01`, `H6-04` |
| 10 | `FUT-011` | Automated Highlight-to-Short & VOD Chapter Pipeline | **8.10** | Quick Wins | `H5-02`, `H7-01`, `H7-04` |
| 11 | `FUT-002` | Hybrid SLM/LLM Tiered Router & Token-Exact Budgeting | **7.80** | Core Evolution | `PH4-04`, `H4-04` |
| 12 | `FUT-004` | Hybrid `sqlite-vec` + FTS5 RRF Scaled Retrieval | **7.75** | Experimental Research | `H4-01` (`EXP-004`) |
| 13 | `FUT-007` | ONNX `silero-vad` + Streaming Partial STT + AEC Duplex | **7.55** | Experimental Research | `PH4-04`, `H5-03` (`EXP-008`) |
| 14 | `FUT-005` | Narrative Identity Graph & Cross-Session Persona Coherence | **7.45** | Long-Term Vision | `H4-05`, `H8-02` |
| 15 | `FUT-009` | Multi-Platform Audience Graph & Longitudinal Relationship Memory | **7.10** | Long-Term Vision | `H6-03` |

---

## 5. Dependency Graph, Cost/Resource Profiles, Risks & Release Governance

- **Critical Path ([DEPENDENCY_GRAPH.md](file:///d:/projects/MaybeAI/strategy/DEPENDENCY_GRAPH.md)):** `PH4-04` (2.1d) $\rightarrow$ `H4-02` (5.3d) $\rightarrow$ `H4-03` (4.7d) $\rightarrow$ `H5-02` (5.2d) $\rightarrow$ `H7-01` (6.2d) $\rightarrow$ `H7-04` (3.9d) $\rightarrow$ `H8-01` (9.8d) = **37.2 sequential person-days**.
- **Cost & Resource Profiles ([COST_AND_RESOURCE_PLAN.md](file:///d:/projects/MaybeAI/strategy/COST_AND_RESOURCE_PLAN.md)):**
  - **Entry-Level (Cloud-Backed Solo):** 4 vCPU, 8 GB RAM, iGPU, 20 GB SSD, 15–45W, ~$3–$15/mo API (Estimated); `900–1,800 ms` turn latency.
  - **Recommended (Hybrid Creator PC):** 8c/16t, 16–32 GB RAM, 8–12 GB VRAM, 100 GB NVMe, 220–380W, ~$10–$45/mo API (Estimated); `500–950 ms` turn latency.
  - **Advanced (Sovereign Local / Split-Node H8):** 12–16+ cores, 32–64 GB RAM, 24 GB+ VRAM, 500 GB+ NVMe, 400–650W, $0/mo API (Estimated); `350–700 ms` turn latency.
- **Top Risks ([RISK_REGISTER.md](file:///d:/projects/MaybeAI/strategy/RISK_REGISTER.md)):** `RISK-SEC-01..03` (Pre-H4 P0s), `RISK-REL-01..02` (Pre-H4 P1/P2s), `RISK-COG-01` (consolidation hallucination), `RISK-AUT-02` (unapproved outbound posting), `RISK-OPS-01` (N-peer split-brain).
- **Release & Continuous Review (§18, [RELEASE_STRATEGY.md](file:///d:/projects/MaybeAI/strategy/RELEASE_STRATEGY.md)):** 6 mandatory CI gates (`unittest -W default` 0 warnings + Playwright E2E, `node --check` + `GuardRunner`, security/hygiene, Chaos A–H, latency budgets, Docker healthcheck), 8–24h soak gates per horizon, runtime feature-flag rollback triggers, and §18 review triggers.

---

## 6. Section 21 — Final CTO Decision Framework

### 21.1 Current State Assessment
1. **Where does MaybeAI actually stand today?**  
   A **hardened, modular single-node AI VTuber platform (overall L3.0–L3.5)** at `HEAD` `96b7315` (`380/381` passing Python tests, `GuardRunner` + 7 JS syntax checks passing). **GO** for Supervised Localhost, **CONDITIONAL GO** for Authenticated LAN/Docker, **NO-GO** for Unattended 24/7 Public Internet.
2. **What is Eve's true cognitive/autonomy ceiling today?**  
   `L2` Cognition/Memory and `L2.5` Collab: Eve **retrieves flat episodic rows (capped at 2,000) and mutates bounded scalar sliders** rather than genuinely learning (`Goal.reflection` is write-only, `StrategyReplanner` is keyword-templated, `fulfill_promise()` is uncalled).

### 21.2 Product Strategy
1. **What is MaybeAI's defensible moat?**  
   **Local-first ownership + embodied real-time presence + hybrid Second Brain**: zero mandatory cloud lock-in, offline Three-VRM (`web/vendor/`), `<1ms` `barge_in()`, SQLite WAL + Markdown Second Brain, and OS-isolated plugins.
2. **Which user segments should we prioritize first?**  
   (1) **Hybrid Creator PC** live VTubers (Recommended profile) who need zero-jank voice/games/karaoke today, followed by (2) **Always-On Docker / Autonomous Studio** hosts once Pre-H4 unlocks Unattended 24/7 `GO`.

### 21.3 Architecture Decisions
1. **Should we rewrite or split into microservices?**  
   **No.** Keep the **Modular Monolith (`run.py` + `Orchestrator` + `EventBus`)** as the low-latency control plane and isolate heavy local ML/audio into **Dedicated Local Worker Processes (`ADR-009`)** over typed local IPC.
2. **Should we adopt external vector/graph DBs (Qdrant/Neo4j)?**  
   **No for H4–H5.** Extend single-file SQLite WAL with `sqlite-vec` ANN + FTS5 RRF + `PRAGMA user_version` (`ADR-010`), preserving zero-daemon backups and `<20 ms` recall up to 50k+ rows.

### 21.4 Future Development & Final CTO Recommendations

#### Top 10 Urgent Engineering Tasks (Pre-Horizon 4 Remediation Sprint)
1. **`SEC-GAP-001` (`PH4-01`):** Switch `web/shared-client.js` + `run.py` WS auth to `Sec-WebSocket-Protocol` and move tokens from `localStorage` to `sessionStorage`/cookie.
2. **`SEC-GAP-002` (`PH4-02`):** Replace Windows Python plugin monkeypatches with Restricted Token/AppContainer isolation; ban `inprocess` for external plugins.
3. **`SEC-GAP-003` (`PH4-03`):** Sanitize `obs.summary` / `obs.eve_commentary` via `Moderator.sanitize_metadata()` + `<visual_observation_data>` delimiters.
4. **`SEC-GAP-004/005` (`PH4-03`):** Pin resolved IPs in `validate_outbound_url()` and add `--max-filesize` + `Semaphore(2)` to `YouTubeKaraokeProcessor`.
5. **`INFRA-MED-001-RES` (`PH4-04`):** Add per-WS bounded outbound `asyncio.Queue(maxsize=64)` + sender task in `run.py`/`Orchestrator`.
6. **`AUDIO-MED-001` (`PH4-04`):** Replace `ClientTimeout(total=1.8)` in `core/brain.py` with `ClientTimeout(connect=1.8, sock_read=5.0)`.
7. **`AUDIO-MED-002/003` (`PH4-04`):** Re-raise `CancelledError` in `TTSEngine.speak()` and forward neural TTS/fallback fields to `Singer.update_config()` in `reload_settings()`.
8. **`CHAOS-B-001` (`PH4-05`):** Reset `floor_state = "idle"` and clear `active_peer` in `CollabManager.disconnect_peer()`; wire `on_hello`.
9. **`FE-REL-001` (`PH4-06`):** Guard all 5 `ws.readyState` calls in `web/app.js` with `ws &&`, complete `onopen` re-sync, and add `:focus-visible` / `prefers-reduced-motion`.
10. **`OPS-001` (`PH4-06`):** Add `RotatingFileHandler` structured logging, close `aiohttp` sessions cleanly (0 `ResourceWarning`s), offload sync `_ingest_message`, and enable Playwright in CI.

#### Top 10 Highest-Value Product Initiatives (Ranked by §10 Score)
1. **`FUT-003` (8.70):** Hierarchical Episodic-to-Semantic Consolidation & `promises.md` Fulfillment Loop.
2. **`FUT-001` (8.60):** Causal Self-Reflection (`Goal.reflection` feedback) & Experience-Driven Replanner.
3. **`FUT-008` (8.35):** Autonomy L2–L3 Goal Supervisor & Telemetry-Verified Agency (`startAutonomyLoop()`).
4. **`FUT-015` (8.30):** Per-WS Bounded Outbound Queues & Structured Telemetry Ops.
5. **`FUT-006` (8.25):** Sanitized Scene-Change VLM Ring Buffer & Live Commentary.
6. **`FUT-014` (8.25):** Unified Creator Studio Shell & Hardened Session Auth.
7. **`FUT-012` (8.25):** OS-Enforced Plugin Capability Jail & Typed `PluginSDK`.
8. **`FUT-010` (8.20):** Unified Showrunner & Multi-Modal Stage Sync (Karaoke + Games).
9. **`FUT-013` (8.15):** Multi-Peer `PeerSession` Mesh & `RoomFloorArbitrator`.
10. **`FUT-011` (8.10):** Automated Highlight-to-Short & VOD Chapter Pipeline.

#### Top 5 Architectural Improvements
1. **Dedicated Inference & Audio Workers (`ADR-009`):** Eliminate `0.11s–0.28s` slow callbacks and isolate GPU/C++ OOMs from the `/ws` control plane.
2. **`sqlite-vec` ANN + `PRAGMA user_version` (`ADR-010`):** Remove the 2,000-row dense recall ceiling while keeping single-file SQLite simplicity.
3. **Per-WS Bounded Outbound Queues + Structured Logging (`ADR-014`):** Guarantee `0 ms` stalled-client HoL impact and bounded 24/7 disk logs.
4. **Zero-Build ES-Module Creator Studio (`ADR-013`):** Split `app.js` (5,896 lines) and eliminate full-page `/settings` WS/mic teardowns.
5. **Multi-Peer `PeerSession` Mesh (`ADR-011`):** Replace 2-peer scalar state with N-peer floor arbitration and automatic subsystem sync.

#### Top 5 Research Experiments (`research/EXPERIMENT_BACKLOG.md`)
1. **`EXP-004` (H4):** Hierarchical Memory Consolidation, `sqlite-vec` (`<=15 ms` @ 10k rows), and Causal `Goal.reflection` benchmark.
2. **`EXP-006` (H4):** Dedicated Inference Worker Isolation (`0` main-loop callbacks `>50 ms`, `<=3s` crash recovery).
3. **`EXP-007` (H4):** Hybrid SLM/Cloud LLM Triage Routing (`>=40%` token cost reduction).
4. **`EXP-008` (H4–H5):** `Silero-VAD` + `faster-whisper` Streaming Partial STT (`<250 ms` partial cadence).
5. **`EXP-005` (H6):** N-Peer Agent Orchestration (`N<=4` Mesh, `0` stuck `floor_state` across 50 peer drops).

#### Top 5 Initiatives to Defer / Reject
1. **Premature Microservices / Kubernetes Split (`REJECTED`):** Adds serialization latency and ops overhead for solo creators.
2. **External Neo4j / Qdrant Vector Databases (`REJECTED`):** Unnecessary daemon complexity when `sqlite-vec` + SQLite WAL handles 50k+ rows in-process.
3. **Unconstrained OS "Computer Use" (`REJECTED`):** Unacceptable blast radius; all desktop actions must remain behind `PermissionManager`.
4. **Monolithic End-to-End Speech-to-Speech Replacement (`REJECTED`):** Bypasses `Moderator`, `RVCVoiceConverter`, `barge_in()`, and Second Brain extraction.
5. **Full Multi-Locale i18n Packs (`DEFER`):** Standardize mixed Indonesian/English UI to clean English first in `FUT-014` before adding multi-locale packs.

#### Recommended Horizon 4 Scope, Long-Term Target & Realistic Sequence
- **Recommended Horizon 4 Scope:** Execute **Pre-H4 Remediation (`PH4-01..06`, 13.5d)** first, then ship **`H4-01..H4-05` (21.2d)**: `sqlite-vec` ANN memory, hierarchical consolidation + `promises.md` loop, causal `Goal.reflection` replanning, tokenizer-exact `ContextBudgetManager` + 4 dead config keys, and valence-weighted affective memory, gated by `EXP-004` and `EXP-006`.
- **Long-Term Target Architecture:** **Modular Monolith Control Plane + Supervised Local/Remote GPU Workers + Event-Driven N-Peer Mesh (`L5`)**, preserving single-command local startup while supporting split-node inference (`H8-01`) and encrypted `.maybeai` identity portability (`H8-02`).
- **Realistic Development Sequence:**
  1. **Weeks 1–2:** Pre-H4 Remediation (`PH4-01..PH4-06`) $\rightarrow$ Achieve **Unattended 24/7 `GO`**.
  2. **Weeks 3–5:** Horizon 4 (`H4-01..H4-05` + `EXP-004/006/007`) $\rightarrow$ Achieve **L4 Cognitive Companion**.
  3. **Weeks 6–9:** Horizon 5 (`H5-01..H5-05` + `EXP-008/010/011`) $\rightarrow$ Achieve **L4 Multimodal Autonomy**.
  4. **Weeks 10–13:** Horizon 6 (`H6-01..H6-04` + `EXP-005`) $\rightarrow$ Achieve **L4.5 Multi-Agent Ecosystem**.
  5. **Weeks 14–16:** Horizon 7 (`H7-01..H7-04`) $\rightarrow$ Achieve **L4.5 Content Studio**.
  6. **Weeks 17–21:** Horizon 8 (`H8-01..H8-04`) $\rightarrow$ Achieve **L5 Digital Companion Platform**.
