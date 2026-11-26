# AI-to-AI Collaboration Protocol Audit (`04_collab_protocol.md`)

**Auditor:** Agent 4 — AI-to-AI Collaboration Protocol Auditor (`cto-collab`)  
**Scope:** `core/collab/protocol.py`, `core/collab/manager.py`, `core/collab/__init__.py`, `run.py` (`/ws/collab`, `/api/collab/*`, `/ws` `collab_action`), `core/orchestrator.py` (collab callbacks & subsystem wiring), `core/config_manager.py`, `config/settings.json`, `tests/test_collab_and_plugins.py`.  
**Test Baseline:** `.venv\Scripts\python.exe -m unittest tests.test_collab_and_plugins -v` — **9/9 tests passing** (1.276s).

---

## 1. Executive Summary

MaybeAI implements a foundational AI-to-AI VTuber collaboration protocol centered on `CollabEnvelope` (`core/collab/protocol.py`) and `CollabManager` (`core/collab/manager.py`), exposed over WebSocket (`/ws/collab`) and HTTP/WS control endpoints (`run.py`). While HMAC-SHA256 canonical signing and basic `turn_utterance` / `turn_yield` turn-counting exist and pass unit tests, **the protocol is not production-hardened against replay attacks, URL-spoofed unsigned frames, floor-state concurrency races, or permanent cooldown deadlocks**. Furthermore, `duet_sync`, `emote_sync`, and `game_move` integrations with Singer, VTube Studio, and Chess are only partially wired (inbound-only or ignoring sync parameters).

---

## 2. Capability Classification Matrix

| Capability | Status | Observed Evidence |
| :--- | :--- | :--- |
| `CollabEnvelope` canonical JSON + HMAC-SHA256 sign/verify | **Current Capability** | `core/collab/protocol.py:55-106`, `tests/test_collab_and_plugins.py:22-46` |
| `/ws/collab` WebSocket server & outbound `aiohttp` WS client | **Current Capability** | `run.py:1611-1670`, `core/collab/manager.py:255-352` |
| `/api/collab/status`, `/api/collab/action`, `/ws` `collab_action` | **Current Capability** | `run.py:177-217, 724-734, 1585-1594` (protected by `verify_api_origin_middleware` & `_CREATOR_ONLY_WS_ACTIONS`) |
| `shared_secret` masking in `ConfigManager` | **Current Capability** | `core/config_manager.py:253`, `tests/test_collab_and_plugins.py:311-323` |
| Turn-taking floor state machine & `max_collab_turns` cap | **Partially Implemented** | Works for sequential happy-path turns (`tests/test_collab_and_plugins.py:48-127`), but `turn_cooldown_sec` never auto-recovers (`core/collab/manager.py:181`), `speaking` is not held during async LLM reply generation, and `listening` is not enforced on outbound turns |
| `ConversationEngine` collab reply loop | **Partially Implemented** | `core/orchestrator.py:537-580` generates replies via `brain.generate_response` and calls `send_utterance`, but lacks concurrency guard against rapid peer `turn_utterance` bursts |
| `duet_sync` (Karaoke / Singer integration) | **Partially Implemented** | Inbound calls `perform_song(song_id=...)` (`core/orchestrator.py:582-587`), ignoring `lyric_index` and `timestamp`; `perform_song` never emits outbound `duet_sync` |
| `emote_sync` (VTS integration) | **Partially Implemented** | Inbound calls `_apply_vts_mood_rig(emotion)` (`core/orchestrator.py:589-596`), ignoring `payload["action"]`; VTS/speech pipeline never emits outbound `emote_sync` |
| `game_move` (Chess integration) | **Partially Implemented** | Inbound calls `chess.make_player_move` (`core/orchestrator.py:598-607`) and discards `(success, err)`; no `send_game_move()` exists on `CollabManager` or `run.py` |
| Nonce/timestamp replay protection & schema versioning | **Planned Capability** | `message_id` and `timestamp` fields exist on `CollabEnvelope`, but neither is validated or tracked on receive |
| Web Dashboard Collab UI | **Planned Capability** | Zero references to `collab` or `/ws/collab` in `web/` |
| Negotiated capability/turn-budget handshake & signed acks | **Proposed Innovation** | Capability exchange in `hello` + monotonic sequence numbers + automatic cooldown recovery |

