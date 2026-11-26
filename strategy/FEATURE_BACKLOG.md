# MaybeAI — Prioritized Feature & Hardening Backlog (`strategy/FEATURE_BACKLOG.md`)

**Author:** Agent 9 — Product Vision & Innovation Strategist (`strat-product`)  
**Grounding Baseline:** `audit/FINAL_AUDIT_REPORT.md` and `audit/00..11`

---

## 1. 7-Criterion Weighted Scoring Rubric

Every backlog item is scored **1–5** on each of the 7 criteria (for **Maintenance Cost**, **5 = lowest ongoing burden**, **1 = highest ongoing burden**, so higher total score = higher priority):

| Criterion | Code | Weight | Scoring Anchor (1 -> 5) |
|---|---|---:|---|
| **User/Creator Value** | `UV` | 20% | 1 = Marginal niche polish -> 5 = Unblocks core streaming/Docker/LAN workflows |
| **Technical Feasibility** | `TF` | 15% | 1 = High R&D / OS-specific risk -> 5 = Surgical, well-scoped change in existing modules |
| **Audit Risk Reduction** | `AR` | 25% | 1 = No audit risk -> 5 = Eliminates Critical security/safety/deadlock finding |
| **Architectural Leverage** | `AL` | 15% | 1 = Isolated 1-file fix -> 5 = Stabilizes shared spine (`EventBus`, `Brain`, `/ws`) |
| **Latency/UX Impact** | `LU` | 10% | 1 = Background/internal only -> 5 = Eliminates visible jitter, stall, or UX lockout |
| **Maintenance Cost** *(inverse)* | `MC` | 10% | 1 = High ongoing maintenance -> 5 = Reduces or adds near-zero maintenance |
| **Differentiation** | `DF` | 5% | 1 = Commodity hygiene -> 5 = Distinct AI companion / multi-AI / studio moat |

**Formula:** `Score = 0.20*UV + 0.15*TF + 0.25*AR + 0.15*AL + 0.10*LU + 0.10*MC + 0.05*DF` (Max = `5.00`).

---

## 2. Prioritized Backlog

### Tier P0 — Release Blockers (Required for `GO` on Supervised & Docker/LAN Streams)

