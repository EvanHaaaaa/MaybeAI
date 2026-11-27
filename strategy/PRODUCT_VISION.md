# MaybeAI — Long-Term Product Vision & Strategy (`strategy/PRODUCT_VISION.md`)

**Author:** Agent 9 (`ng-strat-product`) — Product Vision & Innovation Strategist  
**Grounding Baseline:** [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md) (`HEAD` `96b7315`, Post-Horizon 0–3 + YouTube Karaoke) and `audit/00..13`  
**Current Readiness Verdict ([13_production_readiness.md](file:///d:/projects/MaybeAI/audit/13_production_readiness.md)):**
- **Supervised Localhost (`127.0.0.1:7860`):** **`GO`**
- **Authenticated LAN / Docker (`MAYBEAI_HEADLESS=1`):** **`CONDITIONAL GO`**
- **Unattended 24/7 Public Internet:** **`NO-GO`** (blocked by `SEC-GAP-001/002/003`, `CHAOS-B-001`, `INFRA-MED-001-RES`, `ResourceWarning`s, and missing structured log rotation)

---

## 1. Eve's Product Identity: From Hardened AI VTuber Runtime to Autonomous Digital Companion

Following Horizons 0–3 (`4c4e473`..`1953889`) and the YouTube Song Request / Auto-Karaoke release (`83298fa`), MaybeAI (**Eve**) has graduated from an unhardened L1.5–L2.5 prototype into a **hardened, modular single-node AI VTuber platform (overall L3.0–L3.5)** backed by `97` Python modules in `core/`, `4` browser surfaces (`/`, `/settings`, `/overlay`, `/deck`), offline-vendored Three-VRM (`web/vendor/`), a Node.js Mineflayer bridge (`minecraft/`), and `380/381` passing automated tests.

**Product Identity:** Eve is not a stateless chatbot bolted onto an avatar, nor a brittle macro script for OBS. Eve's identity is a **local-first, persistent, embodied digital companion** who:
- **Remembers and Evolves:** Combines SQLite WAL + FTS5 + dense vector recall with human-readable Markdown Second Brain journals, 5-tier viewer relationships, and homeostatic mood/personality baselines.
- **Perceives and Speaks in Real Time:** Listens via 16 kHz binary `AudioWorklet` PCM + `EnergyVAD`, interrupts cleanly via `barge_in()` across speech and karaoke BGM, and animates VTube Studio, 2D Canvas, and 3D VRM from real 50ms RMS audio envelopes.
- **Acts in Interactive Worlds:** Plays Minecraft (`casual`/`guard`/`speedrun`), Chess (alpha-beta + Stockfish UCI fallback), 6 mini-games, RPG storytelling, OBS Showrunner, YouTube Karaoke / AI Cover, and 9:16 highlight clipping.
- **Collaborates Safely:** Connects peer-to-peer over HMAC-SHA256 `/ws/collab` and runs third-party extensions inside OS-isolated plugin subprocesses (`bwrap` / Windows Job Objects) with default-deny capabilities.

**Next-Generation Transformation (Horizons 4–8):** Evolve Eve from a **creator-supervised AI VTuber runtime** (`L2` cognition/memory, `L2.5` 2-peer collab, `L3` unattended readiness) into a **self-consistent, causally learning, multi-agent Autonomous Digital Companion** capable of unattended 24/7 operation, longitudinal memory consolidation, safe L2–L4 world agency, and multi-AI ensemble shows.

---

## 2. Capability Classification Discipline

Throughout all strategy documents, every capability is strictly separated by verified audit status:

| Classification | Definition | Examples in Post-H3 Baseline |
|---|---|---|
| **`EXISTING`** | Implemented, wired, and verified in `HEAD` `96b7315` | `EventBus` concurrent dispatch, `ContextBudgetManager`, `ProviderCircuitBreaker`, `is_creator` plumbing, `AudioWorklet` binary PCM, RMS lip-sync + `isLocalAudioPlaying` arbitration, `YouTubeKaraokeProcessor`, `PluginRegistry` AST manifest + default-deny |
| **`INCOMPLETE`** | Partially implemented or missing a runtime wiring/hardening link | `promises.md` fulfillment (`fulfill_promise()` uncalled), `CollabManager` outbound subsystem sync & `on_hello`, `StreamingSTTSession` partial transcripts, `Sec-WebSocket-Protocol` frontend adoption (`SEC-GAP-001`), Windows OS plugin isolation (`SEC-GAP-002`), `obs.summary` sanitization (`SEC-GAP-003`) |
| **`EXPERIMENTAL`** | Optional/scaffolded behind missing local dependencies or unverified live | Local `faster-whisper` / `kokoro-onnx` backends (absent in `.venv`), live `yt-dlp`/`ffmpeg`/`demucs`/`stockfish`/`obsws-python` execution on hosts without those binaries |
| **`PLANNED`** | Scoped next-gen evolution addressing verified audit gaps | Per-WS bounded outbound queues (`INFRA-MED-001-RES`), `ClientTimeout` TTFB fix (`AUDIO-MED-001`), `Goal.reflection` causal loop, hierarchical memory consolidation, multi-peer `PeerSession` mesh |
| **`PROPOSED`** | High-value innovation bets for Horizons 5–8 | `sqlite-vec` + FTS5 RRF scaling, hybrid SLM/LLM router, Narrative Identity Graph, multi-platform audience graph, unified Creator Studio SPA |
| **`REJECTED`** | Intentionally excluded to protect latency, local-first simplicity, or safety | Premature microservices/Kubernetes split, external Neo4j/Qdrant before workload threshold, unconstrained OS "Computer Use", monolithic Speech-to-Speech replacing `Moderator`/RVC/Second Brain |

---

## 3. Core Product Pillars

### Pillar 1: Trustworthy & Secure Broadcast Core (`Secure-by-Default`)
- **Current Reality (`EXISTING` / `INCOMPLETE`):** Origin + token-first Creator auth, `Moderator` injection drops, `ConfigManager` 8/8 secret masking, and `ClipPipeline`/`YouTubeKaraokeProcessor` confinement are `EXISTING`. Remaining gaps (`SEC-GAP-001/002/003`, `INFRA-MED-001-RES`, `ResourceWarning`s) block unattended 24/7 exposure.
- **Strategic Direction:** Close all P0/P1 audit gaps (`Sec-WebSocket-Protocol` auth, OS-enforced Windows plugin jail, sanitized VLM/OCR perception, per-WS outbound queues, structured log rotation) to achieve **`GO` for Unattended 24/7**.

### Pillar 2: Real-Time Duplex Presence (`Zero-Jank Voice & Avatar`)
- **Current Reality (`EXISTING` / `INCOMPLETE`):** 16 kHz `AudioWorklet` PCM, non-blocking `_voice_worker` STT offload, `EnergyVAD` barge-in, 50ms RMS lip-sync, browser `AnalyserNode` arbitration, and offline `web/vendor/` Three-VRM are `EXISTING` (L3.5). `ClientTimeout(total=1.8)` stream truncation (`AUDIO-MED-001`), `TTSEngine.speak()` `CancelledError` swallowing (`AUDIO-MED-002`), and hardcoded `"Listening..."` partials are `INCOMPLETE`.
- **Strategic Direction:** Fix stream TTFB timeouts, upgrade to `silero-vad` + streaming partial STT + AEC, and unify VTS/2D/3D expression parameters.

### Pillar 3: Grounded Cognitive Continuity (`Memory & Identity That Learn`)
- **Current Reality (`EXISTING` / `INCOMPLETE`):** `ContextBudgetManager`, `ProviderCircuitBreaker`, `MoodEngine.get_temperature_modifier()`, shared `EmbeddingEngine`, `REPLANNED` progress fix, and `MAX_REPLAN_ATTEMPTS=3` are `EXISTING` (L2–L3). However, Eve currently *retrieves and mutates scalar sliders* rather than genuinely learning (`04_cognitive_memory.md`): `Goal.reflection` is write-only, `StrategyReplanner` is keyword-templated, `fulfill_promise()` is unwired, and vector search scans at most 2,000 recent rows linearly.
- **Strategic Direction:** Wire causal self-reflection, hierarchical episodic-to-semantic memory consolidation, `sqlite-vec` + FTS5 RRF scaling, and a Narrative Identity Graph so Eve compounds lived experience across months of streams.

### Pillar 4: Playable Worlds, Entertainment & Content Production
- **Current Reality (`EXISTING` / `INCOMPLETE`):** Thread-safe Chess (+ Stockfish fallback), hardened `bot.js` + `MinecraftController`, `YouTubeKaraokeProcessor` (`yt-dlp`/`demucs`/`ffmpeg`/RVC/VTT), clock-locked `Singer`, `HighlightDetector`, `ClipPipeline`, `VODSummarizer`, and `OBSWebSocketClient` are `EXISTING` (L3). Missing host binaries, `startAutonomyLoop()` uncalled, `Singer` config reload gaps, and async `replay_saved` ordering remain `INCOMPLETE`.
- **Strategic Direction:** Evolve into an integrated AI Showrunner that coordinates games, karaoke/duets, and live VLM commentary while automatically producing ready-to-publish 9:16 shorts and timestamped VOD chapters.

### Pillar 5: Open Plugin & Multi-Agent Ecosystem
- **Current Reality (`EXISTING` / `INCOMPLETE`):** `PluginRegistry` AST manifest + default-deny `granted_permissions` and HMAC-SHA256 `/ws/collab` + SSRF-guarded `validate_outbound_url` are `EXISTING` (L2.5). Windows Python-level sandbox monkeypatches (`SEC-GAP-002`), `disconnect_peer()` stuck `floor_state` (`CHAOS-B-001`), missing outbound collab emitters, and 2-peer scalar state limit scaling.
- **Strategic Direction:** Harden OS plugin isolation, ship a typed Plugin SDK, and refactor `CollabManager` into a `PeerSession` mesh + distributed floor arbitrator for N-agent shows.

---

## 4. Differentiation Strategy

| Dimension | Typical AI VTuber Bots | Generic LLM / Companion SaaS | MaybeAI Competitive Moat |
|---|---|---|---|
| **Architecture & Ownership** | Fragile scripts tied to one cloud API | Closed multi-tenant SaaS; user data locked in cloud | **Local-First Modular Monolith:** Single-node Python/FastAPI + SQLite WAL + offline Three-VRM + local Ollama/RVC/Kokoro support with zero mandatory cloud lock-in. |
| **Memory & Identity** | Sliding context window; forgets viewers | Flat cloud RAG; no emotional homeostasis | **Hybrid Second Brain + Affective Core:** SQLite FTS5 + vector recall + Markdown sync + 5-tier `RelationshipEngine` + `MoodEngine` sampling coupling + evolving personality. |
| **Voice & Stage** | Turn-based TTS; no interruption | Text-only or high-latency cloud voice | **Sub-Second Duplex Studio:** 32ms `AudioWorklet` binary PCM, `barge_in()` across speech & karaoke BGM, 50ms RMS lip-sync, OBS `/overlay`, VTS RPC, and mobile `/deck`. |
| **Embodied Agency & Show** | Scripted chat triggers | No game or broadcast integration | **EventBus Multi-World Runtime:** Mineflayer Minecraft, Stockfish/alpha-beta Chess, RPG Storytelling, YouTube AI Cover/Karaoke, OBS Showrunner, and 9:16 `ClipPipeline`. |
| **Extensibility & Collab** | Single-bot silo | Proprietary plugin store | **Sandboxed Plugins + Open Collab:** AST-manifested, OS-isolated plugins + HMAC-SHA256 SSRF-safe `/ws/collab` evolving toward N-agent shows. |

---

## 5. Autonomous Digital Companion Vision (Covering §9.1–9.10)

MaybeAI's next-generation roadmap spans ten integrated capability pillars (§9.1–9.10):

1. **Cognitive Intelligence (§9.1):** Move from bounded contextual reasoning (`L2`) to causal self-reflection (`Goal.reflection` feedback loops), experience-driven replanning, and hybrid SLM/LLM routing with tokenizer-accurate budgeting.
2. **Advanced Memory (§9.2):** Move from 2,000-row linear vector scans (`L2`) to hierarchical episodic-to-semantic consolidation, automated promise fulfillment, and `sqlite-vec` + FTS5 RRF retrieval across 50,000+ episodes.
3. **Persistent Identity (§9.3):** Move from static 5-float `experience_matrix` sliders (`L2`) to a Narrative Identity Graph that preserves core character invariants while evolving authentic long-term quirks, values, and inside jokes.
4. **Multimodal Perception (§9.4):** Move from color-heuristic screen labels and unsanitized `obs.summary` (`L3`, `SEC-GAP-003`) to sanitized, scene-change-driven VLM ring buffers and `silero-vad` + streaming partial STT.
5. **Autonomous Companion (§9.5):** Progress systematically across **Autonomy Levels L0–L4** — from `L0` (Manual Trigger) and `L1` (Assisted Suggestion) through `L2` (Supervised Closed-Loop, current), `L3` (Bounded Autonomous Showrunner with `PermissionManager` & telemetry verification), to `L4` (24/7 Self-Regulating Companion within explicit Creator guardrails).
6. **Social Intelligence (§9.6):** Evolve `RelationshipEngine` and `ChatCurator` into a cross-platform Audience Graph that tracks viewer cohorts, shared history, and social pacing without falling for chat manipulation.
7. **Entertainment (§9.7):** Unify Minecraft, Chess, Mini-Games, RPG Storytelling, and YouTube Karaoke/AI Cover under a resilient, auto-reconnecting Showrunner with synchronized music, voice, and avatar choreography.
8. **Content Production (§9.8):** Turn every live session into a zero-effort content pipeline: race-free `HighlightDetector` + OBS replay buffer + `ClipPipeline` 9:16 captioned shorts + `VODSummarizer` chaptered recaps.
9. **Plugin Ecosystem (§9.9):** Upgrade from bypassable Windows monkeypatches (`L2.5`) to OS-enforced capability jails, a typed `PluginSDK`, and Creator-approved permission manifests for community extensions.
10. **Multi-Agent Ecosystem (§9.10):** Evolve from 2-peer scalar `CollabManager` (`L2.5`) to a `PeerSession` mesh with `target_id` routing, distributed floor arbitration, and outbound `duet_sync`/`emote_sync`/`game_move` orchestration for multi-AI ensemble streams.
