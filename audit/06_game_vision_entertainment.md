# Game, Vision & Entertainment Engines Audit (`audit/06_game_vision_entertainment.md`)

**Auditor:** Agent 5 (`ng-games` — Game, Vision & Entertainment Engines Auditor)  
**Scope:** Post-H0/H1/H3 + `83298fa` implementations in `minecraft/`, `core/minecraft/`, `core/chess/`, `core/minigames/`, `core/storytelling/`, `core/vision/`, `core/performance/`, `core/singer.py`, `core/youtube_karaoke.py`, `core/desktop/obs_client.py`, and `core/highlights/`.  
**Rules Compliance:** No source files were modified. All claims are grounded in direct code inspection, environment binary/package checks, and test execution in this session.

---

## 1. Executive Summary & L0–L5 Maturity Scores

Post-H0/H1/H3 and commit `83298fa` resolved the highest-severity runtime hazards identified in the earlier audit (`chess.Board` worker-thread mutation, `VisualAnalyzer` `scene_label` `TypeError`, `OBSWebSocketClient` stale `is_connected=True` on error, `bot.js` timer leaks + `EADDRINUSE` zombie processes, `HighlightDetector` sync `replay_saved` ordering, `ClipPipeline` path confinement, and clock-locked `Singer` playback + `YouTubeKaraokeProcessor`).

| Domain | Maturity Score | Status | Key Rationale |
| :--- | :---: | :--- | :--- |
| **Vision** | **L3** | Functional / Heuristic | `VisualAnalyzer` `scene_label` crash fixed; `VisionEngine.aperceive_with_vlm()` + `MultimodalVisionModel` cooldown/structured output work, but local classification remains color-heuristic and VLM output only patches `obs.summary` post-hoc. |
| **Minecraft** | **L3** | Hardened Bridge | `bot.js` `clearAllIntervals()` + `EADDRINUSE` exit + `MinecraftController._listen_bridge()` `finally` state reset are solid; `startAutonomyLoop()` remains uncalled and no auto-reconnect loop exists on mid-session crash. |
| **Entertainment** (Karaoke, YouTube, Performance, Chess, MiniGames, Storytelling) | **L3** | Rich / Multi-Engine | `ChessEngine` `board.copy()` + Stockfish UCI fallback, `Singer` `vocal_track` + clock-locked cues, `YouTubeKaraokeProcessor` SSRF/VTT/cache/RVC pipeline, and `StoryEngine` showrunner hooks are implemented. External media binaries (`yt-dlp`, `ffmpeg`, `demucs`, `stockfish`) are absent on this host so live E2E media execution is unverified. |
| **OBS** | **L3** | Resilient Wrapper | `OBSWebSocketClient` resets `is_connected=False` and `_client=None` on runtime errors and handles missing `obsws-python` cleanly; lacks `get_replay_buffer_status()` sync, config-change reconnect, and auto-reconnect. |
| **Highlights** | **L3** | Event-Driven + Confined | `HighlightDetector` sets `replay_saved` before `HIGHLIGHT_MARKED` for sync callbacks; `ClipPipeline` enforces `is_relative_to()` path confinement and filtergraph escaping. Async `save_replay_buffer` updates `replay_saved` post-publish; `ClipPipeline.get_status()` is still absent. |
| **VOD** | **L3** | Reliable Markdown Export | `VODSummarizer` subscribes to `EventBus` and writes collision-safe `YYYY-MM-DD.md` summaries to Second Brain; `VODSummarizer.get_status()` is still absent (guarded by `hasattr` in `run.py`). |

---

## 2. Capability Classification Matrix

