# MaybeAI — Explicitly Rejected Proposals (`research/rejected_proposals.md`)

**Owner:** AGENT 10 (`ng-strat-research`) — AI Research & Emerging Technology Architect  
**Grounding Baseline:** Post-Horizon 3 + YouTube Karaoke (`HEAD 96b7315`) — [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md), [03_realtime_audio.md](file:///d:/projects/MaybeAI/audit/03_realtime_audio.md), [04_cognitive_memory.md](file:///d:/projects/MaybeAI/audit/04_cognitive_memory.md), [06_game_vision_entertainment.md](file:///d:/projects/MaybeAI/audit/06_game_vision_entertainment.md), [12_performance_analysis.md](file:///d:/projects/MaybeAI/audit/12_performance_analysis.md)

This document records architectures and technologies that were **explicitly evaluated and rejected** for MaybeAI's Horizons 4–8 roadmap, along with concrete technical rationale grounded in verified post-H3 audit evidence to prevent scope creep or hype-driven rewrites.

---

## 1. Premature Microservices Split & Heavy Message Brokers (Redis / RabbitMQ)

- **Proposal:** Split `core/` (`97` Python files across `18` subpackages: `Brain`, `TTSEngine`, `STTEngine`, `MemoryDatabase`, `MoodEngine`, `GoalEngine`, `MinecraftController`, `CollabManager`) into independent FastAPI/gRPC microservices communicating over HTTP, Redis Pub/Sub, or RabbitMQ.
- **Why Rejected:**
  - **Latency Penalty:** MaybeAI's core voice loop (`AudioWorklet -> VAD -> STT -> Brain -> SentenceChunker -> TTS -> VTS/WS`) targets sub-second conversational turn-around. Adding IPC serialization and broker hops between `ConversationEngine`, `MoodEngine`, `MemoryRetriever`, and `TTSEngine` adds `20–100 ms` (estimated) per turn and complicates `barge_in()` `CancelledError` propagation.
  - **Measured In-Process Headroom:** Chaos Scenario A and Performance Analysis (`audit/11_chaos_testing.md`, `12_performance_analysis.md`) proved that the in-process `EventBus` processes `50` rapid messages + SuperChat + Karaoke + Barge-in in **`0.28 ms`** with `0` handler errors, and fans out to `500` WebSocket listeners in **`2.159 ms`/broadcast**.
  - **Actual Bottleneck:** Remaining event-loop stalls (`0.109s–0.282s` slow callbacks in `-W default` runs) come from synchronous disk/engine I/O and local ML inference—solvable via a **Dedicated Inference Worker** (`EXP-006`) and per-WS outbound queues (`INFRA-MED-001-RES`), not 10+ microservices.
- **Correct Alternative:** Retain the **modular monolith** (`EventBus` + `Orchestrator`) and isolate only heavy ML inference (`EXP-006`), untrusted plugins (`core/plugins/sandbox_worker.py`), external media tools (`yt-dlp`/`ffmpeg`/`demucs`), and the Node.js Mineflayer bridge (`minecraft/bot.js`).

---

## 2. Heavy Kubernetes (K8s) Orchestration

- **Proposal:** Package MaybeAI with Helm charts, Kubernetes manifests, ingress controllers, and multi-pod autoscaling.
- **Why Rejected:**
  - **Single-Streamer Stateful Hardware:** An AI VTuber is an inherently single-instance, stateful application bound to local hardware (OBS WebSocket on `localhost:4455`, VTube Studio on `localhost:8001`, local GPU VRAM, `pygame` audio, and local `data/second_brain/memory.db` SQLite WAL).
  - **Zero Horizontal Scaling Value:** Horizontally scaling a single live stream's voice or Minecraft avatar across multiple pods introduces split-brain state.
  - **Premature Ops Overhead:** K8s adds massive manifest/ops complexity while MaybeAI's `Unattended 24/7 Public Internet` profile is still `NO-GO` due to `SEC-GAP-001` (`?token=` WS URLs), `SEC-GAP-002` (Windows plugin sandbox), and missing `RotatingFileHandler`.
- **Correct Alternative:** Single-host `Dockerfile` / `docker-compose.yml` (`MAYBEAI_HEADLESS=1`) with `MAYBEAI_CREATOR_TOKEN`, Docker log rotation (`max-size`/`max-file`), and persistent `data/` + `config/` volume mounts.

---

## 3. Full Rust / Go Rewrite of `core/`

- **Proposal:** Rewrite MaybeAI's Python `asyncio` backend in Rust (`tokio`/`axum`) or Go for raw performance.
- **Why Rejected:**
  - **Wrong Bottleneck:** `>95%` of turn latency is spent in LLM network/inference (`250–1500 ms`) and neural audio/vision inference, whereas Python `Moderator.clean_text` takes **`0.006 ms/msg`** (`3.19 ms` for `500` msgs) and `EventBus` takes **`0.28 ms`** for `50` msgs.
  - **AI Ecosystem Loss:** Python is the native runtime for `faster-whisper`, `kokoro-onnx`, `fastembed`, `demucs`, `python-chess`, and `edge-tts`. Rewriting in Rust/Go forces brittle FFI or sidecar sprawl.
  - **Regression Risk:** MaybeAI has `97` core Python files and `381` unit tests (`380` passed, `1` skipped). A rewrite would freeze H4–H8 delivery for 6+ months.
- **Correct Alternative:** Keep Python `asyncio` for orchestration, offload heavy ML to a **Dedicated Inference Worker** (`EXP-006`), and use C/ONNX-backed libraries (`numpy`, `sqlite-vec`, `faster-whisper`, `kokoro-onnx`).

---

## 4. Unverified Autonomous OS Desktop Control (Unconstrained "Computer Use")

- **Proposal:** Allow Eve to autonomously control the creator's OS mouse, keyboard, and arbitrary desktop applications (e.g., via PyAutoGUI or unconstrained VLM computer-use agents) driven by stream chat or autonomous mission ticks.
- **Why Rejected:**
  - **Indirect Prompt Injection Risk (`SEC-GAP-003`):** `audit/FINAL_POST_IMPLEMENTATION_AUDIT.md` verified that raw `obs.summary` / `obs.eve_commentary` from VLM/OCR is currently injected without `Moderator.sanitize_metadata()` or untrusted-data delimiters. On-screen text (viewer chat, browser tabs, Discord) could hijack a computer-use agent into leaking stream keys or deleting files.
  - **Sandbox Bypass Risk (`SEC-GAP-002`):** Windows plugin isolation still relies on bypassable Python monkeypatches (`ctypes`/`subprocess`), meaning arbitrary OS execution surfaces are not yet kernel-confined.
- **Correct Alternative:** Restrict desktop automation strictly to **allowlisted, typed APIs** (`OBSWebSocketClient` for scene/replay control, `VTSClient` for Live2D parameters) gated behind `MAYBEAI_CREATOR_TOKEN` and sanitized VLM outputs.

---

## 5. End-to-End Speech-to-Speech Monolithic Audio LLMs as Core Pipeline

- **Proposal:** Replace `STT -> Moderator -> ConversationEngine -> Brain -> SentenceChunker -> TTSEngine -> RVC` with a single cloud Speech-to-Speech WebSocket model.
- **Why Rejected:**
  - **Bypasses Moderation & Persona Controls:** Eliminates `Moderator` text-level prompt-injection filtering (`Chaos C`), `ContextBudgetManager` `[CREATOR VERIFIED]` authority plumbing, and `MoodEngine.get_temperature_modifier()`.
  - **Breaks Voice Identity & Karaoke:** Incompatible with custom character voices (`Kokoro-82M`, `RVCVoiceConverter`) and `Singer` / `YouTubeKaraokeProcessor` stem-synced playback.
  - **Cloud Lock-In:** Eliminates offline/LAN operation and incurs high per-minute audio API costs.
- **Correct Alternative:** Optimize the modular pipeline via `EXP-006` (Dedicated Inference Worker running `Silero-VAD` + `faster-whisper` + `kokoro-onnx`) while keeping `ProviderCircuitBreaker` LLM failover.

---

## 6. External Vector & Graph Databases (Qdrant / Milvus / Pinecone / Neo4j) Before Workload Threshold

- **Proposal:** Deploy external Qdrant/Milvus/Pinecone for episodic vectors and Neo4j for knowledge graphs in Horizon 4.
- **Why Rejected:**
  - **Measured SQLite Headroom:** `audit/12_performance_analysis.md` measured `MemoryDatabase.vector_search` at **`13.54 ms`** (`N=100`) to **`45.32 ms`** (`N=2,000`) in pure Python/NumPy brute-force scan. A single VTuber accumulates `~10K–100K` episodic rows/year—well within embedded **`sqlite-vec` / `hnswlib` + SQLite FTS5** (`<15 ms` estimated at `10K–100K` rows).
  - **Split-Brain & Ops Cost:** External DB containers consume `500 MB–2 GB` RAM, break single-file `data/second_brain/memory.db` backup portability, and introduce dual-write consistency bugs with `user_profiles`, `promises_challenges`, and Markdown sync.
- **Correct Alternative:** Evolve `MemoryDatabase` with `sqlite-vec` / `hnswlib` + FTS5 RRF and a lightweight **SQLite Entity-Relation table** (`EXP-004`). Revisit external vector/graph DBs *only* if a deployment exceeds `250,000+` active memories or multi-tenant cloud hosting.

---

## 7. Unbounded Self-Spawning Multi-Agent Swarms on Live Streams

- **Proposal:** Allow Eve to dynamically spawn arbitrary autonomous sub-agents during live streams to browse, plan, or converse without strict concurrency/turn caps.
- **Why Rejected:**
  - **Soak & Latency Risk:** Unbounded background task spawning requires explicit `EventBus(max_pending_tasks=256)` and `MAX_REPLAN_ATTEMPTS=3` guardrails to stay stable over 8–12h streams.
  - **Cost & Coherence:** Unbounded multi-agent chatter multiplies LLM token spend, introduces turn-taking collisions (even 2-peer `CollabManager` currently has `Chaos B` `floor_state` deadlock on disconnect), and risks unmoderated output.
- **Correct Alternative:** Deterministic `Orchestrator` + `TaskSupervisor` with bounded `N<=4` peer `CollabManager` mesh (`EXP-005`) and explicit HMAC-SHA256 turn-taking protocols.
