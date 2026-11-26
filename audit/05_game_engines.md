# Game Engine & External Runtime Audit (`audit/05_game_engines.md`)

**Auditor:** Agent 5 (`cto-games` — Game Engine & External Runtime Auditor)  
**Scope:** Minecraft (`minecraft/bot.js`, `core/minecraft/controller.py`), `mc_telemetry` flow (`core/orchestrator.py`), Chess (`core/chess/`), Mini-Games (`core/minigames/`), Storytelling/RPG (`core/storytelling/`), Vision/VLM (`core/vision/`), Karaoke/Singer (`core/singer.py`), Performance Director (`core/performance/director.py`), OBS Showrunner (`core/desktop/obs_client.py`, `run.py`), and Highlight Auto-Marker / Clip Pipeline (`core/highlights/`).  
**Evidence Basis:** Direct static inspection of source code in the current workspace. No source files were modified.

---

## 1. Capability Classification Matrix

### Current Capability (Implemented & Wired)
- **Minecraft Mineflayer WebSocket Bridge:** `MinecraftController` ([core/minecraft/controller.py](file:///d:/projects/MaybeAI/core/minecraft/controller.py)) spawns `minecraft/bot.js` via `subprocess.Popen` and communicates over `ws://localhost:25566`, supporting `connect_server`, `disconnect_server`, `set_mode` (`santai`, `kompe`, `guard`), `guard_player`, `advance_speedrun`, `chat`, movement/emote commands, and `mc_telemetry` streaming.
- **Chess Engine & Controller:** `ChessController` + `ChessEngine` ([core/chess/controller.py](file:///d:/projects/MaybeAI/core/chess/controller.py), [core/chess/chess_engine.py](file:///d:/projects/MaybeAI/core/chess/chess_engine.py)) provide `python-chess` board management, ELO-scaled alpha-beta search (depths 1–4 + blunder simulation), SAN/UCI move parsing, and `asyncio.to_thread` offloading.
- **Interactive Mini-Game Engine:** `MiniGameEngine` ([core/minigames/engine.py](file:///d:/projects/MaybeAI/core/minigames/engine.py)) implements 6 chat-driven modes (`trivia`, `guess_number`, `would_you_rather`, `riddle`, `word_association`, `guess_song`) with JSON leaderboard persistence and Second Brain Markdown sync.
- **Storytelling / RPG Engine:** `StoryEngine` ([core/storytelling/engine.py](file:///d:/projects/MaybeAI/core/storytelling/engine.py)) supports preset/custom campaigns, chat choice voting (`!1`/`!2`/`!3`), D20 dice rolls with morale modifiers, party HP/morale/gold tracking, and Second Brain Markdown sync.
- **Vision & VLM Pipeline:** `VisionEngine` + `ScreenCaptureManager` + `VisualAnalyzer` + `MultimodalVisionModel` ([core/vision/engine.py](file:///d:/projects/MaybeAI/core/vision/engine.py), [core/vision/capture.py](file:///d:/projects/MaybeAI/core/vision/capture.py), [core/vision/analyzer.py](file:///d:/projects/MaybeAI/core/vision/analyzer.py), [core/vision/vlm.py](file:///d:/projects/MaybeAI/core/vision/vlm.py)) perform `mss` screen capture with synthetic fallback, pixel-diff change detection, color-heuristic scene classification, and rate-limited Gemini/OpenAI VLM enrichment via `aperceive_with_vlm()`.
- **Karaoke / Singer & Performance Director:** `Singer` ([core/singer.py](file:///d:/projects/MaybeAI/core/singer.py)) synthesizes line-by-line vocals via `edge_tts` (+ optional RVC conversion), plays BGM/vocals via `pygame.mixer` or streams bytes to browser, and `PerformanceDirector` ([core/performance/director.py](file:///d:/projects/MaybeAI/core/performance/director.py)) manages setlists, choreography steps, glowstick cheers, and OBS scene triggers.
- **OBS Showrunner:** `OBSWebSocketClient` ([core/desktop/obs_client.py](file:///d:/projects/MaybeAI/core/desktop/obs_client.py)) wraps `obsws-python` (`ReqClient`) via `asyncio.to_thread` with offline fallback, scene mapping (`DEFAULT_SCENE_MAP`), streaming toggle, replay buffer start/save, and `/api/obs/status` + `/api/obs/action` in [run.py](file:///d:/projects/MaybeAI/run.py).
- **Highlight Auto-Marker, Clip Pipeline & VOD Summarizer:** `HighlightDetector` ([core/highlights/detector.py](file:///d:/projects/MaybeAI/core/highlights/detector.py)) subscribes to `EventBus` signals with cooldown deduplication; `ClipPipeline` ([core/highlights/clipper.py](file:///d:/projects/MaybeAI/core/highlights/clipper.py)) runs `ffmpeg` via `asyncio.create_subprocess_exec` (no `shell=True`) for 9:16 1080x1920 crops; `VODSummarizer` ([core/highlights/vod_summarizer.py](file:///d:/projects/MaybeAI/core/highlights/vod_summarizer.py)) writes session Markdown summaries on shutdown.

### Partially Implemented
- **Minecraft Autonomous Idle Loop:** `startAutonomyLoop()` is defined in [minecraft/bot.js](file:///d:/projects/MaybeAI/minecraft/bot.js#L198-L257) and its timer `autonomyInterval` is cleared in disconnect/mode-switch handlers, but `startAutonomyLoop()` is never invoked anywhere in `bot.js`.
- **Storytelling Freeform Actions & Dice Integration:** `StoryEngine.submit_freeform_action()` stores proposals in `freeform_suggestions`, and `new_scene` sets `requires_dice_roll=True`, but `advance_scene()` ignores both `freeform_suggestions` and `dice_result` and loops indefinitely past `scene_idx >= 4` using hardcoded beats.
- **Chess Endgame & Search Depth:** `ChessEngine` docstring claims Quiescence search, which is not implemented; `get_game_state()` omits 5-fold repetition and 75-move draw checks.
- **Highlights & VOD API Status:** `run.py` queries `clipper.get_status()` and `vod.get_status()`, neither of which exists on `ClipPipeline` or `VODSummarizer`.

### Planned Capability
- **Live VLM-Grounded Commentary:** Using VLM API descriptions directly inside `MultimodalVisionModel.generate_commentary()` rather than only patching `obs.summary` post-hoc.
- **OBS Health Monitoring & Auto-Reconnect:** Automatic reconnection and replay-buffer state synchronization on mid-stream WebSocket drops.

### Proposed Innovation
- **Audio-Clock-Locked Karaoke & Pre-Synthesis:** Pre-synthesizing upcoming lyric lines and synchronizing lyric/choreography cues to `pygame.mixer.music.get_pos()` (or browser AudioWorklet timestamps) to eliminate TTS network jitter drift.
- **Stockfish / NNUE Optional Chess Backend & Board Snapshots:** Passing `self.board.copy()` into `asyncio.to_thread` to guarantee thread safety during async search.

---

## 2. Critical & High-Severity Findings

### `[GAME-CRIT-001]` Unsynchronized `chess.Board` Mutation Across Event Loop and Worker Thread
- **Severity:** Critical
- **Evidence Classification:** `VERIFIED`
- **Location:** [core/chess/controller.py:197-206](file:///d:/projects/MaybeAI/core/chess/controller.py#L197-L206), [core/chess/controller.py:144-153](file:///d:/projects/MaybeAI/core/chess/controller.py#L144-L153), [core/chess/chess_engine.py:184-207](file:///d:/projects/MaybeAI/core/chess/chess_engine.py#L184-L207)
- **Symptom:** Calling `start_game()`, `resign_game()`, `make_player_move()`, or `get_status()` while `amake_bot_move()` is computing in a worker thread can corrupt the move stack (`IndexError` on `pop()`), produce illegal moves, or return inconsistent FEN/turn state.
- **Root Cause:** `amake_bot_move()` offloads `self.engine.choose_move` via `asyncio.to_thread(self.engine.choose_move)` (`controller.py:202`). Inside `choose_move()` -> `alpha_beta()` (`chess_engine.py:185-200`), `self.board.push(move)` and `self.board.pop()` mutate the shared `self.engine.board` instance in-place. Neither `ChessController` nor `ChessEngine` acquires a lock or clones `self.board` before searching, and `_delayed_bot_move` (`controller.py:144`) is spawned as an untracked `asyncio.create_task` that can overlap with `start_game()` or `resign_game()`.
- **Verification Steps:** Trigger `make_player_move()` (which schedules `_delayed_bot_move`), then invoke `start_game()` or `get_status()` while `alpha_beta` at depth 4 is running in the thread pool.
- **Blast Radius:** Complete Chess session corruption, unhandled `IndexError`/`AssertionError` in `python-chess`, and desynced Web UI board state.
- **Recommended Fix:** In `ChessEngine.choose_move()`, search on a cloned `board_copy = self.board.copy(stack=False)` (passing `board_copy` into `alpha_beta` and `evaluate_board`), cancel any pending `_delayed_bot_move` task on `start_game()`/`resign_game()`, and guard state transitions with an `asyncio.Lock`.

---

### `[GAME-CRIT-002]` Minecraft Node.js Bridge Has No Crash Recovery, Leaks Timers, and Silently Swallows Fatal Exceptions
- **Severity:** Critical
- **Evidence Classification:** `VERIFIED`
- **Location:** [core/minecraft/controller.py:183-212](file:///d:/projects/MaybeAI/core/minecraft/controller.py#L183-L212), [core/minecraft/controller.py:340-343](file:///d:/projects/MaybeAI/core/minecraft/controller.py#L340-L343), [minecraft/bot.js:6-9](file:///d:/projects/MaybeAI/minecraft/bot.js#L6-L9), [minecraft/bot.js:417-432](file:///d:/projects/MaybeAI/minecraft/bot.js#L417-L432)
- **Symptom:** If `bot.js` crashes or `ws://localhost:25566` drops, `MinecraftController` never restarts the process or reconnects, leaving `connection_status == "connected"` and `is_active == True` indefinitely. On server reconnects, `bot.js` leaks `setInterval` timers, multiplying `player_nearby` events.
- **Root Cause:**
  1. `_listen_bridge()` (`controller.py:340-343`) catches `Exception`, breaks, and sets `self.bridge_ws = None` without updating `connection_status` / `is_active` or scheduling a reconnect/restart. `_ensure_bridge_running()` is only called inside `connect_to_server()`.
  2. `subprocess.Popen([node_cmd, "bot.js"], cwd="minecraft")` (`controller.py:193-196`) does not capture stdout/stderr or monitor process exit. If a previous `bot.js` is still bound to port `25566`, the new `bot.js` logs `EADDRINUSE` (`bot.js:66-68`) without exiting, while Python connects to the stale instance.
  3. `bot.js:6-9` installs `process.on('uncaughtException', ...)` that swallows all uncaught errors, masking corrupt runtime state.
  4. `bot.js:417-432` creates an unstored `setInterval(..., 3000)` inside `createBot()` that is never cleared on `kicked`, `end`, or `disconnect_server`.
- **Verification Steps:** Inspect `core/minecraft/controller.py:340-343` and `minecraft/bot.js:417-432`; kill the `node` process while connected and observe `MinecraftController.get_status()` remains `"connected"`.
- **Blast Radius:** Total loss of Minecraft bot control, stale UI/LLM game context (`Playing in Minecraft`), and escalating event/CPU load on reconnects.
- **Recommended Fix:** Store and clear the proximity `setInterval` ID in `bot.js`; exit on `wsServer` `EADDRINUSE` instead of continuing; update `connection_status = "disconnected"` and `is_active = False` in `_listen_bridge()` `finally` block; add bounded exponential-backoff healthcheck/restart when `is_active` is expected.

---

### `[GAME-HIGH-001]` `VisualAnalyzer.analyze_frame()` Crashes With `TypeError` When Pillow Is Missing or Image Is `None`
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** [core/vision/analyzer.py:29-36](file:///d:/projects/MaybeAI/core/vision/analyzer.py#L29-L36), [core/vision/models.py:20-32](file:///d:/projects/MaybeAI/core/vision/models.py#L20-L32)
- **Symptom:** In environments without `Pillow` (or when `generate_mock_scene()` returns `None` and `perceive()` passes it to `analyze_frame()`), `VisualObservation(...)` raises `TypeError: VisualObservation.__init__() got an unexpected keyword argument 'detected_label'`.
- **Root Cause:** `VisualObservation` defines `scene_label: str`, not `detected_label`. `VisualAnalyzer.analyze_frame()` passes `detected_label="Desktop"` at `analyzer.py:33`.
- **Verification Steps:** Call `VisualAnalyzer.analyze_frame(None)` and observe `TypeError`.
- **Blast Radius:** Crashes the background vision perception loop (`Orchestrator` auto-perception) in headless/minimal deployments lacking Pillow.
- **Recommended Fix:** Replace `detected_label="Desktop"` with `scene_label="Desktop"` in `core/vision/analyzer.py:33`.

---

### `[GAME-HIGH-002]` `OBSWebSocketClient` Leaves `is_connected=True` on Runtime Errors and Lacks Reconnect / Config-Reload Handling
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** [core/desktop/obs_client.py:165-173](file:///d:/projects/MaybeAI/core/desktop/obs_client.py#L165-L173), [core/desktop/obs_client.py:203-253](file:///d:/projects/MaybeAI/core/desktop/obs_client.py#L203-L253), [core/desktop/obs_client.py:306-327](file:///d:/projects/MaybeAI/core/desktop/obs_client.py#L306-L327)
- **Symptom:** If OBS Studio closes or the WebSocket drops mid-stream, `switch_scene()`, `toggle_streaming()`, `start_replay_buffer()`, and `save_replay_buffer()` fail with exceptions while returning `"connected": self.is_connected` (`True`), and never attempt to reconnect. Hot-reloading `host`/`port`/`password` via `update_config()` also leaves the old client connected.
- **Root Cause:** Exception handlers in `obs_client.py` set `self.last_error = str(exc)` without checking connection loss or resetting `self.is_connected = False` / `self._client = None`. `_sync_initial_state()` (`obs_client.py:94-127`) also does not query `get_replay_buffer_status()`, so `replay_buffer_active` can be out of sync with OBS.
- **Verification Steps:** Connect `OBSWebSocketClient`, terminate OBS, then call `switch_scene("Minecraft")`; observe `connected` remains `True` in `get_status()`.
- **Blast Radius:** Silent failure of autonomous scene switching (Minecraft/Collab/Karaoke) and highlight replay buffer saves for the rest of the stream session.
- **Recommended Fix:** Detect closed-socket/connection errors in `OBSWebSocketClient` methods to reset `is_connected = False` and trigger a single reconnect attempt; query `get_replay_buffer_status()` in `_sync_initial_state()`; reconnect in `apply_configuration_hot_reload()` when connection parameters change.

---

### `[GAME-HIGH-003]` `HighlightDetector` Marks `replay_saved=True` Before Async OBS Save Completes or Even When Skipped
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** [core/highlights/detector.py:94-109](file:///d:/projects/MaybeAI/core/highlights/detector.py#L94-L109), [core/highlights/detector.py:139](file:///d:/projects/MaybeAI/core/highlights/detector.py#L139), [core/orchestrator.py:261-265](file:///d:/projects/MaybeAI/core/orchestrator.py#L261-L265)
- **Symptom:** `HighlightMarker.replay_saved` is recorded as `True` whenever `on_save_replay` is an `async` function, even if OBS is disconnected (`{"success": False, "skipped": True}`) or `save_replay_buffer()` later fails.
- **Root Cause:** `_trigger_replay_callback()` schedules `loop.create_task(res)` (`detector.py:102`) and immediately returns `True` (`detector.py:106`). `Orchestrator._on_highlight_save_replay()` (`orchestrator.py:261-265`) is `async` and returns `{"success": False, "skipped": True}` when OBS is offline, which is never awaited or checked before `marker.replay_saved = ...` (`detector.py:139`).
- **Verification Steps:** Trigger `highlights.mark_manual()` while `obs.is_connected == False`; inspect the returned `HighlightMarker.replay_saved` (evaluates to `True`).
- **Blast Radius:** Misleading highlight metadata in UI/VOD summaries claiming replays were saved when no clip exists on disk.
- **Recommended Fix:** Attach a done-callback to the created task that inspects the return dict (`res.get("success")`) and updates `marker.replay_saved` accordingly (defaulting `marker.replay_saved` to `False` until confirmed).

---

### `[GAME-HIGH-004]` `ClipPipeline.create_vertical_clip()` Lacks `ffmpeg` Timeout and Partial-File Cleanup
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** [core/highlights/clipper.py:121-148](file:///d:/projects/MaybeAI/core/highlights/clipper.py#L121-L148)
- **Symptom:** A hung `ffmpeg` process (e.g., stalled input stream or unexpected prompt) blocks `await proc.communicate()` (`clipper.py:127`) indefinitely, stalling `/api/highlights/action`. Failed runs can also leave truncated `.mp4` files in `data/clips/`.
- **Root Cause:** `create_vertical_clip()` calls `await proc.communicate()` without `asyncio.wait_for(..., timeout=...)`, does not pass `-nostdin` to `ffmpeg`, does not verify `subtitle_path` exists before invoking `ffmpeg`, and does not unlink `out_path` on non-zero exit.
- **Verification Steps:** Inspect `core/highlights/clipper.py:50-74` (missing `-nostdin`) and `121-141` (no `wait_for`, no cleanup on `returncode != 0`).
- **Blast Radius:** Hung HTTP request handlers on `/api/highlights/action` and accumulation of corrupt 0-byte/partial MP4 files.
- **Recommended Fix:** Add `-nostdin` to `build_vertical_clip_cmd()`, wrap `proc.communicate()` in `asyncio.wait_for(..., timeout=120.0)` with `proc.kill()` on `TimeoutError`, validate `subtitle_path` existence, and remove partial `out_path` on failure.

---

### `[GAME-HIGH-005]` `Singer` Karaoke Timing Drift, Blocking I/O on Event Loop, and Missing Concurrency Guard
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** [core/singer.py:136-217](file:///d:/projects/MaybeAI/core/singer.py#L136-L217), [core/singer.py:8-9](file:///d:/projects/MaybeAI/core/singer.py#L8-L9)
- **Symptom:** Vocals progressively drift behind the BGM track on every lyric line, overlapping `sing()` calls corrupt `is_singing` and audio channels, and synchronous `pygame`/`Path` calls block the asyncio event loop.
- **Root Cause:**
  1. `pygame.mixer.music.play()` starts BGM at `singer.py:144`, after which each lyric line awaits `delay_before` (`line 160`) and *then* awaits `edge_tts.Communicate.save()` (`line 180`) + optional RVC HTTP conversion (`line 184`). Every 300–1500ms of TTS/RVC latency compounds into cumulative desync against the playing BGM.
  2. `pygame.mixer.init()`, `pygame.mixer.Sound(vocal_file)`, `Path.read_bytes()`, and `Path.write_bytes()` run synchronously on the event loop.
  3. `sing()` does not check `if self.is_singing:` before starting, allowing concurrent invocations to overwrite `self._active_channel` and `pygame.mixer.music`.
  4. Top-level `import pygame` (`line 9`) and `pygame.mixer.init()` (`line 138`) fail in headless environments without SDL audio devices unless `SDL_AUDIODRIVER=dummy` is set.
- **Verification Steps:** Inspect `core/singer.py:144-188` and `9-10`; run a multi-line song and measure BGM elapsed time vs. line start time.
- **Blast Radius:** Out-of-sync karaoke performances, event-loop stalls during TTS/audio load, and startup/runtime failures in headless Docker deployments.
- **Recommended Fix:** Guard `sing()` against concurrent execution (stop or reject if `is_singing`); pre-synthesize lyric TTS files before starting BGM or align line start to `pygame.mixer.music.get_pos()`; offload `pygame.mixer` and file I/O to `asyncio.to_thread`.

---

## 3. Medium & Low-Severity Findings

### `[GAME-MED-001]` `MiniGameEngine` Trivia/Guess-Number Regex Causes Chat False Positives and Lacks Active Timeout
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** [core/minigames/engine.py:260-285](file:///d:/projects/MaybeAI/core/minigames/engine.py#L260-L285), [core/minigames/engine.py:322-364](file:///d:/projects/MaybeAI/core/minigames/engine.py#L322-L364), [core/minigames/engine.py:234-237](file:///d:/projects/MaybeAI/core/minigames/engine.py#L234-L237)
- **Symptom:** Normal chat messages containing `"a"` (e.g., `"what a play"`) or any 1–3 digit number trigger wrong-answer roasts and reset player streaks; rounds never expire if chat goes quiet; `stop_game()` awards `games_won += 1` to the all-time leaderboard leader rather than the session's top scorer.
- **Root Cause:** Trivia uses `re.search(r'\b([A-Da-d])\b', msg_lower)` (`line 277`) on arbitrary chat sentences instead of anchoring (`^[a-d]$` or `![a-d]`). Guess-the-number matches any `\b(\d{1,3})\b` without checking `1 <= guess <= 100`. `is_expired()` is only polled inside `process_chat_input()` (`line 261`).
- **Verification Steps:** Start a Trivia round and send `"this is a test"` to `process_chat_input()`; observe it matches `"a"` and resets streak.
- **Blast Radius:** Noisy chat UX during mini-games and inaccurate `games_won` leaderboard stats.
- **Recommended Fix:** Require explicit prefix/anchored tokens (`^[!.]?[a-d]$` / `^\d{1,3}$` within `[1, 100]`), track per-session scores for `stop_game()`, and add an async timeout task or orchestrator tick check for `is_expired()`.

---

### `[GAME-MED-002]` `VisionEngine.aperceive_with_vlm()` Updates `obs.summary` After `broadcast_callback` and Swallows Non-200 HTTP Errors
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** [core/vision/engine.py:155-216](file:///d:/projects/MaybeAI/core/vision/engine.py#L155-L216), [core/vision/vlm.py:138-178](file:///d:/projects/MaybeAI/core/vision/vlm.py#L138-L178)
- **Symptom:** `VisionEngine.broadcast_callback` fires inside `perceive()` (`engine.py:157`) *while holding `self._lock`* and *before* `aperceive_with_vlm()` enriches `obs.summary` (`engine.py:213`). Additionally, Gemini/OpenAI HTTP 429/401/500 responses are silently ignored with no log output.
- **Root Cause:** `perceive()` invokes `self.broadcast_callback(self.get_state())` under `self._lock` before returning to `aperceive_with_vlm()`, and `analyze_with_vlm_api()` only checks `if resp.status == 200:` without logging `resp.status` on failure or reusing an `aiohttp.ClientSession`.
- **Verification Steps:** Inspect `core/vision/engine.py:110-160` and `205-216`, and `core/vision/vlm.py:139-147`.
- **Blast Radius:** Subscribers to `broadcast_callback` miss VLM summaries, and VLM API rate-limit/auth failures are invisible in logs.
- **Recommended Fix:** Invoke `broadcast_callback` outside `self._lock` after VLM enrichment completes, log non-200 HTTP status codes in `MultimodalVisionModel.analyze_with_vlm_api()`, and reuse a shared `aiohttp.ClientSession`.

---

### `[GAME-MED-003]` `MinecraftController` Duplicates `mc_telemetry` in `minecraft_state` and Maintains a Split `MultiplayerSocialEngine`
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** [core/minecraft/controller.py:35](file:///d:/projects/MaybeAI/core/minecraft/controller.py#L35), [core/minecraft/controller.py:313-324](file:///d:/projects/MaybeAI/core/minecraft/controller.py#L313-L324), [core/orchestrator.py:1810-1826](file:///d:/projects/MaybeAI/core/orchestrator.py#L1810-L1826)
- **Symptom:** Every 3s telemetry tick broadcasts both `mc_telemetry` and a full `minecraft_state` (which embeds `get_telemetry()`), doubling WebSocket traffic. Furthermore, `MinecraftController.multiplayer` and `Orchestrator.brain.multiplayer` are separate `MultiplayerSocialEngine` instances that diverge when in-game chat arrives via `Orchestrator._on_in_game_chat()`.
- **Root Cause:** `_listen_bridge()` calls `await self.emit_state()` immediately after `on_telemetry_callback` (`controller.py:320-324`), and `MinecraftController.__init__` instantiates its own `MultiplayerSocialEngine()` (`controller.py:35`) instead of sharing `brain.multiplayer`.
- **Verification Steps:** Compare `core/minecraft/controller.py:35` with `core/orchestrator.py:1825`.
- **Blast Radius:** Redundant WebSocket broadcasts and inconsistent multiplayer ledger/chat state between `/api/minecraft/multiplayer` and `minecraft_state`.
- **Recommended Fix:** Pass the shared `MultiplayerSocialEngine` instance into `MinecraftController`, and avoid calling `emit_state()` on every `mc_telemetry` tick when only telemetry changed.

---

### `[GAME-MED-004]` `PerformanceDirector._notify_scene_switch()` & `Minecraft` Idle Loop Dead Code
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** [core/performance/director.py:187-200](file:///d:/projects/MaybeAI/core/performance/director.py#L187-L200), [minecraft/bot.js:198-257](file:///d:/projects/MaybeAI/minecraft/bot.js#L198-L257)
- **Symptom:**
  1. `PerformanceDirector._notify_scene_switch()` spawns an untracked `loop.create_task(res)` (`director.py:196`) whose exceptions are never awaited/logged.
  2. `bot.js` defines `startAutonomyLoop()` (`bot.js:198`) for social head-tracking, player following, and `santai` wandering, but never calls it on `spawn`, leaving `autonomyInterval` permanently `null`.
- **Root Cause:** Missing `startAutonomyLoop()` call in `bot.on('spawn')` and fire-and-forget `create_task` in `PerformanceDirector`.
- **Verification Steps:** Search `minecraft/bot.js` for `startAutonomyLoop` (1 definition, 0 call sites).
- **Blast Radius:** Casual-mode autonomous wandering/head-tracking in `bot.js` is inactive; unhandled exceptions in async `scene_switcher` are lost until GC.
- **Recommended Fix:** Call `startAutonomyLoop()` in `bot.on('spawn')` when `currentMode === 'santai'` (and in `set_mode` when switching back to `santai`), and attach a done-callback to `create_task(res)` in `PerformanceDirector._notify_scene_switch()`.

---

### `[GAME-LOW-001]` Missing `get_status()` on `ClipPipeline`/`VODSummarizer` and Missing Draw Rules in `ChessEngine`
- **Severity:** Low
- **Evidence Classification:** `VERIFIED`
- **Location:** [run.py:294-301](file:///d:/projects/MaybeAI/run.py#L294-L301), [core/highlights/clipper.py:18](file:///d:/projects/MaybeAI/core/highlights/clipper.py#L18), [core/highlights/vod_summarizer.py:16](file:///d:/projects/MaybeAI/core/highlights/vod_summarizer.py#L16), [core/chess/chess_engine.py:259-270](file:///d:/projects/MaybeAI/core/chess/chess_engine.py#L259-L270)
- **Symptom:** `/api/highlights/status` always returns `{}` for `clipper` and `vod_summarizer` because neither implements `get_status()`. In `ChessEngine.get_game_state()`, fivefold repetition or 75-move draws set `is_game_over: True` while `result` remains `"ongoing"`.
- **Root Cause:** `run.py:295-296` checks `hasattr(clipper, "get_status")` / `hasattr(vod, "get_status")` which are unimplemented; `ChessEngine.get_game_state()` only checks `is_checkmate()`, `is_stalemate()`, and `is_insufficient_material()`.
- **Verification Steps:** Call `_get_highlights_status()` or `ChessEngine.get_game_state()` after a 5-fold repetition.
- **Blast Radius:** Incomplete telemetry on `/api/highlights/status` and ambiguous game-over result string on rare chess draws.
- **Recommended Fix:** Add `get_status()` to `ClipPipeline` and `VODSummarizer`, and handle `is_fivefold_repetition()` / `is_seventyfive_moves()` in `ChessEngine.get_game_state()`.

---

## 4. Summary Risk Matrix

| Finding ID | Domain | Severity | Classification | Primary Risk |
| :--- | :--- | :---: | :---: | :--- |
| `[GAME-CRIT-001]` | Chess | Critical | `VERIFIED` | Concurrent `chess.Board` mutation between event loop and `to_thread` |
| `[GAME-CRIT-002]` | Minecraft | Critical | `VERIFIED` | No Node.js bridge crash recovery, leaked `setInterval`, swallowed `uncaughtException` |
| `[GAME-HIGH-001]` | Vision | High | `VERIFIED` | `TypeError` crash (`detected_label` vs `scene_label`) when Pillow is absent |
| `[GAME-HIGH-002]` | OBS | High | `VERIFIED` | Stale `is_connected=True` on drop, no reconnect, stale `replay_buffer_active` |
| `[GAME-HIGH-003]` | Highlights | High | `VERIFIED` | `replay_saved=True` recorded before async OBS save runs or when skipped |
| `[GAME-HIGH-004]` | Clip Pipeline | High | `VERIFIED` | `ffmpeg` subprocess has no timeout, no `-nostdin`, no partial-file cleanup |
| `[GAME-HIGH-005]` | Karaoke / Singer | High | `VERIFIED` | Cumulative TTS latency drift vs BGM, blocking I/O, no concurrency guard |
| `[GAME-MED-001]` | Mini-Games | Medium | `VERIFIED` | Trivia/number regex false positives, no active round timer, wrong winner stat |
| `[GAME-MED-002]` | Vision / VLM | Medium | `VERIFIED` | Broadcast before VLM enrichment under lock; silent non-200 HTTP failures |
| `[GAME-MED-003]` | Minecraft | Medium | `VERIFIED` | Redundant `mc_telemetry` + `minecraft_state` broadcasts; split multiplayer state |
| `[GAME-MED-004]` | Perf / Minecraft | Medium | `VERIFIED` | Untracked `create_task` in `PerformanceDirector`; `startAutonomyLoop()` never called |
| `[GAME-LOW-001]` | Highlights / Chess | Low | `VERIFIED` | Missing `get_status()` on clipper/VOD; missing 5-fold/75-move draw labels |
