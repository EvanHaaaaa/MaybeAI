# 08 — Frontend, UX & Avatar Experience Audit (Post-Implementation)

**Auditor:** AGENT 7 (`ng-frontend`) — Frontend, UX & Avatar Experience Auditor  
**Scope:** Post-H0/H1/H2/H3 + `83298fa` (`web/index.html`, `web/app.js`, `web/style.css`, `web/shared-client.js`, `web/overlay.*`, `web/settings.*`, `web/deck.*`, `web/audio-worklet-processor.js`, `web/vendor/`)  
**Syntax Check:** `node --check web/app.js web/overlay.js web/settings.js web/deck.js web/shared-client.js web/audio-worklet-processor.js` — **PASSED** (exit code `0`).

---

## 1. Executive Summary & Maturity Scores

The MaybeAI frontend has matured significantly from loose static pages into a **multi-surface creator control ecosystem** backed by a shared client utility layer (`web/shared-client.js`), an air-gapped local vendor bundle (`web/vendor/`), a real-time 16 kHz `AudioWorklet` PCM pipeline (`web/audio-worklet-processor.js`), and Web Audio API RMS lip-sync arbitration (`isLocalAudioPlaying`).

However, structurally it remains **four separate HTML/JS applications** (`/`, `/settings`, `/overlay`, `/deck`) rather than a unified single-page Creator Studio, with `web/index.html` (2,255 lines) and `web/app.js` (5,896 lines) acting as a monolithic control panel containing 4 workspace tabs (`stage`, `gaming`, `rpg`, `brain`) and ~20 feature cards.

| Dimension | Maturity Score | Rationale |
| :--- | :---: | :--- |
| **Frontend & Avatar UX** | **L3 (Defined / Functional)** | Solid 2D Canvas + offline 3D VRM fallback, Web Audio RMS lip-sync arbitration, `AudioWorklet` 16 kHz PCM streaming, dedicated OBS overlay & mobile Stream Deck. Held back by monolithic `app.js` (5,896 lines), mixed Indonesian/English UI copy, and missing keyboard/focus/reduced-motion accessibility. |
| **Frontend Developer Experience (DX)** | **L2 (Managed / Basic)** | `web/shared-client.js` cleanly centralizes `CreatorAuth`, `ReconnectingWebSocket`, and `escapeHtml`, and all JS files pass `node --check`. However, zero bundler/TypeScript/module system, duplicated fallback helpers across `app.js`/`settings.js`/`deck.js`, and a 5.9k-line global DOM script create high maintenance friction. |

---

## 2. Claim & Capability Verification Matrix

