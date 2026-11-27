# Post-Implementation Audit — 10: Cross-Module Integration & End-to-End Flow Trace

**Auditor:** `ng-qa` (Agent 8 — Audit Synthesizer)  
**Scope:** End-to-end verification of **Flows A–G** across `run.py`, `core/`, `web/`, and `minecraft/`, synthesizing findings from Agents 1–8 (`audit/00`–`09`, `11`–`13`).

---

## Flow A: Viewer Interaction → Spoken Response

**Path:** `ChatReceiver` (`core/chat_receiver.py`) / `/ws` → `Orchestrator._ingest_message` (`core/orchestrator.py:1205`) → `Moderator.clean_text` (`core/moderator.py`) → `ChatCurator` / `ConversationEngine` (`core/conversation/engine.py`) → `MemoryRetriever` (`core/memory/`) → `Brain.generate_response[_stream]` (`core/brain.py`) → `ActionParser` (`core/actions.py`) → `Orchestrator._speak_with_metrics` → `TTSEngine` (`core/tts.py`) / `RVCVoiceConverter` (`core/tts_providers.py`) → `VTSClient` + `EventBus` → `/ws` (`avatar_state`, `audio_chunk`, `ai_response`) → `web/app.js` / `web/overlay.js`.

| Dimension | Verified Implementation & Gaps |
|---|---|
| **Data Ownership** | `ChatReceiver.queue` (`maxsize=500`) owns ingress buffering; `ConversationEngine` owns `ContextMemory` (`16` turns) & `ChatCurator` (`50` msgs); `MemoryDatabase` owns SQLite WAL; `Orchestrator` owns `_busy_lock` & `_current_emotion`. |
| **Trust Boundaries** | `Moderator` drops prompt-injected or strict-mode non-creator chat (`_ingest_message`); `is_creator` is plumbed end-to-end to `MasterPromptBuilder` (`[CREATOR VERIFIED]`). **Gap (`SEC-GAP-003`):** `obs.summary` from VLM enters system prompt unsanitized. |
| **Async Boundaries** | `ChatReceiver` pushes via `asyncio.Queue`; `Brain` uses pooled `aiohttp.ClientSession` & `ContextBudgetManager`; `EventBus.publish()` fans out via `asyncio.gather` (`timeout=2.0` per WS listener). **Gap (`INFRA-MED-001-RES`, `INFRA-MED-003`):** No per-WS outbound `asyncio.Queue(maxsize=64)`; sync DB/Markdown calls inside `_ingest_message` cause `>100ms` event-loop stalls. |
| **State Transitions** | `_busy_lock` serializes primary interactions; `MoodEngine` updates affect + modulates LLM sampling temperature (`get_temperature_modifier()`). |
| **Failure / Retry** | `ProviderCircuitBreaker` (`failure_threshold=3`, `cooldown_sec=30.0`) fails over across `gemini` → `openai` → `ollama` → `mock`. `TTSEngine` falls back to `edge-tts` (`en-US-AriaNeural`). **Gap (`AUDIO-MED-001`):** `ClientTimeout(total=1.8)` truncates healthy streams >1.8s. |
| **Cancellation** | `_active_interaction_task` is cancelled on `barge_in()` and `Orchestrator.shutdown()`. |
| **Persistence** | Episodic memories written to `data/memory.db` (WAL) + `data/second_brain/*.md`; `vector_search` preserves >128-d blobs on hash fallback. |
| **Observability** | `MetricsCollector` records `llm_requests`, `llm_failovers`, `tts_latency_ms`, `event_bus_published`. |
| **Recovery** | Automatic fallback to persona mock responses and silent/browser audio if external LLM/TTS/VTS fail. |

---

## Flow B: Creator Voice Interruption (Full-Duplex Barge-In)

**Path:** `web/audio-worklet-processor.js` (`MaybeAIPCMProcessor` 16 kHz Int16 PCM, 512-sample frames) → binary `/ws` frame → `run.py` `voice_queue` (`maxsize=64`) → `_voice_worker` → `STTEngine` / `EnergyVAD` (`core/stt.py`) → `Orchestrator.barge_in()` (`core/orchestrator.py:753-824`) → `TTSEngine.stop()` / `Singer.barge_in()` / `_active_interaction_task.cancel()` → `VTSClient.trigger_expression("neutral")` → `EventBus` (`voice.barge_in`).

