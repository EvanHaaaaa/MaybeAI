# AI Collaboration Protocol Audit (`05_collab_protocol.md`)

**Auditor:** Agent 4 (`ng-collab`) — AI Collaboration Protocol Auditor (Post-Implementation CTO Audit)  
**Scope:** `core/collab/protocol.py`, `core/collab/manager.py`, `core/security_net.py`, `core/orchestrator.py`, `run.py` (`/ws/collab`, `/api/collab/*`, `/ws` `collab_action`), `core/config_manager.py`, `config/settings.json`, `web/` (`index.html`, `app.js`, `settings.html`, `settings.js`), `tests/test_horizon3_collab_ssrf.py`, `tests/test_collab_and_plugins.py`  
**Test Baseline:** `.venv\Scripts\python.exe -m unittest tests/test_horizon3_collab_ssrf.py tests/test_collab_and_plugins.py -v` — **16/16 tests passing** (1.355s)

---

## 1. Executive Summary

Following Horizon 0 and Horizon 3 (`H0`, `H3-02`, `H3-03`), MaybeAI's AI-to-AI VTuber collaboration stack has been substantially hardened at the wire-protocol, transport-auth, and SSRF boundaries. `CollabEnvelope` (`core/collab/protocol.py`) and `CollabManager` (`core/collab/manager.py`) now enforce canonical HMAC-SHA256 verification, `NaN`/`Infinity` payload rejection, a `±60s` timestamp skew window, a bounded `(sender_id, message_id)` LRU replay cache, exact hostname parsing in `_is_loopback_url`, automatic time-based `_refresh_cooldown` recovery, `hello` capability handshakes, per-type sliding-window rate limiting, non-query WebSocket authentication (`Authorization: Bearer` / `Sec-WebSocket-Protocol`), and SSRF/DNS-rebinding protection via `validate_outbound_url` (`core/security_net.py`).

However, two structural gaps remain:
1. **Subsystem Outbound Wiring is Incomplete:** While `CollabManager` supports bidirectional `duet_sync`, `emote_sync`, and `game_move`, `Orchestrator` only wires **inbound** callbacks (`_on_collab_duet_sync`, `_on_collab_emote_sync`, `_on_collab_game_move`). Neither `Singer`, `VTSClient`, nor `ChessController` emits outbound sync frames automatically, `run.py:_handle_collab_action` does not expose `game_move`, and `Orchestrator._on_collab_hello` is never registered because `CollabManager.set_action_callbacks` lacks an `on_hello` parameter.
2. **2-Peer Architecture Cannot Scale to Multi-Agent:** `CollabManager` models a single scalar peer (`connected_peer`, `peer_capabilities`, single outbound `_ws_client`, single global `floor_state` and `turn_count`). Scaling to 3+ agents requires per-peer session state, explicit message routing (`target_id`), and distributed floor arbitration.

**AI Collaboration Maturity Score:** **L2.5 / L5** (*L3 Defined/Hardened for 2-Peer Wire Security; L2 Repeatable for Subsystem & Multi-Agent Orchestration*).

---

## 2. Verification & Capability Matrix