| Item / Claim | Verification Status | Capability Status | Evidence & File References |
| :--- | :---: | :---: | :--- |
| **`MaybeAIClient.CreatorAuth`** (token persistence, `authFetch`, `buildWsUrl`) | **VERIFIED** | **EXISTING** | [web/shared-client.js](file:///d:/projects/MaybeAI/web/shared-client.js#L19-L83): Reads `?token=` from URL, persists to `localStorage`/`sessionStorage` (`maybeai_creator_token`), injects `X-Creator-Token` + `Authorization: Bearer`, builds `ws(s)://.../ws?token=...`. |
| **`MaybeAIClient.ReconnectingWebSocket`** (jittered exponential backoff) | **VERIFIED** | **EXISTING** | [web/shared-client.js](file:///d:/projects/MaybeAI/web/shared-client.js#L85-L245): Exponential backoff (`minDelayMs=1000`, `maxDelayMs=30000`, `factor=2`, `jitter=0.25`), detaches stale sockets, resets `_attempt = 0` on `onopen`/`reconnectNow()`. Used in `app.js`, `settings.js`, `overlay.js`, `deck.js`. |
| **`MaybeAIClient.escapeHtml`** | **VERIFIED** | **EXISTING** | [web/shared-client.js](file:///d:/projects/MaybeAI/web/shared-client.js#L9-L17): Escapes `&`, `<`, `>`, `"`, `'`. |
| **`/settings` XSS neutralization & `401/403` token UI** | **VERIFIED** | **EXISTING** | [web/settings.html](file:///d:/projects/MaybeAI/web/settings.html#L47-L57) & [web/settings.js](file:///d:/projects/MaybeAI/web/settings.js#L143-L228): `#creatorAuthBar` shown on `401/403` in `fetchJsonAuth()`. All dynamic config values, labels, descriptions, search queries, and diagnostics fields pass through `escapeHtml()` / `escapeAttr()` ([web/settings.js](file:///d:/projects/MaybeAI/web/settings.js#L290-L779)). |
| **`/overlay` `onopen` state re-sync** | **VERIFIED** | **EXISTING** | [web/overlay.js](file:///d:/projects/MaybeAI/web/overlay.js#L204-L235): `onopen` calls `resyncOverlayState()`, which resets `targetMouthOpen = 0.0` (if `!isLocalAudioPlaying`), sends `{ type: "request_state", scope: "overlay" }`, and fetches `/api/voice/status` to restore `emotion` and `is_singing`. |
| **Local `web/vendor/` offline Three-VRM & fonts (zero CDN)** | **VERIFIED** | **EXISTING** | [web/vendor/](file:///d:/projects/MaybeAI/web/vendor): Contains `three.module.js` (1.3 MB), `three-vrm.module.js` (915 KB), `GLTFLoader.js`, `BufferGeometryUtils.js`, `fonts.css` (local `@font-face` fallbacks). Zero `https://cdn`, `fonts.googleapis`, `unpkg.com`, or `jsdelivr` matches across all `web/` files. |
| **Separate `web/vrm-avatar.js` module** | **NOT VERIFIED** | **REJECTED / REFACTORED** | `web/vrm-avatar.js` does **not** exist on disk. VRM loading/rendering is implemented inline in [web/app.js](file:///d:/projects/MaybeAI/web/app.js#L5622-L5740) and [web/overlay.js](file:///d:/projects/MaybeAI/web/overlay.js#L686-L726) using `/static/vendor/three.module.js` and `/static/vendor/three-vrm.module.js`. |
| **`AudioWorklet` resampler & stop tail flush** | **VERIFIED** | **EXISTING** | [web/audio-worklet-processor.js](file:///d:/projects/MaybeAI/web/audio-worklet-processor.js#L6-L118): Linear interpolation bridging `_lastSample -> mono[0]` (`pos < 0`) so `mono[0]` is never skipped; `_flush(true)` on `"stop"` message posts partial tail frame with `final: true`; `app.js` ([L1052-L1058](file:///d:/projects/MaybeAI/web/app.js#L1052-L1058)) and `deck.js` ([L251-L257](file:///d:/projects/MaybeAI/web/deck.js#L251-L257)) delay `disconnect()`/`close()` by `60ms` and accept `event.data.final`. |
| **Binary `Int16Array` PCM WS frames (with JSON fallback)** | **VERIFIED** | **EXISTING** | [web/app.js](file:///d:/projects/MaybeAI/web/app.js#L1223-L1240) & [web/deck.js](file:///d:/projects/MaybeAI/web/deck.js#L79-L95): Sends `Int16Array` binary frames when `binaryPcmEnabled` is true, falling back to JSON `voice_audio_chunk` base64 on exception. |
| **`isLocalAudioPlaying` lip-sync arbitration** | **VERIFIED** | **EXISTING** | [web/app.js](file:///d:/projects/MaybeAI/web/app.js#L292-L385,L602) & [web/overlay.js](file:///d:/projects/MaybeAI/web/overlay.js#L39-L135,L263): When browser Web Audio playback is active, `AnalyserNode` RMS drives `targetMouthOpen` and server `avatar_state.mouth_open` is ignored (`if (!isLocalAudioPlaying)`), preventing mouth jitter/fighting. |
| **YouTube Song Request dashboard bar** | **VERIFIED** | **EXISTING** | [web/index.html](file:///d:/projects/MaybeAI/web/index.html#L323-L336) & [web/app.js](file:///d:/projects/MaybeAI/web/app.js#L644-L651,L4374-L4392): URL input (`#perfYtUrl`), mode selector (`ai_cover` / `auto_karaoke`), submit button (`#btnPerfYtSing`), and live stage status (`#perfYtStatus`) updated by `youtube_song_status` WS events. |
| **AI VTuber Collab UI (Studio + Deck)** | **VERIFIED** | **EXISTING** | [web/index.html](file:///d:/projects/MaybeAI/web/index.html#L406-L436), [web/app.js](file:///d:/projects/MaybeAI/web/app.js#L5081-L5200), [web/deck.js](file:///d:/projects/MaybeAI/web/deck.js#L541-L573): Peer connect/disconnect, floor/turn badges, topic initiation, duet sync, and XSS-safe `appendCollabMessage` (uses `textContent`). |

---

## 3. Architecture Evaluation: Coherent Creator Studio vs. Separate Control Panels

**Verdict:** The UI presents as a **loosely coupled suite of 4 separate control panels** rather than a single coherent Creator Studio:

1. **Four Separate Entry Points:**
   - `/` ([web/index.html](file:///d:/projects/MaybeAI/web/index.html)): Main Studio (4 workspace tabs: `Live Stage`, `Gaming`, `RPG & Mini-Games`, `Brain & Memory`).
   - `/settings` ([web/settings.html](file:///d:/projects/MaybeAI/web/settings.html)): Configuration Center & Diagnostics.
   - `/overlay` ([web/overlay.html](file:///d:/projects/MaybeAI/web/overlay.html)): Transparent OBS Browser Source.
   - `/deck` ([web/deck.html](file:///d:/projects/MaybeAI/web/deck.html)): Mobile/Tablet Stream Deck.
2. **Navigation Friction:** Moving between Live Stage and Configuration Center triggers a full page navigation (`<a href="/settings">`) that tears down the active WebSocket, `AudioWorklet` mic stream, and browser audio playback context.
3. **Code & Logic Duplication:**
   - Despite `web/shared-client.js`, `app.js`, `settings.js`, `overlay.js`, and `deck.js` each re-implement fallback `getCreatorToken` / `authFetch` / `buildWsUrl` / `ReconnectingWebSocket` boilerplate.
   - `app.js` (5,896 lines) and `overlay.js` (731 lines) duplicate the entire 2D Canvas avatar renderer (`drawEye`, `drawEyebrows`, `drawMouth`, `drawHair`, `render`) and the VRM `GLTFLoader` + `VRMLoaderPlugin` setup.
   - `app.js`, `overlay.js`, and `deck.js` each independently implement Web Audio `AudioContext` + `decodeAudioData` FIFO queues.

---

## 4. Remaining UX, Security, Accessibility & State-Sync Gaps

### A. Reliability & State-Sync Bugs Observed
1. **Unguarded `ws.readyState` calls in `web/app.js` (5 locations):**
   - `onClose` sets `ws = null;` ([web/app.js:482](file:///d:/projects/MaybeAI/web/app.js#L482)).
   - Lines [737](file:///d:/projects/MaybeAI/web/app.js#L737), [865](file:///d:/projects/MaybeAI/web/app.js#L865), [879](file:///d:/projects/MaybeAI/web/app.js#L879), [893](file:///d:/projects/MaybeAI/web/app.js#L893), and [1353](file:///d:/projects/MaybeAI/web/app.js#L1353) (`sendMinecraftAction`) access `ws.readyState` directly without `ws &&`, which throws `TypeError: Cannot read properties of null (reading 'readyState')` if triggered during a WebSocket reconnect window.
2. **Incomplete `onopen` re-sync in `web/app.js`:**
   - Unlike `/overlay` (which calls `resyncOverlayState()` + `/api/voice/status`), `app.js` `onOpen` ([L471-L479](file:///d:/projects/MaybeAI/web/app.js#L471-L479)) only refreshes Mission, Collab, Plugins, and OBS/Highlights. It does not re-sync `/api/voice/status`, Mood, Chess, or Minecraft state after a transient disconnect.
3. **Stream Deck (`web/deck.js`) missing `highlight_marked` / `youtube_song_status` / `collab_state` richness:**
   - `deck.js` handles `highlight_marked` feedback, `obs_scene_changed`, `mission_status`, `avatar_state`, and `voice_barge_in`, but has no pad or status indicator for YouTube Karaoke progress or Collab floor state.

### B. Security & Auth UX Observations
1. **Token in URL & `localStorage`:** `CreatorAuth.getToken()` reads `?token=...` from `window.location.search` and stores it in `localStorage` ([web/shared-client.js:36-49](file:///d:/projects/MaybeAI/web/shared-client.js#L36-L49)), and `buildWsUrl()` appends `?token=...` to the WS URL (required by browser `WebSocket` API limitations, but leaves tokens in browser history/server logs unless stripped via `history.replaceState`).
2. **DOM XSS Hygiene:** `settings.js`, `app.js` chat/collab/highlights, and `overlay.js` (`textContent`) consistently use `escapeHtml()` or `textContent` on user/server strings.

### C. Accessibility & Localization Gaps
1. **Missing Keyboard Focus & Reduced Motion Styles:** Across `web/style.css`, `web/settings.css`, and `web/deck.css`, there are **0** `:focus-visible` rules and **0** `@media (prefers-reduced-motion: reduce)` rules.
2. **Sparse ARIA Semantics:** `web/index.html` has only **11** `aria-`/`role=`/`tabindex` attributes across 2,255 lines (primarily on the 4 workspace tabs). Modals, toast notifications, and dynamic status badges lack `aria-live` or focus trapping (unlike `overlay.html`, which uses `aria-live="polite"`).
3. **Mixed Language UI:** `web/index.html` and `web/app.js` mix English labels (`Live Stage`, `AI VTuber Collab`, `Creator Token`) with Indonesian copy (`Masukkan link YouTube terlebih dahulu`, `Belum ada highlight tercatat`, `Browser Anda belum mendukung...`), whereas `settings.html` and `deck.html` are 100% English.
