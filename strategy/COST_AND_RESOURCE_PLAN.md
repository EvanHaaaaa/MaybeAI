# MaybeAI — Cost & Resource Plan (`strategy/COST_AND_RESOURCE_PLAN.md`)

**Owner:** AGENT 12 (`ng-strat-roadmap` — CTO Strategy & Roadmap Manager)  
**Baseline Grounding:** [12_performance_analysis.md](file:///d:/projects/MaybeAI/audit/12_performance_analysis.md), [04_cognitive_memory.md](file:///d:/projects/MaybeAI/audit/04_cognitive_memory.md), [COST_AND_INFRASTRUCTURE.md](file:///d:/projects/MaybeAI/strategy/COST_AND_INFRASTRUCTURE.md), [pyproject.toml](file:///d:/projects/MaybeAI/pyproject.toml), [Dockerfile](file:///d:/projects/MaybeAI/Dockerfile).

> [!IMPORTANT]
> **Measurement vs. Estimate Discipline:** All figures below explicitly distinguish **Measured** values (directly observed in `audit/12_performance_analysis.md` and `audit/04_cognitive_memory.md`) from **Estimated** planning ranges (hardware sizing, power draw, and cloud API spend).

---

## 1. Verified Measured Baselines (`HEAD` `96b7315`)

- **Moderation Latency (`Moderator.clean_text`):** **Measured** `0.006 ms/msg` (`3.19 ms` for 500 messages).
- **Vector Memory Recall (`MemoryDatabase.vector_search`):** **Measured** `13.54 ms` (N=100) to `45.32 ms` (N=2,000, `vector_scan_limit=2000`).
- **EventBus + WS Fan-Out (`_dispatch_to_web_listeners`):** **Measured** `0.074 ms` (10 clients), `0.262 ms` (100 clients), `2.159 ms` (500 clients) per broadcast; single stalled client caps at `2.0s` until `PH4-04` adds per-WS outbound queues.
- **Prompt Token Budget (`ContextBudgetManager`):** **Measured** caps of `1800` (OpenAI/Gemini/Mock) and `1600` (Ollama) via `(len(text)+3)//4` heuristic, with `max_tokens=800` output cap.
- **Test & Codebase Footprint:** **Measured** `97` `.py` files in `core/`, `19` frontend files + `5` vendored files in `web/vendor/`.

---

## 2. Deployment Profiles (Entry-Level, Recommended, Advanced)

### 2.1 Hardware, Resource & Latency Matrix

| Dimension | Entry-Level (Cloud-Backed Solo) | Recommended (Hybrid Creator PC) | Advanced (Sovereign Local / Split-Node H8) |
|---|---|---|---|
| **Target Persona** | Hobbyist streamer (laptop / mini-PC, Docker headless) | Full-time VTuber + Gaming (OBS, VTS, Minecraft, Karaoke) | 24/7 Autonomous Studio / Multi-Agent Collab + Local LLM |
| **CPU** *(Estimated)* | 4 vCPU / 4 cores (x86_64) | 8 cores / 16 threads (e.g., Ryzen 7 / i7) | 12–16+ cores (or Control Node 4 vCPU + GPU Worker) |
| **System RAM** *(Estimated)* | 8 GB RAM (`~180–350 MB` core RSS) | 16–32 GB RAM (`~1.2–2.5 GB` w/ local STT/TTS) | 32–64 GB RAM |
| **GPU / VRAM** *(Estimated)* | None / Integrated GPU | **8–12 GB VRAM** (e.g., RTX 3060 12GB / 4070) | **24 GB+ VRAM** (e.g., RTX 4090 / 3090 / A5000) |
| **Storage** *(Estimated)* | 20 GB SSD (OS + `data/memory.db` + logs) | 100 GB NVMe (`data/clips/`, Karaoke stems, models) | 500 GB+ NVMe (VODs, HNSW/ANN index, local weights) |
| **Network** *(Estimated)* | 10 Mbps up/down (Cloud LLM + EdgeTTS) | 25+ Mbps up/down (Stream + API + Collab) | 1 Gbps LAN (H8 split-node) + 50+ Mbps WAN |
| **Power Draw** *(Estimated)* | 15–45 W (Mini-PC / Laptop) | 220–380 W under stream + game load | 400–650 W under full local LLM + NVENC + TTS |
| **Voice Turn Latency** *(Estimated)* | `900–1,800 ms` (cloud STT/LLM/EdgeTTS) | `500–950 ms` (local `faster-whisper` + `kokoro` + cloud LLM) | `350–700 ms` (H5 clause TTS + LAN GPU Ollama/vLLM) |
| **API Cost** *(Estimated)* | **$3–$15 / mo** (Flash/Mini tier, 50 hrs/mo) | **$10–$45 / mo** (Hybrid: local audio + Flash/Frontier LLM) | **$0 / mo** variable API (100% local) or **$50–$200/mo** Frontier |

### 2.2 VRAM Allocation Breakdown (Estimated — Recommended & Advanced)

- **`faster-whisper` (`small`/`medium` INT8/FP16):** ~1.0–2.5 GB VRAM
- **`kokoro-onnx` / RVC Voice Converter:** ~0.8–2.0 GB VRAM
- **Local Embeddings (`fastembed` / `sentence-transformers`) + ANN (`H4-01`):** ~0.3–0.6 GB VRAM (or CPU)
- **`demucs` Karaoke Stem Separation (`YouTubeKaraokeProcessor`):** ~2.0–3.5 GB VRAM (transient during song prep)
- **Local LLM via Ollama (8B Q4_K_M / 14B–32B Q4_K_M):** ~5.5–18.0 GB VRAM (Advanced only)
- **Host Creator Apps (OBS + VTube Studio + Browser VRM + Minecraft):** ~2.5–4.0 GB VRAM

---

## 3. Cloud vs. Local vs. Hybrid Comparison

| Criterion | 100% Cloud | Hybrid (Recommended) | 100% Local (Sovereign) |
|---|---|---|---|
| **CapEx (Hardware)** *(Estimated)* | Low ($300–$600 mini-PC / VPS) | Medium ($1,000–$1,800 creator PC) | High ($2,200–$3,500+ 24GB VRAM rig) |
| **OpEx (Monthly API)** *(Estimated)* | High if using ElevenLabs + Frontier LLM ($60–$300+/mo at 130 hrs) | Low–Medium ($10–$45/mo: local STT/TTS + Flash/Mini LLM) | **$0 / mo** API (electricity only: ~$15–$40/mo at 24/7) |
| **Privacy & Air-Gap** | Low (audio/screen/chat leave host) | Medium (audio local; text/VLM to cloud) | **Maximum** (zero external network; `web/vendor/` offline) |
| **Reliability / Outage** | Vulnerable to ISP & API 429/500 | Resilient (`ProviderCircuitBreaker` + local Ollama fallback) | Immune to cloud outages; bound to local hardware |
| **Cognitive Quality (H4–H8)** | Highest (frontier reasoning & VLM) | High (frontier LLM + local low-latency audio) | Good (8B–32B open weights; slower VLM/consolidation) |

---

## 4. Horizon-by-Horizon Resource Impact (H4–H8 Estimates)

| Horizon | Key Resource Shift | Mitigation / Guardrail |
|---|---|---|
| **Pre-H4 (`PH4-04`, `PH4-06`)** | Per-WS `asyncio.Queue(maxsize=64)` + `RotatingFileHandler` | Bounded memory per client; capped log disk usage (`max-size`/`max-file`). |
| **H4 (`H4-01`, `H4-02`)** | ANN vector index (`sqlite-vec`/HNSW) + periodic consolidation LLM calls | Index ~50–150 MB RAM for 100k rows; consolidation runs off-peak during idle. |
| **H5 (`H5-03`, `H5-04`)** | Clause streaming TTS + adaptive VLM fusion | Adaptive VLM rate limiter cuts idle VLM calls by `>=60%`. |
| **H6 (`H6-01`, `H6-02`)** | N-peer Collab + signed plugin cgroup/JobObject caps | Per-plugin CPU/RAM limits prevent runaway third-party extensions. |
| **H7 (`H7-01`, `H7-04`)** | Captioned 9:16 `ffmpeg` batch renders + `data/telemetry.db` | Deferred post-stream rendering + NVENC offload + `clips.max_storage_gb` LRU quota. |
| **H8 (`H8-01`)** | Split-node Control Plane (`<250 MB` RAM) + remote GPU Worker | Enables Entry-Level laptop/VPS to drive Advanced GPU inference over LAN. |
