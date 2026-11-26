# MaybeAI — Architecture Decision Records (ADR-001 through ADR-008)

**Document Owner:** Agent 11 (`strat-arch`) — Principal Software & Future Architecture Engineer  
**Scope:** Formal architectural decisions addressing all Critical and High findings in `audit/FINAL_AUDIT_REPORT.md`.

---

## ADR-001: Non-Blocking EventBus, Per-Client Bounded WS Queues & Centralized `TaskSupervisor`
* **Status:** Proposed (Horizon 0–1)
* **Audit Findings:** `[PERF-HIGH-001]`, `[INFRA-HIGH-001]`, `[INFRA-HIGH-002]`, `[INFRA-HIGH-003]`, `[INFRA-HIGH-004]`, `[INFRA-MED-003]`
* **Context:** `EventBus.publish()` (`core/event_bus.py:193-201`) awaits subscribers sequentially without a per-handler timeout. Chaos Scenario A1 reproduced a `0.207s` pipeline stall from a single `200ms` subscriber. Additionally, 12+ `asyncio.create_task()` calls in `core/orchestrator.py` and `run.py:631` bypass `_spawn_bg_task()`, `perform_song()` bypasses `_busy_lock`, `ChatReceiver.queue` is unbounded, and synchronous disk/SQLite calls cause `0.109s–0.235s` event-loop stalls.
* **Decision:**
  1. Refactor `EventBus.publish()` to dispatch async handlers concurrently via `asyncio.gather(..., return_exceptions=True)` wrapped in `asyncio.wait_for(..., timeout=subscriber_timeout_sec)`.
  2. Replace direct `send_json` calls in `_dispatch_to_web_listeners` with per-client `asyncio.Queue(maxsize=64)` drained by a dedicated writer task; drop oldest frames for high-frequency telemetry (`avatar_state`, `stt_partial`) and evict dead listeners on send failure.
  3. Introduce a `TaskSupervisor` in `Orchestrator` tracking all background tasks, bounding `publish_nowait()` concurrency, and cancelling all tasks on `shutdown()`.
  4. Guard `perform_song()` with `_busy_lock`, bound `ChatReceiver.queue(maxsize=500)`, replace `asyncio.get_event_loop().time()` with `time.monotonic()`, and offload sync disk/SQLite reads to `asyncio.to_thread()`.
* **Consequences:** Eliminates head-of-line blocking and zombie tasks; adds minor per-client queue memory (~64 messages/client) and requires telemetry drop tolerance on slow clients.
* **Alternatives Considered:** Moving to an external message broker (Redis/NATS) — rejected as premature operational complexity for single-node streaming.
* **Verification Criteria:** Chaos Scenario A with a `500ms` stalled WS client completes `EventBus.publish()` to fast subscribers in `<5ms`; zero untracked `asyncio.create_task` calls remain; zero asyncio slow-callback warnings `>100ms` in core suite.

---

## ADR-002: Unified Creator Auth, Origin/Token Policy & Read-Only `/ws/overlay` Separation
* **Status:** Proposed (Horizon 0)
* **Audit Findings:** `[SEC-CRIT-001]`, `[SEC-HIGH-001]`, `[SEC-HIGH-002]`, `[SEC-HIGH-003]`, `[SEC-HIGH-004]`, `[INFRA-HIGH-005]`
* **Context:** `_CREATOR_ONLY_WS_ACTIONS` (`run.py:780-790`) omits `memory_action`, `mood_action`, `relationship_action`, `minigame_action`, `story_action`, `multiplayer_action`, and `trigger_improv`, while `/ws` pushes private state pre-auth. `_is_ws_creator_authorized()` checks `_LOOPBACK_HOSTS` before `MAYBEAI_CREATOR_TOKEN`, breaking Docker/LAN Creator auth. All `GET /api/*` routes except `/api/config` are unauthenticated. `ConfigManager.SECRET_MASK_FIELDS` omits LLM keys, `Moderator` never drops flagged prompts, and `ClipPipeline` lacks path confinement.
* **Decision:**
  1. Unify HTTP and WS authorization into `_verify_creator_request()`: validate `MAYBEAI_CREATOR_TOKEN` (header/subprotocol/first-frame auth, deprecating `?token=`) **before** `_LOOPBACK_HOSTS`. Auto-generate an ephemeral token if `--host 0.0.0.0` is used without one.
  2. Split `/ws` (Creator-authenticated control plane) from `/ws/overlay` (read-only public stream telemetry: `ai_response`, `audio_chunk`, `avatar_state`, `performance_updated`, `minigame_updated`, `story_updated`).
  3. Gate all `GET /api/*` routes except `/api/health` with `_is_http_creator_authorized()`.
  4. Mask `llm.gemini_api_key` and `llm.openai_api_key` in `ConfigManager`; enforce `Moderator.strict_mode` / `prompt_injection_filter` (drop flagged chat, sanitize/cap `user` & `donation_amount`); confine `ClipPipeline` paths to `data/clips` via `Path.resolve().is_relative_to()`.
