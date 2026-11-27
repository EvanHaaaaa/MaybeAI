# MaybeAI Security & Operational Technology Audit (`audit/07_security.md`)

**Auditor:** AGENT 6 (`ng-sec`) — Security & Operational Technology Auditor  
**Scope:** Post-H0/H3 + `83298fa` verification across `run.py`, `core/security_net.py`, `core/moderator.py`, `core/orchestrator.py`, `core/plugins/`, `core/desktop/`, `core/highlights/clipper.py`, `core/youtube_karaoke.py`, `core/config_manager.py`, `core/conversation/engine.py`, and `web/shared-client.js`.  
**Methodology:** Static source-code verification against the live workspace. Zero source files were modified.

---

## 1. Executive Summary & L0–L5 Maturity Score

MaybeAI's post-Horizon 0–3 security posture has improved substantially over the pre-H0 baseline (`audit/06_security.md`). All critical pre-H0 gaps around unauthenticated `/ws` state mutations, unauthenticated sensitive `GET /api/*` routes, dead `Moderator` flags, unmasked `llm.*_api_key` fields, FFmpeg path/filtergraph escaping, and default-allow plugin permissions have been remediated in code.

**Overall Security & Operational Technology Maturity Score: `L3` (Defined & Enforced Baseline)**

| Security Domain | L0–L5 Score | Summary |
| :--- | :---: | :--- |
| **HTTP/WS AuthN, AuthZ & Origin Controls** | **L3.5** | Token-first Creator auth (Docker/LAN-safe), Origin allowlist, sensitive `GET /api/*` & `/ws` action gating. Frontend `CreatorAuth` still stores tokens in `localStorage` and sends `?token=` on WS URLs. |
| **Plugin Sandbox & Capability Model** | **L2.5** | Static AST manifest, default-deny `granted_permissions`, stripped env, Linux `bwrap` + `rlimit`, Windows Job Object. On Windows, FS/network isolation relies on Python-level monkeypatches bypassable via `ctypes`/`subprocess`. |
| **Operational Technology (YouTube, FFmpeg, OBS)** | **L3.5** | `ClipPipeline` path confinement & filtergraph escaping; `YouTubeKaraokeProcessor` SSRF + host allowlist + canonical URL + duration bounds; `OBSWebSocketClient` disabled by default with masked password. |
| **Prompt Injection & Secret Management** | **L3.0** | `Moderator` drops injected/strict-mode chat; `ConfigManager` masks all 8 secret fields (`llm.*_api_key` included). Indirect OCR/VLM screen text (`obs.summary`) enters the system prompt unsanitized. |

---

## 2. Verification Matrix (Post-H0/H3 + `83298fa`)

