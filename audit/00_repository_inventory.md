# MaybeAI Repository Inventory (`audit/00_repository_inventory.md`)

**Auditor:** AGENT 1 (`ng-infra`) — Core Infrastructure & Distributed Concurrency Auditor  
**Scope:** Exact post-Horizon 3 & YouTube Karaoke inventory of repository structure, entrypoints, `core/` modules, `web/` assets, `minecraft/` bridge, `plugins/`, `tests/`, `audit/`, `strategy/`, `research/`, `config/`, `data/`, containerization (`Dockerfile`, `docker-compose.yml`), and dependency footprint (`pyproject.toml`, `requirements.txt`, `minecraft/package.json`).  
**Verification Basis:** Direct filesystem enumeration, line-count inspection, and `unittest` discovery at `d:\projects\MaybeAI` (`HEAD` at `96b7315`).

---

## 1. Top-Level Structure & Entrypoints

| Path | Role | Verified Details |
|---|---|---|
| [run.py](file:///d:/projects/MaybeAI/run.py) | Primary HTTP/WebSocket server & CLI entrypoint | **1,935 lines**; FastAPI app (`lifespan` -> `orchestrator.start()` / `orchestrator.shutdown()`), REST APIs, `/ws` & `/ws/collab` WebSockets, `uvicorn.run(...)` |
| [core/plugins/cli.py](file:///d:/projects/MaybeAI/core/plugins/cli.py) | Package script entrypoint (`maybeai = "core.plugins.cli:main"`) | Declared in [pyproject.toml](file:///d:/projects/MaybeAI/pyproject.toml#L52-L53) |
| [start.bat](file:///d:/projects/MaybeAI/start.bat) / [push.bat](file:///d:/projects/MaybeAI/push.bat) | Windows launcher & git push helper scripts | Root batch scripts |
| [pyproject.toml](file:///d:/projects/MaybeAI/pyproject.toml) | Python package metadata & dependencies | `name = "maybeai"`, `version = "1.0.0"`, `requires-python = ">=3.11"` |
| [requirements.txt](file:///d:/projects/MaybeAI/requirements.txt) | Core Python runtime dependencies | 13 core packages (used by [Dockerfile](file:///d:/projects/MaybeAI/Dockerfile)) |
| [Dockerfile](file:///d:/projects/MaybeAI/Dockerfile) | Headless container build (`python:3.12-slim`) | Installs `ffmpeg`, runs as non-root `maybeai` user, exposes `7860`, `HEALTHCHECK` on `/api/health` |
| [docker-compose.yml](file:///d:/projects/MaybeAI/docker-compose.yml) | Headless compose service (`maybeai-headless`) | Maps `7860:7860`, mounts `./config`, `./data`, `./plugins`, `./data/clips` |
| `.env` / `.env.example` | Environment variable configuration | Loaded via `dotenv.load_dotenv()` in [run.py](file:///d:/projects/MaybeAI/run.py#L23) |
| [README.md](file:///d:/projects/MaybeAI/README.md) / [CHANGELOG.md](file:///d:/projects/MaybeAI/CHANGELOG.md) / [LICENSE](file:///d:/projects/MaybeAI/LICENSE) | Project documentation and MIT license | `HEAD` (`96b7315`) |

---

## 2. Core Python Modules (`core/` — 97 `.py` files)

### 2.1 Top-Level Core (`core/*.py` — 14 files)
| File | Lines | Responsibility |
|---|---:|---|
| [core/orchestrator.py](file:///d:/projects/MaybeAI/core/orchestrator.py) | 2,197 | Master async conductor: `EventBus`, `Brain`, `TTS`, `STT`, `VTS`, `OBS`, `Singer`, `Minecraft`, `Chess`, `ChatReceiver`, `AutonomousMissionExecutor`, `CollabManager`, `PluginRegistry`, `HighlightDetector`, `ClipPipeline`, `VODSummarizer`, YouTube Karaoke |
| [core/config_manager.py](file:///d:/projects/MaybeAI/core/config_manager.py) | 2,317 | Centralized Configuration Center: `DEFAULT_SETTINGS` (24 sections, 157 leaf keys), 157-field UI schema, validation, 8-field secret masking, `mkstemp` atomic JSON saves, diagnostics |
| [core/brain.py](file:///d:/projects/MaybeAI/core/brain.py) | 1,239 | LLM routing (`gemini`, `openai`, `ollama`, `mock`), `ProviderCircuitBreaker`, `ContextBudgetManager`, and `ConversationEngine` facade |
| [core/youtube_karaoke.py](file:///d:/projects/MaybeAI/core/youtube_karaoke.py) | 376 | SSRF-validated YouTube Song Request & AI Cover / Auto-Karaoke pipeline (`yt-dlp`, `ffmpeg`/`demucs`, `RVCVoiceConverter`, VTT/SRT lyric parser) |
| [core/event_bus.py](file:///d:/projects/MaybeAI/core/event_bus.py) | 308 | Typed async/sync pub-sub `EventBus` (concurrent `asyncio.gather`, `handler_timeout=5.0`, `max_pending_tasks=256`), canonical `Events` constants, `WS_TO_BUS_EVENT` / `BUS_TO_WS_EVENT` mappings |
| [core/chat_receiver.py](file:///d:/projects/MaybeAI/core/chat_receiver.py) | 304 | `ChatMessage`, bounded `ChatReceiver` (`asyncio.Queue(maxsize=500)`), Twitch IRCv3 TLS/plain listener, multi-platform adapter registry |
| [core/metrics.py](file:///d:/projects/MaybeAI/core/metrics.py) | 197 | Thread-safe `MetricsCollector` (counters, gauges, latency histograms) exposed via `/api/metrics` |
| [core/security_net.py](file:///d:/projects/MaybeAI/core/security_net.py) | 188 | Outbound SSRF & DNS-rebinding guard (`validate_outbound_url`) for Collab, TTS/RVC, and YouTube Karaoke |
| `core/moderator.py` | — | Input/output profanity, length, strict-mode blocking, and prompt-injection filtering |
| `core/actions.py` | — | `ActionParser` for `[emotion: ...]` and `[action: ...]` tags |
| `core/tts.py` / `core/tts_providers.py` | — | Pipelined TTS synthesis (`edge-tts`, `kokoro`, `elevenlabs`, `gpt_sovits`, `fish_speech`), RVC conversion, RMS lip-sync mouth callbacks |
| `core/stt.py` | — | `STTEngine`, `EnergyVAD`, `StreamingSTTSession` for full-duplex voice & barge-in |
| `core/singer.py` | — | Clock-locked karaoke `Singer` engine with lyric timing and vocal/BGM playback |
| `core/vts_client.py` | — | VTube Studio WebSocket client (port `8001`), multi-param mood rigging & reconnect |

### 2.2 Core Subpackages (`core/*/` — 83 `.py` files across 18 subpackages)
| Subpackage | Files | Responsibility |
|---|---:|---|
| `core/chess/` | 4 | `__init__.py`, `chess_agent.py`, `chess_engine.py`, `controller.py` (`python-chess`, optional Stockfish UCI + alpha-beta fallback) |
| `core/collab/` | 3 | `__init__.py`, `manager.py`, `protocol.py` (`CollabEnvelope`, HMAC-SHA256, nonce/skew replay protection, bidirectional sync) |
| `core/conversation/` | 5 | `__init__.py`, `chat_curator.py`, `engine.py`, `memory.py`, `prompts.py` |
| `core/desktop/` | 6 | `__init__.py`, `controller.py`, `engine.py`, `models.py`, `obs_client.py`, `permission_manager.py` |
| `core/highlights/` | 4 | `__init__.py`, `clipper.py`, `detector.py`, `vod_summarizer.py` |
| `core/memory/` | 6 | `__init__.py`, `database.py`, `embedding.py`, `extractor.py`, `markdown_sync.py`, `retriever.py` |
| `core/minecraft/` | 5 | `__init__.py`, `casual_agent.py`, `controller.py`, `guard_agent.py`, `speedrun_agent.py` |
| `core/minecraft/multiplayer/` | 7 | `__init__.py`, `contribution_ledger.py`, `engine.py`, `group_chat.py`, `models.py`, `negotiation.py`, `team_manager.py` |
| `core/minigames/` | 4 | `__init__.py`, `engine.py`, `game_catalog.py`, `models.py` |
| `core/mood/` | 2 | `__init__.py`, `engine.py` |
| `core/performance/` | 3 | `__init__.py`, `director.py`, `models.py` |
| `core/personality/` | 3 | `__init__.py`, `evolution.py`, `models.py` |
| `core/planning/` | 6 | `__init__.py`, `decomposer.py`, `engine.py`, `executor.py`, `models.py`, `replanner.py` |
| `core/platforms/` | 5 | `__init__.py`, `base.py`, `discord_adapter.py`, `tiktok.py`, `youtube.py` |
| `core/plugins/` | 6 | `__init__.py`, `cli.py`, `registry.py`, `sandbox_worker.py`, `sdk.py`, `word_chain.py` |
| `core/relationship/` | 3 | `__init__.py`, `engine.py`, `models.py` |
| `core/storytelling/` | 4 | `__init__.py`, `engine.py`, `models.py`, `preset_campaigns.py` |
| `core/vision/` | 6 | `__init__.py`, `analyzer.py`, `capture.py`, `engine.py`, `models.py`, `vlm.py` |

*(Count check: 14 top-level + 83 subpackage files = **97 `.py` files** in `core/`.)*

---

## 3. Web Frontend (`web/` — 19 files)

Static assets mounted at `/static` ([run.py](file:///d:/projects/MaybeAI/run.py#L469)) and served via FastAPI `FileResponse`:
- `/` -> `web/index.html`, `web/app.js`, `web/style.css`, `web/audio-worklet-processor.js`, `web/vrm-avatar.js`, `web/shared-client.js`
- `/settings` -> `web/settings.html`, `web/settings.js`, `web/settings.css`
- `/overlay` -> `web/overlay.html`, `web/overlay.js`, `web/overlay.css`
- `/deck` -> `web/deck.html`, `web/deck.js`, `web/deck.css`
- `web/vendor/` (5 offline-vendored files added in Horizon 2 `a08e435`): `BufferGeometryUtils.js`, `GLTFLoader.js`, `fonts.css`, `three-vrm.module.js`, `three.module.js`

---

## 4. External Runtime & Plugins

### 4.1 `minecraft/` (Node.js Mineflayer Bridge)
- Entrypoint: `minecraft/bot.js` (`package.json` `"main": "bot.js"`)
- Mode scripts: `minecraft/casual.js`, `minecraft/guard.js`, `minecraft/speedrun.js`
- Config: `minecraft/config.json`
- Bundled Node runtime/deps: `minecraft/node/` (`node.exe`, `npm`, `npx`) and `minecraft/node_modules/`

### 4.2 `plugins/`
- **Current state:** No `plugins/` directory exists at the repository root, though `ConfigManager.DEFAULT_SETTINGS["plugins"]["plugins_dir"]` defaults to `"plugins"` and [Dockerfile](file:///d:/projects/MaybeAI/Dockerfile#L23) creates `/app/plugins`.
- Built-in plugins (`word_chain`) are shipped under [core/plugins/word_chain.py](file:///d:/projects/MaybeAI/core/plugins/word_chain.py).

---

## 5. Configuration, Audit, Strategy, Research & Persistent Data

| Directory | Contents |
|---|---|
| `config/` | `settings.json`, `character.json`, `filter_words.json`, `minecraft_servers.json`, `songs.json` |
| `audit/` | **13** `.md` reports (`00_repository_inventory.md` .. `11_performance_analysis.md`, `FINAL_AUDIT_REPORT.md`) |
| `strategy/` | **13** `.md` strategic planning documents (`ARCHITECTURE_DECISIONS.md`, `COST_AND_INFRASTRUCTURE.md`, `CURRENT_STATE_ASSESSMENT.md`, `DEPENDENCY_MAP.md`, `DEVELOPMENT_ROADMAP.md`, `FEATURE_BACKLOG.md`, `FUTURE_DEVELOPMENT_MASTER_PLAN.md`, `FUTURE_STATE_ARCHITECTURE.md`, `INNOVATION_PORTFOLIO.md`, `PRODUCT_VISION.md`, `RESEARCH_PLAN.md`, `RISK_REGISTER.md`, `TECHNOLOGY_RADAR.md`) |
| `research/` | **6** `.md` files (`architecture_proposals.md`, `rejected_proposals.md`, `technology_radar.md`, `experiments/EXP-001.md` .. `EXP-003.md`) |
| `data/` | `memory.db` (SQLite), `desktop/permissions.json`, `goals/{agenda.md,goals.json}`, `minecraft/multiplayer_social.json`, `minigames/leaderboard.json`, `performance/director.json`, `personality/evolution.json`, `relationships/relationships.json`, `storytelling/campaigns.json`, `second_brain/` (Markdown sync tree) |
| `assets/` | `assets/songs/digital_world_bgm.wav` |

---

## 6. Tests (`tests/` — 45 files)

- **43** Python `unittest` test modules (`tests/test_*.py`), yielding **381** discovered `unittest` test cases (`unittest.defaultTestLoader.discover('tests').countTestCases() == 381`).
- `tests/__init__.py` (forces `MAYBEAI_LLM_PROVIDER=mock` during test runs).
- `tests/test_guard_runner.js` (Node.js Mineflayer guard unit test).

---

## 7. Dependency Footprint

### 7.1 Python ([pyproject.toml](file:///d:/projects/MaybeAI/pyproject.toml) & [requirements.txt](file:///d:/projects/MaybeAI/requirements.txt))
- **Core (13 packages):** `fastapi>=0.110.0`, `uvicorn>=0.28.0`, `websockets>=12.0`, `aiohttp>=3.9.0`, `edge-tts>=6.1.9`, `pydantic>=2.6.0`, `python-dotenv>=1.0.1`, `requests>=2.31.0`, `pygame>=2.5.2`, `numpy>=1.26.0`, `python-chess>=1.11.0`, `pillow>=10.0.0`, `mss>=9.0.0`.
- **Optional Extras (`pyproject.toml` only):**
  - `stt-local`: `faster-whisper>=1.0.0`, `openai-whisper>=20231117`
  - `embeddings-local`: `sentence-transformers>=2.6.0`, `fastembed>=0.3.0`
  - `tts-local`: `kokoro>=0.9.4`, `kokoro-onnx>=0.4.0`
  - `tiktok`: `TikTokLive>=6.0.0`
  - `obs`: `obsws-python>=1.6.1`
  - `dev`: `pytest>=8.0.0`, `httpx>=0.27.0`

### 7.2 Node.js (`minecraft/package.json`)
- `mineflayer` (`^4.39.0`), `mineflayer-pathfinder` (`^2.4.5`), `mineflayer-pvp` (`^1.3.2`), `prismarine-viewer` (`^1.33.0`), `ws` (`^8.16.0`).