| Claim / Capability | Claim Status | Capability Status | Observed Evidence & Notes |
| :--- | :--- | :--- | :--- |
| HMAC-SHA256 canonical sign & `compare_digest` verify | `VERIFIED` | `EXISTING` | `core/collab/protocol.py:72-123` (`sort_keys=True`, `separators=(",", ":")`, `hmac.compare_digest`). Unsigned frames rejected unless `allow_unauthenticated_loopback and is_loopback and not self.shared_secret` (`core/collab/manager.py:714-716`). |
| Bounded LRU nonce replay cache | `VERIFIED` | `EXISTING` | `core/collab/manager.py:104-105, 732-748` (`OrderedDict[(sender_id, message_id), float]`, `maxsize=1024`, `move_to_end`, FIFO/LRU eviction via `popitem(last=False)`). In-memory only; `sender_id` is self-asserted. |
| `±60s` timestamp skew enforcement | `VERIFIED` | `EXISTING` | `core/collab/manager.py:103, 718-724` (`abs(now - env.timestamp) > 60.0` returns `reason: "timestamp_skew_exceeded"`). |
| `NaN` / `Infinity` rejection | `VERIFIED` | `EXISTING` | `core/collab/protocol.py:144-190` (`_validate_finite_floats` recursive check on `payload`; `math.isfinite` and `bool` rejection on `timestamp` and `turn_index`). |
| `_is_loopback_url` exact hostname check | `VERIFIED` | `EXISTING` | `core/collab/manager.py:454-460` (`urlparse(...).hostname in {"127.0.0.1", "localhost", "::1"}`). |
| `_refresh_cooldown` automatic recovery | `VERIFIED` | `EXISTING` | `core/collab/manager.py:223-228` resets `turn_count=0`, `cooldown_until=0.0`, `floor_state="idle"` when `time.monotonic() >= cooldown_until`. Called on all send/receive/status paths. |
| `hello` capability handshake | `PARTIALLY VERIFIED` | `INCOMPLETE` | `CollabManager.send_hello` (`manager.py:328-362`) and inbound `hello` (`755-766`) work and update `peer_capabilities`/`peer_protocol_version`. However, `Orchestrator._on_collab_hello` (`core/orchestrator.py:684-693`) is dead code because `CollabManager.set_action_callbacks` (`manager.py:161-173`) has no `on_hello` parameter. |
| Bidirectional `duet_sync` / `emote_sync` / `game_move` | `PARTIALLY VERIFIED` | `INCOMPLETE` | `CollabManager` implements all 3 outbound/inbound methods + per-type `_check_rate_limit` (`manager.py:312-326, 597-694, 773-793`). `Orchestrator` only wires inbound callbacks (`orchestrator.py:695-751`); subsystems never emit outbound sync frames, and `run.py:_handle_collab_action` (`218-258`) omits `game_move`. |
| Non-query `Sec-WebSocket-Protocol` & Bearer auth | `VERIFIED` | `EXISTING` | `run.py:130-149, 1862-1886` (`Authorization: Bearer`, `x-collab-secret`, `Sec-WebSocket-Protocol: maybeai.collab.<secret>`). `connect_peer` (`manager.py:392, 398-410`) strips `?secret=`/`?token=` and sends headers/subprotocols. Legacy query param fallback remains in `run.py:1869-1870`. |
| SSRF protection & `allow_private_peers` | `VERIFIED` | `EXISTING` | `core/security_net.py:127-188` (`validate_outbound_url`) + `manager.py:380-390` blocks private/loopback/DNS-rebinding by default (`allow_private_peers=False`) and always blocks cloud metadata (`169.254.169.254`, `100.100.100.200`, `fe80::/10`, `metadata.google.internal`) unless allowlisted. |
| Web Dashboard Collab UI & `shared_secret` masking | `VERIFIED` | `EXISTING` | `web/index.html:424-434`, `web/app.js:5081-5135`, `web/settings.html:149-151`, `core/config_manager.py:265`. |
| Multi-agent (3+ peer) orchestration & routing | `NOT VERIFIED` | `PLANNED` | `CollabManager` is strictly 2-peer; no peer registry, message routing, or multi-party floor arbitration exists. |

---

## 3. Detailed Post-H0/H3 Verification Findings

### 3.1 Wire Protocol & Cryptographic Hardening (`core/collab/protocol.py`, `core/collab/manager.py`)
- **HMAC-SHA256 & Loopback Guard (`VERIFIED`):** `CollabEnvelope._canonical_bytes()` serializes all envelope fields deterministically (`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`) and verifies via `hmac.compare_digest()`. `handle_incoming_envelope()` (`manager.py:714-716`) permits unsigned frames **only** when `allow_unauthenticated_loopback=True`, `is_loopback=True`, and `shared_secret` is empty.
- **Replay & Skew Protection (`VERIFIED`):** `handle_incoming_envelope()` rejects envelopes outside `±60.0s` (`max_timestamp_skew_sec`) before acquiring `self._lock`, and deduplicates `(env.sender_id, env.message_id)` against `self._seen_nonces` (`OrderedDict`, `maxsize=1024`).
  - *Residual Risk:* If `sender_id` is omitted (`""`), two different peers using empty `sender_id` share the same nonce namespace. Additionally, `_seen_nonces` is volatile (lost on process restart, though `±60s` skew limits the window).