* **Consequences:** Immediate `NO-GO -> GO` unblock for Docker/LAN Creator usage; OBS Browser Sources must use `/ws/overlay` (no creator mutations possible).
* **Alternatives Considered:** Per-user RBAC/OAuth2 — rejected as overkill for a single-creator streaming studio.
* **Verification Criteria:** Unauthenticated `/ws` or `GET /api/memory/*` returns `401/403` or `forbidden`; Docker `--host 0.0.0.0` with valid token authorizes `/ws`; path traversal in `POST /api/highlights/action` is rejected.

---

## ADR-003: Hardened Out-of-Process Plugin Isolation & Host-Granted Capability Policy
* **Status:** Proposed (Horizon 0–2)
* **Audit Findings:** `[SEC-CRIT-002]`, `[QA-HIGH-001]`, `[QA-MED-001]`
* **Context:** External plugins in `plugins/*.py` run in a subprocess with clean `env` (`leaks=[]` in Chaos Scenario C2), but share the host OS user, `cwd=REPO_ROOT`, network, and `RLIMIT`s—allowing reads of `.env`, `config/settings.json`, and `data/memory.db`. `PluginRegistry` also trusts self-declared `manifest.permissions`, executes top-level code at discovery, allows `inprocess` mode, shares `hook_timeout_sec` with cold start (`[QA-HIGH-001]`), and retains crashed entries in `_subprocesses` (`[QA-MED-001]`).
* **Decision:**
  1. **Horizon 0:** Separate `startup_timeout_sec` (default `5.0s`) from `hook_timeout_sec`; evict crashed workers from `_subprocesses` on `EOFError`/exit; disable `inprocess` mode for external `plugins_dir` plugins unless `--allow-unsafe-inprocess-plugins` is passed; enforce explicit host-side `plugins.granted_permissions[plugin_id]` in `config/settings.json` instead of trusting `manifest.permissions`.
  2. **Horizon 2:** Run external plugin workers in an OS-level sandbox (Linux `bubblewrap`/namespaces + `seccomp` + `--no-new-privs` in Docker/Linux; Windows Job Objects + restricted token/temp working dir) with read-only access to `core/plugins/sdk.py` and the plugin file only, blocking `.env`, `config/`, and `data/`.
* **Consequences:** Eliminates flaky cold-start test failures and closes host secret exfiltration paths; requires creator approval in `/settings` when installing a new plugin.
* **Alternatives Considered:** Docker-in-Docker per plugin (rejected due to Docker socket escalation risk) or Pyodide/WASM (deferred; breaks native Python stdlib/ecosystem plugins).
* **Verification Criteria:** `test_sandbox_plugins_cli.py` passes `5/5` under full-suite CPU load; crashed plugin is cleanly evicted; plugin attempting `open(".env")` or ungranted `PluginContext` call is denied.

---

