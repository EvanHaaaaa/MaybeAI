# Architecture Trade-Off Analysis & Proposals (`research/architecture_proposals.md`)

**Document Owner:** Agent 11 (`strat-arch`) — Principal Software & Future Architecture Engineer  
**Purpose:** Concrete engineering trade-off analysis of architectural alternatives for MaybeAI's core runtime, memory store, plugin sandbox, real-time audio transport, and frontend stack.

---

## 1. Execution Model for Heavy Local ML (`faster-whisper`, `kokoro-onnx`, `sentence-transformers`, VLM)

Currently, MaybeAI runs a single Python `asyncio` process (`run.py` + `Orchestrator`) using `asyncio.to_thread()` for CPU/GPU-bound tasks.

| Dimension | Option A: Single-Process `asyncio` + `to_thread` (Current) | Option B: `asyncio` + Dedicated Local ML Worker Process(es) (Recommended for H3) | Option C: Full Microservices (Docker Compose per Subsystem) |
|---|---|---|---|
| **Event-Loop Isolation** | Moderate; Python GIL & heavy PyTorch/ONNX allocations can still cause `>100ms` stalls if not carefully bounded. | **High**; STT/TTS/Embeddings run in separate OS process(es) with dedicated GIL & CUDA/ONNX context. | **High**; complete process & container isolation. |
| **Audio/Voice Latency** | Lowest IPC overhead (`<0.1ms` in-memory). | Low IPC overhead (`1–3ms` over stdio/Unix socket/local pipe). | Higher (`5–15ms` HTTP/gRPC serialization + Docker bridge). |
| **Operational Complexity** | **Lowest** (single `python run.py` or `start.bat`). | **Moderate** (managed child process via `TaskSupervisor`, similar to `minecraft/bot.js`). | **High** (multi-container orchestration, healthchecks, shared volumes). |
| **VRAM / RAM Control** | Shared heap; OOM in Whisper/Kokoro crashes the entire stream. | **Bounded**; worker crash restarts cleanly without dropping `/ws`, OBS, or Twitch chat. | Bounded, but highest baseline RAM overhead. |
| **Recommendation** | **Keep for Horizon 0–2** (with `to_thread` + `transcribe_wav_bytes` background task offload per `[AUDIO-HIGH-001]`). | **Adopt in Horizon 3** as an opt-in `--ml-worker` mode for heavy local GPU setups. | **Reject** for single-creator desktop/studio target. |

---

## 2. Vector & Episodic Memory Store (`core/memory/`)

Currently, `MemoryDatabase` (`core/memory/database.py`) uses SQLite + FTS5 + NumPy cosine similarity over a 300-row cap (`[COG-HIGH-005]`), synced to Karpathy-style Markdown files (`data/second_brain/`).

| Dimension | Option A: Current SQLite FTS5 + NumPy (300-row cap) | Option B: SQLite FTS5 + `sqlite-vec` (Recommended for H2) | Option C: External Vector DB (`Qdrant` / `Chroma`) |
|---|---|---|---|
| **Scale Ceiling** | Degrades / truncates silently past 300 episodic memories. | Scales cleanly to **50k–100k+ vectors** in a single `data/memory.db` file. | Scales to millions+ vectors. |
| **Deployment Footprint** | Zero external services; 1 file (`data/memory.db`). | Zero external services; 1 file (`data/memory.db`) + `sqlite-vec` wheel. | Requires running & backing up a separate server/container. |
| **Hybrid Querying** | Two-step Python merge (FTS5 + brute-force NumPy). | Single-connection SQLite hybrid RRF (Reciprocal Rank Fusion) of FTS5 + ANN/KNN. | Separate sync between SQLite metadata/FTS and Qdrant. |
| **Windows / Docker Portability** | 100% portable. | High (prebuilt wheels for Windows & Linux `python:3.12-slim`). | Moderate (extra service in `docker-compose.yml` & `start.bat`). |
| **Recommendation** | Fix duplicate `EmbeddingEngine` (`[COG-HIGH-004]`) & persistent `aiohttp` session (`[PERF-MED-001]`) immediately in H1. | **Adopt in Horizon 2** to eliminate the 300-row cap without adding external infrastructure. | **Defer** unless multi-tenant or `>100k` memory scale is needed. |

---

## 3. Out-of-Process Plugin Sandboxing (`core/plugins/`)

Currently, `PluginRegistry` (`core/plugins/registry.py`) spawns `python -m core.plugins.sandbox_worker` with stripped `os.environ` (`leaks=[]` in Chaos Scenario C2), but shares the host user, `cwd`, filesystem, and network (`[SEC-CRIT-002]`).

