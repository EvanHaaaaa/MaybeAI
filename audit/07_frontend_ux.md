# 07 — Frontend & User Experience Engineering Audit

**Auditor:** AGENT 7 — Frontend & UX Engineering Auditor (`cto-frontend`)  
**Scope:** `web/index.html`, `web/app.js`, `web/overlay.html`, `web/overlay.js`, `web/overlay.css`, `web/settings.html`, `web/settings.js`, `web/deck.html`, `web/deck.js`, `web/audio-worklet-processor.js`, and static/WebSocket serving in `run.py`.  
**Syntax Verification:** `node --check` passed with exit code `0` on all 5 JS files (`app.js`, `audio-worklet-processor.js`, `deck.js`, `overlay.js`, `settings.js`).

---

## 1. Capability Classification Matrix

### Current Capability (Verified in Source)
- **Studio Dashboard (`/` — `web/index.html`, `web/app.js`):** 4-tab modular workspace (`stage`, `gaming`, `rpg`, `brain`) persisted in `localStorage` (`maybeai_active_workspace`); dual Creator VIP vs. Audience Stream chat with unread counter; 2D Canvas avatar with lip-sync, blinking, emotions, and karaoke musical notes; Web Audio API FIFO TTS playback with `AnalyserNode` RMS lip-sync (`app.js:178-296`); AudioWorklet 16 kHz PCM mic streaming with `SpeechRecognition` fallback and VAD barge-in (`app.js:1016-1120`); panels for Chess, Minecraft, Minigames, Storytelling/RPG, Episodic Memory, Dossier, Relationships, Goals, Multiplayer/Collab, Desktop Companion, Performance/Karaoke, Plugins, OBS, and Highlights.
- **OBS Stage Overlay (`/overlay` — `web/overlay.html`, `web/overlay.js`, `web/overlay.css`):** Transparent browser-source overlay supporting `?hide_avatar=1`, `?hide_subs=1`, `?muted=1`, `?renderer=vrm`, `?vrm_url=...`, and `?token=...`; 2D Canvas + optional 3D VRM avatar; Web Audio API unmuted-by-default FIFO playback with RMS lip-sync; floating subtitles and donation alert banner using safe `textContent` assignment (`overlay.js:300, 324-326`).
- **Mobile Creator Stream Deck (`/deck` — `web/deck.html`, `web/deck.js`, `web/deck.css`):** Touch-friendly control surface with live status pills (`WS`, `Mood`, `Mission`, `Barge-In`, `Scene`), creator token prompt bar (`#deck-auth-bar`) on `401`/`403` or WS `forbidden`, AudioWorklet mic streaming, mute toggle, mission step/loop, karaoke, improv, collab topic drawer, stop speech, and highlight marking.
- **Configuration Center (`/settings` — `web/settings.html`, `web/settings.js`, `web/settings.css`):** Schema-driven settings editor across 23 categories with live search, dirty-state tracking, `Ctrl+S` save/hot-reload (`PUT /api/config`), category/full reset (`POST /api/config/reset`), and System Diagnostics cards with live subsystem test probes (`POST /api/config/test/{testName}`).
- **AudioWorklet Downsampler (`web/audio-worklet-processor.js`):** `MaybeAIPCMProcessor` (`maybeai-pcm-processor`) mixing multi-channel input to mono, resampling to 16 kHz Int16 PCM in 512-sample (32 ms) transferable `ArrayBuffer` frames.

### Partially Implemented
- **Creator Authentication UX Across Surfaces:** `/deck` implements `#deck-auth-bar` and handles `401`/`403` and WS `error` (`code === "forbidden"`), whereas `/` and `/settings` rely solely on `?token=` or pre-populated `localStorage` (`maybeai_creator_token`) with no UI prompt or error recovery.
- **3D VRM Avatar Renderer:** Implemented in both `app.js:5375-5530` and `overlay.js:637-677` with graceful 2D fallback, but depends on external CDN imports (`https://esm.sh/three@0.169.0` and `@pixiv/three-vrm@3.2.0`) and lacks WebGL disposal or VRM URL validation.
- **AudioWorklet End-of-Utterance Flushing:** `MaybeAIPCMProcessor._flush()` (`audio-worklet-processor.js:30-36`) sends the final partial PCM frame on `stop`, but main-thread handlers in `app.js` and `deck.js` flip `isListeningMic`/`isMicActive` to `false` before the async port message arrives, dropping the tail frame.

