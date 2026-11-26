# MaybeAI — Structured Innovation Portfolio (`strategy/INNOVATION_PORTFOLIO.md`)

**Author:** Agent 9 — Product Vision & Innovation Strategist (`strat-product`)  
**Grounding Baseline:** `audit/FINAL_AUDIT_REPORT.md` and `audit/00..11`  
**Portfolio Horizons:**
- **Core Hardening (H1):** Stabilize and secure existing `Current Capability` and `Partially Implemented` subsystems so MaybeAI is `GO` for localhost and Docker/LAN streams.
- **Adjacent Expansion (H2):** Deliver `Planned Capability` items and high-leverage upgrades that complete partially wired workflows.
- **Horizon-3 Bets (H3):** `Proposed Innovation` investments that unlock next-generation autonomous companion capabilities once H1/H2 foundations are solid.

---

## Portfolio Overview Matrix (8 Domains × 3 Horizons)

| # | Domain | Core Hardening (H1) | Adjacent Expansion (H2) | Horizon-3 Bets (H3) |
|---|---|---|---|---|
| 1 | **Autonomous Intelligence & Agency** | Fix replan completion & infinite loop (`[COG-CRIT-001/002]`); telemetry delta window (`[COG-HIGH-001]`) | `ContextBudgetManager` (`[COG-HIGH-002]`); Cross-provider LLM failover (`[COG-MED-002]`); `is_creator` plumbing (`[COG-HIGH-003]`) | Telemetry-Verified HTN/Action Supervisor & Bounded Subgoal Sandbox |
| 2 | **Social & Emotional Intelligence** | Wire `strict_mode` / `prompt_injection_filter` (`[SEC-HIGH-004]`); LRU `UserMemory` (`[COG-LOW-001]`) | Wire `MoodEngine.get_temperature_modifier()` & `fulfill_promise()` (`audit/03`); Topic-aware `ChatCurator` | Hybrid BM25 + `sqlite-vec`/HNSW Episodic Recall & Bidirectional Second Brain |
| 3 | **Multimodal Perception** | Fix `VisualAnalyzer` `scene_label` crash (`[GAME-HIGH-001]`) | Live VLM-grounded commentary in `MultimodalVisionModel` (`audit/05`) | Event-Driven Scene-Change VLM Ring Buffer (Selective Frame Captioning) |
| 4 | **Real-Time Voice, Audio & Avatar** | Fix `speak_stream()` `CancelledError` (`[AUDIO-CRIT-001]`), `Singer` barge-in (`[AUDIO-HIGH-002]`), STT offload (`[AUDIO-HIGH-001]`) | Server-side PCM/RMS audio-envelope lip-sync (`[AUDIO-CRIT-002]`); Offline VRM/font vendoring (`[UI-MED-004]`) | Binary WS AudioWorklet Frames + Silero-VAD / AEC Duplex Pipeline |
| 5 | **Gaming & Interactive World** | Thread-safe `chess.Board` clone (`[GAME-CRIT-001]`); Mineflayer bridge recovery & timer cleanup (`[GAME-CRIT-002]`) | OBS auto-reconnect (`[GAME-HIGH-002]`); Storytelling freeform/dice wiring (`audit/05`); Audio-clock-locked Karaoke (`[GAME-HIGH-005]`) | Shared World-State Blackboard Across Mineflayer, Chess & RPG Campaigns |
| 6 | **Creator Ecosystem & Extensibility** | Lock down `/ws` & `GET /api/*` (`[SEC-CRIT-001]`, `[SEC-HIGH-002]`); Fix Docker/LAN auth (`[SEC-HIGH-001]`); `/settings` XSS & token UI (`[UI-HIGH-001/002]`) | Separate plugin `startup_timeout_sec` (`[QA-HIGH-001]`); Evict crashed plugins (`[QA-MED-001]`); Shared `web/shared-client.js` | OS-Level Plugin Jail (AppArmor/seccomp/Job Objects) & Capability Grants (`[SEC-CRIT-002]`) |
| 7 | **Multi-Agent & Social Ecosystem** | Collab replay cache (`[COLLAB-CRIT-001]`); `_is_loopback_url` fix (`[COLLAB-HIGH-001]`); Cooldown recovery (`[COLLAB-HIGH-003]`) | Bidirectional `duet_sync`, `emote_sync`, `game_move`; Web Dashboard Collab UI (`audit/04`) | Negotiated Capability & Turn-Budget Handshake Protocol for N-Agent Shows |
| 8 | **Reliability, Observability & Self-Healing** | Concurrent `EventBus` + bounded WS queues (`[PERF-HIGH-001]`); Track `_spawn_bg_task` (`[INFRA-HIGH-001]`); `ffmpeg` confinement (`[SEC-HIGH-003]`, `[GAME-HIGH-004]`) | Enforce `max_concurrent_tasks` / `response_timeout_sec` (`[INFRA-MED-002]`); Isolate tests from `data/` (`[QA-MED-003]`) | Self-Healing Subsystem Watchdog & Live Latency/Token Telemetry Bus |