| Dimension | Option A: Python Subprocess + Host-Granted Perms (H0) | Option B: OS-Native Jail (`bubblewrap`/namespaces + Job Objects) (Recommended for H2) | Option C: Container-per-Plugin (Docker Socket) | Option D: WASM / Pyodide Sandbox |
|---|---|---|---|---|
| **Filesystem & Secret Protection** | Low (plugin can still `open(".env")` unless OS-jailed). | **High** (bind-mount only `core/plugins/sdk.py` + plugin dir; `.env`, `config/`, `data/` invisible). | High, **but** mounting `/var/run/docker.sock` gives host root equivalent. | **Highest** (virtual FS only). |
| **Network Isolation** | None (unrestricted outbound sockets). | **High** on Linux (`--unshare-net` in `bubblewrap`/Docker); moderate on Windows. | High (`--network=none`). | High. |
| **Python Ecosystem Compat** | 100% native Python. | 100% native Python. | 100% native Python. | **Low** (no C-extensions, asyncio/socket quirks). |
| **Cold-Start Latency** | `~0.3–1.0s` (requires `startup_timeout_sec=5.0`, `[QA-HIGH-001]`). | `~0.3–1.2s` (`bwrap` adds `<20ms`). | `1–5s+` per plugin. | `1–3s` WASM runtime init. |
| **Recommendation** | **Adopt in Horizon 0** (host-granted permissions, disable `inprocess`, separate startup timeout, evict crashed workers). | **Adopt in Horizon 2** (`bubblewrap`+`seccomp` on Linux/Docker; Windows Job Objects + restricted working dir). | **Reject** (Docker socket escalation & heavy overhead). | **Reject** (breaks standard Python plugins). |

---

## 4. Real-Time Audio Transport & Lip-Sync Synchronization

Currently, `web/audio-worklet-processor.js` sends 32 ms PCM frames as JSON+base64 over `/ws` (31.25 msg/s), while `TTSEngine` sends `audio_chunk` (base64 MP3/WAV) + synthetic 80 ms square-wave `avatar_state` (`[AUDIO-CRIT-002]`).

| Dimension | Option A: JSON + Base64 WS + Server RMS Envelope (H1) | Option B: Binary WS Frames + Server RMS Envelope (Recommended for H2) | Option C: WebRTC (`aiortc`) |
|---|---|---|---|
| **Bandwidth & GC Overhead** | ~33% base64 bloat + JSON parse/stringify 31.25x/sec. | **Zero base64 overhead** (`ArrayBuffer` with 1-byte frame tag); minimal GC. | Lowest RTP/Opus bandwidth + native AEC. |
| **Browser / OBS Compatibility** | Works everywhere (localhost, LAN HTTP, OBS CEF). | Works everywhere (localhost, LAN HTTP, OBS CEF). | Requires ICE/STUN/TURN, DTLS, and complex NAT/OBS CEF debugging. |
| **Lip-Sync Accuracy** | High once synthetic square wave is replaced with real PCM RMS envelope & browser authority rule. | High; exact frame alignment with audio buffers. | High, but decouples audio from `/ws` event timeline. |
| **Recommendation** | **Adopt in Horizon 1** to fix `[AUDIO-CRIT-002]` immediately without protocol churn. | **Adopt in Horizon 2** for `voice_audio_chunk` and `audio_chunk` binary frames. | **Reject** for local/LAN studio; complexity outweighs gain over local WebSocket. |

---

## 5. Frontend Architecture (`web/`)

Currently, MaybeAI serves 4 vanilla HTML/JS/CSS surfaces (`/`, `/settings`, `/overlay`, `/deck`) via FastAPI `FileResponse`, with Three.js + `@pixiv/three-vrm` loaded from `https://esm.sh` (`[UI-MED-004]`).

| Dimension | Option A: Vanilla ES Modules + `shared-client.js` + Local `web/vendor/` (Recommended) | Option B: Full SPA Rewrite (React / Vite / TypeScript) |
|---|---|---|
| **Build & Deployment** | **Zero Node.js build step** required for Python/Docker users; `node --check` validates syntax directly. | Requires Node.js build pipeline (`npm run build`), bundling, and source-map management in `Dockerfile`. |
| **Security & Auth UX** | Extracting `shared-client.js` + `escapeHtml()` fixes `[UI-HIGH-001]`, `[UI-HIGH-002]`, and `[UI-HIGH-003]` cleanly. | Component templating prevents `innerHTML` XSS by default, at the cost of rewriting 5,500+ lines of `app.js` + `overlay.js` + `deck.js` + `settings.js`. |
| **Air-Gapped LAN / OBS** | Vendoring Three.js, `@pixiv/three-vrm`, and fonts in `web/vendor/` makes `/overlay` 100% offline-capable. | Same, once bundled. |
| **Recommendation** | **Adopt across Horizon 0–2.** Preserves all working studio features while eliminating XSS, auth lockouts, reconnect storms, and CDN dependencies. | **Reject** (violates evolutionary hardening principle; high regression risk with 0% current browser E2E tests). |
