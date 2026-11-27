# Post-Implementation Audit — 09: QA, Reliability & Observability

**Auditor:** `ng-qa` (Agent 8 — QA, Reliability & Production Engineering)  
**Scope:** Test suite verification, warning/resource-leak analysis, containerization (`Dockerfile`, `docker-compose.yml`), and runtime observability (`/api/health`, `/api/metrics`, `core/metrics.py`).

---

## 1. Automated Verification Summary

All verification commands were executed in read-only/isolated mode against the post-H0/H1/H2/H3 codebase (`MAYBEAI_DATA_DIR` temp isolation in E2E tests; `git status --short data/` remained clean).

| Check | Command | Outcome | Notes |
|---|---|---|---|
| Python Unit & Integration Suite | `.\.venv\Scripts\python.exe -W default -m unittest discover tests` | **381 tests in 34.964s — OK (`380` passed, `1` skipped)** | `VERIFIED`. `43` test modules (`44` `.py` files including `__init__.py`). `1` skipped: `TestPlaywrightBrowserE2E` in [test_e2e_browser.py](file:///d:/projects/MaybeAI/tests/test_e2e_browser.py#L195-L196) (`playwright not installed`). |
| Node.js GuardRunner Tests | `node tests/test_guard_runner.js` | **PASS (exit 0)** | `VERIFIED`. All GuardRunner tests passed. |
| JS Syntax Verification | `node --check web/app.js web/overlay.js web/settings.js web/deck.js web/shared-client.js web/audio-worklet-processor.js minecraft/bot.js` | **PASS (exit 0)** | `VERIFIED`. Zero syntax errors across all 7 JS/Worklet/Bot files. |
| Repository Data Hygiene | `git status --short data/` | **Clean (empty)** | `VERIFIED`. No test artifacts leaked into `data/`. |

---

## 2. Test Coverage: Real vs. Mocked

- **Real / Live Subprocess & Loopback Verification (`VERIFIED`):**
  - [test_e2e_browser.py](file:///d:/projects/MaybeAI/tests/test_e2e_browser.py): Spawns live `uvicorn` on `127.0.0.1:0` with `MAYBEAI_DATA_DIR` temp dir; verifies `/`, `/overlay`, `/deck`, `/settings`, `/static/*`, `/api/health`, `/api/metrics` (origin + Bearer auth-gated), and `/ws` handshake + foreign-origin rejection.
  - [test_sandbox_plugins_cli.py](file:///d:/projects/MaybeAI/tests/test_sandbox_plugins_cli.py) & [test_collab_and_plugins.py](file:///d:/projects/MaybeAI/tests/test_collab_and_plugins.py): Spawn real subprocess sandbox workers (`core/plugins/sandbox_worker.py`) with Windows Job Object (`_WindowsJobObject`) isolation and JSON-RPC 2.0 timeout/exception tests.
  - [core/memory/database.py](file:///d:/projects/MaybeAI/core/memory/database.py): Real SQLite + FTS5 + WAL operations against temporary databases.
- **Mocked / Offline Coverage (`VERIFIED`):**
  - External LLM (Gemini/OpenAI/Ollama HTTP 429/500 failovers), TTS (Kokoro/EdgeTTS/RVC), VTube Studio WS, OBS WebSocket, Twitch IRC, YouTube/Discord adapters, and Mineflayer/Minecraft bot bridges are tested via mocked transports/clients.
- **Coverage Gap (`PARTIALLY VERIFIED`):**
  - Real Chromium browser E2E (`TestPlaywrightBrowserE2E`) is skipped in this environment because `playwright` is not installed (`380` executed, `1` skipped).
  - No automated multi-hour soak test exists in `tests/` (verified via static/dynamic analysis in `audit/12_performance_analysis.md`).

---

## 3. Warnings & Resource Leak Analysis (`-W default`)

Running `unittest` with `-W default` surfaced two recurring warning classes (`REPRODUCED`):

1. **`asyncio` Slow Callbacks (`> 0.100s`):**
   - Observed in `test_audioworklet_deck.py:103` (`0.125s`), `test_brain.py:55,174` (`0.140s`), `test_chess.py:125` (`0.125s`), `test_event_bus.py:188,205` (`0.109s`), `test_horizon2_companion.py:128` (`0.282s`), plus `0.109s–0.156s` callbacks in later async tests.
   - Cause: Synchronous setup/teardown or SQLite/file/subprocess initialization inside `asyncSetUp`/coroutine tasks on Windows ProactorEventLoop.
2. **`ResourceWarning`s (Unclosed Sessions, Transports, Subprocess):**
   - `ResourceWarning: subprocess 29372 is still running` (`subprocess.py:1127`).
   - `ResourceWarning: Unclosed client session <aiohttp.client.ClientSession ...>` (`aiohttp/client.py:527`) and `Unclosed connector` (`aiohttp/connector.py:371`).
   - `ResourceWarning: unclosed <socket.socket ...>` and `unclosed transport <_ProactorSocketTransport ...>` (`asyncio/proactor_events.py:116`).
   - **Production Impact:** In tests where `Orchestrator` or `Brain` aiohttp sessions are not explicitly awaited on shutdown, descriptors leak until GC. In long-running production, `Orchestrator.shutdown()` must always be awaited on exit.

---

## 4. Containerization (`Dockerfile` & `docker-compose.yml`)

- [Dockerfile](file:///d:/projects/MaybeAI/Dockerfile) (`VERIFIED`):
  - Uses `python:3.12-slim`, installs `ffmpeg`, creates non-root user `maybeai`, sets `MAYBEAI_HEADLESS=1`, `SDL_VIDEODRIVER=dummy`, `SDL_AUDIODRIVER=dummy`, exposes `7860`, and defines a 30s `HEALTHCHECK` polling `http://127.0.0.1:7860/api/health`.
- [docker-compose.yml](file:///d:/projects/MaybeAI/docker-compose.yml) (`VERIFIED`):
  - Mounts `./config`, `./data`, `./plugins`, `./data/clips`; passes `MAYBEAI_CREATOR_TOKEN`, `OBS_WS_HOST` (`host.docker.internal`), and LLM keys via env vars with `restart: unless-stopped`.
  - **Gap:** Binds `0.0.0.0:7860` inside container (`CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "7860"]`); safe only behind a reverse proxy or with `MAYBEAI_CREATOR_TOKEN` set. No memory/CPU resource limits (`deploy.resources.limits`) are configured in `docker-compose.yml`.

---

## 5. Observability: `/api/health`, `/api/metrics`, and `MetricsCollector`

- **`/api/health`** ([run.py](file:///d:/projects/MaybeAI/run.py#L540-L542)): Returns `{"status": "ok"}` unauthenticated for Docker/load-balancer liveness probes (`VERIFIED`). Note: it is a shallow liveness check (does not verify SQLite or EventBus health).
- **`/api/metrics`** ([run.py](file:///d:/projects/MaybeAI/run.py#L454-L476), [L545-L567](file:///d:/projects/MaybeAI/run.py#L545-L567)):
  - Protected by `verify_api_origin_middleware` (`_SENSITIVE_GET_EXACT` includes `"/api/metrics"`), requiring allowed `Origin` and Creator Bearer token when configured (`VERIFIED`).
  - Returns `uptime_sec`, `active_ws_clients`, `websocket_clients` (`main`, `collab`, `total`), and `orchestrator` snapshot from [MetricsCollector](file:///d:/projects/MaybeAI/core/metrics.py#L110-L197) (`counters`: `event_bus_published`, `event_bus_errors`, `llm_requests`, `llm_failovers`; `gauges`: `active_ws_clients`, `bg_tasks_active`, `rss_mb`, `uptime_sec`; `histograms`: `tts_latency_ms`, `stt_latency_ms` with `p50_ms`, `p95_ms`, `avg_ms`, `max_ms`).
- **Observability Gaps:**
  - **No structured JSON file logging / log rotation:** Core modules predominantly use `print(...)` to stdout rather than Python `logging` with `RotatingFileHandler`/`TimedRotatingFileHandler` (`VERIFIED` via grep across `core/`).
  - **No Prometheus `/metrics` text exposition:** Metrics are JSON-only at `/api/metrics`.