---

## Detailed Innovation & Technology Justifications

Every proposed innovation below includes all 7 mandatory justification dimensions and explicit maturity classification.

---

### Domain 1: Autonomous Intelligence & Agency

#### 1.1 `ContextBudgetManager` & Cross-Provider Failover Chain
- **Horizon & Maturity:** **Adjacent Expansion (H2)** | `Planned Capability` (addresses `[COG-HIGH-002]`, `[COG-MED-002]`, `[COG-HIGH-003]`)
- **Problem Statement:** `MasterPromptBuilder` unconditionally concatenates 11+ subsystem directives, full `character.lore` JSON, and 16 history turns (`core/conversation/prompts.py`), overflowing 4K–8K local Ollama windows and inflating cloud token costs. Meanwhile, any provider 429/5xx drops straight to offline mock text, and `is_creator` is dropped on all live LLM paths.
- **Expected Benefit:** 30–50% reduction in prompt token bloat, zero silent mock-fallback during transient API blips, consistent `max_tokens` across OpenAI/Gemini/Ollama, and reliable Creator authority in live mode.
- **Technical Justification:** Implement a lightweight token estimator (`len(text) // 4` with optional `tiktoken`), priority-tiered directive pruning (omitting idle `minigame`/`storytelling`/`desktop` blocks), `[CREATOR VERIFIED]` injection in `abuild_system_prompt()`, and a configurable ordered failover list (e.g., `gemini -> openai -> ollama -> mock`) with 1 bounded retry.
- **Complexity Cost:** Low-to-Medium (~200–300 LOC in `core/conversation/prompts.py` and `core/brain.py`).
- **Maintenance Burden:** Low; pure Python logic with deterministic unit tests.
- **Compatibility Analysis:** Fully compatible with existing `Brain` and `ConversationEngine` interfaces; backward-compatible with `settings.json` by adding optional `llm.fallback_order` and `llm.context_budget_tokens`.
- **Alternative Solutions:** (a) Hardcoding static string truncation (loses critical memory/mood context); (b) Adopting a heavy orchestration framework like LangChain (adds unnecessary dependency weight and latency).

#### 1.2 Telemetry-Verified Action Supervisor
- **Horizon & Maturity:** **Horizon-3 Bet (H3)** | `Proposed Innovation` (evolves `[COG-CRIT-001/002]`, `[COG-HIGH-001]`)
- **Problem Statement:** `AutonomousMissionExecutor` currently checks Mineflayer inventory 0ms after dispatching `toggle_wander()`/`jump()`, causing false failures and infinite replan loops, while disconnected domains fabricate `simulated: True` progress.
- **Expected Benefit:** Genuine, trustworthy autonomous gameplay where Eve only credits progress when world state (`mc_telemetry`, `chess` FEN, `performance` completion) actually advances.
- **Technical Justification:** Replace 0ms inline polling with an async action-completion watcher subscribing to `EventBus` telemetry events (`mc_telemetry`, `chess_move`, `song_finished`) using baseline snapshots, bounded `MAX_REPLAN_ATTEMPTS = 3`, and explicit `simulated_commentary` vs. `verified_execution` modes.
- **Complexity Cost:** Medium (~350 LOC across `core/planning/executor.py` and `models.py`).
- **Maintenance Burden:** Low-to-Medium; requires keeping telemetry event schemas aligned with `minecraft/bot.js` and `ChessController`.
- **Compatibility Analysis:** Builds directly on existing `EventBus` and `GoalEngine`; requires `[GAME-CRIT-002]` bridge health tracking first.
- **Alternative Solutions:** (a) Fixed `asyncio.sleep(10)` after every command (brittle, wastes stream time); (b) Full PDDL/GOAP planner (over-engineered for current 4-domain mission set).

