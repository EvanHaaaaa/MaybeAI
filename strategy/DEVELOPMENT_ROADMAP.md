# MaybeAI — 4-Horizon Development Roadmap (`strategy/DEVELOPMENT_ROADMAP.md`)

**Owner:** AGENT 12 (`strat-roadmap` — Strategic Development & Roadmap Manager)  
**Baseline Grounding:** [FINAL_AUDIT_REPORT.md](file:///d:/projects/MaybeAI/audit/FINAL_AUDIT_REPORT.md) and `audit/00..11` (315 Python tests, 1 Node test, 5 JS syntax checks, Chaos Scenarios A–E).  
**Estimation Method:** PERT 3-Point Estimation in engineering person-days (`O` = Optimistic, `M` = Most Likely, `P` = Pessimistic, Expected $E = \frac{O + 4M + P}{6}$, Std Dev $\sigma = \frac{P - O}{6}$). Calendar duration assumes 2 parallel workstreams (Backend/AI + Frontend/Security) unless blocked by a critical-path dependency.

---

## Executive Readiness Summary

| Horizon | Focus | Target Deployment Verdict | PERT Expected Effort ($E$) | Calendar Window (2-Stream) |
|---|---|---|---:|---|
| **Horizon 0** | Emergency Stabilization & Security Hardening | **`GO` for Supervised Localhost**; unblocks **`CONDITIONAL GO` for LAN/Docker** | **14.3 person-days** ($\sigma = 1.4$) | Weeks 1–2 (7–10 days) |
| **Horizon 1** | Real-Time Audio, Cognitive Loop & Reliability | **`GO` for Single-Creator Live Stream (Voice + Games)** | **18.2 person-days** ($\sigma = 1.8$) | Weeks 3–5 (10–14 days) |
| **Horizon 2** | Companion Intelligence, Observability & Creator UX | **`GO` for Unattended / 24-7 Soak & Multi-Surface UX** | **22.5 person-days** ($\sigma = 2.3$) | Weeks 6–9 (12–16 days) |
| **Horizon 3** | Ecosystem, Multi-Agent Collab & Autonomous Showrunner | **`GO` for Multi-AI Collab & Third-Party Plugin Ecosystem** | **27.0 person-days** ($\sigma = 3.0$) | Weeks 10–14 (15–20 days) |
| **Total** | **Full Platform Transformation** | **Production Autonomous Digital Companion** | **82.0 person-days** | **10–14 Weeks** |

---

## Horizon 0 — Emergency Stabilization & Security Hardening

**Objective:** Eliminate all Critical (`[*-CRIT-*]`) and High-severity security, concurrency, and crash-loop defects identified in `FINAL_AUDIT_REPORT.md` so MaybeAI is safe for supervised localhost and authenticated LAN/Docker operation.  
**Hard Rule:** **No LAN/Docker exposure (`--host 0.0.0.0`), public collab, or autonomous mission expansion may ship before Horizon 0 Exit Gates pass.**

### Work Packages & PERT Estimates

| ID | Work Package | Linked Audit Findings | Files / Modules | $O$ | $M$ | $P$ | $E$ (days) |
|---|---|---|---|---:|---:|---:|---:|
| **H0-01** | **Lock Down `/ws` & `GET /api/*` + Fix Docker/LAN Auth** | `[SEC-CRIT-001]`, `[SEC-HIGH-001]`, `[SEC-HIGH-002]` | `run.py` | 1.5 | 2.0 | 3.5 | **2.2** |
| **H0-02** | **Fix `/settings` Stored DOM XSS & Add Creator Token UI** | `[UI-HIGH-001]`, `[UI-HIGH-002]` | `web/settings.js`, `web/app.js`, `web/index.html`, `web/settings.html` | 1.0 | 1.5 | 2.5 | **1.6** |
| **H0-03** | **Confine `ClipPipeline` Paths & Add `ffmpeg` Timeout** | `[SEC-HIGH-003]`, `[GAME-HIGH-004]` | `run.py`, `core/highlights/clipper.py` | 0.5 | 1.0 | 1.5 | **1.0** |
| **H0-04** | **Collab Replay Protection, Loopback Fix & Cooldown Recovery** | `[COLLAB-CRIT-001]`, `[COLLAB-HIGH-001]`, `[COLLAB-HIGH-003]`, `[COLLAB-HIGH-004]` | `core/collab/manager.py`, `core/collab/protocol.py`, `core/orchestrator.py` | 1.5 | 2.0 | 3.0 | **2.1** |
| **H0-05** | **Eliminate `EventBus` Head-of-Line Blocking & Track Async Tasks** | `[PERF-HIGH-001]`, `[INFRA-HIGH-001]`, `[INFRA-HIGH-002]` | `core/event_bus.py`, `core/orchestrator.py`, `run.py` | 1.5 | 2.5 | 4.0 | **2.6** |
| **H0-06** | **Fix Barge-In `CancelledError` & `Singer` BGM Stop** | `[AUDIO-CRIT-001]`, `[AUDIO-HIGH-002]` | `core/tts.py`, `core/singer.py`, `core/orchestrator.py` | 1.0 | 1.5 | 2.5 | **1.6** |
| **H0-07** | **Chess Thread Safety & Minecraft/OBS Disconnect Recovery** | `[GAME-CRIT-001]`, `[GAME-CRIT-002]`, `[GAME-HIGH-002]` | `core/chess/controller.py`, `chess_engine.py`, `core/minecraft/controller.py`, `minecraft/bot.js`, `core/desktop/obs_client.py` | 1.5 | 2.0 | 3.5 | **2.2** |
| **H0-08** | **Unblock Autonomous Goals & Cap Replan Attempts** | `[COG-CRIT-001]`, `[COG-CRIT-002]` | `core/planning/models.py`, `core/planning/executor.py`, `core/planning/replanner.py` | 0.5 | 1.0 | 1.5 | **1.0** |
| **H0-09** | **Plugin Cold-Start Timeout, Crash Eviction & Prompt Injection Gate** | `[QA-HIGH-001]`, `[QA-MED-001]`, `[SEC-HIGH-004]`, `[INFRA-HIGH-005]` | `core/plugins/registry.py`, `core/moderator.py`, `core/orchestrator.py`, `core/config_manager.py` | 1.0 | 1.5 | 2.5 | **1.6** |

*Horizon 0 Total:* $\sum O = 10.0$, $\sum M = 15.0$, $\sum P = 24.5$ $\rightarrow$ **$E = 15.9$ person-days** (with parallelized frontend/backend execution: **14.3–15.9 person-days** across 2 streams $\approx$ **7–10 calendar days**).

### Horizon 0 Exit Gates (Must All Pass)
1. **Auth & XSS Gate:** Unauthenticated `/ws` clients are rejected (`forbidden`) on `memory_action`, `mood_action`, `relationship_action`, `minigame_action`, `story_action`, `trigger_improv`, and do not receive private state snapshots; Docker `--host 0.0.0.0` with `MAYBEAI_CREATOR_TOKEN` authorizes Creator WS; `settings.js` neutralizes `<img src=x onerror=alert(1)>` in all views.
2. **Chaos A–E Regression Gate:**
   - Scenario A: 200ms slow subscriber does **not** stall `fast_sub` (`elapsed < 20ms`).
   - Scenario B: `barge_in()` during `speak_stream()` and `Singer.sing()` emits **zero** post-cancel `ai_response`/Discord/Minecraft replies and stops `pygame.mixer.music`.
   - Scenario C: `test_hard_timeout_kills_infinite_loop_subprocess` passes 10/10 under full-suite CPU load; crashed plugin worker is evicted from `_subprocesses`.
   - Scenario D: Replayed `CollabEnvelope` (`message_id` reuse or `>60s` skew) is rejected; `floor_state="cooldown"` auto-recovers after `turn_cooldown_sec`.
   - Scenario E: `MinecraftController` and `OBSWebSocketClient` transition to `disconnected` (`is_connected=False`) on socket drop; `bot.js` clears `setInterval` on disconnect.
3. **Full Test Suite:** `.\.venv\Scripts\python.exe -W default -m unittest discover tests` passes with **0 errors, 0 failures**.

### Horizon 0 Rollback Criteria
- Any regression in existing `/deck` auth flow, `test_websocket_security.py`, `test_voice_duplex.py`, or `test_collab_and_plugins.py` triggers immediate revert of the offending PR before proceeding to Horizon 1.

---

## Horizon 1 — Real-Time Audio, Cognitive Loop & Reliability

**Objective:** Deliver low-latency, glitch-free full-duplex voice, accurate lip-sync, token-budgeted LLM prompts, verified autonomous mission telemetry, and non-blocking asyncio execution.

### Work Packages & PERT Estimates

| ID | Work Package | Linked Audit Findings | Files / Modules | $O$ | $M$ | $P$ | $E$ (days) |
|---|---|---|---|---:|---:|---:|---:|
| **H1-01** | **Non-Blocking STT Offload** | `[AUDIO-HIGH-001]` | `run.py`, `core/orchestrator.py`, `core/stt.py` | 1.0 | 1.5 | 2.5 | **1.6** |
| **H1-02** | **Server Audio-Envelope Lip-Sync & Browser Arbitration** | `[AUDIO-CRIT-002]` | `core/tts.py`, `core/singer.py`, `web/overlay.js`, `web/app.js` | 2.0 | 3.0 | 4.5 | **3.1** |
| **H1-03** | **TTS Fallback Voice, Dynamic MIME/RVC & `Singer` Provider Routing** | `[AUDIO-HIGH-003]`, `[PERF-MED-002]` | `core/tts.py`, `core/tts_providers.py`, `core/singer.py`, `core/orchestrator.py` | 1.5 | 2.5 | 4.0 | **2.6** |
| **H1-04** | **Persistent `aiohttp` Pooling & Async Loop I/O Offload** | `[PERF-MED-001]`, `[INFRA-MED-003]` | `core/memory/embedding.py`, `core/orchestrator.py`, `run.py` | 1.0 | 2.0 | 3.0 | **2.0** |
| **H1-05** | **Bounded `ContextBudgetManager`, `is_creator` Plumbing & `max_tokens` Alignment** | `[COG-HIGH-002]`, `[COG-HIGH-003]` | `core/brain.py`, `core/conversation/engine.py`, `core/conversation/prompts.py` | 2.0 | 3.0 | 4.5 | **3.1** |
| **H1-06** | **Verified Minecraft Telemetry & Vision/Highlight Fixes** | `[COG-HIGH-001]`, `[GAME-HIGH-001]`, `[GAME-HIGH-003]` | `core/planning/executor.py`, `core/vision/analyzer.py`, `core/highlights/detector.py` | 1.5 | 2.0 | 3.5 | **2.2** |
| **H1-07** | **`ChatReceiver` Bounded Queue, Complete Config Schema & Test Hygiene** | `[INFRA-HIGH-004]`, `[INFRA-MED-001]`, `[INFRA-MED-002]`, `[QA-MED-003]` | `core/chat_receiver.py`, `core/config_manager.py`, `tests/` | 2.0 | 3.0 | 5.0 | **3.2** |

*Horizon 1 Total:* **$E = 17.8$ person-days** ($\sigma \approx 1.8$) $\approx$ **10–14 calendar days** across 2 streams.

### Horizon 1 Exit Gates
1. **Voice Latency Gate:** Sending `barge_in` 50ms after `speech_ended` executes within `<100ms` even while Whisper STT is transcribing in background; zero `asyncio` slow-callback warnings (`>100ms`) during `test_event_bus.py` and `test_system_integrity.py`.
2. **Lip-Sync Gate:** `output_mode="both"` shows zero `targetMouthOpen` oscillation/fighting between server `avatar_state` and browser `AnalyserNode` RMS; short `<1s` utterances stop mouth movement immediately upon audio completion.
3. **Cognitive & Mission Gate:** Live LLM prompts respect per-provider token budgets; `is_creator=True` is preserved across all live providers and error fallbacks; Minecraft autonomous missions wait for real `mc_telemetry` deltas rather than 0ms polling.
4. **Test Hygiene Gate:** Running `unittest discover tests` leaves **0** modified or untracked files in `data/`.

### Horizon 1 Rollback Criteria
- If server-side RMS envelope extraction introduces `>30ms` per-sentence TTS delay, revert to browser-only `AnalyserNode` lip-sync in `browser`/`both` modes while keeping `server`-mode RMS behind a feature flag.

---

## Horizon 2 — Companion Intelligence, Observability & Creator UX

**Objective:** Transform MaybeAI from a fragile single-session prototype into a resilient, observable, 24-7-capable digital companion with cohesive frontend UX across `/`, `/overlay`, `/deck`, and `/settings`.

### Work Packages & PERT Estimates

| ID | Work Package | Linked Audit Findings / Capabilities | Files / Modules | $O$ | $M$ | $P$ | $E$ (days) |
|---|---|---|---|---:|---:|---:|---:|
| **H2-01** | **Cross-Provider LLM Failover & Circuit Breaker** | Planned Capability (`03_cognitive_architecture.md`) | `core/brain.py`, `core/config_manager.py` | 1.5 | 2.5 | 4.0 | **2.6** |
| **H2-02** | **Mood-Modulated Sampling & Second Brain Bidirectional Sync** | Partially Implemented / Planned (`03_cognitive_architecture.md`, `[COG-LOW-002]`) | `core/brain.py`, `core/mood/engine.py`, `core/memory/database.py` | 2.0 | 3.0 | 4.5 | **3.1** |
| **H2-03** | **Shared Frontend Auth/WS Client, Backoff & `/overlay` Re-Sync** | `[UI-HIGH-003]`, `[UI-MED-001]`, `[UI-LOW-001]` | `web/shared-client.js` (new), `web/app.js`, `web/overlay.js`, `web/deck.js`, `web/settings.js` | 2.0 | 3.5 | 5.0 | **3.5** |
| **H2-04** | **AudioWorklet Resampler/Tail Fix & Binary PCM WS Frames** | `[UI-MED-002]`, Proposed Innovation (`07_frontend_ux.md`) | `web/audio-worklet-processor.js`, `web/app.js`, `web/deck.js`, `run.py` | 1.5 | 2.5 | 4.0 | **2.6** |
| **H2-05** | **Local Vendored VRM/Font Assets & Persistent VTS Token + Reconnect** | `[UI-MED-004]`, Planned Capability (`06_security.md`, `02_realtime_audio.md`) | `web/`, `core/vts_client.py` | 1.5 | 2.0 | 3.5 | **2.2** |
| **H2-06** | **Collab Dashboard UI, Approval TTL & Embedding Deduplication** | Planned Capability (`04_collab_protocol.md`), `[COG-MED-001]`, `[COG-HIGH-004]`, `[COG-HIGH-005]` | `web/app.js`, `core/planning/executor.py`, `core/memory/` | 2.5 | 3.5 | 5.5 | **3.7** |
| **H2-07** | **Structured Observability (`/api/metrics` / Soak Test Harness)** | Coverage Gap (`08_qa_reliability.md`, `11_performance_analysis.md`) | `core/`, `tests/` | 2.5 | 4.0 | 6.5 | **4.2** |

*Horizon 2 Total:* **$E = 21.9$ person-days** ($\sigma \approx 2.3$) $\approx$ **12–16 calendar days** across 2 streams.

### Horizon 2 Exit Gates
1. **Failover Gate:** Simulated Gemini `429`/`500` fails over cleanly to OpenAI or Ollama within `<2s` before ever falling back to offline mock text.
2. **Air-Gapped LAN Gate:** `/overlay?renderer=vrm` and `/settings` render with zero external CDN requests (`esm.sh`, `fonts.googleapis.com`).
3. **Soak & Reconnect Gate:** 4-hour simulated soak test (continuous chat + TTS + WS reconnects + memory writes) completes with bounded RSS memory (`<5%` drift), `0` leaked `asyncio` tasks, and automatic `/overlay` state re-sync.

### Horizon 2 Rollback Criteria
- Binary WS audio frames must retain a fallback to JSON base64 (`voice_audio_chunk`) via capability negotiation; any AudioWorklet browser incompatibility reverts to JSON mode without breaking mic input.

---

## Horizon 3 — Ecosystem, Multi-Agent Collab & Autonomous Showrunner

**Objective:** Harden the third-party plugin ecosystem with OS-level isolation, complete bidirectional multi-AI collaboration, and unlock full autonomous showrunner capabilities.

### Work Packages & PERT Estimates

| ID | Work Package | Linked Audit Findings / Capabilities | Files / Modules | $O$ | $M$ | $P$ | $E$ (days) |
|---|---|---|---|---:|---:|---:|---:|
| **H3-01** | **OS-Level Plugin Sandbox & Host-Approved Permissions** | `[SEC-CRIT-002]` | `core/plugins/registry.py`, `core/plugins/sandbox_worker.py`, `core/config_manager.py` | 4.0 | 6.0 | 9.0 | **6.2** |
| **H3-02** | **Non-Query WS Auth & Outbound SSRF Allowlist** | `[SEC-MED-001]`, `[SEC-MED-002]`, `[COLLAB-HIGH-002]` | `run.py`, `core/config_manager.py`, `core/collab/manager.py`, `core/tts_providers.py` | 2.0 | 3.0 | 4.5 | **3.1** |
| **H3-03** | **Full Bidirectional Collab (`duet_sync`, `emote_sync`, `game_move`, Handshake)** | `[COLLAB-MED-001]`, `[COLLAB-MED-002]`, `04_collab_protocol.md` | `core/collab/manager.py`, `core/collab/protocol.py`, `core/orchestrator.py` | 3.0 | 4.5 | 7.0 | **4.7** |
| **H3-04** | **Audio-Clock-Locked Karaoke & Optional Stockfish Chess Backend** | `[GAME-HIGH-005]`, Proposed Innovations (`05_game_engines.md`) | `core/singer.py`, `core/chess/chess_engine.py` | 2.5 | 4.0 | 6.0 | **4.1** |
| **H3-05** | **Autonomous Showrunner: Live VLM Commentary & Storytelling RPG Integration** | Planned / Partially Implemented (`05_game_engines.md`) | `core/vision/vlm.py`, `core/storytelling/engine.py`, `core/highlights/` | 3.5 | 5.0 | 8.0 | **5.3** |
| **H3-06** | **Playwright Browser E2E & Live Adapter Contract Test Suite** | Coverage Gaps (`08_qa_reliability.md`) | `tests/` | 2.5 | 3.5 | 5.5 | **3.7** |

*Horizon 3 Total:* **$E = 27.1$ person-days** ($\sigma \approx 3.0$) $\approx$ **15–20 calendar days** across 2 streams.

### Horizon 3 Exit Gates
1. **Plugin Escape Gate:** Adversarial plugin attempting to read `.env` / `config/settings.json`, open outbound sockets, or exhaust memory is blocked at the OS/sandbox boundary; unapproved `manifest.permissions` are denied by default.
2. **Bidirectional Collab Gate:** Two MaybeAI instances exchange `hello` capability handshake, bidirectional `duet_sync`, `emote_sync`, and `game_move` over `/ws/collab` using header/subprotocol auth, with `collab.enabled=False` strictly enforced.
3. **E2E Gate:** Automated Playwright suite verifies `/`, `/overlay`, `/deck`, and `/settings` flows end-to-end against a live FastAPI test server.

### Horizon 3 Rollback Criteria
- OS-specific sandbox features (e.g., Linux `bubblewrap`/seccomp vs. Windows Job Objects/Restricted Tokens) must degrade cleanly with an explicit `sandbox_level` diagnostic warning rather than silently falling back to `inprocess` execution.