## ADR-004: Audio / Barge-In Cancellation Contract & Server-Side RMS Lip-Sync Envelope
* **Status:** Proposed (Horizon 1–2)
* **Audit Findings:** `[AUDIO-CRIT-001]`, `[AUDIO-CRIT-002]`, `[AUDIO-HIGH-001]`, `[AUDIO-HIGH-002]`, `[AUDIO-HIGH-003]`
* **Context:** `TTSEngine.speak_stream()` suppresses `asyncio.CancelledError` when `_stop_requested=True`, causing post-barge-in `ai_response` / Minecraft / Discord replies (`[AUDIO-CRIT-001]`). `barge_in()` does not stop `Singer` BGM (`[AUDIO-HIGH-002]`), `transcribe_wav_bytes()` blocks the WS receive loop (`[AUDIO-HIGH-001]`), and server lip-sync emits a synthetic 80 ms square wave (`0.95`/`0.50`) that fights browser `AnalyserNode` RMS (`[AUDIO-CRIT-002]`).
* **Decision:**
  1. Enforce a strict cancellation contract: `TTSEngine.speak_stream()` and `Singer.sing()` must clean up resources (reset `mouth_open: 0.0`, stop `pygame.mixer.music`, delete temp files) and **re-raise `CancelledError`**. `Orchestrator._execute_interaction()` checks cancellation before any post-speech broadcast or platform dispatch.
  2. Offload `transcribe_wav_bytes()` to `TaskSupervisor` so `process_voice_chunk()` returns VAD state in `<1ms` and never blocks `/ws` `barge_in`.
  3. Fix `EdgeTTSProvider` fallback voice (`fallback_voice="en-US-AnaNeural"`), detect WAV (`RIFF`) vs MP3 dynamically for MIME/RVC headers, and route `Singer` through `create_tts_provider()`.
  4. Replace the synthetic 80 ms square wave with a real PCM/RMS amplitude envelope computed from synthesized audio; browser clients in `browser`/`both` mode ignore `avatar_state.mouth_open` while `isPlayingAudioQueue` is active.
* **Consequences:** Instantaneous, artifact-free barge-in across TTS, Karaoke, Minecraft, and Discord; accurate syllable-matched lip-sync on both VTS and browser overlays.
* **Alternatives Considered:** Client-only TTS synthesis — rejected to preserve server-side RVC, `pygame` local monitoring, and VTS injection.
* **Verification Criteria:** Barge-in during streaming TTS/Karaoke emits zero post-cancel `ai_response`/chat messages, stops BGM immediately, and `barge_in` WS frames are processed while STT is running.

---

## ADR-005: Bounded Cognitive Prompt (`ContextBudgetManager`), LLM Failover & Hybrid Memory Store
* **Status:** Proposed (Horizon 1–2)
* **Audit Findings:** `[COG-HIGH-002]`, `[COG-HIGH-003]`, `[COG-HIGH-004]`, `[COG-HIGH-005]`, `[PERF-MED-001]`
* **Context:** `MasterPromptBuilder` concatenates 11+ subsystem directives unconditionally with mismatched `max_tokens` (`150` OpenAI vs `800` Gemini). `is_creator` is dropped on all live LLM paths and error fallbacks (`[COG-HIGH-003]`). Provider errors drop directly to offline mock text. `EpisodicMemoryStore` duplicates `EmbeddingEngine`, `_encode_gemini_async()` creates a new `aiohttp.ClientSession` per call, and vector search is capped at 300 rows.
* **Decision:**
  1. Plumb `is_creator` into `abuild_system_prompt()` (emitting `[CREATOR VERIFIED]`) and all fallback calls.
  2. Introduce `ContextBudgetManager` in `core/conversation/` to estimate token usage, prune inactive subsystem directives, and enforce provider-aware context ceilings and harmonized `max_tokens`.
  3. Add a configurable LLM failover chain (`Primary -> Secondary -> Ollama -> Mock`) with per-provider circuit breakers.
  4. Share a single `EmbeddingEngine` instance with a persistent `aiohttp.ClientSession` pool, and evaluate `sqlite-vec` (or pre-filtered FTS5 + indexed vector blobs) to remove the 300-row ceiling while keeping SQLite + Markdown Second Brain.
