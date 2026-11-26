# MaybeAI Repository Inventory (`audit/00_repository_inventory.md`)

**Auditor:** AGENT 1 — Core Infrastructure & Distributed Concurrency Auditor (`cto-infra`)  
**Scope:** Complete verified inventory of repository structure, entrypoints, `core/` modules, `web/` assets, `minecraft/` bridge, `plugins/`, `tests/`, `config/`, containerization (`Dockerfile`, `docker-compose.yml`), and dependency footprint (`pyproject.toml`, `requirements.txt`, `minecraft/package.json`).  
**Verification Basis:** Direct filesystem listing and source file inspection at `d:\projects\MaybeAI`.

---

## 1. Top-Level Structure & Entrypoints

| Path | Role | Notes |
|---|---|---|
| `run.py` | Primary HTTP/WebSocket server & CLI entrypoint | 1,697 lines; FastAPI app (`lifespan` -> `orchestrator.start()` / `orchestrator.shutdown()`), REST APIs, `/ws` & `/ws/collab` WebSockets, `uvicorn.run(...)` |
| `core/plugins/cli.py` | Package script entrypoint (`maybeai = "core.plugins.cli:main"`) | Defined in `pyproject.toml:52-53` |
| `start.bat` / `push.bat` | Windows launcher & git push helper scripts | Root batch scripts |
| `pyproject.toml` | Python package metadata & dependencies | `name = "maybeai"`, `version = "1.0.0"`, `requires-python = ">=3.11"` |
| `requirements.txt` | Pinned/minimum Python runtime dependencies | 13 core packages (used by `Dockerfile`) |
| `Dockerfile` | Headless container build (`python:3.12-slim`) | Installs `ffmpeg`, runs as non-root `maybeai` user, exposes `7860`, `HEALTHCHECK` on `/api/health` |
| `docker-compose.yml` | Headless compose service (`maybeai-headless`) | Maps `7860:7860`, mounts `./config`, `./data`, `./plugins`, `./data/clips` |
| `.env` / `.env.example` | Environment variable configuration | Loaded via `dotenv.load_dotenv()` in `run.py:23` |
| `README.md` / `CHANGELOG.md` / `LICENSE` | Project documentation and MIT license | — |

---

## 2. Core Python Modules (`core/` — 94 `.py` files)

### 2.1 Top-Level Core (`core/*.py`)
| File | Responsibility |
|---|---|
| `core/orchestrator.py` | Master async conductor (1,937 lines): `EventBus`, `Brain`, `TTS`, `STT`, `VTS`, `OBS`, `Singer`, `Minecraft`, `Chess`, `ChatReceiver`, `AutonomousMissionExecutor`, `CollabManager`, `PluginRegistry`, `HighlightDetector`, `ClipPipeline`, `VODSummarizer` |
| `core/event_bus.py` | Typed async/sync pub-sub `EventBus` (264 lines), canonical `Events` constants, `WS_TO_BUS_EVENT` / `BUS_TO_WS_EVENT` mappings |
| `core/config_manager.py` | Centralized Configuration Center (1,791 lines): `DEFAULT_SETTINGS`, 110-field UI schema, validation, secret masking, atomic JSON saves, diagnostics |
| `core/brain.py` | LLM routing (`gemini`, `openai`, `ollama`, `mock`) and `ConversationEngine` facade (703 lines) |
| `core/chat_receiver.py` | `ChatMessage`, `ChatReceiver` (`asyncio.Queue`), Twitch IRCv3 TLS/plain listener, multi-platform adapter registry (288 lines) |
| `core/moderator.py` | Input/output profanity, length, and prompt-injection filtering |
| `core/actions.py` | `ActionParser` for `[emotion: ...]` and `[action: ...]` tags |
| `core/tts.py` / `core/tts_providers.py` | TTS synthesis (`edge-tts`, `kokoro`, `elevenlabs`, `gpt_sovits`, `fish_speech`), RVC conversion, lip-sync mouth callbacks |
| `core/stt.py` | `STTEngine`, `EnergyVAD`, `StreamingSTTSession` for full-duplex voice & barge-in |
| `core/singer.py` | Karaoke `Singer` engine with lyric timing and vocal/BGM playback |
| `core/vts_client.py` | VTube Studio WebSocket client (port `8001`) |