| Dimension | Verified Implementation & Gaps |
|---|---|
| **Data Ownership** | Browser `AudioWorklet` owns mic capture & 16 kHz resampling (`_flush(true)` on stop); `run.py` owns per-WS `voice_queue`; `Orchestrator` owns `_active_interaction_task`. |
| **Trust Boundaries** | `/ws` requires Origin allowlist + Creator auth (`_is_ws_creator_authorized`) for voice/control actions. **Gap (`SEC-GAP-001`):** `web/shared-client.js` still passes `?token=` in WS URL query string. |
| **Async Boundaries** | Inbound binary PCM is decoupled from WS receive loop via `voice_queue` + `_voice_worker` + `asyncio.to_thread` STT offload. |
| **State Transitions** | `EnergyVAD` speech onset triggers `barge_in()`, stopping TTS & Singer BGM (`pygame.mixer.music.stop()`), resetting `mouth_open=0.0`, and emitting `voice_barge_in` (which clears browser Web Audio FIFO). |
| **Failure / Retry** | `voice_queue` drops oldest frame on overflow (`maxsize=64`) rather than blocking WS. |
| **Cancellation** | `TTSEngine.speak_stream()` re-raises `asyncio.CancelledError`. **Gap (`AUDIO-MED-002`):** Single-shot `TTSEngine.speak()` still returns `None` instead of re-raising `CancelledError`. |
| **Persistence** | None (ephemeral audio stream; temp WAV unlinked immediately in `STTEngine`). |
| **Observability** | `MetricsCollector` tracks `stt_latency_ms`; `stt_partial` currently emits static `"Listening..."` (`AUDIO-LOW-002`). |
| **Recovery** | `_voice_worker` and `finally:` block in `run.py:1842-1849` clean up tasks on WS disconnect; `VTSClient` resets `MouthSmile` (`AUDIO-LOW-001`: mismatches `MouthForm` in `apply_mood_rig`). |

---

## Flow C: Autonomous Mission Execution

**Path:** `AutonomousMissionExecutor.step_once()` (`core/planning/executor.py`) → `GoalEngine` / `GoalDecomposer` → human approval gate (`approval_timeout_sec=300.0`) → `MinecraftController` / `ChessController` (`board.copy()` + `to_thread`) → `StrategyReplanner` (`MAX_REPLAN_ATTEMPTS=3`) → `Goal.recalculate_progress()` → `EpisodicMemoryStore` + `EventBus` (`mission.step`, `mission.status`).

| Dimension | Verified Implementation & Gaps |
|---|---|
| **Data Ownership** | `GoalEngine` owns `data/goals/goals.json` & `agenda.md`; `MinecraftController` owns bridge WS state; `ChessController` owns `ChessEngine.board`. |
| **Trust Boundaries** | Mission start/approve/cancel endpoints (`POST /api/missions/*`, WS actions) gated by Creator auth + Origin middleware. |
| **Async Boundaries** | Chess alpha-beta/Stockfish search runs on `asyncio.to_thread(choose_move, board_copy)`; Minecraft bridge listener runs in background task. |
| **State Transitions** | `PENDING` → `AWAITING_APPROVAL` (expires after `300s` via `_expire_stale_approval()`) → `IN_PROGRESS` → `COMPLETED` / `FAILED` (after `3` replans; `REPLANNED` subtasks excluded from progress denominator). |
| **Failure / Retry** | `_execute_minecraft` blocks cleanly when disconnected; `ChessEngine` falls back from Stockfish UCI to `alpha_beta`. **Gap:** `_execute_chess` still returns simulated progress if `self.chess is None`. |
| **Cancellation** | `Goal` cancellation & approval timeout clear active gates. **Gap:** `ChessController._delayed_bot_move` task is not cancelled on `start_game()`/`resign_game()`. |
| **Persistence** | `goals.json`, `agenda.md`. **Gap:** `Goal.reflection` is write-only; `promises.md` archival/fulfillment is not wired into runtime loops. |
| **Observability** | Emits `mission.step` & `mission.status`; `GET /api/missions/status` (Creator-gated). |
| **Recovery** | `MinecraftController._listen_bridge()` `finally:` resets `connection_status="disconnected"` and `is_active=False` (no auto-respawn loop if `bot.js` crashes). |

---

## Flow D: AI-to-AI VTuber Collaboration

**Path:** `CollabManager.connect_peer()` (`core/collab/manager.py`) → `validate_outbound_url` (`core/security_net.py`) → `/ws/collab` (`run.py:1854-1900`) → `CollabEnvelope` (`core/collab/protocol.py`) → `CollabManager.handle_incoming_envelope()` → `Orchestrator` inbound callbacks (`_on_collab_duet_sync`, `_on_collab_emote_sync`, `_on_collab_game_move`) → `EventBus` (`collab.message`, `collab.state`).

