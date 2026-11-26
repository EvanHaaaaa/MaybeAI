# MaybeAI — Detailed Technical Evaluation Matrix (`research/technology_radar.md`)

**Owner:** AGENT 10 — Future AI & Research Architect (`strat-ai`)  
**Grounding Baseline:** `audit/FINAL_AUDIT_REPORT.md`, `audit/02_realtime_audio.md`, `audit/03_cognitive_architecture.md`, `audit/05_game_engines.md`, `audit/11_performance_analysis.md`, `pyproject.toml`, `config/settings.json`

---

## 1. Quantitative & Operational Evaluation Matrix

| Technology / Component | Ring | Latency Impact | VRAM / CPU Footprint | License | Offline / LAN | Integration Impact on MaybeAI Modules |
|---|---|---|---|---|---|---|
| **In-Memory Audio + Persistent `aiohttp` Pool** | **ADOPT** | `-55 to -175 ms` per sentence (eliminates 2 disk writes + TLS handshake) | Negligible (`<5 MB` RAM; `-1` thread/disk I/O spike) | MIT / Apache-2.0 (`aiohttp`, `edge-tts`) | **Yes** (LAN/Local) | `core/tts.py`, `core/tts_providers.py`, `core/stt.py`, `core/memory/embedding.py` (`[AUDIO-HIGH-004]`, `[COG-MED-003]`, `[PERF-MED-001/002]`) |
| **PCM/RMS Envelope Lip-Sync + Browser Arbitration** | **ADOPT** | `<1 ms` envelope compute; removes `80 ms` square-wave jitter & post-speech flap | Negligible (`numpy` CPU only) | BSD (`numpy`) | **Yes** (100% local) | `core/tts.py`, `core/singer.py`, `core/orchestrator.py`, `web/app.js`, `web/overlay.js` (`[AUDIO-CRIT-002]`, `[AUDIO-MED-001]`) |
| **`ContextBudgetManager` (Token-Budgeted Prompts)** | **ADOPT** | `<1 ms` assembly; `-20% to -50%` LLM TTFT on pruned turns | `0` GPU; `-30% to -55%` LLM KV-cache / token usage | Internal (pure Python; optional MIT `tiktoken`) | **Yes** (100% local) | `core/conversation/engine.py`, `core/conversation/prompts.py`, `core/brain.py` (`[COG-HIGH-002]`, `[COG-HIGH-003]`, `[COG-MED-004]`) |
| **Bounded HTN / FSM Mission Loop + MC Telemetry ACK** | **ADOPT** | Eliminates `0 ms` false-fail loop & `25 s` replan spam | Negligible (`<1%` CPU) | Internal (Python + Node.js) | **Yes** (local/LAN MC) | `core/planning/models.py`, `core/planning/executor.py`, `core/planning/replanner.py`, `core/minecraft/controller.py`, `minecraft/bot.js` (`[COG-CRIT-001/002]`, `[COG-HIGH-001]`, `[GAME-CRIT-002]`) |
| **Silero-VAD (ONNX)** | **TRIAL** | `<1 ms` per `32 ms` (512-sample @ 16 kHz) frame | `~2 MB` disk, `<2%` 1 CPU core, `0` VRAM | MIT | **Yes** (100% local) | `core/stt.py` (`EnergyVAD` replacement/option); `core/orchestrator.py` (`[AUDIO-LOW-001]`) |
| **Non-Blocking `faster-whisper` (INT8 CTranslate2)** | **TRIAL** | `150–600 ms` utterance STT (non-blocking `/ws` via worker queue) | `tiny/base`: `~150–300 MB` RAM (CPU) or `~0.5–1.0 GB` VRAM (CUDA); `small`: `~1.5 GB` VRAM | MIT | **Yes** (100% local) | `core/stt.py`, `core/orchestrator.py`, `run.py` (`[AUDIO-HIGH-001]`) |
| **Kokoro-82M (`kokoro-onnx`)** | **TRIAL** | `80–220 ms` TTFA on CPU; `30–90 ms` TTFA on GPU | `~320 MB` ONNX; `~0.6–1.0 GB` VRAM (or 2–4 CPU threads) | Apache-2.0 | **Yes** (100% local) | `core/tts_providers.py`, `core/tts.py`, `core/singer.py` (`[AUDIO-HIGH-003]`, `[AUDIO-HIGH-004]`) |
| **`sqlite-vec` + FTS5 Hybrid RRF** | **TRIAL** | `2–12 ms` top-K over `10K–100K` memories (replaces `300`-row cap) | `<50 MB` RAM; `0` VRAM | MIT / Apache-2.0 | **Yes** (100% local) | `core/memory/database.py`, `core/memory/retriever.py`, `core/memory/__init__.py` (`[COG-HIGH-004/005]`, `[COG-MED-003]`) |
| **FastEmbed (`BAAI/bge-small-en-v1.5` / multilingual)** | **TRIAL** | `5–18 ms` per query embedding on CPU (ONNX) | `~130 MB` RAM (CPU ONNX), `0` VRAM | Apache-2.0 | **Yes** (100% local) | `core/memory/embedding.py` (single shared instance via `EpisodicMemoryStore`, `[COG-HIGH-004]`) |
| **Audio-Clock-Locked Karaoke Pre-Synthesis** | **TRIAL** | `<50 ms` lyric-to-BGM drift (eliminates `300–1500 ms`/line drift) | `+20–50 MB` RAM for 2–3 pre-synthesized WAV buffers | Internal | **Yes** | `core/singer.py`, `core/orchestrator.py` (`[GAME-HIGH-005]`, `[AUDIO-HIGH-002]`) |
| **Local VLM (`qwen2.5vl:3b` via Ollama)** | **ASSESS** | `600–2500 ms` per frame (async `10 s` interval) | `3–4.5 GB` VRAM (or high CPU RAM) | Apache-2.0 / Qwen | **Yes** (local Ollama) | `core/vision/vlm.py`, `core/vision/engine.py`, `core/vision/analyzer.py` (`[GAME-HIGH-001]`, `[GAME-MED-002]`) |
| **GPT-SoVITS / Fish Speech + RVC v2** | **ASSESS** | `250–900 ms` TTS + `100–300 ms` RVC | `2–6 GB` VRAM (GPU strongly recommended) | MIT / Apache-2.0 | **Yes** (local sidecar) | `core/tts_providers.py` (`CustomNeuralTTSProvider`, `RVCVoiceConverter`, `[AUDIO-HIGH-003]`) |
| **Binary WebSocket Audio Frames** | **ASSESS** | `-1 to -4 ms` encode/decode + `-33%` payload bytes | Lower JS/Python GC pressure | Standard WebSocket | **Yes** | `run.py`, `core/orchestrator.py`, `web/app.js`, `web/deck.js`, `web/overlay.js` |
| **Local Bundled Three-VRM (`@pixiv/three-vrm`)** | **ASSESS** | `0 ms` external network dependency on OBS scene load | Browser WebGL2 GPU (`~100–250 MB` GPU mem) | MIT | **Yes** (offline/LAN) | `web/overlay.js`, `web/index.html`, `web/vendor/` (`[UI-MED-004]`) |
| **End-to-End Speech-to-Speech APIs** | **HOLD** | `200–350 ms` raw audio, but breaks pipeline | Cloud-only | Proprietary | **No** (cloud-locked) | Breaks `core/brain.py`, `core/tts.py`, `core/conversation/`, `Moderator` |
| **External Vector DBs (Qdrant / Milvus)** | **HOLD** | `5–20 ms` + IPC/HTTP overhead | `500 MB–2 GB` RAM container | Apache-2.0 | **LAN/Docker only** | Unnecessary split from `data/second_brain/` SQLite |