### 2.2 Core Subpackages (`core/*/`)
| Subpackage | Files | Responsibility |
|---|---|---|
| `core/chess/` | `__init__.py`, `chess_agent.py`, `chess_engine.py`, `controller.py` | `python-chess` engine, AI opponent, commentary/state callbacks |
| `core/collab/` | `__init__.py`, `manager.py`, `protocol.py` | AI-to-AI VTuber collaboration (`CollabEnvelope`, HMAC, turn arbitration, duet/emote/game sync) |
| `core/conversation/` | `__init__.py`, `chat_curator.py`, `engine.py`, `memory.py`, `prompts.py` | `ConversationEngine`, `ChatCurator` priority/debate selection, short-term memory, prompt builder |
| `core/desktop/` | `__init__.py`, `controller.py`, `engine.py`, `models.py`, `obs_client.py`, `permission_manager.py` | Desktop Companion controls + `OBSWebSocketClient` (`obsws-python`) |
| `core/highlights/` | `__init__.py`, `clipper.py`, `detector.py`, `vod_summarizer.py` | `HighlightDetector`, `ClipPipeline` (`ffmpeg` 9:16), `VODSummarizer` (Markdown export) |
| `core/memory/` | `__init__.py`, `database.py`, `embedding.py`, `extractor.py`, `markdown_sync.py`, `retriever.py` | SQLite episodic memory (`data/memory.db`), embeddings (`local`/`gemini`/`openai`/`hash`), Second Brain Markdown sync |
| `core/minecraft/` | `__init__.py`, `casual_agent.py`, `controller.py`, `guard_agent.py`, `speedrun_agent.py` | Mineflayer Node.js subprocess bridge & autonomous gameplay modes (`santai`, `kompe`, `guard`) |
| `core/minecraft/multiplayer/` | `__init__.py`, `contribution_ledger.py`, `engine.py`, `group_chat.py`, `models.py`, `negotiation.py`, `team_manager.py` | Multiplayer social intelligence, team/squad state, negotiation, contribution ledger |
| `core/minigames/` | `__init__.py`, `engine.py`, `game_catalog.py`, `models.py` | Interactive chat mini-games (e.g., trivia) |
| `core/mood/` | `__init__.py`, `engine.py` | 5-dimension affective mood engine with decay and behavioral directives |
| `core/performance/` | `__init__.py`, `director.py`, `models.py` | `PerformanceDirector` setlists, choreography steps, audience cheers |
| `core/personality/` | `__init__.py`, `evolution.py`, `models.py` | Experience-based personality trait evolution & mood baseline sync |
| `core/planning/` | `__init__.py`, `decomposer.py`, `engine.py`, `executor.py`, `models.py`, `replanner.py` | Goal decomposition, `AutonomousMissionExecutor` closed-loop tick runner, replanning |
| `core/platforms/` | `__init__.py`, `base.py`, `discord_adapter.py`, `tiktok.py`, `youtube.py` | `BasePlatformAdapter` and YouTube Live, Discord (REST/Gateway), TikTok Live adapters |
| `core/plugins/` | `__init__.py`, `cli.py`, `registry.py`, `sandbox_worker.py`, `sdk.py`, `word_chain.py` | Plugin SDK, `PluginRegistry`, subprocess `sandbox_worker.py`, built-in `word_chain` plugin, `maybeai` CLI |
| `core/relationship/` | `__init__.py`, `engine.py`, `models.py` | Per-user relationship tracking and gaming/interaction records |
| `core/storytelling/` | `__init__.py`, `engine.py`, `models.py`, `preset_campaigns.py` | Dynamic RPG storytelling, voting, dice rolls, preset campaigns |
| `core/vision/` | `__init__.py`, `analyzer.py`, `capture.py`, `engine.py`, `models.py`, `vlm.py` | Screen capture (`mss`/`pillow`), scene analysis, VLM perception |

---

## 3. Web Frontend (`web/` — 13 files)