---

## 3. Detailed Audit Findings

### [COLLAB-CRIT-001] No Replay Protection (Missing `message_id` Deduplication and `timestamp` Freshness Window)
- **Severity:** Critical
- **Evidence Classification:** `REPRODUCED`
- **Location:** `core/collab/protocol.py:32-41, 128-155`; `core/collab/manager.py:470-579`
- **Symptom:** An identical signed `CollabEnvelope` can be replayed arbitrarily many times over `/ws/collab` or `handle_incoming_envelope`, causing duplicate turn increments, duplicate LLM/TTS responses, duplicate `perform_song` triggers, or duplicate `chess.make_player_move` calls.
- **Root Cause:** Although `CollabEnvelope` includes `message_id` (UUID4 hex) and `timestamp` (`time.time()`), `CollabManager.handle_incoming_envelope()` never records seen `message_id` values and never checks `abs(time.time() - env.timestamp)` against a replay window.
- **Verification Steps:** Executed via `.venv\Scripts\python.exe`:
  ```python
  r1 = await mgr.handle_incoming_envelope(env.to_dict(), is_loopback=False)
  r2 = await mgr.handle_incoming_envelope(env.to_dict(), is_loopback=False)
  # Observed output: REPLAY: True 1 True 2
  ```
- **Blast Radius:** Any network observer or compromised/buggy peer can replay a previously signed `turn_utterance`, `duet_sync`, `emote_sync`, or `game_move` frame to exhaust `max_collab_turns`, trigger repeated LLM API spend, or desynchronize game/avatar state.
- **Recommended Fix:** Maintain a bounded TTL/LRU cache of seen `(sender_id, message_id)` nonces in `CollabManager` (e.g., `OrderedDict` or `deque` + `set` with 5-minute TTL) and reject envelopes whose `timestamp` skews beyond `±60s` (configurable) or whose `message_id` was already processed.

---

### [COLLAB-HIGH-001] Loopback URL Substring Spoofing Bypasses Unsigned Frame Rejection
- **Severity:** High
- **Evidence Classification:** `REPRODUCED`
- **Location:** `core/collab/manager.py:301, 315-317, 474, 485`
- **Symptom:** When `shared_secret` is empty, connecting outbound to a remote malicious URL containing `"localhost"`, `"127.0.0.1"`, or `"::1"` anywhere in the URL string causes `CollabManager` to treat the remote peer as loopback and accept unsigned envelopes. Additionally, `handle_incoming_envelope(..., is_loopback: bool = True)` defaults `is_loopback` to `True`, making any caller that omits it permissive by default.
- **Root Cause:** `_is_loopback_url()` (`core/collab/manager.py:315-317`) performs `any(host in lower for host in ("127.0.0.1", "localhost", "::1"))` on the full URL string instead of parsing `urllib.parse.urlparse(url).hostname`.
- **Verification Steps:** Executed via `.venv\Scripts\python.exe`:
  ```python
  CollabManager._is_loopback_url('ws://localhost.evil.com/ws/collab')  # True
  CollabManager._is_loopback_url('ws://evil.com/127.0.0.1')          # True
  ```
- **Blast Radius:** Remote attacker-controlled WebSocket servers can inject unsigned `turn_utterance`, `duet_sync`, `emote_sync`, or `game_move` frames into Eve's orchestrator when `shared_secret` is unconfigured.
- **Recommended Fix:** Parse `urlparse(url).hostname` and check exact membership in `{"127.0.0.1", "localhost", "::1"}` (or `ipaddress.ip_address(host).is_loopback`). Change `handle_incoming_envelope` default to `is_loopback: bool = False`.

