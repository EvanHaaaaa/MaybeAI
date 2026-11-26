# MaybeAI — Explicitly Rejected Proposals (`research/rejected_proposals.md`)

**Owner:** AGENT 10 — Future AI & Research Architect (`strat-ai`)  
**Grounding Baseline:** `audit/FINAL_AUDIT_REPORT.md`, `audit/02_realtime_audio.md`, `audit/03_cognitive_architecture.md`, `audit/05_game_engines.md`, `audit/11_performance_analysis.md`

This document records architectures and technologies that were **explicitly evaluated and rejected** for MaybeAI's roadmap, along with concrete technical rationale to prevent future scope creep or hype-driven rewrites.

---

## 1. Premature Microservices Split

- **Proposal:** Split `core/` (94 Python modules: `Brain`, `TTSEngine`, `STTEngine`, `MemoryDatabase`, `MoodEngine`, `GoalEngine`, `MinecraftController`, `CollabManager`) into independent FastAPI/gRPC microservices communicating over HTTP/Redis/RabbitMQ.
- **Why Rejected:**
  - **Latency Penalty:** MaybeAI's core loop (`VAD -> STT -> Brain -> SentenceChunker -> TTS -> VTS/WS`) targets sub-second conversational turn-around. Adding IPC serialization and network hops between `ConversationEngine`, `MoodEngine`, `MemoryRetriever`, and `TTSEngine` adds `20–100 ms` per turn and complicates `barge_in()` cancellation (`[AUDIO-CRIT-001]`).
  - **Operational Complexity:** Local Windows/Linux VTuber creators want a single `python run.py` (or single Docker container) launch—not 8+ services, service discovery, and distributed tracing.
  - **Actual Bottleneck:** The audit proved that MaybeAI's concurrency issues come from sequential `EventBus.publish()` (`[PERF-HIGH-001]`), blocking `transcribe_wav_bytes()` (`[AUDIO-HIGH-001]`), and sync SQLite/file I/O (`[PERF-MED-002]`, `[COG-MED-003]`)—all solvable in-process via `asyncio.gather`, `asyncio.to_thread`, and bounded queues.
- **Correct Alternative:** Keep the modular monolith (`EventBus` + `Orchestrator`) and isolate only untrusted/heavy external runtimes via the existing **out-of-process Plugin Sandbox** (`core/plugins/`) and **Node.js Mineflayer bridge** (`minecraft/bot.js`).

---

## 2. Heavy Kubernetes (K8s) Orchestration

- **Proposal:** Package MaybeAI with Helm charts, Kubernetes manifests, ingress controllers, and multi-pod autoscaling.
- **Why Rejected:**
  - **Single-Streamer Stateful Workload:** An AI VTuber is an inherently single-instance, stateful application tied to local hardware (OBS WebSocket on `localhost:4455`, VTube Studio on `localhost:8001`, local GPU VRAM, local `pygame` audio device, and local `data/second_brain/memory.db` SQLite).
  - **Zero Horizontal Scaling Value:** You cannot horizontally scale a single live stream's voice or Minecraft avatar across 3 pods without introducing split-brain state.
  - **Unnecessary Burden:** K8s adds massive YAML/ops overhead while MaybeAI still has basic single-container/LAN auth gaps (`[SEC-HIGH-001]`, `[SEC-CRIT-001]`).
- **Correct Alternative:** Single-host `Dockerfile` / `docker-compose.yml` with proper creator token auth (`MAYBEAI_CREATOR_TOKEN`), `SDL_AUDIODRIVER=dummy` headless support, and persistent volume mount for `data/` and `config/`.

---

## 3. Full Rust / Go Rewrite of `core/`

- **Proposal:** Rewrite MaybeAI's Python `asyncio` backend in Rust (`tokio`/`axum`) or Go for raw performance.
- **Why Rejected:**
  - **Wrong Bottleneck:** >95% of MaybeAI's turn latency is spent in LLM inference (`200–1500 ms`), STT/TTS/RVC neural inference (`100–600 ms`), and network I/O—not Python interpreter overhead (`0.1–2 ms` in `EventBus`).
  - **AI Ecosystem Loss:** Python is the native runtime for `faster-whisper`, `kokoro-onnx`, `sentence-transformers`, `fastembed`, `python-chess`, and `edge-tts`. Rewriting in Rust/Go forces brittle FFI bindings or re-splitting into sidecar servers.
  - **Regression Risk:** MaybeAI already has 94 working modules and 315+ unit tests (`audit/FINAL_AUDIT_REPORT.md`). A rewrite would freeze feature delivery for 6+ months while re-introducing solved bugs.
