# 10 — Chaos Testing Execution Log & Findings

**Auditor:** AGENT 8 (`cto-qa`) — QA & Production Reliability Auditor  
**Execution Script:** Isolated in-memory/scratch harness (`chaos_suite.py` in conversation scratch directory; zero modifications to `core/`, `tests/`, `run.py`, or `web/`).  
**Command:** `.\.venv\Scripts\python.exe -W default "...\scratch\chaos_suite.py"` (Exit Code: `0`).

---

## Scenario A — EventBus Burst + Failing Subscriber + Slow Subscriber

- **Target:** `core/event_bus.py` (`EventBus`)
- **Setup:** `EventBus(max_history=200)` with 4 subscribers on `chat.received`:
  1. `sync_fail` (`raise RuntimeError("sync_fail_boom")`)
  2. `async_fail` (`raise ValueError("async_fail_boom")`)
  3. `slow_sub` (`await asyncio.sleep(0.2)`)
  4. `fast_sub` (records timestamp)
  Followed by a 500-event burst via `publish_nowait("ai.chunk", {"seq": i})`.
- **Observed Output:**
  ```text
  [EventBus] Handler error for 'chat.received': sync_fail_boom
  [EventBus] Handler error for 'chat.received': async_fail_boom
  A1_single_publish: delivered=2/4 elapsed=0.207s fast_hits=1 errors=2
  A2_burst_500: enqueue_dt=0.0029s history_len=200/200 total_published=501 handler_errors=2
  ```
- **Classification & Findings:**
  - `VERIFIED`: Per-handler exception isolation prevented sync/async subscriber crashes from aborting delivery to `fast_sub`.
  - `VERIFIED`: Ring buffer (`deque(maxlen=200)`) capped history at `200/200` during 500-event burst (`enqueue_dt=0.0029s`).
  - `REPRODUCED` **`[PERF-HIGH-001]`**: `EventBus.publish()` awaits subscribers **sequentially** (`core/event_bus.py:193-198`) with no per-handler timeout. The single `0.2s` slow subscriber stalled `publish()` for `0.207s` and delayed `fast_sub` by `200ms`.

---

## Scenario B — Barge-In / TTS Interruption Race Under Concurrent LLM Stream

- **Target:** `core/tts.py` (`TTSEngine.speak_stream`, `TTSEngine.stop`)
- **Setup:**
  - **B1:** `speak_stream()` consuming an async LLM generator yielding 3 sentences at `0ms`, `150ms`, `650ms` with mocked `_synthesize_audio` (`80ms` delay) writing temp files into an isolated `TemporaryDirectory`. `tts.stop(reason="chaos_barge_in")` invoked at `180ms`.
  - **B2:** Immediate `tts2.stop(reason="immediate_race")` invoked 1 event-loop tick (`await asyncio.sleep(0)`) after starting `speak_stream()`.
- **Observed Output:**
  ```text
  B1_stream_barge_in: stopped=True was_interrupted=True is_speaking=False active_tasks=0 active_temp_files=0 disk_leftovers=0 spoken_chunks=['Kalimat pertama selesai.'] last_mouth=0.0
  B2_immediate_stop_race: stopped=True was_interrupted=True is_speaking=False
  ```
- **Classification & Findings:**
  - `VERIFIED`: Both mid-stream barge-in (`B1`) and 1-tick immediate race (`B2`) cleanly cancelled `producer_task`/`consumer_task`, reset `is_speaking=False`, reset mouth lip-sync to `0.0`, and left `0` active tasks and `0` leftover temp `.mp3` files on disk.

---

## Scenario C — Plugin Sandbox Infinite Loop / Crash / Env Leak Probe

- **Target:** `core/plugins/registry.py` (`PluginRegistry`, `_SandboxPluginClient`) & `core/plugins/sandbox_worker.py`
- **Setup:** Populated host `os.environ` with `GEMINI_API_KEY`, `OPENAI_API_KEY`, `MAYBEAI_COLLAB_SECRET`, `DISCORD_BOT_TOKEN`. Created a subprocess-sandboxed probe plugin with `!env`, `!crash` (`os._exit(42)`), and `!loop` (`while True: pass`).
- **Observed Output:**
  ```text
  C1_cold_start_0.25s: discovered=['word_chain', 'probe'] subprocesses=['probe']
  C2_env_probe: discovered=['word_chain', 'probe'] resp=env_keys=['PATH', 'PYTHONPATH', 'PYTHONUNBUFFERED', 'SYSTEMROOT'];leaks=[]
  [PluginRegistry] Command '!crash' error in 'probe': EOFError: Sandbox worker 'probe' exited
  C3_crash_probe: handled=True resp=None error_count=1 last_error=EOFError: Sandbox worker 'probe' exited in_subprocesses=True
  [PluginRegistry] on_unload error for 'probe': ConnectionResetError: Connection lost
  [PluginRegistry] Command '!loop' timed out after 0.8s (plugin=probe)
  C4_loop_probe: handled=True resp=None elapsed=0.811s loaded=False last_error=Command '!loop' timed out after 0.8s in_subprocesses=False
  ```