---

### [COLLAB-HIGH-002] Shared Secret Exposure in WS Query Parameters & Global Secret Mutation Race
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `run.py:1623-1632, 1648-1670`
- **Symptom:**
  1. `/ws/collab` accepts the HMAC shared secret via `?secret=...` or `?token=...` query parameters (`run.py:1624-1625`), exposing credentials in reverse-proxy, access, and client logs.
  2. Upon accepting `/ws/collab`, `run.py:1648-1651` mutates the singleton `orchestrator.collab.shared_secret = secret` and restores `prev_collab_secret` in `finally:` (`run.py:1669-1670`).
- **Root Cause:** Instead of passing `secret` explicitly or keeping `orchestrator.collab.shared_secret` synchronized at config/env load time, `collab_websocket_endpoint` temporarily overwrites the shared mutable attribute on `orchestrator.collab`.
- **Verification Steps:** Static inspection of `run.py:1622-1670`. If two `/ws/collab` clients connect concurrently or `apply_configuration_hot_reload` (`core/orchestrator.py:817`) updates `shared_secret` mid-session, `finally:` can clobber the active secret back to an older `prev_collab_secret`.
- **Blast Radius:** Credential leakage in logs; intermittent HMAC verification failures or secret downgrade during concurrent WS connections or hot-reloads.
- **Recommended Fix:** Prefer `Authorization: Bearer <secret>` or `X-Collab-Secret` headers (deprecate query-string secrets). Remove the `prev_collab_secret` mutation in `run.py:1648-1670` and pass `secret` directly or resolve it consistently inside `CollabManager`.

---

### [COLLAB-HIGH-003] Floor State Deadlock: `turn_cooldown_sec` Never Auto-Recovers After `max_collab_turns`
- **Severity:** High
- **Evidence Classification:** `REPRODUCED`
- **Location:** `core/collab/manager.py:179-183, 380-395, 415-417, 518-543`
- **Symptom:** Once `turn_count` reaches `max_collab_turns` (default `6`), `floor_state` enters `"cooldown"` and **permanently remains stuck in `"cooldown"`** even after `turn_cooldown_sec` (default `2.5s`) elapses, until an operator manually calls `reset_turns()`. Furthermore, every subsequent `send_utterance` or inbound `turn_utterance` resets `self.cooldown_until = time.monotonic() + self.turn_cooldown_sec` (`lines 381, 519, 534`).
- **Root Cause:** `_refresh_cooldown()` (`core/collab/manager.py:181`) checks:
  ```python
  if self.floor_state == "cooldown" and self.turn_count < self.max_collab_turns:
  ```
  However, every single transition into `"cooldown"` in `CollabManager` (`lines 382, 417, 520, 535, 542`) occurs **only** when `self.turn_count >= self.max_collab_turns`. Thus `self.turn_count < self.max_collab_turns` is always `False` during cooldown, making `_refresh_cooldown()` dead code for turn-limit recovery.
- **Verification Steps:** Executed via `.venv\Scripts\python.exe` (`max_collab_turns=1`, `turn_cooldown_sec=0.05`):
  ```python
  s1 = await mgr2.send_utterance('one', yield_turn=True)
  await asyncio.sleep(0.1)
  s2 = await mgr2.send_utterance('two', yield_turn=True)
  # Observed output: COOLDOWN_STUCK: True cooldown False max_collab_turns_reached 0.05
  ```
- **Blast Radius:** Autonomous AI-to-AI collab sessions permanently stall after 6 turns (3 round-trips) and never resume after the configured cooldown window unless manually reset via API.
- **Recommended Fix:** Clarify intended semantics: if `turn_cooldown_sec` is a per-burst cooldown, reset `self.turn_count = 0` when `time.monotonic() >= self.cooldown_until` inside `_refresh_cooldown()` (and do not overwrite `cooldown_until` while already in cooldown). If `max_collab_turns` is a hard session cap requiring manual reset, remove the misleading `cooldown_until` timer on `max_collab_turns_reached` and distinguish `"exhausted"` from `"cooldown"`.

