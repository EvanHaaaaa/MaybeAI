# MaybeAI — Executive Technology Radar (`strategy/TECHNOLOGY_RADAR.md`)

**Owner:** AGENT 10 — Future AI & Research Architect (`strat-ai`)  
**Grounding Baseline:** `audit/FINAL_AUDIT_REPORT.md`, `audit/02_realtime_audio.md`, `audit/03_cognitive_architecture.md`, `audit/05_game_engines.md`, `audit/11_performance_analysis.md`  
**Stack Scope:** Python 3.11+ `asyncio`, FastAPI, WebSockets, SQLite (FTS5 + vector), Edge-TTS / Kokoro / ElevenLabs / GPT-SoVITS / RVC, Faster-Whisper, Three-VRM, OBS WebSocket v5, Mineflayer (Node.js)

---

## 1. Radar Rings & Decision Framework

Every technology on this radar is evaluated against MaybeAI's actual operational profile: a **single-node, real-time interactive AI VTuber platform** running on creator-grade hardware (local Windows/Linux workstation or single Docker host) where **sub-second voice latency, deterministic barge-in, 24/7 soak stability, and offline/LAN capability** matter more than distributed scale.

| Ring | Meaning | Action Policy |
|---|---|---|
| **ADOPT** | Proven fit for MaybeAI's architecture; directly resolves verified audit defects (`CRITICAL`/`HIGH`) with low integration risk. | Prioritize for immediate engineering integration after standard unit/integration testing. |
| **TRIAL** | Strong technical fit with measurable upside, but requires controlled benchmarking (`EXP-001`–`EXP-003`) to validate latency, VRAM, or accuracy before production default. | Run scoped R&D experiment with explicit Go/No-Go gates (`strategy/RESEARCH_PLAN.md`). |
| **ASSESS** | Promising capability for Horizon 2–3 (Showrunner / Multi-Agent), but immature in codebase or carries material resource/operational trade-offs. | Track and prototype in isolation; do not couple to critical stream paths. |
| **HOLD** | High complexity, poor ROI, or incompatible with MaybeAI's current stability/security posture. | Do not adopt; revisit only if core constraints change (see also `research/rejected_proposals.md`). |

### Quadrant Summary

| Technology / Pattern | Quadrant | Ring | Target Audit Findings |
|---|---|---|---|
| **In-Memory Audio Pipeline + Persistent `aiohttp` Pooling** | Audio & Voice | **ADOPT** | `[AUDIO-HIGH-004]`, `[PERF-MED-001]`, `[PERF-MED-002]` |
| **Server-Side PCM/RMS Envelope Lip-Sync + Browser Sync Arbitration** | Audio & Avatar | **ADOPT** | `[AUDIO-CRIT-002]`, `[AUDIO-MED-001]` |
| **Token-Budgeted Prompt Assembly (`ContextBudgetManager`)** | Cognition & LLM | **ADOPT** | `[COG-HIGH-002]`, `[COG-HIGH-003]`, `[COG-MED-004]` |
| **Bounded HTN / State-Machine Mission Loop + Telemetry ACK** | Agency & Games | **ADOPT** | `[COG-CRIT-001]`, `[COG-CRIT-002]`, `[COG-HIGH-001]`, `[GAME-CRIT-002]` |
| **Silero-VAD (ONNX) + Non-Blocking `faster-whisper` Worker** | Audio & Voice | **TRIAL** | `[AUDIO-HIGH-001]`, `[AUDIO-LOW-001]` |
| **Kokoro-82M (`kokoro-onnx`) as Primary Local Low-Latency TTS** | Audio & Voice | **TRIAL** | `[AUDIO-HIGH-003]`, `[AUDIO-HIGH-004]` |
| **`sqlite-vec` + Hybrid BM25/Vector RRF Retrieval** | Cognition & Memory | **TRIAL** | `[COG-HIGH-004]`, `[COG-HIGH-005]`, `[COG-MED-003]` |
| **Audio-Clock-Locked Karaoke Pre-Synthesis (`get_pos()` / AudioWorklet)** | Games & Showrunner | **TRIAL** | `[GAME-HIGH-005]`, `[AUDIO-HIGH-002]` |
| **Local VLM Vision (Ollama Vision / Qwen2.5-VL) + Rate-Limited VLM** | Vision & Multimodal | **ASSESS** | `[GAME-HIGH-001]`, `[GAME-MED-002]` |
| **GPT-SoVITS / Fish Speech + RVC v2 Zero-Disk Streaming** | Audio & Voice | **ASSESS** | `[AUDIO-HIGH-003]`, `[AUDIO-HIGH-004]` |
| **Binary WebSocket Audio Frames + Opus/PCM Streaming** | Infrastructure | **ASSESS** | `[PERF-HIGH-001]`, `[AUDIO-HIGH-004]` |
| **Local Bundled Three-VRM + WebGL2 Avatar Pipeline** | Frontend & Avatar | **ASSESS** | `[UI-MED-004]` |
| **End-to-End Speech-to-Speech Models (e.g., Realtime Audio APIs)** | Audio & LLM | **HOLD** | Bypasses `SentenceChunker`, `Moderator`, RVC, and deterministic barge-in |
| **External Distributed Vector DBs (Qdrant/Milvus/Weaviate)** | Cognition & Memory | **HOLD** | Premature operational overhead for single-streamer SQLite workload |

