# MaybeAI — Executive Future Development Master Plan (`strategy/FUTURE_DEVELOPMENT_MASTER_PLAN.md`)

**Prepared by:** Strategic Planning Swarm (Agents 9–12: `strat-product`, `strat-ai`, `strat-arch`, `strat-roadmap`)  
**Compiled by:** AGENT 12 (`strat-roadmap` — Strategic Development & Roadmap Manager)  
**Audit Grounding:** [FINAL_AUDIT_REPORT.md](file:///d:/projects/MaybeAI/audit/FINAL_AUDIT_REPORT.md) & `audit/00..11` (Zero source modifications)

---

## 1. Executive Vision & Strategic Thesis

MaybeAI (**Eve**) is currently a feature-rich **AI VTuber runtime** (94 Python modules in `core/`, FastAPI/WebSocket server `run.py`, 4 web surfaces `/`, `/settings`, `/overlay`, `/deck`, Node.js `minecraft/` bridge, OBS, VTube Studio, `python-chess`, and an out-of-process plugin sandbox).

**Long-Term Transformation:** Evolve MaybeAI from a creator-triggered stream tool into a **persistent, trustworthy, autonomous digital companion** defined by 4 core pillars ([PRODUCT_VISION.md](file:///d:/projects/MaybeAI/strategy/PRODUCT_VISION.md)):
1. **Trustworthy & Secure Broadcast Core (`Secure-by-Default`)** — Consistent Creator authentication, XSS-free UI, prompt-injection enforcement, and OS-jailed plugins across Localhost, LAN, and Docker.
2. **Real-Time Duplex Presence (`Zero-Jank Voice & Avatar`)** — Sub-second barge-in across speech and karaoke, non-blocking STT, and true audio-envelope lip-sync driving VTS, 2D Canvas, and offline-bundled 3D VRM.
3. **Grounded Cognitive Continuity (`Memory That Earns Trust`)** — Token-budgeted prompts (`ContextBudgetManager`), cross-provider LLM failover, Creator authority propagation, and closed-loop missions verified against real world telemetry.
4. **Interactive Worlds & Multi-AI Stage (`Playable Entertainment`)** — Resilient, reconnect-capable Minecraft, Chess, RPG Storytelling, Karaoke, Highlights, and bidirectional AI-to-AI Collab.

> **Strategic Thesis:** MaybeAI does not win by adding more disconnected mini-features. Its architectural moat already exists (`EventBus` + Second Brain + multi-surface studio + game/world bridges). Winning requires **hardening the core loop into a secure, non-blocking nervous system first (Horizons 0–1)**, then compounding into an observable, multi-AI companion platform (Horizons 2–3).

---

## 2. Current State Summary (Maturity & Production Readiness)

### Production Readiness Verdict ([FINAL_AUDIT_REPORT.md](file:///d:/projects/MaybeAI/audit/FINAL_AUDIT_REPORT.md))
- **Unattended / Public / Docker / LAN Stream:** **`NO-GO`** (blocked by `[SEC-CRIT-001]`, `[SEC-HIGH-001]`, `[SEC-HIGH-002]`, `[UI-HIGH-001]`, `[COLLAB-CRIT-001]`, `[SEC-CRIT-002]`).
- **Supervised Localhost Creator Stream:** **`CONDITIONAL GO`** (viable for local experimentation once P0 fixes land for `[PERF-HIGH-001]`, `[GAME-CRIT-001]`, `[AUDIO-CRIT-001]`, `[COG-CRIT-001/002]`).

### L0–L5 Subsystem Maturity Scorecard ([CURRENT_STATE_ASSESSMENT.md](file:///d:/projects/MaybeAI/strategy/CURRENT_STATE_ASSESSMENT.md))

| Subsystem | Maturity | Readiness | Key Verified Gaps (Audit IDs) |
|---|---|---|---|
| **1. Core Infrastructure** | **L2.5** | Conditional | Sequential `EventBus.publish()` HoL blocking (`[PERF-HIGH-001]`), 12+ untracked `create_task` leaks (`[INFRA-HIGH-001]`), `perform_song()` lock bypass (`[INFRA-HIGH-002]`), LLM key masking gap (`[INFRA-HIGH-005]`). |
| **2. Audio, Voice & Avatar** | **L2.0** | Conditional | `speak_stream()` swallows `CancelledError` (`[AUDIO-CRIT-001]`), 80 ms square-wave lip-sync collides with browser RMS (`[AUDIO-CRIT-002]`), STT blocks WS loop (`[AUDIO-HIGH-001]`), `Singer` BGM ignores barge-in (`[AUDIO-HIGH-002]`). |
| **3. Cognition & Memory** | **L2.5** | Conditional | Replanned goals never complete (`[COG-CRIT-001]`), infinite 25s replan loop (`[COG-CRIT-002]`), 0ms MC polling vs. offline fabrication (`[COG-HIGH-001]`), unbounded prompt (`[COG-HIGH-002]`), `is_creator` dropped (`[COG-HIGH-003]`). |
| **4. AI-to-AI Collab** | **L1.5** | **NO-GO** | Zero replay protection (`[COLLAB-CRIT-001]`), `_is_loopback_url` spoofing (`[COLLAB-HIGH-001]`), permanent cooldown deadlock (`[COLLAB-HIGH-003]`), reply storm (`[COLLAB-HIGH-004]`), partial sync. |
| **5. Games, Vision & OT** | **L2.0** | Conditional | `chess.Board` thread race (`[GAME-CRIT-001]`), Mineflayer bridge no crash recovery (`[GAME-CRIT-002]`), OBS stale `is_connected=True` (`[GAME-HIGH-002]`), `ffmpeg` missing timeout/confinement (`[GAME-HIGH-004]`, `[SEC-HIGH-003]`). |
| **6. Security & Trust** | **L1.5** | **NO-GO** | Unauthenticated `/ws` mutations & state push (`[SEC-CRIT-001]`), unjailed plugin sandbox (`[SEC-CRIT-002]`), Docker/LAN WS auth deadlock (`[SEC-HIGH-001]`), unauthenticated `GET /api/*` (`[SEC-HIGH-002]`), non-blocking `Moderator` (`[SEC-HIGH-004]`). |
| **7. Frontend & UX** | **L2.0** | **NO-GO** (`/settings`) | Stored DOM XSS in `/settings` (`[UI-HIGH-001]`), missing token UI & `401/403` crash (`[UI-HIGH-002]`), 2s WS storm & `deck.js` double-WS (`[UI-HIGH-003]`), CDN VRM dependency (`[UI-MED-004]`). |
| **8. QA, Testing & Ops** | **L2.0** | Conditional | 315 Python tests (1 load-sensitive error `[QA-HIGH-001]`), 0% live adapter/browser E2E, tests mutate `data/` (`[QA-MED-003]`), 13+ asyncio slow-callback warnings (`>100ms`). |

---

## 3. Target Architecture Evolution & Formal ADRs

MaybeAI follows an **evolutionary hardening** path (no microservices split or Rust/Go rewrite), progressing from **L1.5–L2.5** to **L3.0 (Hardened Single-Node, Horizons 0–1)** $\rightarrow$ **L3.5–L4.0 (Modular Event-Driven Companion, Horizon 2)** $\rightarrow$ **L4.5–L5.0 (Autonomous Showrunner & Multi-Agent Runtime, Horizon 3)** ([FUTURE_STATE_ARCHITECTURE.md](file:///d:/projects/MaybeAI/strategy/FUTURE_STATE_ARCHITECTURE.md)).

| ADR | Architectural Decision Summary | Target Horizon |
|---|---|---|
| **ADR-001** | Concurrent `EventBus.publish()` (`asyncio.gather` + per-handler timeout), per-WS bounded `asyncio.Queue(maxsize=64)`, `TaskSupervisor`, `_busy_lock` on `perform_song()`, bounded `ChatReceiver.queue(500)`. | Horizon 0–1 |
| **ADR-002** | Unified `_verify_creator_request()` (token checked before `_LOOPBACK_HOSTS`), split `/ws` (Creator) vs `/ws/overlay` (read-only), gate all `GET /api/*` (except `/api/health`), mask `llm.*_api_key`, enforce `Moderator.strict_mode`, confine `ClipPipeline` to `data/clips`. | Horizon 0 |
| **ADR-003** | Separate `startup_timeout_sec` (`5.0s`), evict crashed plugin workers, disable `inprocess` for external plugins, enforce host-granted `plugins.granted_permissions`, and add OS-level sandbox (`bubblewrap`/seccomp or Windows Job Objects). | Horizon 0–3 |
| **ADR-004** | Strict `CancelledError` propagation in `TTSEngine`/`Singer`, offload `transcribe_wav_bytes()`, fix Edge fallback voice & dynamic MIME, replace 80 ms square wave with server PCM/RMS envelope + browser sync arbitration. | Horizon 0–2 |
| **ADR-005** | Plumb `is_creator` across all live LLM paths/fallbacks, introduce `ContextBudgetManager`, add `Primary -> Secondary -> Ollama -> Mock` failover, share persistent `aiohttp` pool, evaluate `sqlite-vec` + FTS5 RRF. | Horizon 1–2 |
| **ADR-006** | Exclude `REPLANNED` from `Goal.recalculate_progress()`, cap `MAX_REPLAN_ATTEMPTS=3`, add `approval_timeout_sec`, verify Minecraft deltas via `mc_telemetry`, clone `chess.Board` before `to_thread`, auto-reconnect MC/OBS. | Horizon 0–1 |
| **ADR-007** | Enforce `±60s` timestamp skew + `(sender_id, message_id)` nonce LRU cache, exact `urlparse().hostname` loopback check, fix `_refresh_cooldown()` deadlock, hold `"thinking"`/`"speaking"` before LLM reply, enforce `collab.enabled`. | Horizon 0–3 |
| **ADR-008** | Escape all `/settings` & `/` HTML sinks, extract `web/shared-client.js` (`CreatorAuth` + exponential backoff `ReconnectingWebSocket` + `/overlay` `onopen` re-sync), vendor Three-VRM/fonts locally, binary WS PCM frames. | Horizon 0–2 |

*(Full ADR specifications in [ARCHITECTURE_DECISIONS.md](file:///d:/projects/MaybeAI/strategy/ARCHITECTURE_DECISIONS.md).)*

---

## 4. Scored Innovation & Feature Portfolio Summary

Using the 7-criterion weighted rubric (`Score = 0.20*UV + 0.15*TF + 0.25*AR + 0.15*AL + 0.10*LU + 0.10*MC + 0.05*DF`, max `5.00`) in [FEATURE_BACKLOG.md](file:///d:/projects/MaybeAI/strategy/FEATURE_BACKLOG.md) and [INNOVATION_PORTFOLIO.md](file:///d:/projects/MaybeAI/strategy/INNOVATION_PORTFOLIO.md):

- **Top Tier P0 Release Blockers (Scores `4.15–4.75`):**
  - `BL-01` (**4.75**): Lock down `/ws`, `GET /api/*` & Docker/LAN Creator Auth (`[SEC-CRIT-001]`, `[SEC-HIGH-001/002]`).
  - `BL-02` (**4.70**): Fix `/settings` Stored DOM XSS & Creator Token UI (`[UI-HIGH-001/002]`).
  - `BL-04` (**4.65**): Barge-in `CancelledError` propagation, `Singer` BGM stop & STT offload (`[AUDIO-CRIT-001]`, `[AUDIO-HIGH-001/002]`).
  - `BL-03` (**4.50**): Non-blocking `EventBus` + `TaskSupervisor` + `perform_song()` lock (`[PERF-HIGH-001]`, `[INFRA-HIGH-001/002]`).
  - `BL-05` (**4.45**): Collab replay protection, loopback URL fix & cooldown recovery (`[COLLAB-CRIT-001]`, `[COLLAB-HIGH-001/003/004]`).
- **Top Tier P1/P2 Expansion (Scores `3.45–4.30`):**
  - `BL-09` (**4.30**): Prompt injection enforcement & LLM key masking (`[SEC-HIGH-004]`, `[INFRA-HIGH-005]`).
  - `BL-07` (**4.25**): Unblock Autonomous Goals & cap replans (`[COG-CRIT-001/002]`, `[COG-HIGH-001]`).
  - `BL-14` (**4.20**): Server-side audio-envelope lip-sync & browser arbitration (`[AUDIO-CRIT-002]`).
  - `BL-15` (**4.10**): `ContextBudgetManager` & cross-provider LLM failover (`[COG-HIGH-002]`).
  - `BL-16` (**3.80**): Shared Auth/WS client + offline Three-VRM bundling (`[UI-HIGH-003]`, `[UI-MED-004]`).
- **Horizon-3 Bets (`2.70–3.40`):** OS-level Plugin Jail (`BL-21`, **3.40**), Self-Healing Watchdog (`BL-25`, **3.35**), Hybrid `sqlite-vec` + FTS5 RRF (`BL-22`, **3.30**), Binary WS + Silero-VAD (`BL-23`, **3.00**), Negotiated Collab Handshake (`BL-26`, **2.85**), Event-Driven VLM Ring Buffer (`BL-24`, **2.70**).

---

## 5. 4-Horizon Execution Roadmap, Critical Path & Exit Gates

Grounded in [DEVELOPMENT_ROADMAP.md](file:///d:/projects/MaybeAI/strategy/DEVELOPMENT_ROADMAP.md) and [DEPENDENCY_MAP.md](file:///d:/projects/MaybeAI/strategy/DEPENDENCY_MAP.md):

| Horizon | Scope | PERT Expected Effort ($E$) | Calendar (2-Stream) | Mandatory Exit Gate |
|---|---|---|---|---|
| **Horizon 0** | **Emergency Stabilization & Security Hardening** (`H0-01`..`H0-09`) | **15.9 person-days** ($\sigma \approx 1.4$) | **Weeks 1–2** (7–10 days) | Unauth `/ws` & `/api/*` blocked; Docker auth works; XSS neutralized; Chaos A–E regressions fixed; `unittest` 0 errors. |
| **Horizon 1** | **Real-Time Audio, Cognitive Loop & Reliability** (`H1-01`..`H1-07`) | **17.8 person-days** ($\sigma \approx 1.8$) | **Weeks 3–5** (10–14 days) | Non-blocking STT (`<100ms` barge-in); RMS lip-sync with zero `both`-mode jitter; `ContextBudgetManager` + `is_creator` active; 0 `data/` test mutations. |
| **Horizon 2** | **Companion Intelligence, Observability & UX** (`H2-01`..`H2-07`) | **21.9 person-days** ($\sigma \approx 2.3$) | **Weeks 6–9** (12–16 days) | Cross-provider LLM failover `<2s`; air-gapped VRM/fonts; 4-hour soak test (`<5%` RSS drift, `0` leaked tasks). |
| **Horizon 3** | **Ecosystem, Multi-Agent Collab & Showrunner** (`H3-01`..`H3-06`) | **27.1 person-days** ($\sigma \approx 3.0$) | **Weeks 10–14** (15–20 days) | OS plugin jail blocks `.env`/network escape; bidirectional Collab handshake; Playwright E2E suite passing. |

- **Critical Path (`20.8` sequential person-days across 10–14 calendar weeks):** `H0-05` (`EventBus`) $\rightarrow$ `H0-06` (Barge-In) $\rightarrow$ `H1-02` (RMS Lip-Sync) / `H1-05` (`ContextBudgetManager`) $\rightarrow$ `H2-01/H2-02` (Failover & Memory) $\rightarrow$ `H2-07` (4h Soak) $\rightarrow$ `H3-01` (OS Plugin Sandbox).
- **Hard Sequencing Rule:** `H0-01/02` (Auth + XSS) and `H0-05/06` (`EventBus` + Barge-In) **must** complete before any LAN/Docker exposure, real-time audio refactors, or autonomous agency expansion.

---

## 6. R&D & Experiment Program Summary

Grounded in [TECHNOLOGY_RADAR.md](file:///d:/projects/MaybeAI/strategy/TECHNOLOGY_RADAR.md), [RESEARCH_PLAN.md](file:///d:/projects/MaybeAI/strategy/RESEARCH_PLAN.md), and [rejected_proposals.md](file:///d:/projects/MaybeAI/research/rejected_proposals.md):

- **ADOPT Now:** In-memory audio pipeline + persistent `aiohttp` pooling; Server PCM/RMS lip-sync + browser arbitration; `ContextBudgetManager`; Bounded HTN/FSM mission loop + telemetry ACK.
- **TRIAL via Gated Experiments:**
  - **`EXP-001` (Voice Duplex & Lip-Sync):** `Silero-VAD` (ONNX) + async `faster-whisper` + `kokoro-onnx` vs `Edge-TTS`. Gate: `<700ms` local TTFA, `<=50ms` barge-in, `r >= 0.85` lip-sync, `<=2.5 GB` VRAM, 100/100 Chaos B interrupts.
  - **`EXP-002` (Hybrid Memory & Budgeting):** `sqlite-vec` / `hnswlib` + FTS5 BM25 RRF + `ContextBudgetManager`. Gate: `<=15ms` p95 at 10,000 rows, `>=+15%` Recall@5 beyond row 300, `<=1,800` input tokens.
  - **`EXP-003` (Closed-Loop Agency):** `MAX_REPLAN_ATTEMPTS=3`, cross-tick `mc_telemetry` ACK, `bot.js` supervisor. Gate: 2-hour Mineflayer soak with `0` infinite loops and `<=10s` bridge auto-reconnect.
- **Explicitly Rejected (`HOLD`):** Premature microservices split, Kubernetes orchestration, full Rust/Go rewrite of `core/`, unconstrained OS desktop "Computer Use", monolithic Speech-to-Speech models (breaks `Moderator`, RVC, `barge_in`, Second Brain), external Qdrant/Milvus, and unbounded self-spawning live-stream swarms.

---

## 7. Cost, Infrastructure & Risk Mitigation Summary

### Compute & Cost Footprint ([COST_AND_INFRASTRUCTURE.md](file:///d:/projects/MaybeAI/strategy/COST_AND_INFRASTRUCTURE.md))
- **4 Deployment Profiles:** Profile A (Cloud-Backed Minimal, CPU-only), Profile B (Hybrid Creator PC, **8–12 GB VRAM**), Profile C (Air-Gapped Sovereign, **16–24 GB VRAM** with Ollama + local audio), Profile D (Docker Headless 24/7, **180–350 MB RAM** base).
- **Token & Spend Optimization:** `ContextBudgetManager` (`H1-05`) cuts per-turn input tokens from **3,500–6,000** down to **1,200–1,800 (~65% savings)**, lowering 24/7 autonomous Flash/Mini-tier spend from ~$18–$65/mo baseline and preventing 4K/8K local Ollama overflows.

### Chaos Scenarios A–F Mitigation Summary ([RISK_REGISTER.md](file:///d:/projects/MaybeAI/strategy/RISK_REGISTER.md))
- **Scenario A (`EventBus` Stall):** Concurrent `gather` + per-WS bounded queues + dead-listener eviction (`H0-05`).
- **Scenario B (Barge-In Race):** Re-raise `CancelledError`, stop `Singer` BGM, coalesce lip-sync (`H0-06`, `H0-05`).
- **Scenario C (Plugin Escape/Crash):** `startup_timeout_sec` + crash eviction (`H0-09`); OS jail + host-approved permissions (`H3-01`).
- **Scenario D (Collab Replay/Flood):** `±60s` timestamp + `message_id` nonce cache, `urlparse` loopback check, cooldown `turn_count` reset (`H0-04`).
- **Scenario E (MC/OBS Desync & Replan Loop):** Socket-drop state reset + timer cleanup (`H0-07`), `REPLANNED` exclusion + `MAX_REPLAN_ATTEMPTS=3` (`H0-08`).
- **Scenario F (Prompt Injection -> OS/XSS Pivot):** `/ws` + `/api/*` auth (`H0-01`), `/settings` HTML escaping (`H0-02`), `Moderator.strict_mode` + metadata sanitization (`H0-09`).

---

## 8. Immediate Next 7-Day Action Plan (Horizon 0 Kickoff)

| Day | Parallel Track A (Security & Frontend) | Parallel Track B (Core Concurrency, Audio & Games) |
|---|---|---|
| **Days 1–2** | `H0-01`: Gate `/ws` mutating actions & `GET /api/*`; fix `_is_ws_creator_authorized` token-first check for Docker/LAN. | `H0-05`: Refactor `EventBus.publish()` to concurrent `gather` + per-WS bounded queues; route all tasks via `_spawn_bg_task()`. |
| **Days 3–4** | `H0-02`: Escape all dynamic `innerHTML` in `web/settings.js`; add Creator token prompt + `401/403` handling to `/` & `/settings`. | `H0-06` & `H0-08`: Propagate `CancelledError` in `speak_stream()`, stop `Singer` BGM on `barge_in()`, fix `REPLANNED` denominator & cap replans at `3`. |
| **Days 5–6** | `H0-03` & `H0-09`: Confine `ClipPipeline` to `data/clips` + `ffmpeg -nostdin`/timeout; enforce `Moderator.strict_mode`, mask `llm.*_api_key`, fix plugin cold-start timeout & eviction. | `H0-04` & `H0-07`: Add Collab `message_id` nonce + `±60s` window + cooldown recovery; clone `chess.Board` before `to_thread`; fix MC/OBS disconnect state & `bot.js` timers. |
| **Day 7** | **Horizon 0 Gate Verification:** Run full `unittest discover tests` (`-W default`), `test_guard_runner.js`, `node --check web/*.js`, and Chaos Scenarios A–F verification. Target: **0 errors, 0 failures, `GO` for Supervised & Authenticated Docker/LAN**. |