---

### [COLLAB-HIGH-004] Concurrent Reply Task Storm & Missing `speaking` / `listening` Floor Enforcement
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/collab/manager.py:378-397, 529-569`; `core/orchestrator.py:537-580`
- **Symptom:**
  1. When an inbound `turn_utterance` arrives, `handle_incoming_envelope` sets `floor_state = "idle"` (`line 545`), spawns `_on_collab_reply_needed` as a background `asyncio.create_task` (`line 559`), and releases `self._lock`. While `brain.generate_response()` and `_speak_response()` are running (seconds), `floor_state` remains `"idle"`, so additional inbound `turn_utterance` frames spawn **parallel** `_on_collab_reply_needed` tasks.
  2. `send_utterance()` (`lines 378-396`) never checks `self.floor_state in ("listening", "speaking")`, allowing outbound turns to talk over an active peer or concurrent local callers.
- **Root Cause:** Floor state transitions to `"speaking"` only inside `send_utterance()` *after* LLM generation completes (`core/orchestrator.py:556-575`), rather than when acquiring the floor to compose a reply.
- **Verification Steps:** Static trace of `core/collab/manager.py:544-561` -> `core/orchestrator.py:537-580`. If 3 `turn_utterance` frames arrive within 100ms while `max_collab_turns=6`, all 3 pass `floor_state != "speaking"` and spawn 3 concurrent LLM + TTS + `send_utterance` tasks.
- **Blast Radius:** Overlapping/garbled Eve replies, out-of-order `turn_utterance` frames, and unnecessary LLM/TTS resource consumption.
- **Recommended Fix:** Transition `floor_state` to `"speaking"` (or `"thinking"`) *before* spawning `_on_collab_reply_needed` and guarantee `floor_state` is reset in a `try/finally` if the reply task fails or is cancelled. Enforce `floor_state == "idle"` (or explicit preemption) in `send_utterance()`.

---

### [COLLAB-MED-001] `collab.enabled = False` Configuration Flag Is Never Enforced
- **Severity:** Medium
- **Evidence Classification:** `REPRODUCED`
- **Location:** `core/collab/manager.py:49, 95-96, 369-579`; `run.py:177-217, 1611-1666`; `config/settings.json:168`
- **Symptom:** Even when `config/settings.json` has `"collab": {"enabled": false}` (the default), `/ws/collab` accepts connections, `handle_incoming_envelope()` processes frames and triggers LLM/VTS/Chess/Singer callbacks, and `/api/collab/action` executes `initiate` / `send_utterance` / `connect`.
- **Root Cause:** `self.enabled` is stored in `CollabManager.update_config()` (`line 96`) and returned in `get_status()` (`line 626`), but is never checked as a guard in `connect_peer`, `send_utterance`, `handle_incoming_envelope`, or `run.py` endpoints.
- **Verification Steps:** Reproduced in `.venv\Scripts\python.exe`: `CollabManager(settings={'enabled': False, ...})` returned `sent=True` on `send_utterance` and `accepted=True` on `handle_incoming_envelope`.
- **Blast Radius:** Users who believe AI Collab is disabled in settings still have an active `/ws/collab` attack surface on loopback (or remotely if a secret is set).
- **Recommended Fix:** Reject `/ws/collab` connections (close `1008`) and return `{"accepted": False, "error": "collab_disabled"}` / `{"sent": False, "reason": "collab_disabled"}` when `self.enabled` is `False` (allowing `"connect"` or `"status"` only as explicitly intended).

---

### [COLLAB-MED-002] No Anti-Loop or Rate-Limiting on `duet_sync`, `emote_sync`, `game_move`, or `ping`
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/collab/manager.py:440-468, 508-516`; `core/orchestrator.py:582-607`
- **Symptom:** `turn_count` and `max_collab_turns` only gate `turn_utterance` and `turn_yield`. Inbound `duet_sync`, `emote_sync`, `game_move`, and `ping` frames bypass `turn_count`, `floor_state`, and `cooldown` checks completely.
- **Root Cause:** `handle_incoming_envelope()` (`lines 508-516`) unconditionally assigns `action_cb` for these event types and executes them without rate-limiting or cooldown checks.
- **Verification Steps:** Static inspection of `core/collab/manager.py:508-555`. Note that `_on_collab_duet_sync` (`core/orchestrator.py:585-587`) only checks `if not self._busy_lock.locked():`, whereas `_on_collab_emote_sync` and `_on_collab_game_move` have zero throttling.
- **Blast Radius:** A peer flooding `emote_sync` or `game_move` can saturate VTS WebSocket commands, WebSocket `/ws` broadcasts, and `python-chess` move evaluation.
- **Recommended Fix:** Apply per-event-type rate limits (e.g., token bucket or minimum interval) and honor `enabled` / `cooldown` policy for action frames.

