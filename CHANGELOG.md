# Changelog

All notable changes to **MaybeAI (Eve Maybe)** are documented in this file.

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