---

## 2. Hardware & Deployment Profile Compatibility

MaybeAI targets three realistic creator deployment profiles. Technologies in **TRIAL** and **ASSESS** must be gated against these resource envelopes:

| Profile | Typical Hardware | Concurrent Stack Budget | Recommended Radar Configuration |
|---|---|---|---|
| **Profile A: Cloud-Assisted Creator (CPU-Only Local)** | 8-core CPU, 16 GB RAM, integrated/low-VRAM GPU (gaming on same PC) | `<2 GB` RAM for MaybeAI; `0 GB` VRAM reserved | `ADOPT` baseline + `Silero-VAD` (CPU) + `Edge-TTS` or `Kokoro-82M` (CPU) + Gemini/OpenAI LLM + `sqlite-vec` + `FastEmbed` (CPU ONNX). |
| **Profile B: Balanced Single-GPU VTuber Rig** | 8–12 core CPU, 32 GB RAM, 8–12 GB VRAM GPU (running OBS + VTS + Minecraft) | `<=2.5 GB` VRAM for MaybeAI | Profile A + `faster-whisper` (`base` INT8 CUDA, ~0.6 GB) + `Kokoro-82M` (GPU, ~0.8 GB); avoid heavy local 7B+ LLMs + RVC simultaneously while gaming. |
| **Profile C: Dedicated AI / Dual-PC Streamer** | 12+ GB VRAM dedicated GPU (or 24 GB) | `6–14 GB` VRAM for MaybeAI | Profile B + local Ollama LLM (`llama3.2` / `qwen2.5`) + `GPT-SoVITS` / `RVC v2` + local Ollama VLM (`qwen2.5vl:3b`). |

