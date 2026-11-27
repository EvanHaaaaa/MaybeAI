# MaybeAI — Executive Technology Radar (`strategy/TECHNOLOGY_RADAR.md`)

**Owner:** AGENT 10 (`ng-strat-research`) — AI Research & Emerging Technology Architect  
**Synchronized With:** [research/technology_radar.md](file:///d:/projects/MaybeAI/research/technology_radar.md)  
**Grounding Baseline:** Post-Horizon 3 + YouTube Karaoke (`HEAD 96b7315`) — [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md), [03_realtime_audio.md](file:///d:/projects/MaybeAI/audit/03_realtime_audio.md), [04_cognitive_memory.md](file:///d:/projects/MaybeAI/audit/04_cognitive_memory.md), [06_game_vision_entertainment.md](file:///d:/projects/MaybeAI/audit/06_game_vision_entertainment.md), [12_performance_analysis.md](file:///d:/projects/MaybeAI/audit/12_performance_analysis.md)

---

## 1. Strategic Radar Overview

Following Horizons 0–3 and the YouTube Karaoke release, MaybeAI has transitioned from a prototype to a **hardened single-node modular monolith (L3.0–L3.5)**. Our **Horizons 4–8** technology strategy preserves single-node operational simplicity while systematically resolving the remaining post-H3 bottlenecks:
1. **Cognitive Depth (H4):** Moving beyond flat 2,000-row linear vector scan (`45.32 ms`) and write-only `Goal.reflection` via Hierarchical Memory Consolidation (`EXP-004`), `sqlite-vec`/HNSW, and Hybrid SLM/LLM routing.
2. **Event-Loop & Inference Isolation (H4–H5):** Eliminating `0.11s–0.28s` asyncio slow callbacks and unlocking local `faster-whisper`/`kokoro-onnx`/`FastEmbed`/`VLM` via a Dedicated Inference Worker (`EXP-006`).
3. **Multi-Peer Social & Multimodal Presence (H6–H8):** Evolving 2-peer `CollabManager` into an N-peer mesh with automated subsystem sync (`EXP-005`), sanitized VLM grounding (`SEC-GAP-003`), and post-stream Video Understanding.

---

## 2. Executive Quadrant Summary (ADOPT / TRIAL / ASSESS / HOLD)

| Domain | ADOPT (Standardize Now) | TRIAL (Benchmark in `EXP-004`–`006`) | ASSESS (H5–H8 Track) | HOLD (Rejected — Do Not Adopt) |
|---|---|---|---|---|
| **AI Models** | Multi-Provider LLM + `ProviderCircuitBreaker`; `Edge-TTS` + `RVC` | Hybrid SLM/LLM Router; `faster-whisper` + `Silero-VAD`; `Kokoro-82M`; `FastEmbed` | Cross-Encoder Reranker (`bge-reranker`); Local VLM (`qwen2.5vl:3b`) w/ sanitization | End-to-End Speech-to-Speech Realtime APIs |
| **AI Architecture** | `ContextBudgetManager`; Bounded HTN/FSM Mission Loop (`MAX_REPLAN=3`) | Hierarchical Memory Consolidation (`EXP-004`); `sqlite-vec` / `hnswlib` + FTS5 RRF; N-Peer `CollabManager` Mesh (`EXP-005`) | Lightweight SQLite Entity-Relation Knowledge Graph | External Vector/Graph DBs (Qdrant, Milvus, Neo4j); Unbounded Swarms; Unconstrained Computer Use |
| **Runtime** | FastAPI + `EventBus` (`256` tasks) + SQLite WAL/FTS5 | Dedicated Inference Worker (`EXP-006`); Hardened OS Plugin Sandbox (AppContainer/bwrap); `RotatingFileHandler` + `/api/metrics` | — | Microservices Split; Redis/RabbitMQ Brokers; Kubernetes (K8s); Full Rust/Go Rewrite |
| **Frontend / Avatar** | Vendored Three-VRM (`web/vendor/`); `VTSClient`; `AudioWorklet` 16 kHz PCM + `AnalyserNode` | Modular ES State Store unifying `app.js` / `overlay.js` / `deck.js` + `Sec-WebSocket-Protocol` auth | WebGPU VRM Avatar Physics | External CDN Runtime Dependencies |
| **Content Production** | Subprocess `FFmpeg` + Confined `ClipPipeline` | `YouTubeKaraokeProcessor` (`yt-dlp` + `demucs` + `RVC`) w/ `--max-filesize` & job cap | Keyframe + Audio-Peak Video Understanding; DiffSinger SVS | Unconfined shell `ffmpeg` / unguarded URL downloads |

---

## 3. Detailed Evaluation & Go/No-Go Policy

Full 9-column technical evaluation matrices (Problem Solved, Maturity, Alternatives, Licensing, Integration Cost, Resources & Latency, Maintenance) and Deployment Profile Envelopes (**Entry-Level**, **Recommended**, **Advanced**) are maintained in sync in [research/technology_radar.md](file:///d:/projects/MaybeAI/research/technology_radar.md).

### Key Architectural Guardrails for Horizons 4–8
1. **No `TRIAL` or `ASSESS` technology enters `core/` default paths without passing its experiment gate** in [research/EXPERIMENT_BACKLOG.md](file:///d:/projects/MaybeAI/research/EXPERIMENT_BACKLOG.md) and [research/EXPERIMENT_RESULTS.md](file:///d:/projects/MaybeAI/research/EXPERIMENT_RESULTS.md).
2. **Pre-Horizon 4 Security & Reliability Gates First:** `SEC-GAP-001` (`Sec-WebSocket-Protocol`), `SEC-GAP-002` (OS plugin isolation), `SEC-GAP-003` (VLM `obs.summary` sanitization), `INFRA-MED-001-RES` (per-WS outbound queue), `AUDIO-MED-001` (`ClientTimeout` TTFB), and `CHAOS-B-001` (`CollabManager.disconnect_peer()` `floor_state` reset) must land before enabling autonomous H4–H6 features.
3. **Preserve Offline & Graceful Fallback Guarantees:** Every local neural dependency (`faster-whisper`, `kokoro-onnx`, `FastEmbed`, `sqlite-vec`, `demucs`, `yt-dlp`, `ffmpeg`) must remain optional with deterministic fallback to the existing `ADOPT` baseline.