* **Consequences:** Prevents context-window overflows on local 4K–8K Ollama models, preserves Creator authority in live LLM mode, and cuts ~50–150ms TLS overhead per memory lookup.
* **Alternatives Considered:** Replacing SQLite with external Qdrant — deferred unless episodic memory exceeds ~50k–100k rows (see `research/architecture_proposals.md`).
* **Verification Criteria:** Live LLM payloads include `[CREATOR VERIFIED]` when `is_creator=True`; idle subsystems add `0` tokens to system prompt; persistent `aiohttp` session reused across embedding calls.

---

## ADR-006: Closed-Loop Mission State Machine, Replan Caps & Async Telemetry Verification
* **Status:** Proposed (Horizon 1)
* **Audit Findings:** `[COG-CRIT-001]`, `[COG-CRIT-002]`, `[COG-HIGH-001]`, `[COG-MED-001]`, `[GAME-CRIT-001]`, `[GAME-CRIT-002]`, `[GAME-HIGH-002]`, `[GAME-HIGH-003]`, `[GAME-HIGH-004]`
* **Context:** Replanned goals never reach `COMPLETED` (`[COG-CRIT-001]`), failed subtasks loop infinitely every 25s (`[COG-CRIT-002]`), 0ms Minecraft polling triggers false failures while disconnected mode fabricates progress (`[COG-HIGH-001]`), and `pending_approval` never expires (`[COG-MED-001]`). Separately, `chess.Board` has a thread race (`[GAME-CRIT-001]`), and Minecraft/OBS adapters retain stale `"connected"` state on drop (`[GAME-CRIT-002]`, `[GAME-HIGH-002]`).
* **Decision:**
  1. Exclude `GoalStatus.REPLANNED.value` from `Goal.recalculate_progress()` denominator and completion checks.
  2. Enforce `MAX_REPLAN_ATTEMPTS = 3`; on exhaustion, transition goal to `FAILED` and pivot via `autonomous_select_next_activity()`. Add `approval_timeout_sec = 120.0` to `pending_approval`.
  3. Separate `simulated` commentary from `verified_execution`: require `allow_simulated_progress=True` when disconnected, and evaluate live Minecraft deltas across ticks via `mc_telemetry` events instead of 0ms inline polling.
  4. Clone `chess.Board` (`self.board.copy(stack=False)`) before `asyncio.to_thread` + guard transitions with `asyncio.Lock`; reset `connection_status`/`is_connected` in `finally:` blocks on Minecraft/OBS drops with bounded exponential-backoff reconnect.
* **Consequences:** Goals complete or fail cleanly without disk bloat; Minecraft/OBS recover gracefully from mid-stream drops; Chess engine is thread-safe.
* **Alternatives Considered:** Rewriting `AutonomousMissionExecutor` as a full PDDL/BT planner — rejected as unnecessary; fixing the existing state machine preserves all tests and Second Brain integration.
* **Verification Criteria:** Replanned goal reaches `COMPLETED` when active subtasks finish; repeated failure halts after 3 replans; Chaos Scenarios E1/E2 report `connected=False` on drop.

---

## ADR-007: Collab Replay Protection (`message_id` Nonce + Timestamp Window) & Deterministic Floor Arbitration
* **Status:** Proposed (Horizon 0–2)
* **Audit Findings:** `[COLLAB-CRIT-001]`, `[COLLAB-HIGH-001]`, `[COLLAB-HIGH-002]`, `[COLLAB-HIGH-003]`, `[COLLAB-HIGH-004]`, `[COLLAB-MED-001]`, `[QA-MED-002]`
* **Context:** `CollabManager` has zero replay protection (Chaos Scenario D3), `_is_loopback_url()` is spoofable via substring match, `/ws/collab` mutates global `shared_secret` and accepts query-string secrets, `_refresh_cooldown()` deadlocks permanently in `"cooldown"` (`[COLLAB-HIGH-003]`), concurrent `turn_utterance` frames spawn parallel LLM reply storms, and `collab.enabled=False` is ignored.
* **Decision:**
  1. Enforce a `±60s` `timestamp` freshness window and a bounded `(sender_id, message_id)` TTL/LRU nonce cache in `CollabManager.handle_incoming_envelope()`.
  2. Parse `urllib.parse.urlparse(url).hostname` for exact loopback validation (`ipaddress.ip_address(host).is_loopback` or `"localhost"`), default `is_loopback=False`, deprecate query-string secrets, and remove global `shared_secret` mutation in `run.py`.
  3. Fix `_refresh_cooldown()` to reset `self.turn_count = 0` when `time.monotonic() >= self.cooldown_until` (without resetting `cooldown_until` on rejected frames), transition `floor_state` to `"thinking"`/`"speaking"` *before* spawning `_on_collab_reply_needed` with `try/finally` cleanup, enforce `collab.enabled`, and rate-limit `emote_sync`/`duet_sync`.
