# Changelog

All notable changes to **MaybeAI (Eve Maybe)** are documented in this file.

## [2026-11-25] — Mid-Term Upgrades: OBS Overlay, Streaming Brain-to-TTS, EventBus, Semantic Embeddings & Multi-Platform Chat

### Pillar 1 — Dedicated OBS `/overlay` & Modular Tabbed Studio UI
- **Transparent OBS Browser Source (`web/overlay.html`, `web/overlay.css`, `web/overlay.js`, `run.py`):** Added dedicated `GET /overlay` route serving a transparent, zero-clutter stage with Virtual Avatar Canvas (`#avatarCanvas`), floating glassmorphic subtitles (`#subtitles`), real-time Donation/SuperChat alert banner (`#donation-alert-banner`), and `/ws` auto-reconnect (with `?token=` / `localStorage` fallback).
- **Modular 4-Tab Studio Workspace (`web/index.html`, `web/style.css`, `web/app.js`):** Added sticky workspace navigation (`🎤 Live Stage`, `🎮 Gaming`, `🎲 RPG & Mini-Games`, `🧠 Brain & Memory`) with `localStorage` persistence (`maybeai_active_workspace`) and a direct `📺 OBS Overlay` header button while preserving all existing studio DOM IDs and controls.

### Pillar 2 — Streaming Brain-to-TTS
- **Streaming LLM Generation (`core/brain.py`):** Added `Brain.is_streaming_enabled()` and `Brain.generate_response_stream()` supporting Gemini (`streamGenerateContent?alt=sse` via `x-goog-api-key`), OpenAI (`stream: true` SSE), Ollama (`stream: true` NDJSON), and realistic Mock chunking with graceful error fallback and full-turn memory recording.
- **Pipelined Sentence-Chunked TTS (`core/tts.py`, `core/orchestrator.py`):** Added `SentenceChunker` (splitting on `.`, `!`, `?`, `\n`, `~` while protecting `[emotion:]`/`[action:]` tags, abbreviations, and decimals) and `TTSEngine.speak_stream()` (concurrent producer/consumer Edge-TTS synthesis + playback, tag stripping & `on_tag` callbacks, guarded single `pygame.mixer.init()`, and guaranteed temp `speech_*.mp3` cleanup). Enabled `llm.streaming_enabled: true` by default and wired `Orchestrator._execute_interaction()` to emit incremental `ai_chunk` events followed by `ai_response` (`streamed: true`).

### Pillar 3 — Event-Driven Core (`EventBus`)
- **Typed Async Pub/Sub (`core/event_bus.py`):** Implemented `EventBus` and canonical `Events` constants (`chat.received`, `interaction.started`, `ai.chunk`, `ai.response`, `avatar.state`, `mood.updated`, `goal.updated`, `donation.received`, `song.started`, `platform.status`, etc.) with exact + wildcard `*` subscriptions, per-handler exception isolation, bounded history ring buffer, `publish_nowait()`, `get_history()`, `get_stats()`, and `clear()`.
- **Decoupled Core & Endpoints (`core/orchestrator.py`, `core/conversation/engine.py`, `run.py`):** Shared a single `EventBus` instance between `Orchestrator` and `ConversationEngine`, bridged WebSocket broadcasts via a `*` subscriber, exposed `GET /api/eventbus/stats`, and added `await orchestrator.shutdown()` on FastAPI lifespan exit.

### Pillar 4 — Semantic Memory Embeddings & Multi-Platform Chat Adapters
- **Multi-Backend Semantic Embeddings (`core/memory/embedding.py`, `core/memory/database.py`, `core/memory/retriever.py`):** Upgraded `EmbeddingEngine` to support `auto | local | gemini | openai | hash` (local `sentence-transformers`/`fastembed`, Gemini `text-embedding-004`, OpenAI `text-embedding-3-small`, and sublinear-TF `hash` fallback), LRU vector caching, async `aencode()`/`ahybrid_search()`/`arecall()`, and safe dimension-mismatch handling in `vector_search()`.
- **YouTube Live & Discord Adapters (`core/platforms/`, `core/chat_receiver.py`, `core/orchestrator.py`, `run.py`):** Added `BasePlatformAdapter`, `YouTubeLiveAdapter` (YouTube Data API v3 polling + SuperChat/SuperSticker donation mapping), and `DiscordAdapter` (Discord REST API v10 polling + bot filtering), multi-adapter registry on `ChatReceiver`, and `GET /api/platforms/status`.
- **Configuration Center (`config/settings.json`, `core/config_manager.py`, `web/settings.html`, `web/settings.js`):** Added `llm.streaming_enabled`, `memory.embedding_provider`, `youtube` (`api_key` masked as `"********"`), and `discord` (`bot_token` masked as `"********"`) with atomic save preservation and `/settings` UI sections.

### Tests & Documentation
- **New Test Coverage:** Added `tests/test_event_bus.py`, `tests/test_streaming_tts.py`, `tests/test_semantic_memory.py`, `tests/test_platforms.py`, and `tests/test_overlay_route.py` (all offline/mocked with `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)`).
- **Verified Suite:** `246` Python unit/integration tests passing (`0` failures, `0` errors) + `tests/test_guard_runner.js` passing.
- **Documentation:** Updated `README.md`, `CHANGELOG.md`, and `.env.example` (added `YOUTUBE_API_KEY`, `DISCORD_BOT_TOKEN`, `MAYBEAI_EMBEDDING_PROVIDER`).

