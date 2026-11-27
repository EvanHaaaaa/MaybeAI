# Architecture Trade-Off Analysis & Proposals (`research/architecture_proposals.md`)

**Document Owner:** Agent 11 (`ng-strat-arch`) — Principal Software & Future Architecture Engineer  
**Target Baseline:** `HEAD` commit `96b7315` (Post-Horizon 0–3 + YouTube Karaoke)  
**Purpose:** Concrete engineering trade-off analysis of architectural alternatives for MaybeAI's runtime topology, memory store, plugin sandbox, real-time audio transport, and frontend stack.

---

## 1. Runtime Topology: Modular Monolith vs. Dedicated Workers vs. Microservices

**Post-H3 Grounding:** MaybeAI currently runs as a single-process `asyncio` FastAPI + `EventBus` monolith (`run.py` `1,935` lines + `core/orchestrator.py` `2,197` lines) using `asyncio.to_thread()` for CPU/GPU-bound tasks, plus managed subprocesses for untrusted plugins (`core/plugins/sandbox_worker.py`), media tools (`yt-dlp`, `demucs`, `ffmpeg`), and Minecraft (`minecraft/bot.js`). Under test, synchronous disk/DB/engine calls (`_ingest_message`, `ConfigManager`) still produce `0.109s–0.282s` asyncio slow-callback warnings (`INFRA-MED-003`), while local neural ML (`faster-whisper`, `kokoro-onnx`, `sentence-transformers`) shares the main Python GIL and heap when enabled.

| Dimension | Option A: Single-Process Modular Monolith (`asyncio` + `to_thread`) — *Current* | Option B: Modular Monolith + Dedicated Inference & Audio Workers — *Recommended for H4-B* | Option C: Full Microservices (Docker Compose per Subsystem) |
|---|---|---|---|
| **Event-Loop & GIL Isolation** | Moderate; Python GIL & PyTorch/ONNX allocations or sync DB/disk calls cause `0.11s–0.28s` slow callbacks. | **High**; STT/TTS/RVC/Embeddings/VLM run in dedicated OS worker process(es) with isolated GIL & CUDA/VRAM context. | **High**; complete process & container isolation. |
| **Audio & Barge-In Latency** | Lowest IPC overhead (`<0.1ms`), but vulnerable to GC/GIL stalls during heavy inference. | **Predictable `<3ms` IPC** over local Unix socket / stdio / named pipe; `/ws` `EnergyVAD` barge-in stays `<1ms` even under GPU load. | Higher (`5–15ms` HTTP/gRPC serialization + Docker bridge network). |
| **Operational Complexity** | **Lowest** (`python run.py` or single Docker container). | **Moderate** (supervised child processes managed by `Orchestrator` / `TaskSupervisor`, matching `minecraft/bot.js` & `sandbox_worker.py`). | **High** (multi-container orchestration, service discovery, distributed tracing, shared volumes). |
| **Failure Blast Radius & VRAM** | Shared heap; OOM or native segfault in Whisper/Kokoro/Demucs crashes the entire stream. | **Contained**; worker OOM/crash restarts cleanly without dropping `/ws`, OBS, Twitch chat, or `MemoryDatabase`. | Contained, but highest baseline RAM/VRAM overhead. |
| **Recommendation** | **Keep for Pre-H4** while fixing `INFRA-MED-001-RES` (per-WS queue) and `INFRA-MED-003` (`to_thread` offload). | **Adopt in H4-B** as opt-in/auto-managed `inference_worker` and `audio_worker` processes over typed local IPC. | **Reject** — premature operational complexity for a single-creator / small-mesh VTuber studio. |

---

## 2. Memory & Knowledge Store: SQLite + FTS5 + `sqlite-vec` vs. External Vector / Graph DBs