---

### [COLLAB-MED-003] Incomplete Schema Validation (`protocol_version`, `NaN`/`Infinity`, `0.0` Timestamp Mutation, Unbounded Strings)
- **Severity:** Medium
- **Evidence Classification:** `REPRODUCED`
- **Location:** `core/collab/protocol.py:44-53, 55-74, 128-155`
- **Symptom:**
  1. `CollabEnvelope.from_dict()` accepts any `protocol_version` (e.g., `"99.0"`).
  2. `float("nan")` and `float("inf")` pass `float(...)` conversion and serialize as non-standard JSON `NaN`/`Infinity` in `_canonical_bytes()` and `to_json()`.
  3. `timestamp=float(data.get("timestamp", time.time()) or time.time())` (`line 153`) and `message_id=str(data.get("message_id") or uuid.uuid4().hex)` (`line 144`) silently overwrite falsy values (`0.0` or `""`), altering the signed payload before `verify()`.
  4. `speech`, `topic`, `sender_name`, and `payload` have no size/length bounds.
- **Root Cause:** Permissive `or` fallbacks and lack of `math.isfinite()`, `protocol_version`, and length validation in `CollabEnvelope.from_dict()`.
- **Verification Steps:** Executed via `.venv\Scripts\python.exe`:
  ```python
  e_nan = CollabEnvelope.from_dict({'event_type': 'ping', 'timestamp': float('nan')})
  e_zero = CollabEnvelope.from_dict({'event_type': 'ping', 'timestamp': 0.0})
  # Observed output: SCHEMA: True True
  ```
- **Blast Radius:** Non-standard JSON frames, broken HMAC verification for `0.0` timestamps, and unbounded memory/LLM prompt injection via oversized `speech`/`payload` fields.
- **Recommended Fix:** Enforce `protocol_version == PROTOCOL_VERSION`, validate `math.isfinite(timestamp)`, use explicit `is None` checks instead of `or`, pass `allow_nan=False` to `json.dumps()`, and bound `speech`/`topic`/`payload` sizes.

---

