# Changelog

All notable changes to **MaybeAI (Eve Maybe)** are documented in this file.

## [2026-11-26] — Fase 1 Hardening: Security Parity, Browser Audio Unification & Packaging

### Security & Auth Parity
- **Secret Masking in Live Broadcasts (`core/orchestrator.py`):** Masked `ConfigManager.SECRET_MASK_FIELDS` (`creator_token`, `shared_secret`, `oauth_token`, `api_key`, `bot_token`) to `"********"` in `configuration_updated` WebSocket broadcasts via `_mask_settings_for_broadcast()`.
- **HTTP `/api/*` & `/ws` Auth Parity (`run.py`):** Added `_is_http_creator_authorized()` enforcing `creator_token` (`X-Creator-Token` / `Authorization: Bearer`) or loopback-only access on mutating `/api/*` routes and `GET /api/config`. Enforced `ws_creator_authorized` on all mutating `/ws` actions (`config_action`, `desktop_action`, `minecraft_action`, `chess_action`, `set_llm_provider`, `personality_action`, `performance_action`, `vision_action`, `goal_action`).
- **Mock-Mode Desktop Guardrail & Async Performance (`core/conversation/engine.py`, `core/brain.py`, `core/memory/database.py`, `core/chess/controller.py`):** Gated `DesktopController` actions in `generate_mock_response()` behind `is_creator=True`, switched `Brain` prompt building to async `abuild_system_prompt()`, enabled SQLite WAL mode, and added `ChessController.amake_bot_move()` offloaded via `asyncio.to_thread()`.
- **Collab `/ws/collab` Hardening (`run.py`, `core/collab/manager.py`):** Enforced Origin validation, strict `shared_secret` verification on loopback when configured, and per-connection `_inbound_senders` tracking (`register_peer_sender()` / `unregister_peer_sender()`).

### Browser Audio Unification & Frontend Hardening
- **Unified Audio Streaming (`core/tts.py`, `core/singer.py`, `core/orchestrator.py`):** Added `tts.output_mode` (`"both" | "browser" | "server"`), `audio_chunk` WebSocket streaming (`{"audio_b64", "mime": "audio/mpeg", ...}`), dedicated `pygame.mixer.Sound` channel playback (eliminating `pygame.mixer.music` BGM contention), guaranteed `vocal_*.mp3` cleanup in `Singer.sing()`, `Orchestrator._speech_lock` serialization, and `_bg_tasks` cancellation in `Orchestrator.shutdown()`.
- **Web Studio, OBS Overlay & Settings Sync (`web/app.js`, `web/overlay.js`, `web/overlay.css`, `web/settings.js`, `web/settings.css`, `web/style.css`, `core/config_manager.py`, `config/settings.json`):** Wired Web Audio API `AudioContext` + `AnalyserNode` RMS lip-sync and FIFO `audio_chunk` playback on `/` and `/overlay`, added `authFetch` + `escapeHtml()` XSS protection, added `@media (max-width: 900px)` responsive CSS, and synced `get_schema()` (`81` settings keys including `tts.output_mode`).

### Packaging, Launcher & Tests
- **Packaging & Launcher (`pyproject.toml`, `start.bat`, `.env.example`):** Added `pyproject.toml` with optional extras (`[stt-local]`, `[embeddings-local]`, `[dev]`), Windows one-click launcher `start.bat`, and marked reserved/future keys in `.env.example`.
- **Tests (`tests/test_fase1_hardening.py`, `tests/test_desktop_companion.py`, `tests/test_tts.py`, `tests/test_streaming_tts.py`):** Added `tests/test_fase1_hardening.py`, mocked `DesktopController.launch_app` in `test_desktop_companion.py` (eliminating `notepad.exe` `ResourceWarning`), and updated TTS mocks for `pygame.mixer.Sound`.
- **Verified Suite:** `283` Python unit/integration tests passing (`0` failures, `0` errors) + `tests/test_guard_runner.js` passing.

---

## [2026-11-25] — Long-Term Autonomous Vision: Full-Duplex Voice & Barge-In, Closed-Loop Missions, AI Collab Protocol & Plugin SDK