* **Consequences:** Eliminates replay attacks, URL spoofing, cooldown deadlocks, and reply storms; enables reliable multi-hour AI-to-AI collabs.
* **Alternatives Considered:** Replacing `/ws/collab` with gRPC — rejected to preserve lightweight WebSocket interoperability.
* **Verification Criteria:** Chaos Scenario D3 rejects replayed 1h-old envelope; `CollabManager` auto-recovers after `turn_cooldown_sec`; `ws://localhost.evil.com` is rejected as non-loopback.

---

## ADR-008: Local-First Frontend Asset Bundling, Shared Auth/WS Client & XSS-Safe Rendering
* **Status:** Proposed (Horizon 0–2)
* **Audit Findings:** `[UI-HIGH-001]`, `[UI-HIGH-002]`, `[UI-HIGH-003]`, `[UI-MED-001]`, `[UI-MED-002]`, `[UI-MED-003]`, `[UI-MED-004]`
* **Context:** `/settings` has stored DOM XSS in `renderDiagnosticsView()`, `renderCategorySettingsView()`, `renderSearchResults()`, and `renderControlHtml()` (`[UI-HIGH-001]`). `/` and `/settings` lack creator token UI and crash on `401/403` (`[UI-HIGH-002]`). All pages hammer `/ws` every 2000ms on disconnect, `overlay.js` lacks `ws.onopen` re-sync, `deck.js` has a double-WS race (`[UI-HIGH-003]`), `AudioWorklet` skips `mono[0]` and drops tail frames (`[UI-MED-002]`), and 3D VRM/fonts depend on external CDNs (`[UI-MED-004]`).
* **Decision:**
  1. **Horizon 0:** Escape all interpolated values in `web/settings.js` and `web/app.js` with `escapeHtml()`/`escapeAttr()` (or `textContent`); wrap `app.js` `JSON.parse` in `try/catch`; fix `AudioWorklet` linear interpolation and tail-frame flush.
  2. **Horizon 1–2:** Extract `web/shared-client.js` providing `CreatorAuth` (token modal/bar + `401/403` handling across `/`, `/settings`, `/deck`) and `ReconnectingWebSocket` (exponential backoff with jitter `1s -> 30s`, `1008` policy circuit-break, clean `ws.onclose = null` before manual close, `onopen` re-sync).
  3. **Horizon 2:** Vendor Three.js, `@pixiv/three-vrm`, and fonts locally under `web/vendor/` for air-gapped LAN/OBS reliability, and migrate `AudioWorklet` PCM streaming to binary WS frames.
* **Consequences:** Eliminates stored XSS and auth lockouts; makes OBS overlays and Stream Deck resilient to server restarts and offline LANs without requiring a Node/React build pipeline.
* **Alternatives Considered:** Migrating `web/` to React + Vite + TypeScript — rejected (see `research/architecture_proposals.md`) because vanilla ES modules + `shared-client.js` solve all UI issues with zero build-step friction for Python/Docker users.
* **Verification Criteria:** XSS payload `<img src=x onerror=alert(1)>` in `twitch.channel` renders as literal text in `/settings`; `401/403` opens token prompt without crashing; `deck.js` token save opens exactly 1 WS connection.