---

### Domain 2: Social & Emotional Intelligence

#### 2.1 Hybrid BM25/FTS5 + `sqlite-vec` Scaled Episodic Recall
- **Horizon & Maturity:** **Horizon-3 Bet (H3)** | `Proposed Innovation` (evolves `[COG-HIGH-004]`, `[COG-HIGH-005]`)
- **Problem Statement:** `MemoryRetriever` caps vector scans at the 300 most recent rows (`core/memory/database.py`), uses a duplicate `EmbeddingEngine` instance in `EpisodicMemoryStore`, and overwrites real embeddings with 64-dim hash fallbacks during transient API outages.
- **Expected Benefit:** Sub-20ms semantic recall across 50,000+ stream episodes without silent embedding corruption.
- **Technical Justification:** Deduplicate `EmbeddingEngine` as a shared singleton, tag embeddings with `embedding_model` + `embedding_dim` so hash fallbacks never overwrite neural vectors, and evaluate `sqlite-vec` (or `hnswlib` sidecar) combined with existing SQLite FTS5 via Reciprocal Rank Fusion (RRF).
- **Complexity Cost:** Medium (migration script for `embedding_model` column + retriever RRF scoring).
- **Maintenance Burden:** Low if using `sqlite-vec` or pure-NumPy pre-filtered FTS5 + vector; medium if managing an external HNSW index file.
- **Compatibility Analysis:** Preserves `data/memory.db` SQLite single-file simplicity and Markdown Second Brain sync.
- **Alternative Solutions:** (a) External vector DB like Qdrant/Chroma (violates local single-file simplicity and adds Docker/RAM overhead); (b) Increasing the SQLite scan cap to 2,000 rows (temporary band-aid, O(N) latency degrades on long-running companions).

#### 2.2 Mood-Modulated Sampling & Wired Promise Fulfillment
- **Horizon & Maturity:** **Adjacent Expansion (H2)** | `Partially Implemented` -> Complete (`audit/03`)
- **Problem Statement:** `MoodEngine.get_temperature_modifier()` (`core/mood/engine.py:231`) and `MemoryDatabase.fulfill_promise()` (`core/memory/database.py:608`) already exist and are unit-tested, but neither is wired into `Brain` or `Orchestrator`.
- **Expected Benefit:** Eve's creativity/variability naturally reflects her emotional state, and viewer promises tracked in `promises.md` actually resolve instead of appending forever (`[COG-LOW-002]`).
- **Technical Justification:** Pass `mood_engine.get_temperature_modifier()` into `Brain` payload builders (clamped to safe `[0.3, 1.1]` bounds) and hook a lightweight post-turn promise-check into `MemoryExtractor`.
- **Complexity Cost:** Very Low (<100 LOC).
- **Maintenance Burden:** Negligible.
- **Compatibility Analysis:** 100% compatible with existing `MoodEngine` and `MemoryDatabase`.
- **Alternative Solutions:** Prompt-only mood instructions (already present, less consistent than pairing with temperature modulation).

---

### Domain 3: Multimodal Perception

#### 3.1 Event-Driven Scene-Change VLM Ring Buffer
- **Horizon & Maturity:** **Horizon-3 Bet (H3)** | `Proposed Innovation` (builds on `[GAME-HIGH-001]` & `audit/05`)
- **Problem Statement:** `VisionEngine` currently runs `mss` pixel-diff and color-heuristic classification (`core/vision/analyzer.py`), while `MultimodalVisionModel.aperceive_with_vlm()` only enriches `obs.summary` post-hoc rather than driving live commentary.
- **Expected Benefit:** Relevant, low-cost visual awareness (noticing boss fights, chat raids, or desktop errors) without burning VLM API quota on static frames.
- **Technical Justification:** Trigger VLM calls only when pixel-diff exceeds a scene-change threshold *and* cooldown/budget permits, caching recent VLM captions in a 3-frame ring buffer injected into `ContextBudgetManager` when `vision` is active.
- **Complexity Cost:** Medium (~200 LOC in `core/vision/engine.py` and `vlm.py`).
- **Maintenance Burden:** Low; gated behind existing `vision.vlm_enabled` config.
- **Compatibility Analysis:** Requires fixing `[GAME-HIGH-001]` (`detected_label` -> `scene_label`) first.
- **Alternative Solutions:** (a) Continuous 1 FPS VLM polling (prohibitive API cost and latency); (b) Running local LLaVA/Qwen-VL alongside LLM+TTS+Minecraft (high VRAM contention on single-GPU creator PCs).