### Planned Capability (Not Implemented in Frontend)
- **Resilient WebSocket Reconnection & State Re-sync:** Exponential backoff with jitter, auth-failure circuit breaking, and state re-sync on `/overlay` reconnect (`overlay.js` has no `ws.onopen` handler).
- **Live Telemetry & Connection Status in `/settings`:** `#connectionStatusBadge` (`settings.html:31-34`) is static HTML with no WebSocket or polling heartbeat.
- **Offline/Bundled Assets:** Local vendoring of Three.js, `@pixiv/three-vrm`, and fonts (`Outfit`, `JetBrains Mono`) for air-gapped LAN streaming.

### Proposed Innovation
- **Binary WebSocket Frames for AudioWorklet PCM:** Replace per-frame JSON + base64 encoding (31.25 frames/s) with binary `ArrayBuffer` WebSocket frames or a 1-byte message-type prefix to eliminate GC pressure and base64 overhead.
- **Shared Frontend Auth & WS Client Module:** Extract `CreatorAuth` + `ReconnectingWebSocket` (with exponential backoff, jitter, and token modal) into a shared `web/shared-client.js` imported by `/`, `/settings`, `/overlay`, and `/deck`.

---

## 2. Detailed Findings

### `[UI-HIGH-001]` Unescaped Config & Telemetry Interpolation into `innerHTML` in `/settings`
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `web/settings.js:180-191`, `web/settings.js:237-243`, `web/settings.js:458-471`, `web/settings.js:498-634`
- **Symptom:** User-editable configuration values and schema metadata are interpolated directly into `settingsContent.innerHTML` without HTML escaping.
- **Root Cause:** Although `settings.js` defines `escapeHtml()` (`settings.js:45-50`) and `escapeAttr()` (`settings.js:288-294`), `renderDiagnosticsView()` (`settings.js:498-634`) interpolates `diag.uptime_human`, `modules.llm_brain?.provider`, `modules.llm_brain?.model`, `modules.tts?.voice`, `modules.tts?.rate`, `modules.tts?.pitch`, `modules.vts?.host`, `modules.vts?.port`, and `modules.twitch?.channel` raw into HTML. Similarly, `renderCategorySettingsView()` (`settings.js:180-191`), `renderControlHtml()` (`settings.js:237-243` for `select` options and `250` for `number`), and `renderSearchResults()` (`settings.js:458-471`) interpolate `item.path`, `item.label`, `item.description`, `opt.value`, and `opt.label` unescaped.
- **Verification Steps:**
  1. Set `twitch.channel` (or `llm.model`) via `PUT /api/config` to `<img src=x onerror=alert(1)>`.
  2. Open `/settings` (which defaults to `activeCategory = "diagnostics"`).
  3. Observe script execution when `settingsContent.innerHTML = html` executes at `settings.js:648`.
- **Blast Radius:** Stored DOM XSS in the highest-privilege creator surface (`/settings`), enabling theft of `localStorage.maybeai_creator_token` or arbitrary `PUT /api/config` / `POST /api/config/reset` calls.
- **Recommended Fix:** Wrap all dynamic values in `renderDiagnosticsView()`, `renderCategorySettingsView()`, `renderSearchResults()`, and `renderControlHtml()` with `escapeHtml()` / `escapeAttr()`.

---

### `[UI-HIGH-002]` Missing Creator Token Entry UI & Unchecked `401/403` Responses in `/` and `/settings`
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `web/settings.js:77-98`, `web/app.js:145-175`, `web/app.js:374-566`, `web/index.html` (no auth bar), `web/settings.html` (no auth bar)
- **Symptom:** When `security.creator_token` is configured on the backend (`run.py:89`), opening `/` or `/settings` without `?token=` in the URL fails silently or crashes `/settings` on the loading screen.
- **Root Cause:**
  1. In `settings.js:79-83`, `init()` calls `authFetch(...).then(r => r.json())` without checking `r.ok`. When `/api/config/schema` returns `401`/`403` (`{"detail": "..."}`), `schema` is assigned an object rather than an array, causing `TypeError: schema.filter is not a function` when rendering.
  2. In `app.js:374-566`, `handleWsMessage()` has no branch for `msg.type === "error"` (e.g., `data.code === "forbidden"`), unlike `deck.js:331-333` which reveals `#deck-auth-bar`.
  3. Neither `index.html` nor `settings.html` has a token input UI.