---

## 2. Detailed Radar Entries

> Every entry below includes all seven required evaluation dimensions: **Problem Statement, Expected Benefit, Technical Justification, Complexity Cost, Maintenance Burden, Compatibility Analysis, and Alternative Solutions**.

---

### 2.1 ADOPT — In-Memory Audio Pipeline & Persistent `aiohttp` Session Pooling

- **Problem Statement:** `EdgeTTSProvider.synthesize()` writes `edge_tts_*.mp3` to disk, reads it back, and deletes it; `TTSEngine.speak_stream()` then writes `speech_*.mp3` to disk and reads it back again (`[AUDIO-HIGH-004]`, `[PERF-MED-002]`) even when `output_mode == "browser"`. Simultaneously, `KokoroTTSProvider`, `ElevenLabsTTSProvider`, `CustomNeuralTTSProvider`, `RVCVoiceConverter`, `STTEngine`, and `EmbeddingEngine` (`[COG-MED-003]`, `[PERF-MED-001]`) create and close a new `aiohttp.ClientSession` per request.
- **Expected Benefit:** Eliminates 2 redundant disk roundtrips per sentence (~5–25ms I/O + filesystem churn) and removes 50–150ms TCP+TLS handshake overhead per cloud TTS/STT/embedding call, improving Time-to-First-Audio (TTFA) and multi-hour soak stability.
- **Technical Justification:** `edge_tts.Communicate.stream()` already yields audio chunks in memory; `aiohttp.ClientSession` is designed to be long-lived per event loop with connection pooling (`TCPConnector`). Offloading remaining server-mode `pygame` file writes to `asyncio.to_thread` eliminates event-loop blocking (`[AUDIO-MED-003]`).
- **Complexity Cost:** Low. Refactoring `core/tts_providers.py`, `core/tts.py`, `core/stt.py`, and `core/memory/embedding.py` to accept/manage a shared `aiohttp.ClientSession` with clean `shutdown()` closure.
- **Maintenance Burden:** Low. Standard Python `asyncio`/`aiohttp` lifecycle pattern; no new dependencies.
- **Compatibility Analysis:** 100% compatible with Python 3.11+ `asyncio`, `FastAPI` lifespan, `edge-tts>=6.1.9`, and existing `output_mode` (`"server"`, `"browser"`, `"both"`).
- **Alternative Solutions:** (1) RAM-disk (`tmpfs`) mount — OS-specific and fails on Windows; (2) `httpx.AsyncClient` migration — unnecessary dependency churn when `aiohttp>=3.9.0` is already in `pyproject.toml`.

---

### 2.2 ADOPT — Server-Side PCM/RMS Envelope Lip-Sync & Browser Sync Arbitration