Static assets mounted at `/static` (`run.py:382`) and served via FastAPI `FileResponse`:
- `/` -> `web/index.html`, `web/app.js`, `web/style.css`, `web/audio-worklet-processor.js`
- `/settings` -> `web/settings.html`, `web/settings.js`, `web/settings.css`
- `/overlay` -> `web/overlay.html`, `web/overlay.js`, `web/overlay.css`
- `/deck` -> `web/deck.html`, `web/deck.js`, `web/deck.css`

---

## 4. External Runtime & Plugins

### 4.1 `minecraft/` (Node.js Mineflayer Bridge)
- Entrypoint: `minecraft/bot.js` (`package.json` `"main": "bot.js"`)
- Mode scripts: `minecraft/casual.js`, `minecraft/guard.js`, `minecraft/speedrun.js`
- Config: `minecraft/config.json`
- Bundled Node runtime/deps: `minecraft/node/` (`node.exe`, `npm`, `npx`) and `minecraft/node_modules/`

### 4.2 `plugins/`
- **Current state:** No `plugins/` directory exists at the repository root (`Test-Path plugins` returned `False`), though `ConfigManager.DEFAULT_SETTINGS["plugins"]["plugins_dir"]` defaults to `"plugins"` and `Dockerfile:23` creates `/app/plugins`.
- Built-in plugins (`word_chain`) are shipped under `core/plugins/word_chain.py`.

---

## 5. Configuration & Persistent Data (`config/` & `data/`)

| Directory | Contents |
|---|---|
| `config/` | `settings.json`, `character.json`, `filter_words.json`, `minecraft_servers.json`, `songs.json` |
| `data/` | `memory.db` (SQLite), `desktop/permissions.json`, `goals/{agenda.md,goals.json}`, `minecraft/multiplayer_social.json`, `minigames/leaderboard.json`, `performance/director.json`, `personality/evolution.json`, `relationships/relationships.json`, `storytelling/campaigns.json`, `second_brain/` (Markdown sync tree: `MEMORY_INDEX.md`, `promises.md`, `community/`, `desktop/`, `journals/`, `minigames/`, `performance/`, `personality/`, `relationships/`, `storytelling/`, `teams/`, `users/`) |
| `assets/` | `assets/songs/digital_world_bgm.wav` |

---

## 6. Tests (`tests/` — 39 files)

- 37 Python `unittest` test files (`tests/test_*.py`), plus `tests/__init__.py`
- 1 Node.js test runner (`tests/test_guard_runner.js`)
- Verified core infrastructure subset (`test_event_bus.py`, `test_configuration.py`, `test_system_integrity.py`): **29 tests passed in 1.729s** via `.venv\Scripts\python.exe -m unittest`.

---

## 7. Dependency Footprint

### 7.1 Python (`pyproject.toml` & `requirements.txt`)
- **Core (13 packages, identical in `pyproject.toml` and `requirements.txt`):** `fastapi>=0.110.0`, `uvicorn>=0.28.0`, `websockets>=12.0`, `aiohttp>=3.9.0`, `edge-tts>=6.1.9`, `pydantic>=2.6.0`, `python-dotenv>=1.0.1`, `requests>=2.31.0`, `pygame>=2.5.2`, `numpy>=1.26.0`, `python-chess>=1.11.0`, `pillow>=10.0.0`, `mss>=9.0.0`.
- **Optional Extras (`pyproject.toml` only):**
  - `stt-local`: `faster-whisper>=1.0.0`, `openai-whisper>=20231117`
  - `embeddings-local`: `sentence-transformers>=2.6.0`, `fastembed>=0.3.0`
  - `tts-local`: `kokoro>=0.9.4`, `kokoro-onnx>=0.4.0`
  - `tiktok`: `TikTokLive>=6.0.0`
  - `obs`: `obsws-python>=1.6.1`
  - `dev`: `pytest>=8.0.0`, `httpx>=0.27.0`

### 7.2 Node.js (`minecraft/package.json`)
- `mineflayer` (`^4.39.0`), `mineflayer-pathfinder` (`^2.4.5`), `mineflayer-pvp` (`^1.3.2`), `prismarine-viewer` (`^1.33.0`), `ws` (`^8.16.0`).