---

### Domain 4: Real-Time Voice, Audio & Avatar

#### 4.1 Server-Side Audio-Envelope Lip-Sync & Conflict-Free Browser Playback
- **Horizon & Maturity:** **Adjacent Expansion (H2)** | `Planned Capability` (resolves `[AUDIO-CRIT-002]`)
- **Problem Statement:** `TTSEngine._play_and_lipsync()` and `Singer.sing()` emit a synthetic 80 ms square wave (`0.95`/`0.50`) that mismatches real syllables, flaps past short sentences, and collides with browser `AnalyserNode` RMS in `output_mode="both"`.
- **Expected Benefit:** Natural syllable-accurate mouth movement in VTube Studio, 2D Canvas, and 3D VRM with zero jitter.
- **Technical Justification:** Decode synthesized audio bytes on the server (using `wave`/`numpy` or `miniaudio`/`ffmpeg` pipe) to compute a 30–50 Hz RMS amplitude envelope array, stream envelope frames synchronized with `pygame` playback for VTS, and instruct `/overlay` and `/` to ignore `avatar_state.mouth_open` whenever `isPlayingAudioQueue` is active.
- **Complexity Cost:** Medium (~250 LOC across `core/tts.py`, `core/singer.py`, `web/app.js`, `web/overlay.js`).
- **Maintenance Burden:** Low; pure signal-processing math.
- **Compatibility Analysis:** Backward-compatible with `VTSClient.update_mouth()` and WebSocket `avatar_state` schema.
- **Alternative Solutions:** (a) Phoneme-to-viseme forced alignment (higher CPU/dependency cost; overkill for 1-parameter `MouthOpen` VTS/2D rigs); (b) Client-only lip-sync (leaves VTube Studio desktop avatars motionless in `server` mode).

#### 4.2 Binary WebSocket Audio Frames + Silero-VAD / AEC Duplex Pipeline
- **Horizon & Maturity:** **Horizon-3 Bet (H3)** | `Proposed Innovation` (evolves `web/audio-worklet-processor.js` & `core/stt.py`)
- **Problem Statement:** Browser `AudioWorklet` currently encodes 31.25 frames/s as JSON + base64 (`run.py:1534`), adding ~33% bandwidth overhead and GC pressure, while `EnergyVAD` (`core/stt.py`) cannot distinguish human speech from speaker bleed or background music.
- **Expected Benefit:** ~33% lower WS audio bandwidth, zero base64 GC churn, and far fewer false barge-ins from speaker echo.
- **Technical Justification:** Introduce a 1-byte binary WS frame header (`0x01` = mic PCM16, `0x02` = TTS audio) alongside JSON control frames, and swap `EnergyVAD` behind a pluggable VAD interface for `silero-vad` (ONNX, ~2 MB, <1 ms/frame on CPU) + browser `echoCancellation: true` constraints.
- **Complexity Cost:** Medium-to-High (touches `run.py` WS binary handler, `web/app.js`, `web/deck.js`, and `core/stt.py`).
- **Maintenance Burden:** Low-to-Medium (`onnxruntime` optional extra).
- **Compatibility Analysis:** Keep JSON `voice_audio_chunk` as fallback for older clients.
- **Alternative Solutions:** (a) WebRTC media tracks via `aiortc` (heavy native/ICE dependency, breaks simple reverse-proxy setups); (b) Keeping `EnergyVAD` with higher threshold (misses soft-spoken creators).

---

### Domain 5: Gaming & Interactive World

#### 5.1 Audio-Clock-Locked Karaoke & Pre-Synthesis
- **Horizon & Maturity:** **Adjacent Expansion (H2)** | `Proposed Innovation` (resolves `[GAME-HIGH-005]`, `audit/05`)
- **Problem Statement:** `Singer.sing()` synthesizes each lyric line sequentially *during* playback and blocks on `pygame` sleep loops, causing cumulative network-jitter drift between vocals, lyrics, and BGM.
- **Expected Benefit:** Tightly synchronized karaoke performances where lyrics, choreography, and vocals stay locked to the BGM beat.
- **Technical Justification:** Pre-synthesize the next 2–3 lyric lines concurrently in an `asyncio` prefetch queue before BGM starts, and anchor lyric/choreography triggers to `pygame.mixer.music.get_pos()` (or browser audio-chunk timestamps) rather than wall-clock `sleep()`.
- **Complexity Cost:** Medium (~200 LOC in `core/singer.py`).
- **Maintenance Burden:** Low.
- **Compatibility Analysis:** Compatible with `PerformanceDirector` setlists and `CollabManager` `duet_sync`.
- **Alternative Solutions:** Pre-rendering entire songs to WAV before starting (adds 10–20s startup delay).