| Capability | Classification | Evidence & Notes |
| :--- | :--- | :--- |
| **Chess Thread-Safe Search & Stockfish UCI Fallback** | `EXISTING` | `VERIFIED` — [core/chess/controller.py](file:///d:/projects/MaybeAI/core/chess/controller.py#L203-L213), [core/chess/chess_engine.py](file:///d:/projects/MaybeAI/core/chess/chess_engine.py#L105-L175), [core/chess/chess_engine.py](file:///d:/projects/MaybeAI/core/chess/chess_engine.py#L298-L321). |
| **Minecraft Disconnect Recovery & `bot.js` Timer Cleanup** | `EXISTING` | `VERIFIED` — [core/minecraft/controller.py](file:///d:/projects/MaybeAI/core/minecraft/controller.py#L361-L376), [minecraft/bot.js](file:///d:/projects/MaybeAI/minecraft/bot.js#L69-L100), [minecraft/bot.js](file:///d:/projects/MaybeAI/minecraft/bot.js#L466-L499). |
| **Minecraft `startAutonomyLoop()` Idle Behavior** | `INCOMPLETE` | `VERIFIED` — Defined at [minecraft/bot.js](file:///d:/projects/MaybeAI/minecraft/bot.js#L229-L288) and cleared on mode switch, but never invoked. |
| **YouTube Song Request & Auto-Karaoke Pipeline** | `EXISTING` | `VERIFIED` (unit/mocked) / `NOT VERIFIED` (live YouTube download due to missing `yt-dlp`/`ffmpeg`/`demucs`) — [core/youtube_karaoke.py](file:///d:/projects/MaybeAI/core/youtube_karaoke.py). |
| **Singer `vocal_track` & Clock-Locked Scheduling** | `EXISTING` | `VERIFIED` — [core/singer.py](file:///d:/projects/MaybeAI/core/singer.py#L219-L404). |
| **VisualAnalyzer `scene_label` & VLM Cooldown/Structured Output** | `EXISTING` | `VERIFIED` — [core/vision/analyzer.py](file:///d:/projects/MaybeAI/core/vision/analyzer.py#L29-L36), [core/vision/vlm.py](file:///d:/projects/MaybeAI/core/vision/vlm.py#L32-L96). |
| **OBSWebSocketClient Disconnect Reset & Missing `obsws-python` Fallback** | `EXISTING` | `VERIFIED` — [core/desktop/obs_client.py](file:///d:/projects/MaybeAI/core/desktop/obs_client.py#L62-L92), [core/desktop/obs_client.py](file:///d:/projects/MaybeAI/core/desktop/obs_client.py#L165-L314). |
| **HighlightDetector `replay_saved` Ordering & Showrunner Hooks** | `EXISTING` | `VERIFIED` (sync) / `PARTIALLY VERIFIED` (async `on_save_replay` mutates post-publish) — [core/highlights/detector.py](file:///d:/projects/MaybeAI/core/highlights/detector.py#L106-L166), [core/storytelling/engine.py](file:///d:/projects/MaybeAI/core/storytelling/engine.py#L62-L110). |
| **ClipPipeline Path Confinement & Subtitles Escaping** | `EXISTING` | `VERIFIED` — [core/highlights/clipper.py](file:///d:/projects/MaybeAI/core/highlights/clipper.py#L10-L34), [core/highlights/clipper.py](file:///d:/projects/MaybeAI/core/highlights/clipper.py#L102-L145). |
| **ClipPipeline / VODSummarizer `.get_status()`** | `INCOMPLETE` | `VERIFIED` — [run.py](file:///d:/projects/MaybeAI/run.py#L336-L337) checks `hasattr(clipper, "get_status")` and `hasattr(vod, "get_status")`; neither class implements `get_status()`. |
| **Live VLM-Grounded Commentary & OBS Auto-Reconnect** | `PLANNED` | `VERIFIED` — VLM summary does not drive `generate_commentary()`; OBS has no background reconnect loop. |

---

## 3. Detailed Component Verification

### 3.1 Chess Engine (`core/chess/chess_engine.py`, `core/chess/controller.py`)
- **Claim: `chess.Board.copy()` thread safety** — **`VERIFIED`**
  - `ChessController.amake_bot_move()` ([core/chess/controller.py:203-213](file:///d:/projects/MaybeAI/core/chess/controller.py#L203-L213)) clones `board_copy = self.engine.board.copy()` before calling `await asyncio.to_thread(self.engine.choose_move, board_copy)`.
  - `ChessEngine.choose_move()` ([core/chess/chess_engine.py:298-300](file:///d:/projects/MaybeAI/core/chess/chess_engine.py#L298-L300)) also clones `search_board = board.copy() if board is not None else self.board.copy()`, isolating `alpha_beta()` `push()`/`pop()` mutations from `self.engine.board`.
  - After `to_thread` returns, `amake_bot_move()` re-checks `self._can_bot_move()` and `best_move in self.engine.board.legal_moves` before `_apply_bot_move()`.
  - *Remaining minor gap:* `_delayed_bot_move` ([core/chess/controller.py:144](file:///d:/projects/MaybeAI/core/chess/controller.py#L144)) is still spawned via `asyncio.create_task` without cancellation on `start_game()`/`resign_game()`.
- **Claim: Stockfish UCI fallback** — **`VERIFIED`**
  - `ChessEngine.__init__()` ([core/chess/chess_engine.py:105-111](file:///d:/projects/MaybeAI/core/chess/chess_engine.py#L105-L111)) locates `shutil.which("stockfish")` when `use_stockfish=True`.
  - `_ensure_stockfish()` / `_choose_move_stockfish()` ([core/chess/chess_engine.py:138-165](file:///d:/projects/MaybeAI/core/chess/chess_engine.py#L138-L165)) catch UCI launch/play exceptions, mark `self._stockfish_failed = True`, call `self.close()`, and fall through to `alpha_beta()` in `choose_move()`.

### 3.2 Minecraft (`core/minecraft/controller.py`, `minecraft/bot.js`)
- **Claim: `MinecraftController` disconnect recovery** — **`VERIFIED`**
  - `_listen_bridge()` `finally` block ([core/minecraft/controller.py:361-376](file:///d:/projects/MaybeAI/core/minecraft/controller.py#L361-L376)) closes `self.bridge_ws`, sets `self.bridge_ws = None`, resets `connection_status = "disconnected"`, `is_active = False`, `viewer_url = None`, and emits state.
  - `connect_to_server()` ([core/minecraft/controller.py:413-424](file:///d:/projects/MaybeAI/core/minecraft/controller.py#L413-L424)) and `send_bridge_cmd()` ([core/minecraft/controller.py:473-479](file:///d:/projects/MaybeAI/core/minecraft/controller.py#L473-L479)) also reset those fields on WebSocket send errors.
  - *Remaining gap:* There is no automatic reconnect/respawn loop if `bot.js` crashes mid-session; recovery requires calling `connect_to_server()` again.
- **Claim: `bot.js` timer cleanup & `EADDRINUSE` handling** — **`VERIFIED`**
  - `clearAllIntervals()` ([minecraft/bot.js:69-75](file:///d:/projects/MaybeAI/minecraft/bot.js#L69-L75)) clears `autonomyInterval`, `telemetryInterval`, `proximityInterval`, `danceInterval`, and `telemetryDebounceTimer`.
  - `cleanupBotResources()` ([minecraft/bot.js:77-85](file:///d:/projects/MaybeAI/minecraft/bot.js#L77-L85)) closes `bot.viewer`, stops `speedrunRunner`/`casualRunner`/`guardRunner`, and invokes `clearAllIntervals()` on `createBot()`, `kicked`, `end`, `disconnect_server`, and `wsServer` `EADDRINUSE` (`process.exit(1)` at [minecraft/bot.js:93-97](file:///d:/projects/MaybeAI/minecraft/bot.js#L93-L97)).
  - *Remaining gap:* `startAutonomyLoop()` ([minecraft/bot.js:229](file:///d:/projects/MaybeAI/minecraft/bot.js#L229)) is still never called; `uncaughtException` ([minecraft/bot.js:6-12](file:///d:/projects/MaybeAI/minecraft/bot.js#L6-L12)) logs and emits `bot_error` without exiting.

### 3.3 YouTube Karaoke (`core/youtube_karaoke.py`)
- **Claim: `yt-dlp`, `ffmpeg`, `demucs`, `RVCVoiceConverter`, VTT/SRT parser, `data/karaoke_cache/`** — **`PARTIALLY VERIFIED`** (unit-tested with mocks; live binary execution `NOT VERIFIED` on this host because `yt-dlp`, `ffmpeg`, and `demucs` are not installed)
  - **URL & SSRF Guard:** `extract_youtube_video_id()` ([core/youtube_karaoke.py:49-77](file:///d:/projects/MaybeAI/core/youtube_karaoke.py#L49-L77)) calls `validate_outbound_url(..., allowed_schemes=("https", "http"), allow_private=False)`, restricts host to `_YOUTUBE_HOSTS`, and validates 11-char `_VIDEO_ID_RE`, canonicalizing to `https://www.youtube.com/watch?v=<video_id>`.
  - **Subprocess Execution:** `_run_exec()` ([core/youtube_karaoke.py:159-178](file:///d:/projects/MaybeAI/core/youtube_karaoke.py#L159-L178)) uses `asyncio.create_subprocess_exec` (no `shell=True`) with `asyncio.wait_for` timeout + `proc.kill()`.
  - **Stem Separation & Fallback:** Uses `sys.executable -m demucs --two-stems=vocals` when `demucs` is available and `mode == "ai_cover"`; otherwise falls back to `ffmpeg -af pan=stereo|c0=c0-c1|c1=c1-c0` ([core/youtube_karaoke.py:292-332](file:///d:/projects/MaybeAI/core/youtube_karaoke.py#L292-L332)).
  - **RVC Conversion:** When `rvc_converter` is enabled with `rvc_url`, `RVCVoiceConverter.convert()` ([core/tts_providers.py:667-701](file:///d:/projects/MaybeAI/core/tts_providers.py#L667-L701)) validates `rvc_url` via `validate_outbound_url` and falls back to original audio bytes on HTTP/network failure.
  - **VTT/SRT Parser:** `parse_captions_to_lyrics()` ([core/youtube_karaoke.py:80-126](file:///d:/projects/MaybeAI/core/youtube_karaoke.py#L80-L126)) parses VTT/SRT timestamps, strips `<...>` tags, skips numeric cue indices, and deduplicates consecutive identical rolling auto-captions.
  - **Cache:** Stores `meta.json`, `source.wav`, `instrumental.wav`, `vocals.wav`, `eve_vocals.wav` under `data/karaoke_cache/<video_id>/` (respecting `MAYBEAI_DATA_DIR`), validating `bgm`, `vocal_track`, and `mode` before returning cached results ([core/youtube_karaoke.py:200-216](file:///d:/projects/MaybeAI/core/youtube_karaoke.py#L200-L216)).

### 3.4 Singer (`core/singer.py`)
- **Claim: `vocal_track` + clock-locked scheduling** — **`VERIFIED`**
  - `vocal_track` mode ([core/singer.py:292-377](file:///d:/projects/MaybeAI/core/singer.py#L292-L377)) reads `vocal_track`, emits `on_vocal_audio` for browser playback, extracts 50ms RMS envelope (`extract_rms_envelope_from_sound` / `extract_rms_envelope_from_wav`), plays via `pygame.mixer.Sound`, and dispatches sorted lyrics (`cue_sec` / `timestamp_sec` / `start_sec` / `time`) + lip-sync against `_get_playback_clock_sec()`.
  - `_get_playback_clock_sec()` ([core/singer.py:219-233](file:///d:/projects/MaybeAI/core/singer.py#L219-L233)) anchors to `pygame.mixer.music.get_pos()` when server BGM is playing and falls back to `time.monotonic() - start_time`. Line-by-line mode uses `_wait_until_clock()` ([core/singer.py:235-248](file:///d:/projects/MaybeAI/core/singer.py#L235-L248)).

### 3.5 Vision (`core/vision/analyzer.py`, `core/vision/vlm.py`, `core/vision/engine.py`)
- **Claim: `VisualAnalyzer` `scene_label` fix** — **`VERIFIED`**
  - [core/vision/analyzer.py:30-36](file:///d:/projects/MaybeAI/core/vision/analyzer.py#L30-L36) now passes `scene_label="Desktop"` when `not HAS_PIL or image is None`, eliminating the previous `TypeError` on `VisualObservation(detected_label=...)`.
  - `MultimodalVisionModel` ([core/vision/vlm.py:32-96](file:///d:/projects/MaybeAI/core/vision/vlm.py#L32-L96)) provides `can_emit_commentary()`, `generate_periodic_commentary()`, and `build_structured_output()` with cooldown gating.

### 3.6 OBS Client (`core/desktop/obs_client.py`)
- **Claim: `OBSWebSocketClient` disconnect reset** — **`VERIFIED`**
  - `switch_scene()`, `toggle_streaming()`, `start_replay_buffer()`, `save_replay_buffer()`, and `set_source_visibility()` ([core/desktop/obs_client.py:165-314](file:///d:/projects/MaybeAI/core/desktop/obs_client.py#L165-L314)) all set `self.is_connected = False` and `self._client = None` in their `except Exception` handlers and return `"connected": False`.
  - *Remaining gap:* `_sync_initial_state()` ([core/desktop/obs_client.py:94-127](file:///d:/projects/MaybeAI/core/desktop/obs_client.py#L94-L127)) still does not query `get_replay_buffer_status()`.

### 3.7 Highlights & Clip Pipeline (`core/highlights/detector.py`, `core/highlights/clipper.py`)
- **Claim: `HighlightDetector` `replay_saved` ordering** — **`PARTIALLY VERIFIED`**
  - `_record_marker()` ([core/highlights/detector.py:160-165](file:///d:/projects/MaybeAI/core/highlights/detector.py#L160-L165)) assigns `marker.replay_saved = self._trigger_replay_callback(marker)` BEFORE `self._markers.append(marker)` and BEFORE `self.event_bus.publish_nowait(HIGHLIGHT_MARKED, marker.to_dict())`.
  - However, when `on_save_replay` is async (such as `Orchestrator._on_highlight_save_replay` -> `obs.save_replay_buffer()` at [core/orchestrator.py:282-286](file:///d:/projects/MaybeAI/core/orchestrator.py#L282-L286)), `_trigger_replay_callback()` ([core/highlights/detector.py:119-126](file:///d:/projects/MaybeAI/core/highlights/detector.py#L119-L126)) spawns `_await_replay_result` as a background task and returns `False` synchronously, so the published `HIGHLIGHT_MARKED` event payload still carries `replay_saved: False` initially and `marker.replay_saved` is mutated asynchronously upon completion.
- **Claim: `ClipPipeline` path confinement** — **`VERIFIED`**
  - `_resolve_confined_path()` ([core/highlights/clipper.py:25-34](file:///d:/projects/MaybeAI/core/highlights/clipper.py#L25-L34)) enforces `resolved.is_relative_to(base_dir)` on `input_path`, `output_path`, and `subtitle_path`, rejecting traversal (`../`) and outside absolute paths with `ValueError`.
  - `_escape_ffmpeg_filter_path()` ([core/highlights/clipper.py:10-15](file:///d:/projects/MaybeAI/core/highlights/clipper.py#L10-L15)) escapes `\`, `:`, `'`, `,`, `[`, `]`, `;` before embedding in `subtitles='...'`.

---

## 4. Missing External Binary & Optional Package Behavior

Direct check in this workspace environment:
- `yt-dlp`: **Missing** (`Get-Command yt-dlp` empty) -> `YouTubeKaraokeProcessor.tools_available()["yt_dlp"] == False`; `prepare_song()` raises `YouTubeKaraokeError("yt-dlp is not installed on PATH.")` cleanly (`VERIFIED`).
- `ffmpeg`: **Missing** (`Get-Command ffmpeg` empty) -> `YouTubeKaraokeProcessor.prepare_song()` raises `YouTubeKaraokeError("ffmpeg is not installed on PATH.")`; `ClipPipeline.create_vertical_clip()` returns `{"success": False, "error": "ffmpeg executable not found in PATH"}` (`VERIFIED`).
- `demucs`: **Missing** (`find_spec("demucs") is None`) -> `YouTubeKaraokeProcessor.prepare_song()` falls back to `ffmpeg` center-channel cancellation and copies `source.wav` to `vocals.wav` in `ai_cover` mode (`VERIFIED` by code inspection).
- `stockfish`: **Missing** (`Get-Command stockfish` empty) -> `ChessEngine.backend == "alpha_beta"`; `choose_move()` uses internal alpha-beta search cleanly (`VERIFIED`).
- `obsws-python`: **Missing** (`find_spec("obsws_python") is None`) -> `OBSWebSocketClient.connect()` returns `False` with `last_error="obsws-python is not installed"` (`VERIFIED`).
- `node`: **Present** (`C:\Program Files\nodejs\node.exe` and `minecraft/node/node.exe`).

---

## 5. Test Execution Evidence

Executed in this session without modifying any files:
1. `.\.venv\Scripts\python.exe -W default -m unittest tests.test_chess tests.test_vision tests.test_highlights_and_vod tests.test_storytelling tests.test_neural_tts_rvc tests.test_youtube_karaoke` → **53 tests OK** (6.535s).
2. `.\.venv\Scripts\python.exe -W default -m unittest tests.test_minigames tests.test_obs_showrunner tests.test_performance tests.test_guard_mode tests.test_multiplayer_social` → **51 tests OK** (0.856s).
3. `node tests/test_guard_runner.js` → **All GuardRunner tests passed**.

Total verified in this audit slice: **104 Python unit tests + GuardRunner JS suite passing**. Live external media/binary flows (`yt-dlp`, `ffmpeg`, `demucs`, `stockfish`, `OBS Studio`) remain `NOT VERIFIED` live on this host due to missing binaries.
