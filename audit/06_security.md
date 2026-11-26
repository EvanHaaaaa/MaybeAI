# MaybeAI Security & Operational Technology Audit (`audit/06_security.md`)

**Auditor:** AGENT 6 — Security & Operational Technology Auditor (`cto-sec`)  
**Scope:** Authentication & authorization boundaries (`run.py`), HTTP/WebSocket origin & token checks, Plugin SDK & out-of-process sandbox (`core/plugins/`), Desktop Companion (`core/desktop/`), FFmpeg/OBS operational technology (`core/highlights/clipper.py`, `core/desktop/obs_client.py`), prompt injection surfaces (`core/moderator.py`, `core/chat_receiver.py`, `core/platforms/`, `core/brain.py`, `core/orchestrator.py`, `core/conversation/prompts.py`), AI Collab protocol (`core/collab/`), secret management (`core/config_manager.py`, `.env.example`), and Docker/LAN deployment hardening (`Dockerfile`, `docker-compose.yml`).  
**Methodology:** Static source-code verification against the live workspace. Zero source files were modified.

---

## 1. Executive Summary & Capability Classification

MaybeAI has implemented several foundational security controls—most notably Origin validation on mutating HTTP endpoints and WebSockets, constant-time token comparison (`secrets.compare_digest` / `hmac.compare_digest`), secret masking in `ConfigManager`, creator-only gating on high-risk desktop/Minecraft/Chess commands, `subprocess` isolation for external plugins with stripped environment variables, and parameterized SQLite/FTS5 queries.

However, **critical and high-severity gaps** remain across WebSocket action authorization, unauthenticated read endpoints, plugin filesystem/network isolation, Docker/LAN Creator authentication, FFmpeg path/filtergraph handling, prompt-injection enforcement, and Collab replay protection.

### Capability Maturity Matrix

| Capability | Classification | Evidence Summary |
| :--- | :--- | :--- |
| Origin & Loopback/Token Auth on Mutating HTTP & Select WS Actions | **Current Capability** | `run.py:50-130, 368-379, 780-801` enforces `_is_allowed_origin`, `_is_http_creator_authorized`, and `_CREATOR_ONLY_WS_ACTIONS`. |
| Secret Masking in Config API & WS Broadcasts | **Current Capability** | `core/config_manager.py:248-272, 1547-1563` and `core/orchestrator.py:285-294` mask 6 secret fields with `"********"` and preserve them on save. |
| Parameterized SQLite & FTS5 Queries | **Current Capability** | `core/memory/database.py:145-193, 309-336` uses parameterized `?` bindings and strips non-alphanumeric chars in `fts_search`. |
| Desktop Companion Policy & Safe App Launcher | **Current Capability** | `core/desktop/permission_manager.py` and `core/desktop/controller.py:17, 171-205` enforce master/category toggles, metacharacter regex, and `subprocess.Popen([...])` without `shell=True`. |
| Out-of-Process Plugin Sandbox (Env Strip + Timeout Kill) | **Partially Implemented** | `core/plugins/registry.py:373-383, 880-888` strips `os.environ` and kills timed-out workers, but lacks OS-level filesystem/network/resource isolation and trusts self-declared manifest permissions. |
| Prompt Injection & Strict Moderation Filtering | **Partially Implemented** | `core/moderator.py:63-91` only redacts keywords with `[CENSORED]` and never drops messages; `strict_mode` and `prompt_injection_filter` are dead config flags. |
| AI-to-AI Collab HMAC Authentication | **Partially Implemented** | `core/collab/protocol.py:76-106` signs/verifies envelopes with HMAC-SHA256, but `core/collab/manager.py:470-488` lacks nonce/timestamp replay checks. |
| Persistent VTube Studio Auth Token (`VTS_AUTH_TOKEN`) | **Planned Capability** | `.env.example:44-45` marks `VTS_AUTH_TOKEN` as reserved; `core/vts_client.py:18, 95-108` requests a fresh ephemeral token each startup. |
| Reserved LLM Provider Keys (`ANTHROPIC_API_KEY`, `GROQ_API_KEY`) | **Planned Capability** | `.env.example:9-11` reserves env vars not yet wired into `core/brain.py`. |
| OS-Level Plugin Sandbox (seccomp/AppArmor/Read-Only Mounts) & Non-Query Auth | **Proposed Innovation** | Recommended hardening for production multi-plugin and LAN/Docker deployments. |