---

### Domain 6: Creator Ecosystem & Extensibility

#### 6.1 Shared Frontend Auth & Resilient WS Client (`web/shared-client.js`)
- **Horizon & Maturity:** **Adjacent Expansion (H2)** | `Proposed Innovation` (resolves `[UI-HIGH-002]`, `[UI-HIGH-003]`, `[UI-LOW-001]`)
- **Problem Statement:** `/`, `/settings`, `/overlay`, and `/deck` duplicate WebSocket connection logic (3 of 4 use uncapped 2000ms reconnect loops), `/deck` has a double-WS race on token save, and `/` + `/settings` crash or fail silently on `401/403`.
- **Expected Benefit:** Eliminates duplicated WS/auth bugs across all 4 surfaces, provides a unified Creator token modal, and stops reconnect storms.
- **Technical Justification:** Extract `CreatorAuth` + `ReconnectingWebSocket` (exponential backoff 1s -> 30s with jitter, `1008` policy circuit breaker, clean `onclose = null` before manual close) into `web/shared-client.js` loaded by all 4 HTML entrypoints.
- **Complexity Cost:** Low (~150 LOC JS).
- **Maintenance Burden:** Reduces overall maintenance by removing 4x duplicated WS/auth code.
- **Compatibility Analysis:** Vanilla ES module/script; requires zero build step or bundler.
- **Alternative Solutions:** Migrating frontend to React/Vite (high rewrite cost, breaks zero-build `web/` simplicity).

#### 6.2 OS-Level Plugin Jail & Host-Approved Capability Grants
- **Horizon & Maturity:** **Horizon-3 Bet (H3)** | `Proposed Innovation` (resolves `[SEC-CRIT-002]`)
- **Problem Statement:** `core/plugins/sandbox_worker.py` strips env vars and kills on timeout, but runs as the same OS user in `REPO_ROOT` with full read/write access to `.env`, `config/settings.json`, `data/memory.db`, and unrestricted outbound network.
- **Expected Benefit:** Safe execution of untrusted community plugins without risking Creator API keys or private Second Brain journals.
- **Technical Justification:** Run plugins in a dedicated temporary/plugin working directory outside `REPO_ROOT`, enforce `RLIMIT_AS`/`RLIMIT_CPU` (Linux) or Windows Job Objects, disable `inprocess` mode by default, and require explicit Creator approval in `settings.json` for declared capabilities (`network`, `memory_read`, `chat_send`) before `PluginRegistry` dispatches RPCs.
- **Complexity Cost:** High (OS-specific process containment on Windows + Linux).
- **Maintenance Burden:** Medium; must be tested in CI on both Windows and Docker/Linux.
- **Compatibility Analysis:** Compatible with `PluginSDK` JSON-RPC protocol; built-in `word_chain` requires zero filesystem/network grants.
- **Alternative Solutions:** (a) Docker-per-plugin (prohibitive startup latency and Windows Desktop friction); (b) WebAssembly/Pyodide plugin runtime (breaks native Python plugin libraries).

---

### Domain 7: Multi-Agent & Social Ecosystem

#### 7.1 Bidirectional Collab Sync & Studio Collab UI
- **Horizon & Maturity:** **Adjacent Expansion (H2)** | `Planned Capability` (completes `audit/04`)
- **Problem Statement:** `duet_sync` ignores `lyric_index`/`timestamp`, `emote_sync` drops `action`, `send_game_move` does not exist, and `web/` has zero UI for managing `/ws/collab` sessions.
- **Expected Benefit:** Multi-AI Collab Producers ("Ren") can run synchronized duets, reactive emotes, and AI-vs-AI Chess from the Studio Dashboard.
- **Technical Justification:** Wire `Orchestrator` outbound emitters for `duet_sync`, `emote_sync`, and `game_move`, enforce `collab.enabled` + per-message-type rate limits (`[COLLAB-MED-001/002]`), and add a Collab status/control panel to `web/index.html` + `web/app.js`.
- **Complexity Cost:** Medium (~300 LOC Python + JS).
- **Maintenance Burden:** Low; builds on existing `CollabEnvelope` and `CollabManager`.
- **Compatibility Analysis:** Requires H1 fixes `[COLLAB-CRIT-001]` (replay cache) and `[COLLAB-HIGH-003]` (cooldown recovery) first.
- **Alternative Solutions:** Controlling collabs solely via raw `curl` calls to `/api/collab/action` (unusable for live producers).