---

## [2026-11-25] — Quick Wins: Security, Performance, Config UI, Tests & Docs (`400b32a`)

### Security & Trust
- **Origin Validation (`run.py`):** Added `_is_allowed_origin()` and `verify_api_origin_middleware` to reject untrusted `Origin` headers on mutating `/api/*` endpoints (`POST`/`PUT`/`PATCH`/`DELETE`, HTTP `403`) and `/ws` connections (WebSocket close code `1008`). Allows localhost origins and configured `security.allowed_origins`.
- **Strict Creator Authorization (`run.py`, `core/chat_receiver.py`, `core/conversation/chat_curator.py`, `core/orchestrator.py`, `web/app.js`):**
  - Removed username-based Creator privilege grants (`"creator"`, `"admin"`, `"evanh"`).
  - `/ws` Creator status now requires a loopback client host (`127.0.0.1`, `::1`, `localhost`) and, when `MAYBEAI_CREATOR_TOKEN` or `security.creator_token` is configured, a matching `?token=` query parameter verified with `secrets.compare_digest`.
  - Unauthorized connections have `is_creator` forced to `False` and `source` `"creator"`/`"mic"` downgraded to `"web"`.
  - `web/app.js` reads `?token=` from URL or `localStorage.maybeai_creator_token` and appends it to `/ws` when present.
- **Safe App Launching (`core/desktop/controller.py`):** Removed `shell=True`, added shell metacharacter and `..` traversal rejection, enforced `allowed_apps`, resolved executable paths, and launched via `subprocess.Popen([resolved_path])` (or `os.startfile` for `.lnk`).

### Performance & Concurrency
- **HTTP Session Reuse & Gemini Header (`core/brain.py`, `core/vision/vlm.py`):** Reused a lazily created `aiohttp.ClientSession` with `async def close()` wired into `Orchestrator.shutdown()`/`close()`. Moved Gemini API key from `?key=` URL query to `x-goog-api-key` header.
- **Provider Persistence & Env Override (`core/brain.py`):** Updated `Brain.set_provider()` to persist via `ConfigManager.save_config()` with atomic `.tmp` + `os.replace` fallback, and added `MAYBEAI_LLM_PROVIDER` environment override.
- **TTS Resource Hygiene (`core/tts.py`):** Guarded `pygame.mixer.init()` to initialize once and deleted temporary `speech_*.mp3` files in `finally`.
- **Concurrency & Async Vision (`core/orchestrator.py`, `core/vision/capture.py`, `core/vision/engine.py`):** Replaced bare `is_busy` boolean checks with `asyncio.Lock` (`_busy_lock`, preserving `@property def is_busy`), and offloaded `VisionEngine.perceive()` to `asyncio.to_thread()` with thread-local `mss` and `threading.Lock`.

### Configuration Center (`/settings`)
- **STT & Security Settings (`core/config_manager.py`, `config/settings.json`, `web/settings.html`, `web/settings.js`):**
  - Exposed `stt` (`enabled`, `model`, `device`) and `security` (`creator_token` masked as `"********"`, `allowed_origins` list editor) in `/settings`.
  - Preserved masked `"********"` secrets on atomic `.tmp` + `os.replace()` saves.

### Tests & QA
- **Test Hygiene (`tests/__init__.py`, `tests/test_*.py`):** Defaulted `MAYBEAI_LLM_PROVIDER="mock"` in `tests/__init__.py` and converted hardcoded `data/test_*` paths across 8 test modules to `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)`.
- **New Coverage:** Added `tests/test_vts_client.py`, `tests/test_chat_receiver.py`, `tests/test_tts.py`, `tests/test_brain.py`, `tests/test_websocket_security.py`, `TestDesktopController` security tests in `tests/test_desktop_companion.py`, and non-creator `"Admin"` guardrail coverage in `tests/test_chess.py`; fixed intermittent `test_dice_roll_mechanics` assertion in `tests/test_storytelling.py`.
- **Verified Suite:** `208` Python tests passing (`0` failures, `0` errors) + `tests/test_guard_runner.js` passing.

### Documentation & Repository
- **`README.md`, `LICENSE`, `.env.example`:** Synced `README.md` with actual `/ws` protocol, real chat commands, all 37 HTTP routes, default `gemini-3-flash-preview` + mock fallback, `[emotion: x]`/`[action: x]` tags, Security & Config documentation, directory tree, and test counts; added MIT `LICENSE` (`EvanH 2026`) and `.env.example` with `MAYBEAI_LLM_PROVIDER` and `MAYBEAI_CREATOR_TOKEN`.

---

## [2026-11-17] — Dual Chat Channels & Desktop Fixes (`a0d2ca8`, `f514f2a`)
- Separated **Creator VIP** (`👑 Chat Saya`) and **Audience Stream** (`👥 Stream Chat`) panels in `web/index.html`, `web/style.css`, and `web/app.js`, relocating the Voice/STT microphone dock into the Creator panel.
- Added Creator priority queue (`priority_score = 350.0`) and audience guardrails for `!desktop`, `!mc mode/server`, and `!chess elo/new`.
- Implemented Windows app launching (`os.startfile` / `subprocess.Popen`) and chat command routing in `core/desktop/controller.py` and `core/orchestrator.py`.