---

## 2. Threat Model

```
+-----------------------------------------------------------------------------+
| Untrusted External Inputs                                                   |
| - Twitch IRC / YouTube Live / Discord / TikTok Live chatters                |
| - Unauthenticated LAN / WebSocket clients (/ws, /ws/collab)                 |
| - External third-party plugins (plugins/*.py)                               |
| - Browser / OBS Overlay / Deck clients                                      |
+--------------------------------------+--------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
| Trust Boundaries                                                            |
| [TB-1] HTTP/WS Middleware & Auth (run.py:50-130, 368-379, 780-801)          |
| [TB-2] Chat Moderator & Creator Flag (core/moderator.py, orchestrator.py)   |
| [TB-3] Plugin Subprocess & RPC Host Callbacks (core/plugins/registry.py)    |
| [TB-4] Collab Envelope HMAC & Peer WS (/ws/collab, core/collab/manager.py)  |
| [TB-5] Desktop Companion & FFmpeg/OBS OT (core/desktop/, core/highlights/)  |
+--------------------------------------+--------------------------------------+
                                       |
                                       v
+-----------------------------------------------------------------------------+
| Protected Assets                                                            |
| - Host OS execution & local filesystem (.env, config/settings.json, data/)  |
| - Creator API keys & platform tokens (GEMINI, OPENAI, Discord, Twitch, OBS) |
| - Creator private memory/journal (data/memory.db, data/second_brain/)       |
| - Live stream integrity (OBS scenes/stream state, TTS voice output, VTS)    |
+-----------------------------------------------------------------------------+
```

---

## 3. Detailed Security Findings

### `[SEC-CRIT-001]` Unauthenticated WebSocket State Mutation & Private Data Exposure

- **Severity:** Critical
- **Evidence Classification:** `VERIFIED`
- **Location:** `run.py:780-790`, `run.py:815-921`, `run.py:927-1604`
- **Symptom:** Any WebSocket client connected to `/ws`—including non-creator LAN/Docker clients or unauthenticated local tabs—receives sensitive system/memory/desktop state immediately upon connecting and can invoke state-mutating actions (`memory_action`, `mood_action`, `relationship_action`, `multiplayer_action`, `minigame_action`, `story_action`, `trigger_improv`).
- **Root Cause:**
  1. `_CREATOR_ONLY_WS_ACTIONS` (`run.py:780-790`) only gates 9 action types (`config_action`, `desktop_action`, `minecraft_action`, `chess_action`, `set_llm_provider`, `personality_action`, `performance_action`, `vision_action`, `goal_action`), plus explicit inline checks on `barge_in`, `voice_audio_chunk`, `mission_action`, `collab_action`, and `plugin_action`.
  2. The remaining handlers in the `/ws` receive loop (`run.py:972-1486`)—notably `memory_action` (`get_journal`, `get_recent`, `get_user_profile`, `add_memory`), `mood_action`, `relationship_action` (`set_tier`, `add_inside_joke`), `multiplayer_action`, `minigame_action`, `story_action`, and `trigger_improv`—have **no** `ws_creator_authorized` check.
  3. On connection (`run.py:815-921`), `/ws` immediately pushes `memory_updated`, `relationship_updated`, `desktop_updated`, `goal_updated`, `system_diagnostics`, and `collab_state` without checking `ws_creator_authorized`.
- **Verification Steps:**
  1. Connect to `/ws` from a non-loopback IP (or loopback without `?token=` when `MAYBEAI_CREATOR_TOKEN` is set) so `ws_creator_authorized == False`.
  2. Observe initial state frames pushed at `run.py:842-921`.
  3. Send `{"type": "memory_action", "action": "get_journal"}` or `{"type": "memory_action", "action": "add_memory", "title": "test", "content": "injected"}`; `run.py:1067-1092` executes both without returning `forbidden`.