| Control / Claim | Verification Status | Capability Status | Primary Evidence |
| :--- | :---: | :---: | :--- |
| Origin validation on HTTP mutating/sensitive routes & WS | `VERIFIED` | `EXISTING` | `run.py:53-86, 119-128, 462-476, 949-952, 1854-1857` |
| Creator token auth (token-first for Docker/LAN) | `VERIFIED` | `EXISTING` | `run.py:88-117, 152-171` |
| Non-query WS auth (`Sec-WebSocket-Protocol`) | `PARTIALLY VERIFIED` | `INCOMPLETE` | Server supports `maybeai.token.` (`run.py:137-170, 954-960`); frontend still uses `?token=` (`web/shared-client.js:71-82, 164`) |
| `GET /api/*` & `/ws` action gating + private WS event filtering | `VERIFIED` | `EXISTING` | `run.py:439-476, 914-944, 963-966, 1070-1090, 1126-1188, 1759-1836` |
| `validate_outbound_url` SSRF & DNS-rebinding guard | `PARTIALLY VERIFIED` | `EXISTING` | `core/security_net.py:1-188` (DNS resolved & checked, but URL string returned without IP pinning -> TOCTOU window) |
| `PluginRegistry` AST manifest + `granted_permissions` default-deny | `VERIFIED` | `EXISTING` | `core/plugins/registry.py:613-635, 735-829, 869-875` |
| `sandbox_worker.py` boundary guards + Windows Job Object / Linux `rlimit`/`bwrap` | `PARTIALLY VERIFIED` | `INCOMPLETE` | `core/plugins/registry.py:35-151, 221-283`; `core/plugins/sandbox_worker.py:28-196` (Python monkeypatch on Windows) |
| `ClipPipeline` traversal confinement & filtergraph escaping | `VERIFIED` | `EXISTING` | `core/highlights/clipper.py:10-34, 56-59, 102-115`; `run.py:349-366` |
| `YouTubeKaraokeProcessor` URL/host/SSRF/duration bounds | `VERIFIED` | `EXISTING` | `core/youtube_karaoke.py:24-78, 132-276`; `core/orchestrator.py:1830-1875` |
| `Moderator` strict/injection filtering & metadata sanitization | `VERIFIED` | `EXISTING` | `core/moderator.py:7-165`; `core/orchestrator.py:1200-1218` |
| `llm.*_api_key` & all secret masking in `ConfigManager` | `VERIFIED` | `EXISTING` | `core/config_manager.py:258-267, 292-313, 2072-2104` |
| `localStorage` Creator token persistence | `REPRODUCED` | `INCOMPLETE` | `web/shared-client.js:22-53`; `web/app.js:163-192`; `web/settings.js:24-52`; `web/deck.js:15-20`; `web/overlay.js:194` |
| Indirect OCR/VLM prompt injection sanitization | `NOT VERIFIED` (Gap) | `INCOMPLETE` | `core/conversation/engine.py:316-325` interpolates `obs.summary` raw into system prompt |

---

## 3. Explicit Domain Assessments

### 3.1 Plugin Workers (`core/plugins/`)
- **Discovery & Manifest**: `PluginRegistry._extract_manifest_from_ast()` (`core/plugins/registry.py:735-829`) parses `PluginManifest` and `@plugin_command`/`@plugin_event` via `ast.parse` + `ast.literal_eval` without executing plugin code. Dynamic/unparseable plugins are recorded as blocked (`_record_blocked_plugin`).
- **Default-Deny Capabilities**: `_get_effective_permissions()` (`core/plugins/registry.py:613-623`) intersects manifest-requested permissions with `plugins.granted_permissions` (default `{}` in `core/config_manager.py:210`). Host RPC callbacks (`_handle_worker_callback`, `core/plugins/registry.py:404-489`) enforce `tts:speak` and `event:pub` before executing `speak`, `broadcast`, or `event_bus.publish`.
- **Environment & OS Isolation**:
  - `_build_sandbox_env()` (`core/plugins/registry.py:644-654`) strips all host secrets, passing only `PATH`, `PYTHONUNBUFFERED`, `PYTHONPATH`, and `SYSTEMROOT` (Windows).
  - **Linux**: Uses `bwrap` (`--die-with-parent`, `--new-session`, `--unshare-net` unless `net:outbound`, `--ro-bind` system/plugin, `--bind` scratch_dir) when available (`core/plugins/registry.py:221-242`), plus `RLIMIT_AS`/`RLIMIT_DATA` (512 MB) and `RLIMIT_NOFILE` (128) in `apply_os_resource_limits()` (`core/plugins/sandbox_worker.py:28-72`).
  - **Windows**: `_WindowsJobObject.attach()` (`core/plugins/registry.py:35-151`) enforces `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `ProcessMemoryLimit=512MB`, and `ActiveProcessLimit=2`.
  - **Gap**: `install_boundary_guards()` (`core/plugins/sandbox_worker.py:89-196`) only monkeypatches `builtins.open`, `io.open`, `os.open`, and 4 `socket` methods (`connect`, `connect_ex`, `create_connection`, `socketpair`). On Windows (no `bwrap`/seccomp), a malicious plugin can bypass these Python-level hooks via `ctypes`, `subprocess.Popen`, `os.system`, `os.remove`/`Path.unlink`, or UDP `socket.sendto` to read `.env`/`config/settings.json` or exfiltrate data. Additionally, `sandbox_mode="inprocess"` remains an accepted config value (`VALID_SANDBOX_MODES`, `core/plugins/registry.py:27`).

### 3.2 YouTube Downloads (`core/youtube_karaoke.py`)
- `extract_youtube_video_id()` (`core/youtube_karaoke.py:49-77`) enforces `validate_outbound_url(..., allowed_schemes=("https", "http"), allow_private=False)`, restricts hostnames to `_YOUTUBE_HOSTS`, validates an 11-character `_VIDEO_ID_RE` (`^[A-Za-z0-9_-]{11}$`), and reconstructs a canonical URL (`https://www.youtube.com/watch?v={video_id}`), preventing flag or URL injection into `yt-dlp`.
- `prepare_song()` (`core/youtube_karaoke.py:180-276`) fetches metadata with `--dump-single-json --no-playlist` (30s timeout), enforces `duration <= self.max_duration_sec` (default 600s, min 30s), and executes `yt-dlp`, `demucs`, and `ffmpeg` via `asyncio.create_subprocess_exec` (no `shell=True`) with bounded timeouts (180s/300s/120s).
- **Gap**: `yt-dlp` does not pass `--max-filesize` (only duration is bounded), and `POST /api/performance/youtube` (`run.py:756-766`) has no concurrent job cap or rate limit (though gated behind Creator auth).

