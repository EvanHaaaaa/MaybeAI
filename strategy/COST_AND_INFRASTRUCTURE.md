# MaybeAI — Compute, Cost & Infrastructure Model (`strategy/COST_AND_INFRASTRUCTURE.md`)

**Owner:** AGENT 12 (`strat-roadmap` — Strategic Development & Roadmap Manager)  
**Baseline Grounding:** [pyproject.toml](file:///d:/projects/MaybeAI/pyproject.toml), [Dockerfile](file:///d:/projects/MaybeAI/Dockerfile), [docker-compose.yml](file:///d:/projects/MaybeAI/docker-compose.yml), [audit/02_realtime_audio.md](file:///d:/projects/MaybeAI/audit/02_realtime_audio.md), [audit/03_cognitive_architecture.md](file:///d:/projects/MaybeAI/audit/03_cognitive_architecture.md), [audit/11_performance_analysis.md](file:///d:/projects/MaybeAI/audit/11_performance_analysis.md).

---

## 1. Deployment Hardware Profiles (Local vs. Cloud vs. Docker)

| Profile | Target Persona | CPU / RAM | GPU / VRAM | Local ML Stack (`pyproject.toml` extras) | External APIs Required |
|---|---|---|---|---|---|
| **Profile A: Cloud-Backed Minimal** | Solo Streamer (Laptop / Mini-PC) | 4 cores / 8 GB RAM | None (Integrated) | `edge-tts`, local hash embeddings (`<1ms`), `python-chess` | Gemini / OpenAI LLM + optional Whisper API |
| **Profile B: Hybrid Creator PC** | Technical Creator (Live VTuber + Games) | 8 cores / 16–32 GB RAM | **8–12 GB VRAM** (e.g., RTX 3060/4070) | `faster-whisper` (STT), `kokoro-onnx` / RVC (TTS), VTube Studio, OBS, Mineflayer (`node`) | Gemini / OpenAI LLM + VLM |
| **Profile C: Air-Gapped Sovereign** | Privacy / LAN-Only Creator | 12+ cores / 32–64 GB RAM | **16–24 GB VRAM** (e.g., RTX 4090 / A5000) | Ollama (7B–14B Q4/Q8), `faster-whisper`, `kokoro`/`GPT-SoVITS`, `fastembed`/`sentence-transformers`, vendored Three-VRM | **None** (100% offline LAN) |
| **Profile D: Docker Headless 24/7** | Always-On Collab / Bot Host | 4–8 vCPU / 8–16 GB RAM | Optional (CPU or GPU passthrough) | `python:3.12-slim` + `ffmpeg`, `MAYBEAI_HEADLESS=1`, `SDL_*=dummy` | Gemini / OpenAI or remote Ollama host |

### VRAM Budget Breakdown (Profile B & C)
- **Faster-Whisper (`small`/`medium` INT8/FP16):** ~1.0–2.5 GB VRAM
- **Kokoro-ONNX / Local TTS + RVC:** ~0.8–2.0 GB VRAM
- **Local Embeddings (`fastembed` / `sentence-transformers`):** ~0.3–0.6 GB VRAM (or CPU)
- **Ollama Local LLM (8B Q4_K_M / 14B Q4_K_M):** ~5.5–10.0 GB VRAM
- **OBS + VTube Studio + Minecraft + Browser VRM (on Creator Windows Host):** ~2.5–4.0 GB VRAM overhead
- **Total:** **~4.5–6.5 GB VRAM** (Profile B with Cloud LLM) | **~10–17 GB VRAM** (Profile C 100% Local).

---

## 2. LLM, VLM, STT & TTS Token / API Cost Modeling

### 2.1 Prompt Token Overhead (Impact of `[COG-HIGH-002]`)
In the current codebase (`core/conversation/prompts.py:22-170`, `core/conversation/engine.py:259-318`), `MasterPromptBuilder` concatenates character bio, full `character.lore` JSON, 10 Conversational Pillars, `rolling_summary`, `memory_recall_block`, `chat_digest`, `social_context`, **11 subsystem directives** (even when idle), and 16 turns of history unconditionally:
- **Current Unbounded Input:** **~3,500–6,000 input tokens/turn** (plus optional base64 vision frames).
- **Post-Horizon 1 (`ContextBudgetManager`):** Pruning idle directives and capping history dynamically reduces input to **~1,200–1,800 input tokens/turn** (**~60–70% token reduction**).
- **Output Tokens:** `Brain._build_openai_payload` currently caps at `150` tokens vs. `_build_gemini_payload` at `800` tokens (`[COG-HIGH-002]`); harmonized target for spoken VTuber turns is **~120–250 output tokens/turn**.

### 2.2 Operational Cost Scenarios (Illustrative Planning Ranges)
*Assumes active stream interaction rate of **120 LLM turns/hour** (1 turn every 30s, including chat replies, idle banter, and mission ticks) + **15 VLM screen-perception calls/hour** (4-min interval).*

| Usage Tier | Hours / Month | Total Turns / Month | Unbounded (`[COG-HIGH-002]`) Input Tokens | Budgeted (H1) Input Tokens | Estimated Cloud Cost Range (Low-Cost Tier e.g. Flash/Mini vs. Frontier Tier)* |
|---|---|---|---|---|---|
| **Hobbyist Streamer** (4h/day, 3 days/wk) | ~50 hrs | 6,000 turns | ~27M tokens | ~9M tokens | **$1–$5 / mo** (Flash/Mini) \| **$15–$45 / mo** (Frontier) |
| **Full-Time VTuber** (6h/day, 5 days/wk) | ~130 hrs | 15,600 turns | ~70M tokens | ~23M tokens | **$3–$12 / mo** (Flash/Mini) \| **$40–$120 / mo** (Frontier) |
| **24/7 Autonomous Channel** | 720 hrs | 86,400 turns | ~389M tokens | ~130M tokens | **$18–$65 / mo** (Flash/Mini) \| **$220–$650 / mo** (Frontier) |

*\*Note: Exact USD depends on chosen provider pricing (`gemini-2.5-flash` / `gpt-4o-mini` vs. flagship models) and whether ElevenLabs TTS (~$0.15–$0.30/1K chars) or OpenAI Whisper API ($0.006/min) are used instead of local `edge-tts` / `kokoro-onnx` / `faster-whisper` (zero marginal API cost).*

### 2.3 Cost Optimization Levers
1. **Horizon 1 `ContextBudgetManager` (`H1-05`):** Immediate **~65% LLM input token savings** by omitting inactive subsystem directives.
2. **Horizon 1 `aiohttp` Session Pooling (`H1-04`):** Eliminates 50–150ms TLS handshake overhead per Gemini embedding call (`[PERF-MED-001]`).
3. **Horizon 0 Replan Cap (`H0-08`):** Stops `[COG-CRIT-002]` infinite 25s mission failure/TTS loops that burn API quota and disk I/O.
4. **Hybrid Local Audio:** Using `faster-whisper` + `kokoro-onnx`/`edge-tts` reduces variable audio API cost to **$0/hr**.

---

## 3. Docker & 24/7 Operational Footprint

### Container Footprint (`Dockerfile` & `docker-compose.yml`)
- **Base Image:** `python:3.12-slim` + `ffmpeg` (~450–650 MB base image without local PyTorch/CUDA; ~3.5–6.0 GB if `stt-local`/`tts-local`/`embeddings-local` with GPU runtime are baked in).
- **Runtime Memory (RSS):**
  - Core FastAPI + `Orchestrator` + SQLite (`data/memory.db`): **~180–350 MB RAM**.
  - With local `kokoro-onnx` + `faster-whisper` (CPU): **~1.2–2.5 GB RAM**.
- **Persistent Volumes (`docker-compose.yml:18-22`):** `./config`, `./data`, `./plugins`, `./data/clips`.

### 24/7 Disk & Memory Growth Risks (Must Be Bounded in H0–H2)
1. **`data/goals/goals.json` & `data/goals/agenda.md`:** Currently grow unboundedly on `[COG-CRIT-002]` replan loops — fixed by `MAX_REPLAN_ATTEMPTS` (`H0-08`).
2. **`data/second_brain/promises.md`:** Append-only (`[COG-LOW-002]`) — needs compaction/archival in `H2-02`.
3. **`data/clips/`:** Partial `.mp4` leftovers on failed `ffmpeg` runs (`[GAME-HIGH-004]`) and unrotated vertical clips — fixed in `H0-03` + retention policy.
4. **In-Memory Queues & Tasks:** `ChatReceiver.queue` (`[INFRA-HIGH-004]`), `EventBus.publish_nowait` (`[PERF-LOW-002]`), and 12+ untracked `asyncio.create_task` calls (`[INFRA-HIGH-001]`) — bounded in `H0-05` and `H1-07`.
5. **Docker Networking:** Currently `CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "7860"]` hits `[SEC-HIGH-001]` Creator WS Auth deadlock and `[SEC-CRIT-001]` unauthenticated `/ws` exposure — **Docker deployment remains `NO-GO` until `H0-01` lands**.