| Dimension | Verified Implementation & Gaps |
|---|---|
| **Data Ownership** | `CollabManager` owns `floor_state`, `turn_count`, `_seen_nonces` (`OrderedDict(maxsize=1024)`), and `peer_capabilities`. **Gap:** Scalar peer fields prevent 3+ peer scaling. |
| **Trust Boundaries** | `validate_outbound_url` blocks private/metadata IPs (`allow_private_peers=False` default); `/ws/collab` verifies `Authorization: Bearer` / `Sec-WebSocket-Protocol`; `CollabEnvelope` verifies HMAC-SHA256, `±60s` skew, replay nonce, and `NaN`/`Infinity`. **Gap:** `is_loopback=True` default on `handle_incoming_envelope`; DNS-rebinding TOCTOU window (`SEC-GAP-004`). |
| **Async Boundaries** | Inbound receive loop (`_receive_loop`) + `asyncio.Lock` around floor state transitions; per-type sliding-window rate limit (`10` events / `5s`). |
| **State Transitions** | `idle` → `speaking` → `yielding` → `listening` → `cooldown` (auto-recovers via `_refresh_cooldown()`). **Gap (Chaos Scenario B):** `disconnect_peer()` does not reset `floor_state` from `"listening"` back to `"idle"`. |
| **Failure / Retry** | WS/auth errors abort cleanly; unsigned frames rejected outside loopback. |
| **Cancellation** | `disconnect_peer()` cancels `_receive_task` and closes `_ws_client` & `_http_session`. |
| **Persistence** | Volatile in-memory state (`_seen_nonces` resets on restart; `±60s` skew bounds replay window). |
| **Observability** | Emits `collab.state` & `collab.message`; `GET /api/collab/status` (Creator-gated). **Gap:** `Orchestrator._on_collab_hello` is dead code (`set_action_callbacks` lacks `on_hello`). |
| **Recovery** | `_refresh_cooldown()` exits cooldown automatically; **Gap:** subsystems (`Singer`, `VTS`, `Chess`) never auto-emit outbound sync frames. |

---

## Flow E: YouTube Song Request & Auto-Karaoke

**Path:** `web/app.js` (`#btnPerfYtSing`) → `POST /api/performance/youtube` (`run.py:756`) → `Orchestrator` → `YouTubeKaraokeProcessor.prepare_song()` (`core/youtube_karaoke.py`) → `yt-dlp` / `demucs` / `ffmpeg` / `RVCVoiceConverter` → `data/karaoke_cache/<video_id>` → `Orchestrator.perform_song()` (`_busy_lock`) → `Singer` clock-locked `vocal_track` + `lyric_line` + `avatar_movement` → `PersonalityEvolutionEngine`.

| Dimension | Verified Implementation & Gaps |
|---|---|
| **Data Ownership** | `YouTubeKaraokeProcessor` owns `data/karaoke_cache/<video_id>/`; `Orchestrator` owns `_busy_lock`; `Singer` owns playback clock & lyric schedule. |
| **Trust Boundaries** | `POST /api/performance/youtube` is Creator-auth + Origin gated; `extract_youtube_video_id()` enforces `validate_outbound_url` + `_YOUTUBE_HOSTS` + 11-char `_VIDEO_ID_RE` + `max_duration_sec=600`. **Gap (`SEC-GAP-005`):** No `--max-filesize` on `yt-dlp` and no concurrent job cap. |
| **Async Boundaries** | Subprocesses (`yt-dlp`, `demucs`, `ffmpeg`) run via `asyncio.create_subprocess_exec` with bounded timeouts (`30s`/`180s`/`300s`/`120s`) and `proc.kill()` on timeout. |
| **State Transitions** | Emits `youtube_song_status` stages (`downloading` → `separating` → `converting` → `ready` / `error`) → `song_started` → `lyric_line` → `song_ended`. |
| **Failure / Retry** | Missing `yt-dlp`/`ffmpeg` raises `YouTubeKaraokeError` cleanly; missing `demucs` falls back to `ffmpeg` center-channel cancellation; `RVCVoiceConverter` falls back to original audio. |
| **Cancellation** | `barge_in()` stops `Singer` BGM (`pygame.mixer.music.stop()`) and vocal channel. |
| **Persistence** | Cached stems & `meta.json` in `data/karaoke_cache/<video_id>/` (respects `MAYBEAI_DATA_DIR`). |
| **Observability** | Broadcasts `youtube_song_status`, `performance_updated`, `song_started`, `lyric_line`, `song_ended`. **Gap (`AUDIO-MED-003`):** `Orchestrator.reload_settings()` omits neural TTS provider fields for `Singer`. |
| **Recovery** | Cache validates `bgm`, `vocal_track`, and `mode` before reuse; `_busy_lock` prevents concurrent song overlap. |

---

## Flow F: OBS Showrunner & Highlights Pipeline