### 3.3 OBS Controls (`core/desktop/obs_client.py`, `core/desktop/permission_manager.py`, `run.py`)
- `OBSWebSocketClient` (`core/desktop/obs_client.py:23-93`) is disabled by default (`enabled=False`), uses `asyncio.to_thread` for `obsws_python.ReqClient`, and `obs.password` is masked in `ConfigManager.SECRET_MASK_FIELDS` (`core/config_manager.py:266`).
- `POST /api/obs/action` (`run.py:893-898`) is gated by `verify_api_origin_middleware` (Origin + Creator auth).
- Autonomous AI desktop requests route through `DesktopCompanionEngine.request_action()` (`core/desktop/engine.py:93-150`) and `PermissionManager.evaluate_action()` (`core/desktop/permission_manager.py:57-100`), which classify `start_stream`/`stop_stream`/`change_stream_key` as `RiskLevel.HIGH` (requiring confirmation) and scene switching as `RiskLevel.MEDIUM`.

### 3.4 Prompt Injection (`core/moderator.py`, `core/orchestrator.py`, `core/conversation/engine.py`)
- **Direct Chat & Metadata**: `Moderator` (`core/moderator.py:7-14, 96-165`) defines `_PROMPT_INJECTION_PATTERNS` and `sanitize_metadata()` (stripping control characters and `<|...|>`/`[SYSTEM]`/`[INST]` delimiters). `Orchestrator._ingest_message()` (`core/orchestrator.py:1205-1215`) actively drops messages when `has_injection` is True (when `prompt_injection_filter` is enabled) or when `strict_mode` is True and `not is_creator_flag`.
- **Indirect OCR/VLM Prompt Injection Gap**: `core/conversation/engine.py:316-325` interpolates `obs.summary` (produced by `MultimodalVisionModel.analyze_with_vlm_api()` in `core/vision/vlm.py:176-230`) directly into the `[LIVE VISUAL PERCEPTION / SCREEN AWARENESS]` system prompt without running `Moderator.sanitize_metadata()` or wrapping it in untrusted-content delimiters.

---

## 4. Remaining Security Gaps & Recommendations

### `[SEC-GAP-001]` Frontend WebSocket Auth Still Uses Query String `?token=` & `localStorage`
- **Severity:** High | **Classification:** `REPRODUCED` | **Capability:** `INCOMPLETE`
- **Location:** `web/shared-client.js:22-53, 71-82, 164`; `web/app.js:502`; `web/deck.js:394`; `web/overlay.js:238`; `run.py:160, 1869-1870`
- **Mechanics:** Although `run.py:137-170` implements `Sec-WebSocket-Protocol: maybeai.token.<token>`, the frontend `CreatorAuth.buildWsUrl()` still appends `?token=<token>` to the WS URL, and `new WebSocket(url)` is called without subprotocols. Tokens are also persisted in `localStorage`, exposing them to any XSS payload.
- **Recommendation:** Update `CreatorAuth` / `ReconnectingWebSocket` to pass `["maybeai.token." + token]` as the `WebSocket(url, protocols)` second argument, remove `?token=` from `buildWsUrl()`, deprecate query-param token acceptance in `run.py:160`, and prefer `sessionStorage` or `HttpOnly` session cookies over `localStorage`.