- **Problem Statement:** `TTSEngine._play_and_lipsync()` and `Singer.sing()` emit a synthetic 80ms square wave (`0.95`/`0.50` and `0.70`/`0.20`), causing VTS Live2D mouths to flap after short sentences end and collide with browser `AnalyserNode` RMS in `output_mode="both"` (`[AUDIO-CRIT-002]`). Non-streaming callers also wrap `on_mouth_update` in unawaited `asyncio.create_task` lambdas (`[AUDIO-MED-001]`).
- **Expected Benefit:** True syllable-aligned mouth movement for VTube Studio (`VTSClient`), elimination of post-utterance flapping, and jitter-free 2D/Three-VRM lip-sync in `output_mode="both"`.
- **Technical Justification:** `numpy>=1.26.0` is already a core dependency. Extracting a 20–30ms RMS amplitude envelope from decoded PCM frames (or pre-computing envelope frames alongside `audio_chunk` emission) takes <1ms per sentence. On the browser (`web/app.js`, `web/overlay.js`), ignoring `avatar_state.mouth_open` while `isPlayingAudioQueue === true` cleanly arbitrates ownership.
- **Complexity Cost:** Low-to-Medium. Requires WAV/MP3-to-PCM RMS envelope extraction (using `miniaudio` or `pydub`/`ffmpeg` or WAV header parsing for Kokoro) and passing `async def` callbacks directly instead of `create_task` lambdas.
- **Maintenance Burden:** Low. Self-contained in `core/tts.py`, `core/singer.py`, `web/app.js`, and `web/overlay.js`.
- **Compatibility Analysis:** Compatible with `VTSClient` (`InjectParameterDataRequest`), `web/overlay.js` (2D Canvas & `@pixiv/three-vrm`), and `TTSEngine.speak_stream()`.
- **Alternative Solutions:** (1) Phoneme/viseme alignment via Rhubarb Lip Sync or MFA — high CPU/latency overhead (200–500ms) incompatible with streaming `SentenceChunker`; (2) Browser-only lip-sync — leaves `VTSClient` (which runs server-side) without envelope data.

---

### 2.3 ADOPT — Token-Budgeted Prompt Assembly (`ContextBudgetManager`)

- **Problem Statement:** `ConversationEngine` and `MasterPromptBuilder` unconditionally concatenate character bio, full `character.lore` JSON, 10 Conversational Pillars, `rolling_summary`, `memory_recall_block`, `chat_digest`, `social_context`, and 11 subsystem directives plus 16 raw turns (`[COG-HIGH-002]`). Additionally, `is_creator` is dropped on live LLM paths (`[COG-HIGH-003]`), `MoodEngine.get_temperature_modifier()` is dead code (`[COG-MED-004]`), and `max_tokens` defaults diverge (`150` OpenAI vs `800` Gemini).
- **Expected Benefit:** Prevents context overflow on 4K–8K local Ollama models, reduces cloud LLM input token cost by 30–55%, lowers TTFT (Time-to-First-Token), and enforces consistent `is_creator` authority and mood-modulated sampling.
- **Technical Justification:** Priority-tiered prompt assembly (Tier 0: Identity + `[CREATOR VERIFIED]` + Safety; Tier 1: Active Turn + Relevant Directives; Tier 2: Episodic Memory + Rolling Summary; Tier 3: Idle/Background Directives pruned when inactive) with fast `len(text) // 4` (or optional `tiktoken`) estimation requires zero external services and deterministic <1ms execution.
- **Complexity Cost:** Low-to-Medium. Centralized in `core/conversation/engine.py`, `core/conversation/prompts.py`, and `core/brain.py`.
- **Maintenance Burden:** Low. Pure Python logic; easily unit-tested with deterministic token-ceiling assertions.
- **Compatibility Analysis:** Works identically across Gemini, OpenAI, Ollama, and Mock providers; harmonizes `max_tokens` configuration in `config/settings.json`.
- **Alternative Solutions:** (1) LangChain/LlamaIndex prompt templates — adds heavy dependency bloat and obscures MaybeAI's custom 11-subsystem state; (2) Fixed character-count truncation — risks cutting mid-JSON or dropping safety/creator directives.

---

### 2.4 ADOPT — Bounded HTN / State-Machine Mission Loop & Telemetry ACK