- **Non-Finite Float Rejection (`VERIFIED`):** `CollabEnvelope.from_dict()` recursively traverses `payload` (`_validate_finite_floats`) and checks `math.isfinite()` on `timestamp` and `turn_index`, rejecting `NaN`, `Infinity`, `-Infinity`, and booleans.
  - *Minor Gap:* `run.py:1895` uses Starlette's `websocket.receive_json()`, which relies on Python's `json.loads()` (permitting `NaN`/`Infinity` tokens during initial JSON parse); `from_dict()` catches them immediately afterward, but `to_json()` (`protocol.py:142`) and `_canonical_bytes()` (`protocol.py:86`) do not pass `allow_nan=False`.
- **`_is_loopback_url` & Default `is_loopback` (`VERIFIED` with Caveat):** `_is_loopback_url()` (`manager.py:454-460`) now inspects `urlparse(url).hostname`, eliminating substring spoofing (e.g., `wss://evil.com/?localhost`). Both `_receive_loop()` (`manager.py:441`) and `/ws/collab` (`run.py:1860, 1898`) pass `is_loopback` explicitly. However, `handle_incoming_envelope(..., is_loopback: bool = True)` (`manager.py:700`) still defaults `is_loopback` to `True`, which is unsafe-by-default for any future caller that omits the argument.

### 3.2 Transport Security & SSRF (`run.py`, `core/security_net.py`, `core/collab/manager.py`)
- **Non-Query WebSocket Auth (`VERIFIED`):** `run.py:1862-1886` authenticates `/ws/collab` via `Authorization: Bearer <secret>`, `x-collab-secret`, or `Sec-WebSocket-Protocol: maybeai.collab.<secret>` (echoing `subprotocol=selected_subprotocol` on `accept()`). `CollabManager.connect_peer()` (`manager.py:392, 398-410`) strips `secret` and `token` query parameters via `_strip_secret_query_params()` and sends credentials in headers.
  - *Residual Risk:* `run.py:1869-1870` still accepts `websocket.query_params.get("secret")` / `token` for backward compatibility, meaning legacy clients could still expose secrets in reverse-proxy access logs.
- **SSRF & DNS Rebinding (`VERIFIED`):** `validate_outbound_url()` (`core/security_net.py:127-188`) restricts schemes to `("ws", "wss")`, resolves hostnames via `socket.getaddrinfo()`, unwraps IPv4-mapped IPv6 (`_unwrap_ip`), blocks link-local/metadata/unspecified/multicast/reserved IPs unconditionally, and blocks RFC1918/loopback IPs unless `allow_private_peers=True` or matched by `peer_allowlist`.
  - *Config Gap:* `allow_private_peers` and `peer_allowlist` are supported in `CollabManager.update_config()` (`manager.py:143-150`) and tested in `tests/test_horizon3_collab_ssrf.py`, but are not listed in `config/settings.json:176-183` or `core/config_manager.py:1309-1360` schema metadata (so operators cannot toggle them from `/settings` UI).

### 3.3 Floor State Machine & Bidirectional Subsystem Wiring (`core/collab/manager.py`, `core/orchestrator.py`, `run.py`)
- **Cooldown Recovery (`VERIFIED`):** `_refresh_cooldown()` (`manager.py:223-228`) cleanly exits `"cooldown"` and resets `turn_count = 0` once `turn_cooldown_sec` elapses.
- **Dead `on_hello` Orchestrator Hook (`PARTIALLY VERIFIED`):** `core/orchestrator.py:191-192` checks `if "on_hello" in inspect.signature(self.collab.set_action_callbacks).parameters:` before registering `self._on_collab_hello`. Because `CollabManager.set_action_callbacks()` (`manager.py:161-173`) only accepts `on_duet_sync`, `on_emote_sync`, and `on_game_move`, `_on_collab_hello` is never called. (The Web UI still receives updates via `EventBus` `collab.state` events.)
- **Asymmetric Bidirectional Wiring (`PARTIALLY VERIFIED`):**
  - `CollabManager` provides `send_duet_sync`, `send_emote_sync`, and `send_game_move` with per-type sliding-window rate limiting (`rate_limit_max_events=10`, `rate_limit_window_sec=5.0`).
  - `Orchestrator` handles inbound `duet_sync` (`orchestrator.py:695-719`), `emote_sync` (`721-735`), and `game_move` (`737-751`). Note that `_on_collab_game_move` still ignores the `(success, err)` return value from `self.chess.make_player_move(move_str)`.
  - **Gap:** No subsystem (`Singer`, `VTSClient`, `ChessController`, or `Orchestrator` speech/emote pipeline) automatically invokes `collab.send_duet_sync`, `collab.send_emote_sync`, or `collab.send_game_move` during live performance or gameplay. `run.py:_handle_collab_action` (`240-252`) exposes manual `duet_sync` and `emote_sync` triggers, but does **not** expose `game_move`.