### `[SEC-GAP-002]` Windows Plugin Sandbox Relies on Bypassable Python Monkeypatches
- **Severity:** High | **Classification:** `VERIFIED` | **Capability:** `INCOMPLETE`
- **Location:** `core/plugins/sandbox_worker.py:89-196`; `core/plugins/registry.py:27, 265-273`
- **Mechanics:** On Windows, `_WindowsJobObject` limits memory (512 MB) and process count (2), but does not restrict filesystem or network access. `install_boundary_guards()` only wraps `builtins.open`, `io.open`, `os.open`, and 4 TCP `socket` methods, leaving `ctypes`, `subprocess`, `os.system`, `Path.unlink`, and UDP sockets unguarded.
- **Recommendation:** On Windows, run untrusted plugins under a low-privilege OS user / AppContainer token (`CreateRestrictedToken`) or inside a Docker/WSL2 `bwrap` container, and disallow `sandbox_mode="inprocess"` for non-builtin plugins in production.

### `[SEC-GAP-003]` Indirect OCR/VLM Prompt Injection via `obs.summary`
- **Severity:** Medium | **Classification:** `VERIFIED` | **Capability:** `INCOMPLETE`
- **Location:** `core/conversation/engine.py:316-325`; `core/vision/vlm.py:176-230`
- **Mechanics:** On-screen text transcribed by the VLM into `obs.summary` is injected verbatim into the system prompt (`[LIVE VISUAL PERCEPTION / SCREEN AWARENESS]`), bypassing `Moderator` injection filtering.
- **Recommendation:** Pass `obs.summary` and `obs.eve_commentary` through `Moderator.sanitize_metadata()` / `_PROMPT_INJECTION_PATTERNS` and wrap visual observations in explicit untrusted-data tags (e.g., `<visual_observation_data>...</visual_observation_data>`) with a system instruction to never execute directives found inside screen text.

### `[SEC-GAP-004]` `validate_outbound_url` DNS-Rebinding TOCTOU Window
- **Severity:** Low–Medium | **Classification:** `PARTIALLY VERIFIED` | **Capability:** `EXISTING`
- **Location:** `core/security_net.py:127-188`
- **Mechanics:** `validate_outbound_url()` resolves DNS and validates all returned IPs, then returns the original URL string. The caller (`aiohttp`/`websockets`) performs a second DNS lookup at connect time, leaving a DNS-rebinding TOCTOU window.
- **Recommendation:** Have `validate_outbound_url()` optionally return the pinned IP (or provide an `aiohttp.TCPConnector` / custom resolver) so outbound connections connect directly to the validated IP with the `Host` / SNI header preserved.

### `[SEC-GAP-005]` Unbounded File Size & Job Queue in YouTube Karaoke + Initial WS `mission_status`/`collab_state`
- **Severity:** Low | **Classification:** `VERIFIED` | **Capability:** `EXISTING`
- **Location:** `core/youtube_karaoke.py:254-273`; `run.py:756-766, 1093-1100`
- **Mechanics:** `yt-dlp` lacks `--max-filesize` (only `max_duration_sec` is checked), and `POST /api/performance/youtube` has no concurrency cap. Separately, `/ws` sends `mission_status` and `collab_state` on initial connect (`run.py:1093-1100`) even when `ws_creator_authorized=False`.
- **Recommendation:** Add `--max-filesize 100M` to `yt-dlp` args, cap concurrent YouTube jobs to 1–2, and gate `mission_status` / `collab_state` initial pushes behind `ws_creator_authorized` if considered operational metadata.