### [COLLAB-MED-004] Partial / Asymmetric Integrations with Singer (`duet_sync`), VTS (`emote_sync`), and Chess (`game_move`)
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/orchestrator.py:582-607, 1636-1770`; `core/chess/controller.py:102-170`; `core/collab/manager.py:440-468`
- **Symptom:**
  1. **`duet_sync`:** `_on_collab_duet_sync` (`core/orchestrator.py:582-587`) calls `self.perform_song(song_id=song_id, dedication_user=dedication)` and completely ignores `env.payload["lyric_index"]` and `env.payload["timestamp"]`. Conversely, `perform_song()` (`core/orchestrator.py:1636-1770`) never calls `self.collab.send_duet_sync(...)` during `on_lyric_update`.
  2. **`emote_sync`:** `_on_collab_emote_sync` (`core/orchestrator.py:589-596`) ignores `env.payload.get("action")`, and neither `_apply_vts_mood_rig` nor `_speak_response` ever emits `send_emote_sync(...)`.
  3. **`game_move`:** `_on_collab_game_move` (`core/orchestrator.py:598-607`) calls `await self.chess.make_player_move(move_str)` and discards its `(bool, str)` result. `CollabManager` has no `send_game_move()` method, `run.py` has no `game_move` action, and `ChessController._apply_bot_move()` (`core/chess/controller.py:154-170`) never sends Eve's move back to the collab peer.
- **Root Cause:** Outbound hooks into `Singer`, `VTS`, and `ChessController` were not wired beyond manual `/api/collab/action` triggers (`duet_sync`, `emote_sync`) and inbound stubs.
- **Verification Steps:** Static search across `core/` confirmed zero callers of `send_duet_sync` or `send_emote_sync` outside `tests/test_collab_and_plugins.py` and `run.py`, and zero definitions of `send_game_move`.
- **Blast Radius:** AI-to-AI karaoke duets cannot stay lyric-synchronized, emote actions are dropped, and AI-vs-AI chess games cannot progress past the peer's opening move without external polling.
- **Recommended Fix:** Wire `perform_song` lyric callbacks to `send_duet_sync` (when `collab.peer_connected`), pass `lyric_index`/`timestamp` to `Singer` for seek/sync, forward `payload["action"]` in `_on_collab_emote_sync`, and add `CollabManager.send_game_move()` + `ChessController` outbound move hook.

---

### [COLLAB-LOW-001] Single `connected_peer` Metadata Overwrite on Multi-Peer `/ws/collab` Connections
- **Severity:** Low
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/collab/manager.py:131-158, 229-253, 500-507`
- **Symptom:** `CollabManager` tracks multiple inbound WS connections in `self._inbound_senders` (`dict[conn_id, cb]`), but stores only a single `self.connected_peer: Optional[str]` and `self.peer_connected: bool`. If Peer A and Peer B are both connected, Peer B's `bye` or disconnect clears `connected_peer` even while Peer A remains connected; and `_send_envelope()` prefers `self._ws_client` exclusively over `_inbound_senders` (`elif`, `line 236`).
- **Root Cause:** Scalar peer metadata fields (`connected_peer`, `peer_name`) were not keyed per `conn_id`.
- **Verification Steps:** Static inspection of `core/collab/manager.py:131-158, 229-253, 504-507`.
- **Blast Radius:** Misleading `peer_name` / `connected_peer` status in `/api/collab/status` and `collab.state` events when multiple peers connect.
- **Recommended Fix:** Track peer metadata per `conn_id` or explicitly enforce single-active-peer semantics on `/ws/collab`.

---

## 4. Prioritized Remediation Roadmap

1. **Immediate (Security):** Add `(sender_id, message_id)` nonce deduplication + `timestamp` skew window (`[COLLAB-CRIT-001]`), fix `_is_loopback_url` hostname parsing and default `is_loopback=False` (`[COLLAB-HIGH-001]`), and remove query-string secrets & `shared_secret` mutation in `run.py` (`[COLLAB-HIGH-002]`).
2. **Short-Term (Reliability):** Fix `_refresh_cooldown()` turn-reset logic (`[COLLAB-HIGH-003]`), hold `floor_state = "speaking"` across async `_on_collab_reply_needed` execution (`[COLLAB-HIGH-004]`), enforce `collab.enabled` (`[COLLAB-MED-001]`), and tighten `CollabEnvelope.from_dict()` validation (`[COLLAB-MED-003]`).
3. **Medium-Term (Feature Completeness):** Add rate-limiting on `duet_sync`/`emote_sync`/`game_move` (`[COLLAB-MED-002]`) and complete bidirectional wiring for Singer, VTS, and Chess (`[COLLAB-MED-004]`).