### Pillar 1 — Full-Duplex Voice & Barge-In
- **Energy VAD & Streaming STT (`core/stt.py`):** Added `VADResult`, `EnergyVAD` (NumPy/Python PCM16 & float32 RMS VAD with onset hysteresis `min_speech_frames` and hangover smoothing `hangover_frames`), `StreamingSTTSession` (`feed_pcm_chunk`, `flush`, pre-roll + in-memory WAV buffering), and `STTEngine.transcribe_wav_bytes()` / `transcribe_audio_file()` supporting `faster-whisper`, `openai-whisper`, OpenAI Whisper API, and deterministic offline mock fallback.
- **Interruptible TTS & Orchestrator Preemption (`core/tts.py`, `core/orchestrator.py`):** Upgraded `TTSEngine.stop(reason="barge_in")` to cleanly interrupt both `speak()` and `speak_stream()`, stop/unload `pygame.mixer.music`, reset mouth (`0.0`), and delete temporary `speech_*.mp3` files. Added `Orchestrator.barge_in()`, `Orchestrator.process_voice_chunk()`, and non-blocking `_active_interaction_task` cancellation (never acquiring `_busy_lock`, preventing deadlocks) plus auto-barge-in on authorized Creator `mic` input.
- **Voice Status, Creator-Only WS & Live VAD UI (`run.py`, `web/index.html`, `web/style.css`, `web/app.js`):** Added `GET /api/voice/status`, creator-only `/ws` `barge_in` and `voice_audio_chunk` handlers (rejecting non-creators with `code: "forbidden"`), `voice.barge_in` / `voice.vad_state` / `stt.final` EventBus events, and Web Audio API RMS/VAD bar + barge-in toggle in the Creator Voice Dock.

### Pillar 2 — Closed-Loop Autonomous Missions
- **Domain-Aware Planning & Execution (`core/planning/models.py`, `core/planning/decomposer.py`, `core/planning/engine.py`, `core/planning/executor.py`):** Added `GoalCategory.PERFORMANCE`, Performance/Karaoke & Chess decomposition templates, expanded `GoalEngine.evaluate_event()`, and implemented `AutonomousMissionExecutor` for closed-loop execution across Minecraft, Chess, Performance Director, and Social goals with `agenda.md` syncing, automatic `StrategyReplanner` fallback on failure, and `human_approval_required` (`approve_pending()` / `reject_pending()`).
- **Mission APIs, WS & Studio Controls (`core/orchestrator.py`, `run.py`, `web/index.html`, `web/app.js`):** Wired `Orchestrator.missions`, added `GET /api/missions/status`, `POST /api/missions/step`, `POST /api/missions/toggle`, creator-only `/ws` `mission_action`, and the Autonomous Missions control bar in the `Brain & Memory` tab.

### Pillar 3 — AI Collab Protocol & Community Plugin SDK
- **AI-to-AI Collab Protocol (`core/collab/protocol.py`, `core/collab/manager.py`, `run.py`):** Implemented `CollabEnvelope` with HMAC-SHA256 signing and constant-time `hmac.compare_digest` verification, `CollabManager` turn-taking floor state machine (`idle`, `speaking`, `yielding`, `listening`, `cooldown`), `max_collab_turns` & `turn_cooldown_sec` anti-loop protection, `send_duet_sync` / `send_emote_sync`, `/ws/collab` peer WebSocket (HMAC secret / loopback auth), `GET /api/collab/status`, `POST /api/collab/action`, and `#collabCard` studio controls.
- **Plugin SDK & Built-in Sambung Kata (`core/plugins/sdk.py`, `core/plugins/registry.py`, `core/plugins/word_chain.py`, `core/orchestrator.py`, `run.py`):** Built `PluginManifest`, sandboxed `PluginContext`, `MaybeAIPlugin`, `@plugin_command` / `@plugin_event`, and `PluginRegistry` with built-in/external plugin discovery, enable/disable/reload lifecycle, `asyncio.wait_for` timeout & exception isolation, `creator_only_commands` enforcement, `WordChainPlugin` (`!sambungkata` / `!wc`), `GET /api/plugins`, `POST /api/plugins/action`, and `#pluginsCard` studio controls.
- **Settings & Secret Masking (`config/settings.json`, `core/config_manager.py`, `web/settings.html`, `web/settings.js`):** Added `stt.vad_enabled` / `vad_energy_threshold` / `barge_in_enabled`, `autonomous_agent.closed_loop_missions` / `mission_tick_interval_sec`, and new `collab` & `plugins` categories in `/settings` (19 categories total), with `"********"` masking and preservation for `collab.shared_secret`.

### Tests & Documentation
- **New Test Coverage:** Added `tests/test_voice_duplex.py`, `tests/test_autonomous_missions.py`, and `tests/test_collab_and_plugins.py` (all offline/deterministic using `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)`).
- **Verified Suite:** `274` Python unit/integration tests passing (`0` failures, `0` errors) + `tests/test_guard_runner.js` passing.
- **Documentation:** Updated `README.md`, `CHANGELOG.md`, and `.env.example` (added `MAYBEAI_COLLAB_SECRET`).

---

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