- **Problem Statement:** Replanned goals never reach `COMPLETED` because `REPLANNED` subtasks remain in the denominator (`[COG-CRIT-001]`); failed subtasks loop infinitely every 25s growing `goals.json`/`agenda.md` (`[COG-CRIT-002]`); Minecraft tasks check inventory 0ms after `toggle_wander()` (`[COG-HIGH-001]`) or fabricate progress when disconnected; and `MinecraftController` lacks Node.js crash recovery (`[GAME-CRIT-002]`).
- **Expected Benefit:** Eliminates infinite replanning loops, prevents false "simulated" mission completions, and restores reliable autonomous Minecraft/Chess/Performance execution.
- **Technical Justification:** A bounded finite-state-machine / HTN-lite supervisor (`MAX_REPLAN_ATTEMPTS = 3`, `REPLANNED` excluded from progress denominator, explicit `simulated` vs `verified_execution` mode, and cross-tick `baseline_count` delta evaluation via `mc_telemetry` events) directly fixes the root causes without over-engineering a full PDDL planner.
- **Complexity Cost:** Medium. Touches `core/planning/models.py`, `core/planning/executor.py`, `core/planning/replanner.py`, `core/minecraft/controller.py`, and `minecraft/bot.js`.
- **Maintenance Burden:** Low. Deterministic state transitions are straightforward to test in `tests/test_planning.py` (which already exists).
- **Compatibility Analysis:** Preserves `GoalEngine`, `StrategyReplanner`, `AutonomousMissionExecutor`, and `mc_telemetry` WebSocket protocol.
- **Alternative Solutions:** (1) LLM-based ReAct agent loop per 25s tick — high token cost, non-deterministic, and slow; (2) Full PDDL/BehaviorTree framework (`py_trees`) — unnecessary abstraction for 5-step hierarchical goals.

---

### 2.5 TRIAL — Silero-VAD (ONNX) + Non-Blocking `faster-whisper` Worker

- **Problem Statement:** `EnergyVAD` uses a static RMS threshold (`0.02`) vulnerable to keyboard/BGM/fan noise (`[AUDIO-LOW-001]`), `transcribe_wav_bytes()` blocks the `/ws` receive loop (`[AUDIO-HIGH-001]`), and `stt_partial` only emits `"Listening..."`.
- **Expected Benefit:** Accurate speech-vs-noise discrimination (reducing false barge-ins), non-blocking `/ws` receive loop during STT, and optional sliding-window partial transcripts.
- **Technical Justification:** `silero-vad` (ONNX, ~2MB model, <1ms per 32ms 512-sample frame on CPU) matches MaybeAI's exact `AudioWorklet` frame size (`512 samples @ 16kHz`). Offloading `faster-whisper` (CTranslate2 INT8) to a dedicated `asyncio.to_thread` / worker queue decouples transcription latency (150–600ms) from WebSocket frame ingestion.
- **Complexity Cost:** Medium. Requires ONNX Runtime (`onnxruntime`) or `silero-vad` package, per-session transcription ordering queue, and `EXP-001` benchmarking.
- **Maintenance Burden:** Low-to-Medium. `silero-vad` and `faster-whisper` are stable; must maintain `EnergyVAD` + `STTEngine` mock fallback when optional extras are absent.
- **Compatibility Analysis:** Fits `core/stt.py` (`StreamingSTTSession`) and `web/audio-worklet-processor.js` (512-sample @ 16kHz PCM) with zero frontend protocol changes.
- **Alternative Solutions:** (1) `webrtcvad` — unmaintained C extension with Windows build issues and poorer music/noise rejection; (2) Browser-only `SpeechRecognition` — Chrome-only, cloud-dependent, no offline/LAN support.

---

### 2.6 TRIAL — Kokoro-82M (`kokoro-onnx`) as Primary Local Low-Latency TTS

- **Problem Statement:** Default `edge-tts` requires internet access, incurs 300–900ms cloud round-trip latency per sentence, and fails offline. Meanwhile, `TTSEngine` fallback to `EdgeTTSProvider` breaks when `self.voice` is a Kokoro voice ID (`[AUDIO-HIGH-003]`), and `kokoro-onnx` is listed in `pyproject.toml` (`tts-local`) but not yet benchmarked for streaming TTFA.
- **Expected Benefit:** Sub-200ms local CPU/GPU Time-to-First-Audio, zero per-character API cost, full offline/LAN operation, and native WAV PCM output (simplifying RMS lip-sync envelope extraction).
- **Technical Justification:** Kokoro-82M (`kokoro-onnx>=0.4.0`, Apache-2.0) is ~82M parameters (~300MB ONNX), runs at >5x real-time on modern CPUs and >30x on consumer GPUs (~0.5–1.0GB VRAM), and outputs 24kHz PCM/WAV directly in memory.
- **Complexity Cost:** Medium. Requires fixing `[AUDIO-HIGH-003]` (dedicated `fallback_voice`, dynamic `audio/wav` vs `audio/mpeg` MIME detection), routing `Singer` through `create_tts_provider()`, and validating Indonesian/English voice quality.
- **Maintenance Burden:** Low-to-Medium. Model weights are static; `kokoro-onnx` already has scaffolding in `core/tts_providers.py`.
- **Compatibility Analysis:** Existing `KokoroTTSProvider` in `core/tts_providers.py` supports both local `kokoro_onnx` and HTTP mode; requires `EXP-001` latency/quality gate.
- **Alternative Solutions:** (1) Piper TTS — faster on ultra-low-end CPUs (Raspberry Pi) but noticeably more robotic prosody; (2) `edge-tts` only — zero local footprint but internet-dependent and higher jitter.