- **Verification Steps:**
  1. Configure `security.creator_token` in `config/settings.yaml` and start `run.py`.
  2. Open `http://localhost:8000/settings` in a clean browser session without `?token=`.
  3. Observe `401`/`403` responses parsed as JSON and `schema.filter is not a function` in DevTools Console.
- **Blast Radius:** Complete UX lockout on `/settings` and silent control failure on `/` whenever creator authentication is enabled, forcing users to manually craft `?token=` URLs.
- **Recommended Fix:** Check `if (!r.ok)` in `settings.js:init()`, handle `msg.type === "error"` in `app.js`, and add a shared creator-token modal/bar (matching `#deck-auth-bar`) to both `/` and `/settings`.

---

### `[UI-HIGH-003]` Uncapped 2000ms WebSocket Reconnection Loop & `deck.js` Double-Connection Race
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `web/app.js:361-369`, `web/overlay.js:198-204`, `web/deck.js:315-325`, `web/deck.js:383-385`
- **Symptom:** Disconnected clients hammer `/ws` every 2000ms indefinitely with no backoff; `/overlay` loses state synchronization after reconnect; `/deck` spawns duplicate WebSocket connections when saving a creator token.
- **Root Cause:**
  1. `app.js:364`, `overlay.js:199`, and `deck.js:320` all hardcode `reconnectTimer = setTimeout(connectWs, 2000)` without exponential backoff, jitter, or stopping on policy/origin rejection (`1008`).
  2. `overlay.js:176-207` defines `ws.onclose`, `ws.onerror`, and `ws.onmessage`, but no `ws.onopen` handler, so state is never re-synced after a disconnect.
  3. `deck.js:384-385` calls `ws.close()` and immediately calls `connectWs()` without nulling `ws.onclose` first; the closed socket's async `onclose` event fires and schedules another `connectWs()` 2 seconds later.
- **Verification Steps:**
  1. Open `/deck`, enter a token in `#deck-auth-bar`, and click Save Token (`deck.js:379-387`).
  2. Observe `ws.close()` triggering `onclose` -> `setTimeout(connectWs, 2000)` even though `connectWs()` already opened a new socket.
  3. Stop the backend server and observe Network tab showing synchronized 2000ms `/ws` retries across all open tabs.
- **Blast Radius:** Unnecessary server/browser churn during restarts or origin/auth blocks, stale OBS overlay state after transient disconnects, and duplicate event handling on `/deck`.
- **Recommended Fix:** Implement bounded exponential backoff with jitter (e.g., 1s -> 2s -> 4s -> max 30s), detach `ws.onclose = null` before manual `ws.close()`, and add `ws.onopen` state refresh in `overlay.js`.

---

### `[UI-MED-001]` Uncaught `JSON.parse` in Dashboard WebSocket Message Handler
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `web/app.js:374-375`
- **Symptom:** Any malformed or non-JSON WebSocket frame received on `/` throws an uncaught `SyntaxError` in `handleWsMessage`.
- **Root Cause:** `app.js:375` executes `const msg = JSON.parse(event.data);` without a `try / catch` block, unlike `overlay.js:211-215` and `deck.js:329`.
- **Verification Steps:** Inspect `web/app.js:374-376`; send a non-JSON text frame over `/ws` and observe uncaught `SyntaxError` in console.
- **Blast Radius:** Breaks message processing for that event and pollutes browser error telemetry.
- **Recommended Fix:** Wrap `JSON.parse(event.data)` in `try { ... } catch (e) { return; }`.

---