**Path:** `HighlightDetector` (`core/highlights/detector.py`) → `OBSWebSocketClient.save_replay_buffer()` (`core/desktop/obs_client.py`) → `EventBus` (`HIGHLIGHT_MARKED`) → `ClipPipeline.create_vertical_clip()` (`core/highlights/clipper.py`) → `ffmpeg` → `VODSummarizer` (`core/highlights/vod_summarizer.py`) → `data/second_brain/streams/YYYY-MM-DD.md`.

| Dimension | Verified Implementation & Gaps |
|---|---|
| **Data Ownership** | `HighlightDetector` owns marker history; `ClipPipeline` owns `data/clips/`; `VODSummarizer` owns `data/second_brain/streams/`. |
| **Trust Boundaries** | `POST /api/obs/action` & `POST /api/highlights/clip` gated by Creator auth + Origin middleware. `ClipPipeline._resolve_confined_path()` enforces `is_relative_to(base_dir)` + `_escape_ffmpeg_filter_path()` prevents filtergraph injection. |
| **Async Boundaries** | `OBSWebSocketClient` wraps blocking `obsws_python` calls in `asyncio.to_thread`; `VODSummarizer.generate_summary()` runs via `asyncio.to_thread`; `ClipPipeline` runs `ffmpeg -nostdin` with timeout. |
| **State Transitions** | Sync `on_save_replay` updates `marker.replay_saved` before `HIGHLIGHT_MARKED` is published. **Gap:** Async `on_save_replay` (`obs.save_replay_buffer()`) spawns background task, so initial `HIGHLIGHT_MARKED` payload has `replay_saved: False`. |
| **Failure / Retry** | `OBSWebSocketClient` resets `is_connected=False` and `_client=None` on runtime error; missing `obsws-python` or `ffmpeg` returns structured failure dicts. |
| **Cancellation** | `ffmpeg` subprocess killed on timeout. |
| **Persistence** | Vertical clips in `data/clips/`; VOD summaries in `data/second_brain/streams/YYYY-MM-DD.md` (collision-safe). |
| **Observability** | Emits `obs.scene_changed`, `highlight.marked`, `vod.summary_ready`. **Gap:** `ClipPipeline` & `VODSummarizer` lack `.get_status()` (guarded by `hasattr` in `run.py`). |
| **Recovery** | Graceful degradation when OBS or `ffmpeg` is unavailable (no background OBS auto-reconnect loop). |

---

## Flow G: Plugin Execution & Sandbox Isolation

**Path:** `PluginRegistry.discover_plugins()` (`core/plugins/registry.py`) → AST manifest extraction → `granted_permissions` default-deny → `_SandboxPluginClient` (`windows_job_object` / Linux `bwrap` + `sandbox_worker.py`) → `dispatch_command()` / `EventBus` `_on_bus_event()` → JSON-RPC 2.0 (`hook_timeout_sec=5.0`) → Host RPC callback permission check.

| Dimension | Verified Implementation & Gaps |
|---|---|
| **Data Ownership** | `PluginRegistry` owns plugin lifecycle, command map, and `granted_permissions`; each external worker owns an isolated `scratch_dir` (`cwd`). |
| **Trust Boundaries** | AST manifest parsing avoids import-time execution; `_build_sandbox_env()` strips all `.env` secrets; host RPC enforces `tts:speak` / `event:pub`; Linux uses `bwrap` + `rlimit`; Windows uses `_WindowsJobObject` (512MB, 2 procs, kill-on-close). **Gap (`SEC-GAP-002`):** Windows FS/net boundary guards rely on Python monkeypatches bypassable via `ctypes`/`subprocess`. |
| **Async Boundaries** | Host communicates with worker over async stdio JSON-RPC 2.0 with `startup_timeout_sec` and `hook_timeout_sec` (`5.0s`). |
| **State Transitions** | `discovered` → `blocked` (invalid manifest/AST) or `loaded` (`os_isolated` / `subprocess_restricted` / `builtin`). |
| **Failure / Retry** | Timeouts and worker crashes increment `error_count`, log `last_error`, and trigger `_evict_dead_subprocess` without crashing host `EventBus` or `Orchestrator`. |
| **Cancellation** | `PluginRegistry.shutdown()` gracefully stops or kills all worker subprocesses. |
| **Persistence** | Config in `settings.json` (`plugins.enabled_plugins`, `plugins.granted_permissions`). |
| **Observability** | `GET /api/plugins` (Creator-gated) exposes `sandbox_level`, `os_isolation_detail`, `granted_permissions`, `denied_permissions`, `error_count`, `last_error`; emits `plugin.event`. |
| **Recovery** | Dead workers are evicted cleanly; `reload_plugin()` restarts worker cleanly. |