---

## 4. Multi-Agent Scaling Evaluation (`CollabManager`: 2-Peer -> Multi-Agent Ecosystem)

**Verdict:** `CollabManager` in its current form **cannot** scale to a multi-agent (3+ peer) ecosystem without an architectural refactor. While `register_peer_sender()` (`manager.py:175-188`) was updated to store multiple inbound `/ws/collab` callbacks in `_inbound_senders: Dict[str, Callable]`, the rest of the class remains fundamentally 2-peer:

1. **Single Outbound Connection & Split-Brain Send Path:** `self._ws_client` (`manager.py:93`) holds only one outbound WebSocket. Worse, `_send_envelope()` (`manager.py:274-298`) uses `if self._ws_client ... elif self._inbound_senders:` — if Eve initiates an outbound connection to Peer A while Peer B is connected inbound to `/ws/collab`, all outbound envelopes go **only** to Peer A and never reach Peer B.
2. **Scalar Peer Metadata:** `self.connected_peer`, `self.peer_name`, `self.peer_capabilities`, and `self.peer_protocol_version` are single scalar attributes overwritten by whichever peer most recently sent `hello` or `turn_utterance` (`manager.py:757-765, 803`).
3. **Global Single-Channel Floor & Turn Counter:** `self.floor_state` and `self.turn_count` are global to `CollabManager`, not scoped per conversation/room or peer. In a 3-agent conversation, `turn_yield` has no `target_peer_id`, so either all peers race to reply simultaneously (causing reply collisions) or none know who holds the floor.
4. **Unbound Sender Identity:** `_seen_nonces` keys on `(env.sender_id, env.message_id)` (`manager.py:732`), where `sender_id` is self-reported in the JSON envelope rather than bound to the authenticated WebSocket connection (`conn_id`), allowing one compromised peer in a multi-peer mesh to spoof another peer's `sender_id`.

### Recommended Evolution Path for Multi-Agent Scaling
- Introduce a `PeerSession` dataclass (`peer_id`, `ws_client` or `inbound_sender`, `capabilities`, `protocol_version`, `is_loopback`, `last_seen`) stored in `self.peers: Dict[str, PeerSession]`.
- Add `target_id` (or `room_id` / `"*"` broadcast) to `CollabEnvelope` so `turn_yield`, `game_move`, and `duet_sync` can be directed or broadcast cleanly.
- Move `floor_state`, `turn_count`, and `cooldown_until` into a `RoomFloorArbitrator` (supporting moderator/host token passing or round-robin turn queues for `N >= 3` agents).
- Bind `env.sender_id` verification to the authenticated `PeerSession.peer_id` on receipt.

---

## 5. L0–L5 Maturity Assessment

| Dimension | Score | Rationale |
| :--- | :---: | :--- |
| **Wire Security & Auth** | **L3 (Defined)** | HMAC-SHA256, `±60s` skew, LRU nonce cache, `NaN`/`Infinity` rejection, non-query WS auth, SSRF/DNS-rebinding guard. |
| **2-Peer Floor & Recovery** | **L3 (Defined)** | `asyncio.Lock` floor state machine, `max_collab_turns`, automatic `_refresh_cooldown`, per-type rate limiting. |
| **Subsystem Integration** | **L2 (Repeatable)** | Inbound `duet_sync`/`emote_sync`/`game_move` wired, but outbound emission from `Singer`/`VTS`/`Chess` is unimplemented and `on_hello` is unwired. |
| **Multi-Agent Scalability** | **L1 (Initial)** | Single `_ws_client`, scalar peer state, global floor, no `target_id` routing. |
| **Overall AI Collaboration** | **L2.5 / L5** | Production-grade 2-peer security foundation; requires outbound subsystem hooks and `PeerSession` refactoring for multi-agent ecosystems. |