---

## 3. Module-Level Integration Impact Map

| Current Module | Audit Findings Addressed | Planned Technical Change | Risk / Regression Guard |
|---|---|---|---|
| `core/tts.py` & `core/tts_providers.py` | `[AUDIO-CRIT-001/002]`, `[AUDIO-HIGH-003/004]`, `[PERF-MED-002]` | Re-raise `CancelledError` on barge-in; in-memory `BytesIO` streaming; shared `aiohttp.ClientSession`; dedicated `fallback_voice`; dynamic WAV/MP3 MIME; PCM/RMS envelope extraction. | Verify Chaos Scenario B (`0` temp files, `mouth=0.0`, no post-barge-in broadcasts). |
| `core/stt.py` | `[AUDIO-HIGH-001]`, `[AUDIO-LOW-001]` | Decouple `transcribe_wav_bytes()` from WS receive loop via async worker queue; benchmark `Silero-VAD` vs `EnergyVAD` in `EXP-001`. | Preserve `EnergyVAD` + `[STT Mock]` fallback when `onnxruntime` / `faster-whisper` absent. |
| `core/singer.py` | `[AUDIO-HIGH-002/003]`, `[AUDIO-MED-003]`, `[GAME-HIGH-005]` | Route through `create_tts_provider()`; wire `singer.stop()` to `barge_in()`; offload `pygame.mixer` to `asyncio.to_thread`; pre-synthesize lyrics + clock-lock (`EXP-001` / Horizon 1). | Guard `if self.is_singing:` with lock; support `SDL_AUDIODRIVER=dummy` in headless CI/Docker. |
| `core/memory/*` | `[COG-HIGH-004/005]`, `[COG-MED-003]` | Share single `EmbeddingEngine` instance; add `embedding_backend`/`embedding_dim` columns; prevent `hash` overwrite of cloud vectors; benchmark `sqlite-vec` + FTS5 RRF in `EXP-002`. | Preserve `data/second_brain/*.md` sync and zero-dependency SQLite fallback. |
| `core/conversation/*` & `core/brain.py` | `[COG-HIGH-002/003]`, `[COG-MED-002/004]` | Implement `ContextBudgetManager` in `EXP-002`; plumb `is_creator` to `abuild_system_prompt()` and all fallbacks; wire `MoodEngine.get_temperature_modifier()`; gate Gemini `thinkingConfig`. | Enforce deterministic unit tests for token ceiling and `[CREATOR VERIFIED]` injection. |
| `core/planning/*` & `core/minecraft/controller.py` | `[COG-CRIT-001/002]`, `[COG-HIGH-001]`, `[GAME-CRIT-002]` | Exclude `REPLANNED` from `Goal.recalculate_progress()`; enforce `MAX_REPLAN_ATTEMPTS`; cross-tick `mc_telemetry` ACK (`EXP-003`); Node.js bridge supervisor + timer cleanup. | Separate `simulated` commentary mode from `verified_execution` mode. |
| `web/app.js` & `web/overlay.js` | `[AUDIO-CRIT-002]`, `[UI-MED-004]` | Arbitrate `targetMouthOpen` (ignore `avatar_state.mouth_open` when `isPlayingAudioQueue` active); bundle local Three-VRM assets. | Maintain `node --check web/*.js` clean pass. |
