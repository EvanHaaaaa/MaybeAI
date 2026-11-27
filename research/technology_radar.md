# MaybeAI — Next-Generation Technology Radar (`research/technology_radar.md`)

**Owner:** AGENT 10 (`ng-strat-research`) — AI Research & Emerging Technology Architect  
**Synchronized With:** [strategy/TECHNOLOGY_RADAR.md](file:///d:/projects/MaybeAI/strategy/TECHNOLOGY_RADAR.md)  
**Grounding Baseline:** Post-Horizon 3 + YouTube Karaoke (`HEAD 96b7315`) — [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md), [03_realtime_audio.md](file:///d:/projects/MaybeAI/audit/03_realtime_audio.md), [04_cognitive_memory.md](file:///d:/projects/MaybeAI/audit/04_cognitive_memory.md), [06_game_vision_entertainment.md](file:///d:/projects/MaybeAI/audit/06_game_vision_entertainment.md), [12_performance_analysis.md](file:///d:/projects/MaybeAI/audit/12_performance_analysis.md)

---

## 1. Radar Rings & Evaluation Criteria

MaybeAI is a **hardened single-node modular monolith (L3.0–L3.5)** targeting local Windows/Linux workstations and single-host Docker deployments (`Supervised Localhost: GO`, `Authenticated LAN/Docker: CONDITIONAL GO`). Technologies are evaluated against sub-second voice duplex latency, 8–12h stream soak stability, offline/LAN resilience, and creator-rig resource budgets.

> [!NOTE]
> All latency and throughput figures explicitly distinguish **Measured** values (observed in `audit/11_chaos_testing.md` and `audit/12_performance_analysis.md`) from **Estimated** values (literature/hardware projections pending `EXP-004`–`EXP-006`).

| Ring | Meaning | Action Policy |
|---|---|---|
| **ADOPT** | Proven in MaybeAI's post-H3 baseline or low-risk immediate upgrade; solves verified bottlenecks. | Standardize in `core/` and `web/`; maintain regression tests. |
| **TRIAL** | High-value Horizon 4–6 capability; requires isolated benchmarking (`EXP-004`–`EXP-006`) before default enablement. | Validate against explicit Go/No-Go gates in `research/experiments/`. |
| **ASSESS** | Promising Horizon 6–8 capability; immature ecosystem fit, high VRAM cost, or requires upstream stabilization. | Prototype in isolation; never couple to live stream critical paths. |
| **HOLD** | Premature operational complexity, security risk, or incompatible with single-node VTuber constraints. | Do not adopt; see [rejected_proposals.md](file:///d:/projects/MaybeAI/research/rejected_proposals.md). |

---

## 2. Comprehensive Technology Radar Matrix

### 2.1 AI Models (LLM, SLM, VLM, Speech, Embeddings, Rerankers)

| Technology | Ring | Problem Solved | Maturity (MaybeAI Status) | Alternatives | License | Integration Cost | Resources & Latency | Maintenance |
|---|---|---|---|---|---|---|---|---|
| **Multi-Provider Cloud/Local LLM + `ProviderCircuitBreaker`** (Gemini SSE, OpenAI SSE, Ollama NDJSON) | **ADOPT** | Resilient conversational generation with automatic failover (`failure_threshold=3`, `cooldown=30s`) and mood-modulated sampling (`[-0.15, +0.15]`). | Production (`EXISTING`, needs `ClientTimeout` TTFB fix `AUDIO-MED-001`) | LiteLLM, vLLM router | MIT / Apache-2.0 / Proprietary | Low (already in `core/brain.py`) | Measured: `<1 ms` circuit overhead; Est: `250–1200 ms` TTFB | Low |
| **Edge-TTS (`edge-tts`) + `RVCVoiceConverter`** | **ADOPT** | Zero-VRAM cloud TTS with `is_edge_tts_voice()` fallback safety and optional RVC timbre conversion. | Production (`EXISTING`) | Piper TTS, ElevenLabs | LGPL-3.0 (`edge-tts`) / MIT (RVC) | Low (`core/tts_providers.py`) | Est: `300–900 ms` TTFA (network); `0` local VRAM for Edge-TTS | Low |
| **Hybrid SLM/LLM Router** (`qwen2.5:3b/7b` or Gemini Flash-Lite for triage/reflection, Frontier LLM for main persona) | **TRIAL** | Cuts cloud token cost and latency for background classification, memory consolidation (`EXP-004`), and `Goal.reflection` synthesis. | Emerging (`PLANNED` for H4) | Single cloud LLM, static heuristics | Apache-2.0 / Qwen | Medium (`core/brain.py`, `core/planning/`) | Est: `2–5 GB` VRAM (local 3B–7B Q4) or `<300 ms` Flash-Lite | Medium |
| **`faster-whisper` (INT8 CTranslate2) + `Silero-VAD` (ONNX)** | **TRIAL** | Local offline STT + noise-robust VAD replacing static `EnergyVAD` (`0.02`) and `[STT Mock]` fallback; enables streaming partials. | Mature OSS (`EXPERIMENTAL` in MaybeAI — packages absent in `.venv`) | OpenAI Whisper API, `whisper.cpp`, Vosk | MIT | Medium (`core/stt.py`, `EXP-006` worker) | Est: `~2 MB` disk + `<2%` CPU (Silero); `0.5–1.5 GB` VRAM / `150–600 ms` (Whisper) | Low-Medium |
| **Kokoro-82M (`kokoro-onnx`)** | **TRIAL** | Sub-200ms offline/LAN neural TTS with native 24 kHz WAV output for exact RMS lip-sync. | Mature OSS (`EXPERIMENTAL` — absent in `.venv`) | Piper TTS, Fish Speech, ElevenLabs | Apache-2.0 | Low-Medium (`core/tts_providers.py` scaffolded) | Est: `~320 MB` ONNX, `0.6–1.0 GB` VRAM or 2–4 CPU threads; `80–220 ms` CPU TTFA | Low |
| **FastEmbed (`BAAI/bge-small-en-v1.5` / `bge-m3`)** | **TRIAL** | Consistent 384-d/1024-d local CPU ONNX embeddings eliminating 128-d hash fallback mismatches (`Chaos D`). | Mature OSS (`PLANNED`) | Gemini/OpenAI Embeddings, `sentence-transformers` (heavy PyTorch) | Apache-2.0 | Low (`core/memory/embedding.py`) | Est: `~130 MB` RAM (CPU ONNX), `0` VRAM, `5–18 ms`/query | Low |
| **Cross-Encoder Reranker (`bge-reranker-v2-m3` / `ms-marco-MiniLM`)** | **ASSESS** | Re-scores top-20 hybrid memory candidates before prompt injection to improve `Recall@5` precision on noisy multi-stream logs. | Mature OSS (`PROPOSED` H5) | RRF-only scoring, LLM-as-judge | Apache-2.0 / MIT | Medium (`core/memory/retriever.py`) | Est: `~300–600 MB` RAM (CPU ONNX), `15–40 ms` per 20-doc batch | Low |
| **Local VLM (`qwen2.5vl:3b` via Ollama) + Sanitized Grounding** | **ASSESS** | Offline desktop/game visual perception; requires `Moderator.sanitize_metadata()` (`SEC-GAP-003`) before commentary injection. | Maturing (`INCOMPLETE` — heuristic fallback active) | Gemini Flash Vision, GPT-4o-mini Vision | Apache-2.0 / Qwen | Medium (`core/vision/vlm.py`, `core/conversation/engine.py`) | Est: `3.0–4.5 GB` VRAM, `600–2500 ms`/frame (`10s` cooldown) | Medium |
| **End-to-End Speech-to-Speech APIs (Realtime Audio)** | **HOLD** | Direct audio-in/audio-out LLM. Rejected because it bypasses `Moderator`, `SentenceChunker`, `RVC`, `Second Brain`, and deterministic `barge_in()`. | Cloud-proprietary (`REJECTED`) | Modular `Silero-VAD -> faster-whisper -> Brain -> Kokoro` | Proprietary | High (breaks core pipeline) | Cloud-only, high per-minute cost | High (lock-in) |

---

### 2.2 AI Architecture (Orchestration, Memory, RAG, Knowledge Graphs, Planning, Tool Use, Multi-Agent)

| Technology | Ring | Problem Solved | Maturity (MaybeAI Status) | Alternatives | License | Integration Cost | Resources & Latency | Maintenance |
|---|---|---|---|---|---|---|---|---|
| **`ContextBudgetManager` (Priority-Tiered Prompt Assembly)** | **ADOPT** | Enforces per-provider token ceilings (`1600–1800` heuristic tokens) and `[CREATOR VERIFIED]` retention across 11 subsystems. | Production (`EXISTING` in `core/brain.py`) | LangChain prompt templates, raw string concat | Internal (MIT `tiktoken` optional) | Low (done) | Measured/Est: `<1 ms` assembly; `-30% to -55%` input tokens | Low |
| **Bounded HTN/FSM Mission Loop (`MAX_REPLAN_ATTEMPTS=3`)** | **ADOPT** | Prevents infinite 25s replanning loops (`REPLANNED` excluded from progress denominator, `approval_timeout_sec=300`). | Production (`EXISTING` in `core/planning/`) | Unbounded ReAct loops, `py_trees` | Internal | Low (done) | Negligible (`<1%` CPU) | Low |
| **Hierarchical Memory Consolidation + Causal Reflection** | **TRIAL** | Solves flat episodic-only storage, write-only `Goal.reflection`, and unwired `promises.md` fulfillment (`EXP-004`). | Research (`PLANNED` H4) | Flat RAG + rolling 4-snippet string concat | Internal + LLM/SLM | Medium (`core/memory/`, `core/planning/`) | Est: async off-peak / post-stream batch (`1–3` LLM calls/session) | Medium |
| **Hybrid FTS5 + `sqlite-vec` / `hnswlib` RRF Retrieval** | **TRIAL** | Eliminates `vector_scan_limit=2000` blind spot (`45.32 ms` linear scan) while keeping single-file SQLite portability. | Maturing (`PLANNED` H4) | Linear NumPy scan, external Qdrant/Milvus | MIT / Apache-2.0 | Medium (`core/memory/database.py`) | Measured baseline: `45.32 ms` @ 2K rows; Est: `<10 ms` @ 10K–100K rows | Low |
| **N-Peer `CollabManager` Mesh (HMAC-SHA256 + Subsystems Sync)** | **TRIAL** | Extends 2-peer collab to N-peer turn-taking, fixes `disconnect_peer()` `floor_state` deadlock (`Chaos B`), and wires `duet_sync`/`emote_sync`/`game_move` (`EXP-005`). | Research (`INCOMPLETE` -> `PLANNED` H6) | Static 2-peer scalar protocol | Internal (`hmac`, `aiohttp`) | Medium (`core/collab/manager.py`, `core/orchestrator.py`) | Est: `<5 ms` LAN HMAC frame; bounded `N<=4` peers | Medium |
| **Lightweight SQLite Entity-Relation Knowledge Graph** | **ASSESS** | Tracks structured `(subject, predicate, object, confidence, valid_from)` facts (viewer lore, Minecraft recipes, inside jokes) without Neo4j. | Emerging (`PROPOSED` H5) | Neo4j, Graphiti, flat Markdown | Internal (SQLite) | Medium (`core/memory/`) | Est: `<20 MB` RAM, `<5 ms` 2-hop SQL join | Medium |
| **External Graph/Vector DBs (Neo4j, Qdrant, Milvus, Weaviate)** | **HOLD** | Multi-million vector/graph clustering. Rejected as premature overhead for single-streamer `10K–100K` row workloads. | Mature (`REJECTED`) | SQLite + FTS5 + `sqlite-vec` + SQLite KG | Apache-2.0 / GPL | High (Docker sidecar + dual-write) | `500 MB–2 GB` RAM container | High |
| **Unbounded Self-Spawning Agent Swarms / Unconstrained Computer Use** | **HOLD** | Arbitrary sub-agent spawning or OS mouse/keyboard control. Rejected due to `SEC-GAP-003` prompt injection and soak/cost risks. | Experimental (`REJECTED`) | Allowlisted typed APIs (`OBSWebSocketClient`, `VTSClient`) + `TaskSupervisor` | N/A | High risk | Unbounded token/CPU cost | High |

---

### 2.3 Runtime (Async, Isolation, Brokers, SQLite/Vector, Observability)

| Technology | Ring | Problem Solved | Maturity (MaybeAI Status) | Alternatives | License | Integration Cost | Resources & Latency | Maintenance |
|---|---|---|---|---|---|---|---|---|
| **FastAPI + Typed `EventBus` + Bounded Queues** | **ADOPT** | Concurrent in-process pub/sub (`max_pending_tasks=256`, `handler_timeout=5.0`, `ChatReceiver(500)`). Needs per-WS outbound `asyncio.Queue(64)` (`INFRA-MED-001-RES`). | Production (`EXISTING` in `core/event_bus.py`) | Redis Pub/Sub, RabbitMQ, Celery | MIT | Low (per-WS queue is P1) | Measured: `0.28 ms` for 50 msgs; `0.074–2.159 ms` WS fan-out (10–500 clients) | Low |
| **SQLite WAL + FTS5 (`MemoryDatabase`)** | **ADOPT** | Zero-server ACID persistence with `PRAGMA journal_mode=WAL` and dimension-mismatch protection (`Chaos D`). | Production (`EXISTING`) | PostgreSQL, DuckDB | Public Domain | Low | Measured: `13.54 ms` (N=100) to `45.32 ms` (N=2000) `vector_search` | Low |
| **Dedicated Inference Worker Subprocess (JSON-RPC / Shared IPC)** | **TRIAL** | Isolates heavy local ML (`faster-whisper`, `kokoro-onnx`, `FastEmbed`, `qwen2.5vl:3b`) from FastAPI event loop, eliminating `0.11s–0.28s` slow callbacks (`EXP-006`). | Research (`PLANNED` H4–H5) | `asyncio.to_thread` (shares GIL/VRAM lifecycle), HTTP microservices | Internal (`multiprocessing` / `asyncio.subprocess`) | Medium (`core/inference/`, `core/orchestrator.py`) | Est: `+80–150 MB` base worker RSS; `0 ms` main event-loop blocking | Medium |
| **Hardened OS Plugin Sandbox (`bwrap` / Windows AppContainer / Restricted Token)** | **TRIAL** | Replaces bypassable Python monkeypatches (`SEC-GAP-002`) with kernel-enforced FS/network isolation for untrusted plugins. | Maturing (`INCOMPLETE` on Windows — `JobObject` only) | Docker-per-plugin, WASM (`wasmtime`) | MIT / OS native | Medium-High (`core/plugins/sandbox_worker.py`) | Est: `<20 MB` per worker, `<=5.0s` hook timeout | Medium |
| **Structured JSON Logging (`RotatingFileHandler`) + OpenTelemetry / `/api/metrics`** | **TRIAL** | Fixes unbounded stdout `print()` soak risk (`Chaos E`) and `ResourceWarning` visibility across 8–12h streams. | Mature (`INCOMPLETE` — `/api/metrics` exists, `RotatingFileHandler` missing) | `logrotate` + Docker driver only | Python stdlib / Apache-2.0 | Low (`core/`, `run.py`) | Negligible (`<1%` CPU, bounded disk) | Low |
| **Heavy Brokers / Microservices / K8s (Redis, RabbitMQ, Helm)** | **HOLD** | Distributed message brokering and multi-pod orchestration. Rejected for single-node stateful VTuber workloads. | Mature (`REJECTED`) | In-process `EventBus` + dedicated inference/plugin subprocesses | BSD / MPL | High | High RAM/ops overhead | High |

---

### 2.4 Frontend / Avatar (VRM, Live2D, WebGPU, WebAudio/Worklet)

| Technology | Ring | Problem Solved | Maturity (MaybeAI Status) | Alternatives | License | Integration Cost | Resources & Latency | Maintenance |
|---|---|---|---|---|---|---|---|---|
| **Offline-Vendored Three-VRM (`@pixiv/three-vrm`) + WebGL2** | **ADOPT** | Zero-CDN 3D VRM rendering in OBS Browser Source (`/overlay`) and Studio (`/`) with offline/LAN reliability. | Production (`EXISTING` in `web/vendor/`) | Live2D Cubism SDK (proprietary), Unity VSeeFace | MIT | Low (done) | Est: `100–250 MB` browser GPU mem; `0 ms` external network | Low |
| **VTube Studio WebSocket API (`VTSClient`)** | **ADOPT** | Live2D parameter injection with persistent token (`data/vts_token.json`) and exponential-backoff reconnect. | Production (`EXISTING` in `core/vts_client.py`) | Warudo, Animaze | Proprietary VTS app | Low (unify `MouthForm`/`MouthSmile` P2) | `<5 ms` local WS | Low |
| **WebAudio `AudioWorklet` (16 kHz Binary PCM) + `AnalyserNode` Arbitration** | **ADOPT** | 32ms (512-sample) mic capture + client-side `isLocalAudioPlaying` arbitration eliminating `output_mode="both"` jitter. | Production (`EXISTING`) | `ScriptProcessorNode` (deprecated), JSON base64 | Web Standard | Low (done) | Negligible CPU; `-33%` WS bytes vs base64 | Low |
| **Modular ES Frontend State Store (Unifying `app.js` / `overlay.js` / `deck.js` / `settings.js`)** | **TRIAL** | Eliminates `5,896`-line `web/app.js` duplication, 5 unguarded `ws.readyState` bugs, and missing `Sec-WebSocket-Protocol` auth (`SEC-GAP-001`). | Standard Web (`PLANNED` H4) | React/Vite build step (adds Node build toolchain), keeping 4 monolithic scripts | Vanilla ES Modules (zero-build) | Medium (`web/shared-client.js`, `web/app.js`) | `0` runtime overhead | Low (reduces tech debt) |
| **WebGPU VRM / Client-Side Avatar Physics** | **ASSESS** | Next-gen GPU compute for hair/cloth physics and post-processing shaders in `/overlay` without OBS CPU contention. | Maturing (`PROPOSED` H7) | WebGL2 (`@pixiv/three-vrm` current) | Web Standard | Medium (`web/overlay.js`) | Est: lower CPU overhead on modern Chromium; fallback to WebGL2 required | Medium |

---

### 2.5 Content Production (FFmpeg, Demucs, RVC, Video Understanding)

| Technology | Ring | Problem Solved | Maturity (MaybeAI Status) | Alternatives | License | Integration Cost | Resources & Latency | Maintenance |
|---|---|---|---|---|---|---|---|---|
| **Subprocess `FFmpeg` + Confined `ClipPipeline`** | **ADOPT** | Vertical 9:16 highlight clipping with `is_relative_to()` path confinement and filtergraph subtitle escaping. | Production (`EXISTING`, host binary optional) | MoviePy (slow Python wrapper), OBS-only | LGPL/GPL (`ffmpeg` binary) | Low (add `get_status()` + binary check) | Est: `1–4` CPU cores during clip render (async subprocess) | Low |
| **YouTube Karaoke Pipeline (`yt-dlp` + `demucs` + `RVC`)** | **TRIAL** | Automated song request stem separation (`--two-stems=vocals` / ffmpeg fallback), VTT/SRT lyric sync, and AI cover conversion. | Functional (`EXISTING` code, `NOT VERIFIED` live on host missing binaries; needs `SEC-GAP-005` `--max-filesize` & job cap) | Spleeter (older), UVR5 | Unlicense (`yt-dlp`), MIT (`demucs`) | Low-Medium (`core/youtube_karaoke.py`) | Est: `2–4 GB` VRAM or `15–45s` CPU per song (`demucs`); cached in `data/karaoke_cache/` | Medium (`yt-dlp` updates) |
| **Keyframe + Audio-Peak Video Understanding (VLM + Whisper Highlight Summarizer)** | **ASSESS** | Upgrades `VODSummarizer` and `ClipPipeline` from event-only markers to semantic chaptering and auto-captioned Shorts/Reels. | Emerging (`PROPOSED` H7) | Event-only `HighlightDetector` + `VODSummarizer` | Apache-2.0 / MIT | Medium (`core/highlights/`, `core/vision/`) | Est: post-stream offline batch (`2–6 GB` VRAM or cloud VLM) | Medium |
| **Real-Time Singing Voice Synthesis (SVS / DiffSinger)** | **ASSESS** | Pitch-accurate singing synthesis from MIDI/MusicXML instead of spoken-TTS-over-BGM in `Singer`. | Research (`PROPOSED` H7–H8) | `YouTubeKaraokeProcessor` + `RVC` | MIT / Apache-2.0 | High (`core/singer.py`) | Est: `2–4 GB` VRAM | High |

---

## 3. Deployment Profile Resource Envelopes

| Profile | Target Hardware | Budget for MaybeAI | Recommended Radar Stack |
|---|---|---|---|
| **Entry-Level (Cloud-Assisted / CPU-Only)** | 6–8 core CPU, 16 GB RAM, iGPU/low VRAM | `<2 GB` RAM, `0 GB` VRAM | `EventBus` + `SQLite WAL` + Cloud LLM (`ProviderCircuitBreaker`) + `Edge-TTS` + `Silero-VAD` (CPU) + `FastEmbed` (CPU) + `Three-VRM`. |
| **Recommended (Balanced Single-GPU VTuber Rig)** | 8–12 core CPU, 32 GB RAM, 8–12 GB VRAM (sharing with OBS/VTS/Game) | `<=2.5 GB` VRAM, `<4 GB` RAM | Entry-Level + `EXP-006` Inference Worker (`faster-whisper` `base` INT8 + `kokoro-onnx` GPU) + `sqlite-vec` + `FFmpeg` clipping. |
| **Advanced (Dedicated AI / Dual-PC Studio)** | 12+ core CPU, 32–64 GB RAM, 16–24 GB VRAM | `6–14 GB` VRAM | Recommended + Local SLM/LLM (`qwen2.5:7b` / `llama3.2`) + `qwen2.5vl:3b` VLM + `demucs` + `RVC v2` + N-peer `CollabManager`. |