**Post-H3 Grounding:** `MemoryDatabase` (`core/memory/database.py`) uses SQLite WAL + FTS5 + a Python `for`-loop cosine similarity scan bounded by `vector_scan_limit=2000` (`45.32ms` at 2,000 rows in Chaos Scenario H), synced one-way to Karpathy-style Markdown files (`data/second_brain/`). Memories older than the 2,000th most recent row are invisible to dense vector search (`04_cognitive_memory.md`), and there is no hierarchical episodic-to-semantic consolidation or schema migration versioning.

| Dimension | Option A: SQLite FTS5 + Python Linear Scan (`limit=2000`) — *Current* | Option B: SQLite WAL + FTS5 + `sqlite-vec` (ANN/KNN) + Hierarchical Consolidation — *Recommended for H4* | Option C: External Vector DB (`Qdrant` / `Milvus`) + Graph DB (`Neo4j`) |
|---|---|---|---|
| **Scale & Recall Ceiling** | `45.32ms` at `2,000` rows; silently drops rows beyond `2,000` from vector recall. | Scales cleanly to **50k–100k+ vectors** in a single `data/memory.db` file with zero silent truncation. | Scales to millions+ vectors and multi-hop graph traversals. |
| **Hybrid Querying** | Two-step Python merge (FTS5 + brute-force loop). | **Single-connection SQLite** hybrid RRF (Reciprocal Rank Fusion) of FTS5 + `sqlite-vec` KNN + importance/recency decay. | Dual-write sync hazard between SQLite/Markdown and external Qdrant/Neo4j containers. |
| **Deployment & Backup** | 1 file (`data/memory.db`) + `data/second_brain/*.md`. | **1 file (`data/memory.db`)** + `sqlite-vec` wheel + `schema_version` migrations (`PRAGMA user_version`). | Requires running, securing, and backing up 1–2 additional server daemons in `docker-compose.yml` & Windows `start.bat`. |
| **Windows / Docker Portability** | 100% portable. | High (prebuilt wheels for Windows & Linux `python:3.12-slim`; fallback to NumPy scan if wheel absent). | Low-Moderate (heavy RAM footprint for local Windows creators). |
| **Recommendation** | Insufficient beyond 2,000 episodic memories. | **Adopt in H4-A/H4-B** (`ADR-010`): add `sqlite-vec` + `schema_version` + nightly episodic-to-semantic distillation + bidirectional `promises.md` sync. | **Defer** unless multi-tenant SaaS or `>100k` active memories/entities are required. |

---

## 3. Out-of-Process Plugin Sandboxing (`core/plugins/`)

**Post-H3 Grounding:** `PluginRegistry` (`core/plugins/registry.py`) now parses manifests via `ast.parse` (`_extract_manifest_from_ast`), enforces default-deny `plugins.granted_permissions`, strips `env`, uses Linux `bwrap` + `RLIMIT` when available, and attaches `_WindowsJobObject` (512 MB, 2 processes). However, on Windows `install_boundary_guards()` relies on Python-level monkeypatches (`builtins.open`, `io.open`, `os.open`, 4 TCP `socket` methods) bypassable via `ctypes`/`subprocess`/`Path.unlink` (`SEC-GAP-002`), and `inprocess` remains in `VALID_SANDBOX_MODES`.

| Dimension | Option A: Python Monkeypatch + Job Object — *Current Windows* | Option B: OS-Native Restricted Token / AppContainer (Windows) + `bwrap`/`seccomp` (Linux) — *Recommended* | Option C: Container-per-Plugin (Docker Socket) | Option D: WASM / Pyodide Sandbox |
|---|---|---|---|---|
| **Secret & FS Protection** | Low on Windows (`ctypes`/`subprocess` bypasses Python hooks to read `.env`). | **High** (`bwrap` bind-mounts on Linux; Windows `CreateRestrictedToken` / AppContainer + ACL-isolated scratch dir; disallow `inprocess` for external plugins). | High, **but** mounting `/var/run/docker.sock` grants host-root equivalence. | **Highest** (virtual FS only). |
| **Python Ecosystem Compat** | 100% native Python. | 100% native Python. | 100% native Python. | **Low** (breaks C-extensions & native asyncio/sockets). |
| **Cold-Start Latency** | `~0.3–1.0s`. | `~0.3–1.2s`. | `1–5s+` per plugin. | `1–3s` WASM init. |
| **Recommendation** | Inadequate for untrusted third-party plugins (`SEC-GAP-002`). | **Adopt in Pre-H4 (`ADR-012`)** to close `SEC-GAP-002` across both Linux and Windows. | **Reject** (Docker socket escalation risk). | **Reject** (breaks Python plugin ecosystem). |