- **Correct Alternative:** Targeted Python `asyncio` hardening (`[PERF-HIGH-001]`, `[AUDIO-HIGH-004]`, `[COG-MED-003]`) and C-backed/ONNX libraries (`numpy`, `sqlite-vec`, `faster-whisper`, `kokoro-onnx`) for compute-hot paths.

---

## 4. Unverified Autonomous OS Desktop Control (Unconstrained "Computer Use")

- **Proposal:** Allow Eve to autonomously control the creator's OS mouse, keyboard, and arbitrary desktop applications (e.g., via unconstrained PyAutoGUI or VLM computer-use agents) driven by chat or autonomous mission ticks.
- **Why Rejected:**
  - **Severe Security & Hijack Risk:** The audit verified that `Moderator`'s `strict_mode` and `prompt_injection_filter` are currently **non-blocking dead code** (`[SEC-HIGH-004]`), `/ws` lacks auth on mutating actions (`[SEC-CRIT-001]`), and `is_creator` is dropped on live LLM paths (`[COG-HIGH-003]`). Giving an unauthenticated/prompt-injectable LLM arbitrary OS input control during a live stream is catastrophic (accidental stream-key leak, file deletion, or OS takeover).
  - **Unbounded Execution Risk:** Even with `human_approval_required`, `AutonomousMissionExecutor` lacks approval TTL/goal-ID validation (`[COG-MED-001]`) and has infinite loop bugs (`[COG-CRIT-002]`).
- **Correct Alternative:** Restrict desktop automation strictly to **explicitly allowlisted, typed APIs** (`OBSWebSocketClient` for scene/replay control, `VTSClient` for Live2D parameters) gated behind verified Creator auth (`MAYBEAI_CREATOR_TOKEN`) and non-bypassable `Moderator` filtering.

---

## 5. End-to-End Speech-to-Speech Monolithic Audio LLMs as Core Pipeline

- **Proposal:** Replace `STT -> ConversationEngine -> Brain -> SentenceChunker -> TTSEngine -> RVC` with a single cloud Speech-to-Speech WebSocket model.
- **Why Rejected:**
  - Eliminates `Moderator` text-level safety/injection filtering before speech generation.
  - Breaks custom character voice identity (`Kokoro`, `GPT-SoVITS`, `RVC v2`) and karaoke (`Singer`).
  - Breaks `Second Brain` memory extraction, `MoodEngine`, `GoalEngine`, and deterministic `barge_in()` cancellation.
  - Eliminates offline/LAN operation and introduces high per-minute audio API costs.
- **Correct Alternative:** Optimize the modular pipeline (`EXP-001`) to achieve `< 700 ms` local TTFA while retaining full control over voice, memory, moderation, and tool use.

---

## 6. External Distributed Vector Databases (Qdrant / Milvus / Pinecone)

- **Proposal:** Deploy an external vector database server for MaybeAI's episodic memory.
- **Why Rejected:**
  - Single-streamer episodic memory (`10K–100K` rows/year) is easily served in `< 15 ms` by embedded `sqlite-vec` or `hnswlib` + SQLite FTS5 (`EXP-002`).
  - External DBs break single-file `data/second_brain/` backup portability, introduce dual-write consistency bugs with `user_profiles`/`promises_challenges`, and waste 500 MB–2 GB of creator RAM.
- **Correct Alternative:** `sqlite-vec` (or `hnswlib` fallback) inside `core/memory/database.py` with schema-versioned embeddings.

---

## 7. Unbounded Self-Spawning Multi-Agent Swarms on Live Streams

- **Proposal:** Allow Eve to dynamically spawn arbitrary autonomous sub-agents during live streams to research, browse, or execute parallel tasks without strict budgets.
- **Why Rejected:**
  - Unbounded task spawning already caused resource/soak risks even for simple callbacks (`[INFRA-HIGH-001]`, `[PERF-LOW-002]`, `[COG-CRIT-002]`).
  - On a live stream, multi-agent chatter multiplies LLM token costs, creates latency spikes, and produces incoherent, unmoderated output.
- **Correct Alternative:** Deterministic single-coordinator `Orchestrator` with bounded `TaskSupervisor`, capped `MAX_REPLAN_ATTEMPTS`, and explicit peer-to-peer `CollabManager` protocol (`[COLLAB-CRIT-001]`/`[COLLAB-HIGH-003]` hardened) for intentional multi-VTuber collabs.