- **Classification & Findings:**
  - `VERIFIED`: Zero host secret leakage (`env_keys=['PATH', 'PYTHONPATH', 'PYTHONUNBUFFERED', 'SYSTEMROOT']; leaks=[]`).
  - `VERIFIED`: Infinite CPU loop (`!loop`) was hard-killed at `0.811s` (`hook_timeout_sec=0.8`), `loaded=False`, and evicted from `_subprocesses`.
  - `REPRODUCED` **`[QA-MED-001]`**: After worker crash (`!crash` -> `os._exit(42)`), host survived with `EOFError`, but `probe` remained in `reg._subprocesses` (`in_subprocesses=True`), causing subsequent `reload_plugin` to hit `ConnectionResetError: Connection lost` during `on_unload`.
  - `REPRODUCED` **`[QA-HIGH-001]`** (in full `unittest` run): Under CPU contention, `_probe_sandbox_manifest` sharing `hook_timeout_sec=0.3` timed out on cold start, causing `KeyError: 'hang_plugin'`.

---

## Scenario D — Collab HMAC Invalid Signature / Replay / Anti-Loop Flood

- **Target:** `core/collab/protocol.py` (`CollabEnvelope`) & `core/collab/manager.py` (`CollabManager`)
- **Setup:** `CollabManager(settings={"shared_secret": "super_secret_key", "max_collab_turns": 4, "turn_cooldown_sec": 1.0}, allow_unauthenticated_loopback=True)`.
- **Observed Output:**
  ```text
  D1_invalid_hmac: {'accepted': False, 'error': 'Invalid or missing collab HMAC signature.'}
  D2_unsigned_with_secret: {'accepted': False, 'error': 'Invalid or missing collab HMAC signature.'}
  D3_replay_same_msg_id_1hr_old: r1_accepted=True r2_accepted=True turn_count=2
  D4_antiloop_flood: [(True, 'floor_acquired', 'idle', 3), (True, 'max_collab_turns_reached', 'cooldown', 4), (True, 'turn_cooldown_active', 'cooldown', 4), (True, 'turn_cooldown_active', 'cooldown', 4), (True, 'turn_cooldown_active', 'cooldown', 4)]
  D5_emote_sync_during_cooldown: {'accepted': True, 'event_type': 'emote_sync', 'reply_triggered': False, 'reason': 'emote_sync_received', 'floor_state': 'cooldown', 'turn_count': 4}
  ```
- **Classification & Findings:**
  - `VERIFIED`: Invalid HMAC (`D1`) and unsigned loopback when `shared_secret` is configured (`D2`) are both rejected.
  - `VERIFIED`: `max_collab_turns=4` caps `turn_utterance` turns and enters `cooldown` (`D4`).
  - `REPRODUCED` **`[QA-CRIT-001]`**: Identical signed `CollabEnvelope` (`message_id` reused, `timestamp` 1 hour stale) was accepted twice (`r1_accepted=True`, `r2_accepted=True`, `turn_count=2`). No nonce/timestamp replay defense exists.
  - `REPRODUCED` **`[QA-MED-002]`**: `emote_sync` (and `duet_sync`/`game_move`) bypass `max_collab_turns` and `cooldown` (`D5`).

---

## Scenario E — Node.js / OBS / Platform Adapter Disconnect & Recovery

- **Targets:** `core/minecraft/controller.py`, `core/desktop/obs_client.py`, `core/platforms/youtube.py`
- **Setup:**
  - **E1:** `MinecraftController._listen_bridge()` fed 1 `bot_spawned` frame then `ConnectionError("WebSocket 1006 abnormal closure")`.
  - **E2:** `OBSWebSocketClient.switch_scene("Minecraft")` with mocked `ReqClient` raising `ConnectionError("OBS WS broken pipe")`.
  - **E3:** `YouTubeLiveAdapter.poll_once()` receiving HTTP `500` followed by HTTP `200`.
- **Observed Output:**
  ```text
  [Minecraft] Eve spawned in server! Pos: {'x': 1, 'y': 64, 'z': 1}
  [Minecraft Bridge Reader] Error or disconnect: WebSocket 1006 abnormal closure
  E1_mc_bridge_drop: bridge_ws=None connection_status=connected is_active=True
  E2_obs_call_failure: res={'success': False, 'scene': 'Minecraft', 'reason': '', 'connected': True, 'error': 'OBS WS broken pipe'} obs_is_connected_after=True
  E3_yt_recovery: on_500=(False, 'HTTP 500: Internal Server Error', 10.0) on_200=(True, None, 1.5)
  ```
- **Classification & Findings:**
  - `REPRODUCED` **`[QA-HIGH-002]`**: `MinecraftController` leaves `connection_status='connected'` and `is_active=True` after bridge WebSocket drop, with no auto-reconnect.
  - `REPRODUCED` **`[QA-HIGH-003]`**: `OBSWebSocketClient` leaves `is_connected=True` after transport failure.
  - `VERIFIED`: `YouTubeLiveAdapter` degrades cleanly (`is_connected=False`, `10.0s` backoff) on HTTP 500 and self-recovers (`is_connected=True`, `1.5s` poll interval) on HTTP 200.