#### 7.2 Negotiated Capability & Turn-Budget Handshake
- **Horizon & Maturity:** **Horizon-3 Bet (H3)** | `Proposed Innovation` (`audit/04`)
- **Problem Statement:** Current `hello` frames do not negotiate supported features, protocol versions, or turn budgets, and `CollabManager` only supports 1-to-1 peer links.
- **Expected Benefit:** Version-safe multi-agent shows where peers automatically agree on shared capabilities (e.g., `duet_sync`, `chess`) and fair turn-taking budgets.
- **Technical Justification:** Extend `hello` payload with `protocol_version`, `capabilities[]`, and `max_turns_proposed`, plus monotonic per-session sequence numbers and signed `ack` frames.
- **Complexity Cost:** Medium (~200 LOC in `core/collab/protocol.py` & `manager.py`).
- **Maintenance Burden:** Low.
- **Compatibility Analysis:** Additive fields in `CollabEnvelope.payload` preserve backward compatibility.
- **Alternative Solutions:** Static manual configuration on both peers (error-prone during live collabs).

---

### Domain 8: Reliability, Observability & Self-Healing

#### 8.1 Concurrent `EventBus` Dispatch & Bounded WebSocket Queues
- **Horizon & Maturity:** **Core Hardening (H1)** | `Proposed Innovation` (resolves `[INFRA-HIGH-003]` / `[PERF-HIGH-001]`)
- **Problem Statement:** `EventBus.publish()` awaits subscribers sequentially; a single 200ms slow subscriber stalls the entire bus and fast subscribers (`0.207s` reproduced in Chaos Scenario A), and `_dispatch_to_web_listeners` silently swallows exceptions without evicting dead clients.
- **Expected Benefit:** Zero head-of-line blocking across TTS, VTS, and chat loops; bounded memory under `avatar_state` bursts.
- **Technical Justification:** Dispatch async handlers concurrently (`asyncio.gather(..., return_exceptions=True)` or bounded worker tasks), give each WebSocket client a bounded `asyncio.Queue(maxsize=64)` with drop-oldest policy for high-frequency `avatar_state` frames, and evict clients on send failure.
- **Complexity Cost:** Medium (~180 LOC in `core/event_bus.py` and `core/orchestrator.py`).
- **Maintenance Burden:** Low.
- **Compatibility Analysis:** Preserves `EventBus.publish()` / `subscribe()` public signatures.
- **Alternative Solutions:** External message broker like Redis Pub/Sub (unnecessary single-process overhead).

#### 8.2 Self-Healing Subsystem Watchdog & Telemetry Bus
- **Horizon & Maturity:** **Horizon-3 Bet (H3)** | `Proposed Innovation` (evolves `[GAME-CRIT-002]`, `[GAME-HIGH-002]`, `audit/11`)
- **Problem Statement:** External bridges (`MinecraftController`, `OBSWebSocketClient`, `VTSClient`) leave stale `"connected"` flags on socket drops and lack unified health/latency observability.
- **Expected Benefit:** Unattended streams automatically recover from transient OBS, VTS, or Mineflayer drops and surface real-time p95 latency/error metrics in `/settings` diagnostics.
- **Technical Justification:** Add a lightweight periodic health-probe supervisor in `Orchestrator` (using `_spawn_bg_task`) that tracks circuit-breaker states (`CLOSED`/`OPEN`/`HALF-OPEN`), triggers exponential-backoff reconnects for enabled bridges, and publishes structured `system_health` snapshots to `/settings` and `/deck`.
- **Complexity Cost:** Medium (~250 LOC).
- **Maintenance Burden:** Low.
- **Compatibility Analysis:** Consolidates ad-hoc `get_status()` methods across controllers.
- **Alternative Solutions:** Heavy Prometheus + Grafana sidecar stack (excessive operational burden for solo streamers).