---

## 4. Real-Time Audio Transport & Lip-Sync Synchronization

**Post-H3 Grounding:** `AudioWorklet` (`web/audio-worklet-processor.js`) now streams 16 kHz `Int16Array` binary PCM frames over `/ws` (with JSON fallback), `TTSEngine`/`Singer` extract real 50ms RMS envelopes, and `app.js`/`overlay.js` arbitrate via `isLocalAudioPlaying`. Remaining issues are `ClientTimeout(total=1.8)` truncating >1.8s LLM streams (`AUDIO-MED-001`), `TTSEngine.speak()` swallowing `CancelledError` (`AUDIO-MED-002`), and `VTSClient` `MouthSmile` vs `MouthForm` split.

| Dimension | Option A: Binary WS PCM + Server RMS Envelope + Browser `AnalyserNode` — *Current (with P1 fixes)* | Option B: Dedicated Audio Worker + Timestamped Lip-Sync Frames — *Recommended for H4-B* | Option C: WebRTC (`aiortc`) |
|---|---|---|---|
| **Bandwidth & Latency** | Zero base64 overhead on ingress; minimal GC. | Zero base64 overhead on both ingress & egress; deterministic audio-clock alignment. | Lowest Opus bandwidth + native AEC. |
| **OBS & LAN Compatibility** | Works everywhere (`127.0.0.1`, LAN HTTP, OBS CEF). | Works everywhere (`127.0.0.1`, LAN HTTP, OBS CEF). | Requires ICE/STUN/TURN, DTLS, and complex OBS CEF NAT debugging. |
| **Recommendation** | **Fix `AUDIO-MED-001/002/003` immediately in Pre-H4.** | **Adopt in H4-B (`ADR-009`)** for heavy local TTS/RVC/Demucs isolation. | **Reject** for local/LAN studio. |

---

## 5. Frontend Architecture (`web/`)

**Post-H3 Grounding:** `web/shared-client.js` and `web/vendor/` (zero CDN) are live, and all 7 JS files pass `node --check`. However, `web/` remains 4 separate HTML/JS apps (`/`, `/settings`, `/overlay`, `/deck`) with `web/app.js` at `5,896` lines, duplicated 2D/VRM/audio code, `5` unguarded `ws.readyState` accesses, `?token=` + `localStorage` (`SEC-GAP-001`), and `0` `:focus-visible`/`prefers-reduced-motion` rules (`08_frontend_ux.md`).

| Dimension | Option A: Modular Vanilla ES Modules + Unified Studio Shell + Shared State Store — *Recommended* | Option B: Full SPA Rewrite (React / Vite / TypeScript) |
|---|---|---|
| **Build & Deployment** | **Zero Node.js build step** for Python/Docker users; `node --check` + Playwright E2E validate directly. | Requires Node.js build pipeline (`npm run build`), bundling, and source-map management in `Dockerfile`. |
| **Maintainability & Auth UX** | Splitting `app.js` (`5,896` lines) into ES modules (`avatar-renderer.js`, `audio-player.js`, `studio-store.js`) + `Sec-WebSocket-Protocol` (`SEC-GAP-001`) + `ws &&` guards eliminates duplication and XSS/auth gaps cleanly. | Component model enforces structure, at the cost of rewriting ~7,500+ lines of working UI (`app.js`, `overlay.js`, `deck.js`, `settings.js`) with high regression risk. |
| **Recommendation** | **Adopt in Pre-H4 & H4 (`ADR-013`)** — incremental ES module extraction without build-chain bloat. | **Reject** — violates evolutionary hardening principle. |