### `[UI-MED-002]` AudioWorklet Linear Resampler Skips `mono[0]` & Drops Tail Audio Frame on Stop
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `web/audio-worklet-processor.js:83-95`, `web/app.js:882-886`, `web/app.js:1048`, `web/deck.js:176`, `web/deck.js:228-233`
- **Symptom:** AudioWorklet 16 kHz resampling introduces a 1-sample discontinuity at quantum boundaries when `pos < 1`, and the final <32 ms PCM tail flushed on mic stop is discarded.
- **Root Cause:**
  1. At `audio-worklet-processor.js:88`, `const s0 = idx === 0 && pos < 1 ? this._lastSample : mono[idx];` and `const s1 = idx + 1 < frameLen ? mono[idx + 1] : mono[idx];`. When `pos` is in `[0, 1)`, `idx` is `0`, so `s0` uses `_lastSample` and `s1` uses `mono[1]`—skipping `mono[0]` entirely.
  2. When stopping the mic, `app.js:1099` (`isListeningMic = false`) and `deck.js:228` (`updateMicButton(false)`) clear the active flag before `workletNode.port.postMessage({ type: "stop" })` triggers `_flush()`. When the flushed `pcm16` message arrives asynchronously on `port.onmessage`, the guard (`if (!isListeningMic ...) return;`) drops it.
- **Verification Steps:** Trace `audio-worklet-processor.js:84-94` with `srcRate = 48000`, `dstRate = 16000` (`ratio = 3`), `this._phase = 0.5`: `idx = 0`, `s0 = this._lastSample`, `s1 = mono[1]`, `mono[0]` is never read.
- **Blast Radius:** Subtle audio aliasing/clicking at 128-sample Web Audio quantum boundaries (every ~2.67 ms at 48 kHz) and truncated final phoneme on mic stop.
- **Recommended Fix:** Interpolate between `this._lastSample` and `mono[0]` when `pos < 0` (if tracking negative fractional phase) or between `mono[idx]` and `mono[idx + 1]` for `pos >= 0`, and allow flushed `pcm16` frames to be sent before tearing down the `port.onmessage` listener.

---

### `[UI-MED-003]` Residual Unescaped `innerHTML` Sinks in Memory & Goal Cards (While Chat/Overlay Are Safe)
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `web/app.js:1797-1807`, `web/app.js:2173-2193`
- **Symptom:** Episodic memory cards and goal tier cards interpolate several backend-supplied fields into `innerHTML` without `escapeHtml()`.
- **Root Cause:**
  - In `renderMemoryCards()` (`app.js:1797-1807`), `mem.title`, `mem.episode_type`, `mem.content`, and `mem.user` are escaped, but `badgeCls` (derived from `mem.episode_type`), `emotionStr` (`mem.emotional_tag`), and `dateStr` (`mem.date_str`) are not escaped.
  - In `updateGoalUi()` (`app.js:2173, 2189`), `g.id` and `tierKey` are interpolated unescaped.
  - **Positive Verification:** Live chat (`addChatMessage` at `app.js:621-625`), OBS subtitles (`overlay.js:300` via `textContent`), and donation alerts (`app.js:592-594`, `overlay.js:324-326` via `textContent`) are **safe** from DOM XSS.
- **Verification Steps:** Inspect `web/app.js:1792-1807` and `web/app.js:2173-2193`.
- **Blast Radius:** Low-to-medium stored XSS risk if an LLM-extracted `emotional_tag` or crafted memory/goal record contains HTML metacharacters.
- **Recommended Fix:** Apply `escapeHtml()` to `emotionStr`, `dateStr`, `badgeCls`, `g.id`, and `tierKey`, or construct elements via `document.createElement` + `textContent`.

---

### `[UI-MED-004]` External CDN Dependency for 3D VRM & Fonts Breaks Offline/LAN Streaming
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `web/app.js:5421-5425`, `web/overlay.js:640-644`, `web/index.html:8`, `web/overlay.html:8`, `web/settings.html:8`, `web/deck.html:8`
- **Symptom:** 3D VRM mode fails and falls back to 2D Canvas in offline/air-gapped environments or when `esm.sh` is blocked/throttled; OBS overlay also lacks WebGL context cleanup and VRM URL scheme validation.
- **Root Cause:** `initAndLoadVrm()` (`app.js:5421-5425`) and `initOverlayVrm()` (`overlay.js:640-644`) dynamically `import()` `https://esm.sh/three@0.169.0` and `https://esm.sh/@pixiv/three-vrm@3.2.0?deps=three@0.169.0` from the public internet. All four HTML entrypoints also reference `https://fonts.googleapis.com`. Additionally, `overlay.js:25, 661` passes `?vrm_url=` directly to `GLTFLoader.loadAsync()` without validating `http:`/`https:`/relative path schemes.
- **Verification Steps:** Block `esm.sh` in browser DevTools or disconnect internet; switch to `3D VRM` in `/` or open `/overlay?renderer=vrm&vrm_url=...`; observe fallback `"Offline / Load Failed (2D Fallback)"`.
- **Blast Radius:** 3D VRM avatars are unusable in offline/LAN-only broadcast setups.
- **Recommended Fix:** Bundle or vendor `three` and `@pixiv/three-vrm` under `web/vendor/` (served via `/static/vendor/...`), validate `vrm_url` schemes, and dispose `vrmRenderer` on `beforeunload`.