---

### 2.7 TRIAL — `sqlite-vec` + Hybrid BM25 (FTS5) / Vector RRF Retrieval

- **Problem Statement:** `MemoryDatabase.vector_search()` fetches only `limit=300` recent rows (`[COG-HIGH-005]`), synchronously/sequentially re-encodes mismatched dimensions (up to 300 REST calls on a chat turn) and can overwrite 768-d/1536-d vectors with 128-d hash fallbacks. `EpisodicMemoryStore` also instantiates `EmbeddingEngine` twice (`[COG-HIGH-004]`), and `MemoryRetriever.arecall()` runs blocking SQLite on the event loop (`[COG-MED-003]`).
- **Expected Benefit:** Unbounded episodic recall beyond 300 rows with <10ms query latency for 10K–100K memories, higher retrieval precision via Reciprocal Rank Fusion (RRF) of FTS5 BM25 + dense cosine, and safe schema-versioned embeddings.
- **Technical Justification:** `sqlite-vec` is a zero-server C extension for SQLite (single-file DB preserved), while `hnswlib` provides an in-memory ANN index fallback if `sqlite-vec` wheel availability is constrained on Windows. Combining existing SQLite FTS5 (`[COG-HIGH-005]` baseline) with vector top-K via RRF (`1/(k + rank)`) eliminates single-signal recall blind spots.
- **Complexity Cost:** Medium. Requires `embedding_backend`/`embedding_dim` columns in `episodic_memories`, background batch re-indexing, `asyncio.to_thread` wrapping, and `EXP-002` recall/latency benchmarking.
- **Maintenance Burden:** Low. Preserves SQLite single-file backup/portability (`data/second_brain/`).
- **Compatibility Analysis:** Drop-in evolution of `core/memory/database.py` and `core/memory/retriever.py`; preserves Karpathy Markdown sync.
- **Alternative Solutions:** (1) Pure NumPy matrix scan over all rows — viable up to ~10K rows (~5–15ms) if RAM-cached, good fallback if `sqlite-vec` binary fails; (2) External Qdrant/Chroma server — rejected for single-node complexity (see `HOLD`).

---

### 2.8 TRIAL — Audio-Clock-Locked Karaoke Pre-Synthesis

- **Problem Statement:** `Singer.sing()` starts `pygame.mixer.music.play()` and then awaits `edge_tts` + RVC per lyric line inside the playback loop (`[GAME-HIGH-005]`), causing 300–1500ms of cumulative drift per line. It also bypasses `TTSEngine` providers (`[AUDIO-HIGH-003]`) and ignores `barge_in()` (`[AUDIO-HIGH-002]`).
- **Expected Benefit:** <50ms lyric-to-BGM synchronization across full 3-minute songs, clean barge-in cancellation, and support for Kokoro/custom TTS providers.
- **Technical Justification:** Pre-synthesizing upcoming lyric lines (bounded lookahead buffer of 2–3 lines or full song pre-cache) before `pygame.mixer.music.play()`, and scheduling line playback against `pygame.mixer.music.get_pos()` (or browser `AudioContext.currentTime`), removes network/synthesis jitter from the real-time music clock.
- **Complexity Cost:** Medium. Requires refactoring `core/singer.py` into a pre-synthesis queue + clock-aligned scheduler and wiring `self.singer.stop()` into `Orchestrator.barge_in()`.
- **Maintenance Burden:** Low. Contained within `core/singer.py` and `core/orchestrator.py`.
- **Compatibility Analysis:** Compatible with `PerformanceDirector` choreography cues and `karaoke.bgm_volume` / `karaoke.vocal_volume` settings.
- **Alternative Solutions:** (1) Pre-render entire vocal track into a single WAV mixed offline — loses per-line dynamic mouth/choreography events and slows start-of-song latency.