| ID | Item | Maturity Class | Linked Audit Findings | `UV` | `TF` | `AR` | `AL` | `LU` | `MC` | `DF` | Weighted Score |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **BL-01** | **Lock Down `/ws`, `GET /api/*` & Fix Docker/LAN Creator Auth** (`run.py`: gate `memory_action`, `mood_action`, `relationship_action`, `multiplayer_action`, `minigame_action`, `story_action`, `trigger_improv`, initial state push; check `MAYBEAI_CREATOR_TOKEN` before loopback; reject `origin is None`) | `Current Capability` (Hardening) | `[SEC-CRIT-001]`, `[SEC-HIGH-001]`, `[SEC-HIGH-002]` | 5 | 5 | 5 | 5 | 4 | 5 | 2 | **4.75** |
| **BL-02** | **Fix `/settings` Stored DOM XSS & Add Creator Token UI** (`web/settings.js`, `web/index.html`, `web/app.js`: escape all dynamic `innerHTML` sinks, check `r.ok`, handle `forbidden`, add shared token prompt) | `Current Capability` (Hardening) + `Partially Implemented` | `[UI-HIGH-001]`, `[UI-HIGH-002]`, `[UI-MED-003]` | 5 | 5 | 5 | 4 | 5 | 5 | 2 | **4.70** |
| **BL-03** | **Eliminate `EventBus` Head-of-Line Blocking & Track Async Tasks** (`core/event_bus.py`, `core/orchestrator.py`: concurrent dispatch, bounded per-WS queues, dead-listener eviction, `_spawn_bg_task`, `_busy_lock` in `perform_song()`) | `Proposed Innovation` (H1 Core) + `Current Capability` | `[INFRA-HIGH-003]`, `[PERF-HIGH-001]`, `[INFRA-HIGH-001]`, `[INFRA-HIGH-002]` | 4 | 4 | 5 | 5 | 5 | 5 | 2 | **4.50** |
| **BL-04** | **Fix Barge-In `CancelledError` Propagation, `Singer` BGM Stop & STT Offload** (`core/tts.py`, `core/orchestrator.py`, `core/singer.py`: re-raise/check cancellation, stop `pygame.mixer.music`, offload `transcribe_wav_bytes()`) | `Partially Implemented` (Completion) | `[AUDIO-CRIT-001]`, `[AUDIO-HIGH-002]`, `[AUDIO-HIGH-001]` | 5 | 5 | 5 | 4 | 5 | 4 | 3 | **4.65** |
| **BL-05** | **Collab Replay Protection, Loopback URL Fix & Cooldown Recovery** (`core/collab/manager.py`, `run.py`: `message_id` TTL cache + `±60s` timestamp window, `urlparse().hostname` check, reset `turn_count` in `_refresh_cooldown()`, remove query-secret mutation) | `Partially Implemented` (Completion) | `[COLLAB-CRIT-001]`, `[QA-CRIT-001]`, `[SEC-HIGH-005]`, `[COLLAB-HIGH-001]`, `[COLLAB-HIGH-002]`, `[COLLAB-HIGH-003]`, `[COLLAB-HIGH-004]` | 4 | 5 | 5 | 4 | 4 | 5 | 3 | **4.45** |
| **BL-06** | **Confine `ClipPipeline` Paths, Escape Filtergraph & Add `ffmpeg` Timeout** (`run.py`, `core/highlights/clipper.py`: restrict to `data/clips`, escape `, [ ] ;`, `-nostdin`, `asyncio.wait_for`) | `Current Capability` (Hardening) | `[SEC-HIGH-003]`, `[GAME-HIGH-004]` | 4 | 5 | 5 | 3 | 3 | 5 | 2 | **4.15** |
| **BL-07** | **Unblock Autonomous Goals & Cap Replan Attempts** (`core/planning/models.py`, `executor.py`, `replanner.py`: exclude `REPLANNED` from denominator, `MAX_REPLAN_ATTEMPTS=3`, replace 0ms MC polling) | `Partially Implemented` (Completion) | `[COG-CRIT-001]`, `[COG-CRIT-002]`, `[COG-HIGH-001]`, `[COG-MED-001]` | 4 | 4 | 5 | 4 | 4 | 4 | 4 | **4.25** |
| **BL-08** | **Fix Chess Thread Safety & Minecraft/OBS Disconnect Recovery** (`core/chess/`, `core/minecraft/controller.py`, `minecraft/bot.js`, `core/desktop/obs_client.py`: `board.copy()`, clear `bot.js` timers, reset `connection_status`/`is_connected`) | `Current Capability` (Hardening) | `[GAME-CRIT-001]`, `[GAME-CRIT-002]`, `[QA-HIGH-002]`, `[GAME-HIGH-002]`, `[QA-HIGH-003]`, `[GAME-HIGH-003]` | 4 | 4 | 5 | 4 | 4 | 4 | 2 | **4.15** |

---

### Tier P1 — Core Hardening & Security Hygiene (Weeks 2–4)

| ID | Item | Maturity Class | Linked Audit Findings | `UV` | `TF` | `AR` | `AL` | `LU` | `MC` | `DF` | Weighted Score |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **BL-09** | **Enforce Prompt Injection Filtering & Mask LLM API Keys** (`core/moderator.py`, `core/config_manager.py`: wire `strict_mode`/`prompt_injection_filter` to drop flagged chat, sanitize `user`/`donation_amount`, mask `llm.*_api_key`, unique `.tmp` save) | `Partially Implemented` + `Current Capability` | `[SEC-HIGH-004]`, `[INFRA-HIGH-005]`, `[INFRA-HIGH-004]` | 4 | 5 | 5 | 4 | 3 | 5 | 2 | **4.30** |
| **BL-10** | **Plumb `is_creator` Across All Live LLM Paths & Fallbacks** (`core/brain.py`, `core/conversation/engine.py`: inject `[CREATOR VERIFIED]` in `abuild_system_prompt()` and pass to mock fallbacks) | `Current Capability` (Hardening) | `[COG-HIGH-003]` | 4 | 5 | 4 | 4 | 3 | 5 | 3 | **4.10** |
| **BL-11** | **Fix Plugin Cold-Start Flakiness & Evict Crashed Workers** (`core/plugins/registry.py`: separate `startup_timeout_sec` from `hook_timeout_sec`, evict dead workers, isolate tests from `data/`) | `Partially Implemented` (Completion) | `[QA-HIGH-001]`, `[QA-MED-001]`, `[QA-MED-003]` | 3 | 5 | 4 | 4 | 3 | 5 | 2 | **3.85** |
| **BL-12** | **Fix `VisualAnalyzer` `scene_label` Crash & SSRF URL Validation** (`core/vision/analyzer.py`, `core/config_manager.py`, `core/collab/manager.py`: fix `detected_label` typo, validate outbound HTTP/WS URLs) | `Current Capability` (Hardening) | `[GAME-HIGH-001]`, `[SEC-MED-001]` | 3 | 5 | 4 | 3 | 3 | 5 | 1 | **3.65** |
| **BL-13** | **Fix AudioWorklet Tail-Frame Drop & Resampler Discontinuity** (`web/audio-worklet-processor.js`, `web/app.js`, `web/deck.js`) | `Partially Implemented` (Completion) | `[UI-MED-002]`, `[UI-MED-001]` | 4 | 4 | 2 | 3 | 5 | 5 | 2 | **3.45** |