---

### `[UI-LOW-001]` Static Hardcoded Connection Badge in Configuration Center (`/settings`)
- **Severity:** Low
- **Evidence Classification:** `VERIFIED`
- **Location:** `web/settings.html:31-34`, `web/settings.js`
- **Symptom:** The top-right status pill always displays `SYSTEM ONLINE` even when the backend is stopped or returning HTTP errors.
- **Root Cause:** `settings.html:31-34` hardcodes `class="status-pill status-online"` and `SYSTEM ONLINE`, and `settings.js` never queries or updates `#connectionStatusBadge` or `#connectionText`.
- **Verification Steps:** Open `/settings`, stop `run.py`, and observe the header badge still reads `SYSTEM ONLINE`.
- **Blast Radius:** Misleading operator feedback during server restarts or failures.
- **Recommended Fix:** Update `#connectionStatusBadge` based on `authFetch` health/errors or a lightweight `/api/system/diagnostics` heartbeat.

---

### `[UI-LOW-002]` Per-Frame String Concatenation Base64 Encoding & `localStorage` Token Exposure
- **Severity:** Low
- **Evidence Classification:** `VERIFIED`
- **Location:** `web/app.js:780-787`, `web/deck.js:77-84`, `web/app.js:145-163`, `web/settings.js:13-31`, `web/overlay.js:184-193`
- **Symptom:** `arrayBufferToBase64()` builds strings byte-by-byte 31.25 times/sec during AudioWorklet streaming, and `creator_token` is persisted in `localStorage` and passed via `?token=` query strings.
- **Root Cause:** `for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);` runs on every 512-sample (1024-byte) frame. Meanwhile, `?token=` URLs leak into browser history/logs and `localStorage` is readable by any XSS payload (such as `[UI-HIGH-001]`).
- **Verification Steps:** Inspect `web/app.js:780-787` and `web/app.js:147-163`.
- **Blast Radius:** Minor CPU/GC overhead during long voice sessions; amplified credential exposure if any XSS is triggered.
- **Recommended Fix:** Use `String.fromCharCode.apply(null, bytes)` (safe for 1024-byte chunks) or binary WebSocket frames, and migrate creator auth to `HttpOnly` session cookies for browser pages.

---

## 3. Summary & UX Consistency Verdict

| Surface | Auth UX | XSS Posture | WS Resilience | Offline Readiness |
| :--- | :--- | :--- | :--- | :--- |
| `/` Studio Dashboard | Missing UI (`[UI-HIGH-002]`) | Chat/Subs/Donos safe; Memory/Goal minor gaps (`[UI-MED-003]`) | Fixed 2s retry, uncaught `JSON.parse` (`[UI-HIGH-003]`, `[UI-MED-001]`) | 2D works; 3D VRM & Fonts require internet (`[UI-MED-004]`) |
| `/settings` Config Center | Crashes on 401/403 (`[UI-HIGH-002]`) | **High-risk `innerHTML` sinks** (`[UI-HIGH-001]`) | No WS / static `SYSTEM ONLINE` (`[UI-LOW-001]`) | Fonts require internet (`[UI-MED-004]`) |
| `/overlay` OBS Stage | `?token=` + `localStorage` | Safe (`textContent` only) | Fixed 2s retry, no `onopen` re-sync (`[UI-HIGH-003]`) | 2D works; 3D VRM & Fonts require internet (`[UI-MED-004]`) |
| `/deck` Stream Deck | Complete (`#deck-auth-bar`) | Safe (`textContent` only) | Fixed 2s retry + token-save race (`[UI-HIGH-003]`) | Fonts require internet (`[UI-MED-004]`) |