---

### 2.9 ASSESS — Local VLM Vision (Ollama Vision / Qwen2.5-VL) + Rate-Limited VLM

- **Problem Statement:** `VisualAnalyzer.analyze_frame()` currently crashes with `TypeError` when Pillow is missing (`[GAME-HIGH-001]`), `aperceive_with_vlm()` broadcasts before VLM enrichment under `self._lock` (`[GAME-MED-002]`), and cloud VLM calls (Gemini/OpenAI) incur ongoing API cost and latency.
- **Expected Benefit:** Enables privacy-preserving, zero-API-cost screen understanding (games, desktop, chat overlays) on workstations with spare VRAM (e.g., 4–8GB).
- **Technical Justification:** `Ollama` already exists in MaybeAI's LLM stack (`core/brain.py`). Supporting local vision models (`qwen2.5vl:3b` / `llama3.2-vision`) via the same `http://localhost:11434` endpoint requires minimal new protocol code once `[GAME-HIGH-001]` and `[GAME-MED-002]` are fixed.
- **Complexity Cost:** Medium. VRAM contention with local STT/TTS/LLM must be profiled carefully on single-GPU creator rigs.
- **Maintenance Burden:** Low-to-Medium. Reuses Ollama HTTP/NDJSON conventions.
- **Compatibility Analysis:** Fits `core/vision/vlm.py` (`MultimodalVisionModel`); must remain optional (`vision.vlm_enabled: false` default).
- **Alternative Solutions:** (1) Cloud-only Gemini Flash Vision — lower local VRAM pressure, better for 8GB-VRAM creator PCs, but requires API key and internet.

---

### 2.10 ASSESS — GPT-SoVITS / Fish Speech + RVC v2 Zero-Disk Streaming

- **Problem Statement:** `CustomNeuralTTSProvider` and `RVCVoiceConverter` exist in `core/tts_providers.py`, but use unpooled `aiohttp.ClientSession` per sentence and hardcode `filename="input.mp3"` / `content_type="audio/mpeg"` (`[AUDIO-HIGH-003]`, `[AUDIO-HIGH-004]`).
- **Expected Benefit:** High-expressiveness custom character voice cloning and singing/speaking timbre consistency.
- **Technical Justification:** Both GPT-SoVITS and Fish Speech expose local HTTP streaming/WAV endpoints, and RVC v2 can run as a local sidecar on a second GPU or high-VRAM card (12GB+ VRAM total when paired with VTS/OBS/game).
- **Complexity Cost:** High (VRAM/deployment). External Python environments and 2–6GB VRAM per model make this unsuitable as a default, but valuable as an optional sidecar for dedicated dual-PC or high-end GPU setups.
- **Maintenance Burden:** Medium. External sidecar APIs evolve frequently; MaybeAI should only maintain a clean HTTP client contract.
- **Compatibility Analysis:** Already scaffolded in `core/tts_providers.py` (`CustomNeuralTTSProvider`, `RVCVoiceConverter`).
- **Alternative Solutions:** (1) Kokoro-82M (`TRIAL`) for fast local voice; (2) ElevenLabs streaming API for zero local VRAM when cloud budget is acceptable.

---

### 2.11 ASSESS — Binary WebSocket Audio Frames + Opus/PCM Streaming

- **Problem Statement:** Browser mic (`web/audio-worklet-processor.js`) and server TTS (`audio_chunk`) currently base64-encode audio inside JSON WebSocket messages (`run.py:1534`, `core/orchestrator.py:301`), inflating payload size by ~33% and adding JSON parse/stringify overhead on the event loop.
- **Expected Benefit:** ~33% bandwidth reduction on `/ws`, lower GC pressure in browser and Python, and cleaner framing for timestamped lip-sync envelopes.
- **Technical Justification:** FastAPI/Starlette WebSockets natively support `send_bytes()` / `receive_bytes()`. A simple 8-byte binary header (frame type + timestamp/utterance ID) avoids JSON overhead for high-frequency 32ms mic frames and TTS chunks.
- **Complexity Cost:** Medium. Requires updating both `run.py` WS handler and `web/app.js` / `web/deck.js` / `web/overlay.js` binary frame decoders, plus fixing `[PERF-HIGH-001]` (per-WS bounded queues) first.
- **Maintenance Burden:** Low once stabilized.
- **Compatibility Analysis:** Must preserve JSON control messages (`barge_in`, `avatar_state`, `ai_chunk`) on the same `/ws` connection.
- **Alternative Solutions:** (1) Keep JSON+base64 — acceptable for localhost, only problematic over constrained LAN/remote Creator Studio connections.