---

### Tier P2 — Adjacent Expansion (Months 2–3)

| ID | Item | Maturity Class | Linked Audit Findings | `UV` | `TF` | `AR` | `AL` | `LU` | `MC` | `DF` | Weighted Score |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **BL-14** | **Server-Side Audio-Envelope Lip-Sync & Conflict-Free Browser Playback** (`core/tts.py`, `core/singer.py`, `web/app.js`, `web/overlay.js`: compute RMS envelope frames, gate browser `targetMouthOpen` during local playback) | `Planned Capability` (Delivery) | `[AUDIO-CRIT-002]` | 5 | 3 | 4 | 4 | 5 | 4 | 5 | **4.20** |
| **BL-15** | **`ContextBudgetManager` & Cross-Provider LLM Failover** (`core/conversation/prompts.py`, `core/brain.py`: token estimation, idle directive pruning, `max_tokens` parity, `gemini -> openai -> ollama -> mock` failover, model-gated `thinkingConfig`) | `Planned Capability` (Delivery) | `[COG-HIGH-002]`, `[COG-MED-002]` | 5 | 4 | 3 | 5 | 4 | 4 | 4 | **4.10** |
| **BL-16** | **Shared Frontend Auth & Resilient WS Client (`web/shared-client.js`) + Offline VRM Bundling** (exponential backoff + jitter, `overlay.js` `onopen` re-sync, `deck.js` race fix, `/settings` live status, local `three`/`three-vrm` vendor) | `Proposed Innovation` + `Planned Capability` | `[UI-HIGH-003]`, `[UI-MED-004]`, `[UI-LOW-001]`, `[UI-LOW-002]` | 4 | 4 | 3 | 4 | 4 | 5 | 3 | **3.80** |
| **BL-17** | **TTS Provider Parity, Session Pooling & Persistent VTS Auth Token** (`core/tts_providers.py`, `core/vts_client.py`: Edge fallback voice fix, dynamic MIME, shared `aiohttp` pool, `VTS_AUTH_TOKEN` persistence + auto-reconnect) | `Partially Implemented` + `Planned Capability` | `[AUDIO-HIGH-003]`, `[AUDIO-HIGH-004]`, `[AUDIO-MED-002]`, `[SEC-LOW-001]` | 4 | 4 | 2 | 4 | 4 | 4 | 3 | **3.45** |
| **BL-18** | **Bidirectional Collab Sync (`duet_sync`, `emote_sync`, `game_move`) & Studio Collab UI** (`core/orchestrator.py`, `core/collab/`, `web/index.html`, `web/app.js`: enforce `collab.enabled`, per-type rate limits) | `Planned Capability` (Delivery) | `[COLLAB-MED-001]`, `[COLLAB-MED-002]`, `[QA-MED-002]` | 4 | 3 | 3 | 3 | 3 | 4 | 5 | **3.40** |
| **BL-19** | **Audio-Clock-Locked Karaoke & Storytelling Freeform/Dice Wiring** (`core/singer.py`, `core/storytelling/engine.py`: lyric prefetch + `get_pos()` sync; wire `freeform_suggestions` & `dice_result`) | `Proposed Innovation` + `Partially Implemented` | `[GAME-HIGH-005]` | 4 | 4 | 2 | 2 | 4 | 4 | 4 | **3.20** |
| **BL-20** | **Wire `MoodEngine.get_temperature_modifier()` & `fulfill_promise()` + Enforce Runtime Concurrency Keys** (`core/brain.py`, `core/memory/`, `core/orchestrator.py`: wire `max_concurrent_tasks` & `response_timeout_sec`) | `Partially Implemented` + `Planned Capability` | `[INFRA-MED-002]`, `[COG-LOW-001]`, `[COG-LOW-002]` | 3 | 5 | 2 | 3 | 3 | 5 | 3 | **3.25** |