- **Blast Radius:** Unauthenticated read access to private creator journals, episodic memories, user dossiers, and desktop notification/audit state; unauthorized mutation of AI memory, mood, relationships, and active stream games/improv.
- **Recommended Fix:**
  1. Move `memory_action`, `mood_action`, `relationship_action`, `multiplayer_action`, `minigame_action`, `story_action`, and `trigger_improv` (or at minimum all mutating/private sub-actions) into `_CREATOR_ONLY_WS_ACTIONS` or enforce `ws_creator_authorized` per sub-action.
  2. Restrict `/ws` initial state snapshots so unauthenticated/overlay clients only receive public stream overlay telemetry (`ai_response`, `audio_chunk`, `performance_updated`, `minigame_updated`, `story_updated`), or require creator auth for `/ws` and serve a dedicated read-only `/ws/overlay` endpoint.

---

### `[SEC-CRIT-002]` Plugin Subprocess Sandbox Lacks Filesystem, Network, Resource, & Capability Enforcement

- **Severity:** Critical
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/plugins/registry.py:372-383, 443-456, 687-708, 869-888`, `core/plugins/sandbox_worker.py:34-62`
- **Symptom:** Although external plugins run in a separate Python subprocess with stripped environment variables (`_build_sandbox_env`), a malicious or compromised plugin in `plugins/*.py` can read host secrets from `.env` and `config/settings.json`, tamper with `data/memory.db`, make arbitrary network requests, execute code during discovery before RPC starts, and self-grant any `PluginContext` permission.
- **Root Cause:**
  1. **No Filesystem Isolation:** `_SandboxPluginClient.start()` (`core/plugins/registry.py:63-73`) spawns `python -m core.plugins.sandbox_worker` as the same OS user with `cwd=str(REPO_ROOT)`. `.env` and `config/settings.json` (which stores plaintext `oauth_token`, `api_key`, `bot_token`, `creator_token`, `shared_secret`, `obs.password`) are directly readable by the plugin process.
  2. **No Network or Resource Limits:** No OS sandbox (seccomp, AppArmor, network namespace, `RLIMIT_AS`/`RLIMIT_CPU`) is applied. A plugin can exfiltrate read files over HTTP/DNS or allocate unbounded memory.
  3. **Self-Declared Permissions:** In `core/plugins/registry.py:448-452`, `permission_provider` reads `self._manifests.get(plugin_id).permissions`, which comes directly from the plugin's own `manifest` returned by `sandbox_worker.py:119-121`. There is no host-side permission allowlist or user approval gate.
  4. **Import-Time Execution & In-Process Fallback:** `load_plugin_from_path()` (`sandbox_worker.py:46`) calls `spec.loader.exec_module(module)` at discovery time, executing arbitrary top-level Python code before `SandboxWorker` enters its RPC loop. Additionally, if `plugins.sandbox_mode` is set to `"inprocess"` (`registry.py:701-719`), external `.py` plugins execute directly inside the host process.
- **Verification Steps:**
  1. Inspect `core/plugins/registry.py:372-383` and `core/plugins/registry.py:63-73`: only `env` is restricted; `cwd` is `REPO_ROOT` and no OS-level jail or `preexec_fn` limits exist.
  2. Inspect `core/plugins/registry.py:448-452`: `permission_provider` returns `self._manifests[plugin_id].permissions` without comparing against a host-configured policy.
- **Blast Radius:** Full disclosure of all API keys, OAuth tokens, creator/collab secrets, and episodic memory database; arbitrary outbound network exfiltration; host compromise via `inprocess` mode or writable `data/`/`config/` files.
- **Recommended Fix:**
  1. Run external plugin subprocesses under a dedicated unprivileged OS user/container or OS sandbox (e.g., Linux namespaces/seccomp/bubblewrap) with read-only access to `core/plugins/sdk.py` only and no access to `.env`, `config/`, or `data/`.
  2. Require explicit creator-approved permission grants in `config/settings.json` (`plugins.granted_permissions[plugin_id]`) rather than trusting `manifest.permissions` blindly.
  3. Remove `"inprocess"` mode for external `plugins_dir` plugins (or require an explicit CLI flag `--allow-unsafe-inprocess-plugins`).
  4. Bound concurrent worker callbacks in `_SandboxPluginClient._stdout_reader_loop` (`registry.py:124`) with a semaphore.

---

### `[SEC-HIGH-001]` Docker/LAN Creator WebSocket Auth Deadlock & Origin-less Request Bypass

- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `run.py:50-83, 95-129, 368-379, 793-801, 1611-1641`, `Dockerfile:33`
- **Symptom:**
  1. In Docker (`CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "7860"]`) or LAN deployments, even a Creator presenting the exact `MAYBEAI_CREATOR_TOKEN` is **always** denied Creator privileges on `/ws`.
  2. Conversely, non-browser clients that omit the `Origin` header bypass `_is_allowed_origin()` on both `/ws`, `/ws/collab`, and mutating `/api/*` endpoints; when `MAYBEAI_CREATOR_TOKEN` is unset (the default), any local process or loopback browser tab gains full Creator privileges.
- **Root Cause:**
  1. `_is_ws_creator_authorized()` (`run.py:116-129`) checks `if client_host not in _LOOPBACK_HOSTS: return False` **before** checking `MAYBEAI_CREATOR_TOKEN`. In Docker bridge networking or LAN access, `websocket.client.host` is a non-loopback IP (e.g., `172.17.0.1` or `192.168.1.x`), so Creator WS auth always fails—inconsistent with `_is_http_creator_authorized()` (`run.py:95-113`), which allows non-loopback requests when a valid `configured_token` is provided.
  2. `verify_api_origin_middleware` (`run.py:374`) and `websocket_endpoint` (`run.py:796`) only validate `origin` `if origin is not None`. Any script or proxy stripping `Origin` skips origin validation.
- **Verification Steps:**
  1. Compare `run.py:95-113` (`_is_http_creator_authorized`) with `run.py:116-129` (`_is_ws_creator_authorized`): the HTTP helper checks `configured_token` first and falls back to `_LOOPBACK_HOSTS`, whereas the WS helper hard-fails non-loopback hosts even when `configured_token` matches.
- **Blast Radius:** Creator dashboard (`/`, `/deck`) is non-functional for privileged WS actions in Docker/LAN deployments; local privilege escalation when `MAYBEAI_CREATOR_TOKEN` is empty.
- **Recommended Fix:**
  1. Align `_is_ws_creator_authorized` with `_is_http_creator_authorized`: if `configured_token` is set, authorize based on constant-time token match regardless of `client_host`; only restrict to `_LOOPBACK_HOSTS` when no token is configured.
  2. Auto-generate an ephemeral `MAYBEAI_CREATOR_TOKEN` on startup (or fail-closed when `--host 0.0.0.0` is used without `MAYBEAI_CREATOR_TOKEN`).

---

### `[SEC-HIGH-002]` Unauthenticated Sensitive HTTP GET Endpoints

- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `run.py:368-379`, `run.py:400-524`, `run.py:670-778`
- **Symptom:** Remote/LAN callers can read episodic memories, creator journals, viewer profiles, desktop notifications/audit logs, system diagnostics, and plugin/OBS/collab status without `MAYBEAI_CREATOR_TOKEN` or loopback restriction.
- **Root Cause:** `verify_api_origin_middleware` (`run.py:370-372`) only checks `is_mutating_api` (`PUT`, `POST`, `PATCH`, `DELETE`) and `GET /api/config`. All other `GET /api/*` routes—including `/api/system/diagnostics`, `/api/memory/search`, `/api/memory/journal`, `/api/memory/recent`, `/api/relationships/{username}`, `/api/desktop/state`, `/api/goals/agenda`, `/api/plugins`, `/api/collab/status`, and `/api/obs/status`—are unauthenticated.
- **Verification Steps:** Inspect `run.py:371`: `is_sensitive_get = request.url.path == "/api/config" and request.method == "GET"`. No other `GET` endpoint checks `_is_http_creator_authorized`.
- **Blast Radius:** Unauthenticated information disclosure of private creator notes (`data/goals/agenda.md`, `memory/journal`), viewer dossiers, desktop notifications, and internal service host/port topology.
- **Recommended Fix:** Protect all `/api/*` `GET` endpoints except explicit public health/status routes (`/api/health`, and optionally a minimal `/api/status`) with `_is_http_creator_authorized`.

---

### `[SEC-HIGH-003]` Arbitrary File Overwrite & FFmpeg Filtergraph Injection in Clip Pipeline

- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `run.py:331-355`, `core/highlights/clipper.py:10-16, 44-74, 88-96`
- **Symptom:** An authenticated caller (or SSRF/CSRF chain) invoking `POST /api/highlights/action` with `action="clip"` can supply arbitrary `input_path`, `output_path`, and `subtitle_path` values outside `data/clips`, causing `ffmpeg -y` to overwrite arbitrary writable files or inject FFmpeg filtergraph directives.
- **Root Cause:**
  1. `run.py:334-348` passes `input_path`, `output_path`, and `subtitle_path` directly to `ClipPipeline.create_vertical_clip()` without path canonicalization or directory confinement.
  2. `ClipPipeline.create_vertical_clip()` (`core/highlights/clipper.py:88-95`) runs `Path(output_path).parent.mkdir(parents=True, exist_ok=True)` and passes `"-y"` (`clipper.py:52`), overwriting any existing file writable by the server process (e.g., `config/settings.json`, `.env`, or `plugins/*.py`).
  3. `_escape_ffmpeg_filter_path()` (`core/highlights/clipper.py:10-15`) only escapes `\`, `:`, and `'`, leaving `,`, `[`, `]`, and `;` unescaped inside `-vf subtitles='...'` (`clipper.py:46`).
- **Verification Steps:** Inspect `run.py:331-354` and `core/highlights/clipper.py:44-96`; no `.resolve().is_relative_to(...)` check exists on `input_path`, `output_path`, or `subtitle_path`.
- **Blast Radius:** Arbitrary file overwrite/corruption within the process's write permissions; potential FFmpeg filtergraph manipulation.
- **Recommended Fix:**
  1. Confine `input_path`, `output_path`, and `subtitle_path` to approved base directories (e.g., `data/clips` / configured recordings dir) using `Path.resolve()` and `is_relative_to()`, rejecting `..` and symlinks escaping the root.
  2. Escape `,`, `[`, `]`, and `;` in `_escape_ffmpeg_filter_path()` or pass subtitles via a sanitized temporary `.srt` path inside `data/clips`.

---

### `[SEC-HIGH-004]` Prompt Injection Surface: Non-Blocking Moderator, Dead Config Flags, and Unsanitized Metadata

- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/moderator.py:63-91`, `core/orchestrator.py:1045-1084`, `core/brain.py:395-407, 510-515, 588-598`, `core/conversation/prompts.py:71-84`, `core/config_manager.py:146-149`
- **Symptom:** Chat messages containing prompt injection payloads (from Twitch, YouTube, Discord, TikTok, Minecraft, or `/ws`) are never dropped—even when `moderator.strict_mode` and `moderator.prompt_injection_filter` are `True`—and `user` / `donation_amount` fields bypass moderation entirely.
- **Root Cause:**
  1. `Moderator.clean_text()` (`core/moderator.py:63-91`) only performs substring/regex replacement (`[CENSORED]`) against `config/filter_words.json` (which contains only 4 static English phrases and 3 regexes) and returns `(is_safe, sanitized_text)`.
  2. `Orchestrator._ingest_message()` (`core/orchestrator.py:1047-1084`) logs a warning when `is_safe` is `False` **but still ingests `clean_input`** into `ChatCurator`, `ConversationEngine`, `minigames`, and `storytelling`.
  3. `moderator.prompt_injection_filter` (`core/config_manager.py:148, 1020`) and `Moderator.strict_mode` (`core/moderator.py:10`) are **never evaluated** anywhere in `Moderator.clean_text()` or `Orchestrator._ingest_message()`.
  4. `msg.user` and `msg.donation_amount` are never passed through `Moderator.clean_text()` or length-bounded, yet are interpolated directly into LLM user prompts (`core/brain.py:395-396, 510-511, 588-589`) and system prompts (`core/conversation/prompts.py:73-79`).
  5. **Mitigation Note:** High-risk execution paths (`!desktop`, crucial `!mc`, crucial `!chess`) in `core/orchestrator.py:1213, 1275, 1325` are gated by `is_creator`, which prevents direct command execution from unauthenticated chatters even if the LLM is manipulated.
- **Verification Steps:**
  1. Search `core/` for `prompt_injection_filter` and `strict_mode`: `prompt_injection_filter` appears only in `config_manager.py`, and `strict_mode` is never branched on in `moderator.py`.
  2. Inspect `core/orchestrator.py:1047-1084`: `if not is_safe:` only calls `print(...)` and continues execution.
- **Blast Radius:** Attackers in public live chat can manipulate LLM responses (brand/stream safety risk, toxic/unwanted TTS output, memory poisoning via `record_turn`) and bypass the 250-char limit via `user` or `donation_amount` fields.
- **Recommended Fix:**
  1. Enforce `strict_mode` and `prompt_injection_filter` in `Orchestrator._ingest_message()`: drop messages flagged `is_safe=False` when `strict_mode` is enabled instead of forwarding them to `ChatCurator`/LLM.
  2. Sanitize and length-cap `msg.user` (e.g., max 32–64 chars, strip newlines/control chars) and `donation_amount` before prompt construction.
  3. Wrap untrusted chat inputs in explicit XML/delimiter boundaries in `Brain` payloads so the LLM distinguishes system instructions from viewer chat.

---

### `[SEC-HIGH-005]` AI Collab Protocol Lacks Replay Protection & Allows Unsigned Loopback

- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/collab/protocol.py:44-106`, `core/collab/manager.py:39, 470-488`, `run.py:1618-1641`
- **Symptom:** Valid signed `CollabEnvelope` frames intercepted from `/ws/collab` can be replayed indefinitely, and when `MAYBEAI_COLLAB_SECRET` is unset, any local process can inject unsigned collab frames (including `duet_sync`, `emote_sync`, `game_move`, and `turn_utterance`).
- **Root Cause:**
  1. `CollabEnvelope` includes `message_id` (`uuid4().hex`) and `timestamp` (`time.time()`) in `_canonical_bytes()` (`protocol.py:55-74`), but `CollabManager.handle_incoming_envelope()` (`manager.py:470-488`) **never** checks `message_id` against a seen-nonce cache and **never** validates `timestamp` against a freshness/skew window (e.g., ±60s).
  2. `CollabManager.__init__` sets `allow_unauthenticated_loopback: bool = True` (`manager.py:39`), and `/ws/collab` (`run.py:1639-1641`) accepts unauthenticated loopback connections whenever `shared_secret` is empty.
- **Verification Steps:** Inspect `core/collab/manager.py:470-488` and `core/collab/protocol.py:92-106`: `env.verify(...)` only validates the HMAC digest over the static payload; neither `message_id` nor `timestamp` is checked for uniqueness or recency.
- **Blast Radius:** Replay of previously signed collab utterances, game moves, or emote/duet sync triggers; unauthorized local collab injection when `shared_secret` is unconfigured.
- **Recommended Fix:**
  1. Add a bounded TTL/LRU cache of seen `message_id` values in `CollabManager` and reject envelopes with `abs(time.time() - env.timestamp) > 60.0` or duplicate `message_id`.
  2. Default `allow_unauthenticated_loopback` to `False` in production or require `MAYBEAI_COLLAB_SECRET` whenever `collab.enabled` is `True`.

---

### `[SEC-MED-001]` SSRF via Unvalidated Outbound Service URLs

- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/config_manager.py:1534-1566`, `core/collab/manager.py:255-268`, `core/tts_providers.py:219-241, 365-387, 446-470`, `core/platforms/tiktok.py:34, 93-96`
- **Symptom:** URLs configured in `settings.json` or passed via `/api/collab/action` (`peer_ws_url`)—including `tts.rvc_url`, `tts.kokoro_url`, `tts.custom_tts_url`, `llm.ollama_url`, `tiktok.webcast_ws_url`, and `collab.peer_ws_url`—are dialed by `aiohttp` without scheme or host validation.
- **Root Cause:** `ConfigManager.validate_config()` (`core/config_manager.py:1522-1524`) only checks `isinstance(val, str)` for `"text"` fields. Neither `ConfigManager` nor the downstream `aiohttp` clients restrict schemes (`http`/`https`/`ws`/`wss`) or block cloud metadata/internal IPs (`169.254.169.254`, etc.) when non-local URLs are supplied.
- **Verification Steps:** Inspect `run.py:179-183` (`connect` action passes `payload.get("peer_ws_url")` straight to `collab.connect_peer`) and `core/config_manager.py:1522-1524`.
- **Blast Radius:** A compromised Creator session or config update can pivot HTTP/WS requests to internal LAN services or cloud instance metadata endpoints.
- **Recommended Fix:** Validate URLs with `urllib.parse.urlparse` (require `http`/`https` or `ws`/`wss`, reject empty/unrecognized schemes, and optionally enforce an allowlist or block link-local metadata ranges `169.254.0.0/16`).

---

### `[SEC-MED-002]` Credential & Secret Exposure in Query Strings, Error Telemetry, and Console Logs

- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `run.py:123, 1624-1625, 1694`, `core/platforms/youtube.py:123, 162-164`, `core/orchestrator.py:1049`
- **Symptom:**
  1. `MAYBEAI_CREATOR_TOKEN` and `MAYBEAI_COLLAB_SECRET` are transmitted as URL query parameters (`?token=`, `?secret=`) on `/ws` and `/ws/collab` while `uvicorn.run(..., log_level="info")` logs full request paths.
  2. `YouTubeLiveAdapter.poll_once()` passes `api_key` in the `?key=` query string; any `aiohttp` transport exception containing the request URL is stored in `self.last_error` (`youtube.py:164`) and exposed unauthenticated via `GET /api/platforms/status` and `GET /api/status`.
  3. `Orchestrator._ingest_message()` (`core/orchestrator.py:1049`) prints raw unfiltered `msg.text` to stdout.
- **Verification Steps:** Inspect `run.py:123, 1624, 1694` and `core/platforms/youtube.py:123, 164`.
- **Blast Radius:** Token/secret leakage in server access logs, browser history, reverse-proxy logs, and unauthenticated status endpoints.
- **Recommended Fix:**
  1. Prefer WebSocket subprotocol or post-connect auth frame (or `Authorization` header for non-browser clients) instead of `?token=` / `?secret=` query parameters, and redact query strings in Uvicorn access logs.
  2. Pass YouTube API key via `X-Goog-Api-Key` header instead of `?key=` query parameter, and scrub URLs/secrets from `last_error` before returning in `/api/status` or `/api/platforms/status`.

---

### `[SEC-MED-003]` Desktop Whitelist Prefix-Match Anomaly & Non-Creator Minecraft Side Effects

- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/desktop/permission_manager.py:81-89`, `core/orchestrator.py:1210-1269`
- **Symptom:**
  1. `PermissionManager.evaluate_action()` checks `any(a.startswith(app_target) for a in allowed)` (`permission_manager.py:84`), allowing partial prefixes like `"n"` to pass policy evaluation for `"notepad.exe"` (though `DesktopController.launch_app()` at `controller.py:187-192` blocks it at execution time).
  2. In `Orchestrator._execute_interaction()` (`core/orchestrator.py:1210-1269`), non-creator chatters can still trigger Minecraft bot actions (`guard`, `gift`, `follow`, `jump`, `crouch`, `diam`/`stay` calling `stop_moving()`, and simulated `attack`/`nearby` events updating mood and relationships).
- **Verification Steps:** Inspect `core/desktop/permission_manager.py:84` and `core/orchestrator.py:1212-1267` (`"diam"` and `"stay"` are not in `is_crucial_mc` at line 1212, yet line 1247 calls `stop_moving()`).
- **Blast Radius:** Policy/audit log inconsistency in Desktop Companion; chatters can disrupt Minecraft gameplay (`stop_moving`, `guard_player`, `attack` simulation) without Creator approval.
- **Recommended Fix:**
  1. Replace `any(a.startswith(app_target) for a in allowed)` with exact normalized matching (matching `DesktopController.launch_app`).
  2. Gate `stop_moving`, `guard_player`, and `simulate_event` (`attack`/`nearby`) behind `is_creator` or configurable audience permissions.

---

### `[SEC-MED-004]` Docker & LAN Deployment Hardening Gaps

- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `Dockerfile:21-33`, `docker-compose.yml:6-23`, `.env.example:24-25`
- **Symptom:** The default container configuration binds port `7860:7860` on all host interfaces, runs with `MAYBEAI_CREATOR_TOKEN` empty by default, mounts `./config` and `./plugins` read-write, and lacks container runtime hardening (`read_only`, `cap_drop`, `no-new-privileges`).
- **Root Cause:** Combined with `[SEC-HIGH-001]` and `[SEC-HIGH-002]`, exposing port `7860` on a LAN or public interface without `MAYBEAI_CREATOR_TOKEN` and without TLS/reverse-proxy auth exposes unauthenticated read endpoints and breaks Creator WS auth.
- **Verification Steps:** Inspect `docker-compose.yml:7-23` and `Dockerfile:26-33`.
- **Blast Radius:** LAN/network-adjacent attackers can query diagnostics/memory/desktop endpoints and tamper with unauthenticated WS actions.
- **Recommended Fix:**
  1. Bind `docker-compose.yml` ports to `127.0.0.1:7860:7860` by default unless behind a TLS reverse proxy.
  2. Require `MAYBEAI_CREATOR_TOKEN` when `--host 0.0.0.0` is active.
  3. Add `security_opt: ["no-new-privileges:true"]` and `cap_drop: ["ALL"]` in `docker-compose.yml`, and mount `./plugins` as `:ro` if runtime plugin installation is not needed.

---

### `[SEC-LOW-001]` Ephemeral VTube Studio Auth Token & Plaintext `ws://` Transport

- **Severity:** Low
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/vts_client.py:15, 18, 95-108`, `.env.example:44-45`
- **Symptom:** `VTS_AUTH_TOKEN` documented in `.env.example` is never loaded by `VTSClient`, so `VTSClient` requests a new authentication token over plaintext `ws://` on every restart.
- **Root Cause:** `VTSClient.__init__` initializes `self.auth_token = None` (`vts_client.py:18`) and never reads `os.getenv("VTS_AUTH_TOKEN")`.
- **Verification Steps:** Inspect `core/vts_client.py:12-20, 95-108`.
- **Blast Radius:** Minor operational friction (re-approval in VTube Studio) and plaintext local WS traffic if VTS is on a non-loopback host.
- **Recommended Fix:** Wire `VTS_AUTH_TOKEN` into `VTSClient` (or persist securely) and warn if `vts.host` is non-loopback over `ws://`.

---

## 4. Prioritized Remediation Roadmap

1. **Immediate (P0):**
   - Lock down `/ws` actions (`memory_action`, `mood_action`, `relationship_action`, `multiplayer_action`, `minigame_action`, `story_action`, `trigger_improv`) and initial sensitive state broadcasts (`[SEC-CRIT-001]`).
   - Fix `_is_ws_creator_authorized` so `MAYBEAI_CREATOR_TOKEN` works over Docker/LAN (`[SEC-HIGH-001]`), and protect sensitive `GET /api/*` routes (`[SEC-HIGH-002]`).
   - Confine `ClipPipeline` paths to `data/clips` and escape FFmpeg filtergraph metacharacters (`[SEC-HIGH-003]`).
2. **Short-Term (P1):**
   - Add `message_id` nonce cache + `timestamp` freshness validation to `CollabManager.handle_incoming_envelope` (`[SEC-HIGH-005]`).
   - Wire `strict_mode` and `prompt_injection_filter` in `Orchestrator._ingest_message` to drop flagged messages and sanitize `user`/`donation_amount` (`[SEC-HIGH-004]`).
   - Enforce host-side plugin permission allowlists and remove/gate `inprocess` external plugin loading (`[SEC-CRIT-002]`).
3. **Hardening (P2):**
   - Add URL scheme/SSRF validation for outbound service URLs (`[SEC-MED-001]`), move WS tokens out of query strings (`[SEC-MED-002]`), tighten Docker Compose defaults (`[SEC-MED-004]`), and fix Desktop prefix matching (`[SEC-MED-003]`).