---

### 2.12 ASSESS — Local Bundled Three-VRM + WebGL2 Avatar Pipeline

- **Problem Statement:** `web/overlay.js` loads Three.js, `@pixiv/three-vrm`, and Google Fonts from external CDNs (`[UI-MED-004]`), breaking offline/LAN streams and introducing supply-chain/availability risk during live broadcasts.
- **Expected Benefit:** 100% offline/LAN-resilient 3D VRM avatar rendering inside OBS Browser Source and Creator Studio.
- **Technical Justification:** Bundling pinned, local vendor ES modules (`web/vendor/`) eliminates CDN failures, version drift, and CSP violations.
- **Complexity Cost:** Low-to-Medium. One-time vendor asset bundling + CSP header alignment.
- **Maintenance Burden:** Low. Periodic manual version bumps only when needed.
- **Compatibility Analysis:** Directly compatible with `web/overlay.js` and `avatar.renderer = "vrm"`.
- **Alternative Solutions:** (1) VTube Studio (`VTSClient`) for 2D Live2D — already primary for Live2D users, but Three-VRM is essential for 3D VRM creators without VTS.

---

### 2.13 HOLD — End-to-End Speech-to-Speech Models (Realtime Audio APIs)

- **Problem Statement:** Monolithic speech-to-speech APIs promise ultra-low-latency voice conversation by bypassing separate STT -> LLM -> TTS stages.
- **Expected Benefit:** ~200–350ms raw conversational turn latency in simple voice-only chatbots.
- **Technical Justification (Why HOLD):** Bypassing text-level LLM streaming breaks MaybeAI's core architecture: (1) `Moderator` prompt-injection and strict-mode chat filtering (`[SEC-HIGH-004]`), (2) `SentenceChunker` + RVC / Kokoro / character voice identity, (3) `Second Brain` memory extraction and `MoodEngine` / `GoalEngine` state updates, (4) Minecraft/Discord/OBS text-driven tool dispatch, and (5) deterministic `barge_in()` cancellation (`[AUDIO-CRIT-001]`). It also locks the creator into high per-minute cloud audio pricing with zero offline fallback.
- **Complexity Cost:** High (requires parallel shadow-text pipeline to retain memory/moderation).
- **Maintenance Burden:** High (vendor lock-in to proprietary WebRTC/WebSocket audio protocols).
- **Compatibility Analysis:** Incompatible with `core/tts_providers.py`, `core/stt.py`, `core/brain.py`, and `core/conversation/engine.py`.
- **Alternative Solutions:** Optimize the existing modular pipeline via `EXP-001` (Silero-VAD + non-blocking `faster-whisper` + Kokoro-82M + in-memory `aiohttp` pooling), which achieves ~400–700ms TTFA while preserving full control, RVC, moderation, and offline support.

---

### 2.14 HOLD — External Distributed Vector DBs (Qdrant / Milvus / Weaviate)

- **Problem Statement:** Scaling semantic memory beyond the current 300-row cap (`[COG-HIGH-005]`).
- **Expected Benefit:** Multi-million vector ANN search and distributed horizontal scaling.
- **Technical Justification (Why HOLD):** A single AI VTuber's episodic memory grows at ~50–500 rows per stream (~10K–100K rows/year). Running an external vector database container/cluster adds memory overhead (500MB–2GB RAM), network serialization latency, backup split-brain between SQLite (`user_profiles`, `promises_challenges`) and the external DB, and deployment friction for local Windows creators.
- **Complexity Cost:** High (Docker/service orchestration, dual-write consistency).
- **Maintenance Burden:** High.
- **Compatibility Analysis:** Breaks single-file `data/second_brain/` portability.
- **Alternative Solutions:** `sqlite-vec` or in-process `hnswlib` + FTS5 hybrid RRF (`EXP-002`), which handles 100K+ vectors in <10ms inside the existing SQLite database.