---

### Tier P3 — Horizon-3 Bets (Months 4–6+)

| ID | Item | Maturity Class | Linked Audit Findings | `UV` | `TF` | `AR` | `AL` | `LU` | `MC` | `DF` | Weighted Score |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **BL-21** | **OS-Level Plugin Jail & Host-Approved Capability Grants** (dedicated sandbox working dir outside `REPO_ROOT`, Linux `RLIMIT`/AppArmor & Windows Job Objects, disable `inprocess`, capability approval UI) | `Proposed Innovation` | `[SEC-CRIT-002]` | 4 | 2 | 5 | 3 | 2 | 2 | 4 | **3.40** |
| **BL-22** | **Hybrid BM25/FTS5 + `sqlite-vec` Scaled Episodic Recall** (shared `EmbeddingEngine` singleton, `embedding_model` versioning, RRF scoring beyond 300-row cap) | `Proposed Innovation` | `[COG-HIGH-004]`, `[COG-HIGH-005]` | 4 | 3 | 2 | 4 | 4 | 3 | 5 | **3.30** |
| **BL-23** | **Binary WS Audio Frames + Silero-VAD / AEC Duplex Pipeline** (1-byte binary WS framing, ONNX `silero-vad`, browser AEC constraints) | `Proposed Innovation` | `audit/02`, `audit/07` | 4 | 3 | 1 | 3 | 5 | 3 | 5 | **3.00** |
| **BL-24** | **Event-Driven Scene-Change VLM Ring Buffer** (selective frame captioning on pixel-diff spike, 3-frame VLM context cache) | `Proposed Innovation` | `audit/05` | 3 | 3 | 1 | 3 | 3 | 4 | 5 | **2.70** |
| **BL-25** | **Self-Healing Subsystem Watchdog & Live Telemetry Bus** (circuit breakers + reconnect supervision for MC/OBS/VTS + p95 latency diagnostics) | `Proposed Innovation` | `[GAME-CRIT-002]`, `[GAME-HIGH-002]`, `audit/11` | 4 | 3 | 3 | 4 | 3 | 3 | 3 | **3.35** |
| **BL-26** | **Negotiated Collab Capability & Turn-Budget Handshake** (`hello` capability negotiation, monotonic sequence numbers, signed `ack` frames) | `Proposed Innovation` | `audit/04` | 3 | 3 | 2 | 3 | 2 | 4 | 5 | **2.85** |

---

## 3. Recommended Execution Sequence

1. **Sprint 1 (P0 Security & Stability Gate):** `BL-01`, `BL-02`, `BL-03`, `BL-04`, `BL-05`, `BL-06`, `BL-07`, `BL-08`. Unlocks `GO` for Supervised Localhost and resolves all Critical audit findings.
2. **Sprint 2 (P1 Hardening & Docker/LAN Gate):** `BL-09`, `BL-10`, `BL-11`, `BL-12`, `BL-13`. Unlocks `GO` for Docker/LAN Creator streams and eliminates test flakiness.
3. **Sprints 3–5 (P2 Adjacent Expansion):** `BL-14` (Lip-Sync), `BL-15` (Context Budgeter + Failover), `BL-16` (Shared WS/Auth + Offline VRM), `BL-17`, `BL-18`, `BL-19`, `BL-20`.
4. **H3 R&D Track (P3 Horizon-3 Bets):** Execute behind R&D go/no-go gates (`BL-21` -> `BL-22` -> `BL-25` -> `BL-23` -> `BL-26` -> `BL-24`).
