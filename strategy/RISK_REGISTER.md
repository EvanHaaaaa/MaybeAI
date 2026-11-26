# MaybeAI — Strategic & Operational Risk Register (`strategy/RISK_REGISTER.md`)

**Owner:** AGENT 12 (`strat-roadmap` — Strategic Development & Roadmap Manager)  
**Baseline Grounding:** [FINAL_AUDIT_REPORT.md](file:///d:/projects/MaybeAI/audit/FINAL_AUDIT_REPORT.md), [10_chaos_testing.md](file:///d:/projects/MaybeAI/audit/10_chaos_testing.md), [06_security.md](file:///d:/projects/MaybeAI/audit/06_security.md).

---

## 1. Chaos & Failure Scenarios (A–F) Matrix

| Scenario | Failure Mode | Audit Evidence & Findings | Likelihood | Impact | Risk Rating | Mitigation (Roadmap ID) | Owner |
|---|---|---|---|---|---|---|---|
| **Scenario A: EventBus Stall & Burst** | Slow `/ws` client or subscriber blocks `EventBus.publish()`, freezing TTS lip-sync, barge-in, and LLM chunks; `publish_nowait()` leaks tasks. | `REPRODUCED` in Chaos A1 (`0.207s` stall on 200ms sub); `[PERF-HIGH-001]`, `[INFRA-HIGH-003]`, `[PERF-LOW-002]` | **High** | **High** | **CRITICAL** | Concurrent `asyncio.gather` dispatch with per-handler timeout, per-WS bounded queues (drop-oldest for telemetry), dead-listener eviction (`H0-05`). | Core Infra (`H0-05`) |
| **Scenario B: Barge-In Race & Side Effects** | Mid-stream `barge_in()` swallows `CancelledError` in `speak_stream()`, emitting partial `ai_response`/Discord/MC replies; `Singer` BGM keeps playing; untracked `on_mouth_update` tasks reopen mouth. | `VERIFIED` in `02_realtime_audio.md` & `01_core_infrastructure.md`; `[AUDIO-CRIT-001]`, `[AUDIO-HIGH-002]`, `[INFRA-HIGH-001]` | **High** | **High** | **CRITICAL** | Re-raise `CancelledError` / check `was_interrupted` before broadcasts; call `singer.stop()` in `barge_in()`; coalesce lip-sync worker (`H0-06`, `H0-05`). | Audio / Orchestrator (`H0-06`) |
| **Scenario C: Plugin Escape & Crash** | External plugin reads `.env` / `config/settings.json`, exfiltrates keys over network, executes code at import time, or crashes leaving dead entry in `_subprocesses` / flaking cold start. | `VERIFIED` & `REPRODUCED` in Chaos C3/C4; `[SEC-CRIT-002]`, `[QA-HIGH-001]`, `[QA-MED-001]` | **Medium** | **Critical** | **CRITICAL** | Separate `startup_timeout_sec` & evict crashed workers (`H0-09`); OS-level filesystem/network jail + host-approved `granted_permissions` + drop `inprocess` (`H3-01`). | Security / Plugins (`H0-09`, `H3-01`) |
| **Scenario D: Collab Replay, Spoof & Flood** | Intercepted `CollabEnvelope` replayed indefinitely; `localhost.evil.com` bypasses unsigned check; `turn_cooldown_sec` deadlocks permanently; `emote_sync` floods cooldown; parallel reply tasks spawn. | `REPRODUCED` in Chaos D3/D5 & `04_collab_protocol.md`; `[COLLAB-CRIT-001]`, `[COLLAB-HIGH-001/003/004]`, `[QA-MED-002]` | **High** | **High** | **CRITICAL** | `message_id` nonce cache + `±60s` timestamp window; `urlparse().hostname` check; reset `turn_count` on cooldown expiry; hold `"speaking"` state before LLM call (`H0-04`, `H3-03`). | Collab (`H0-04`, `H3-03`) |
| **Scenario E: Minecraft/OBS Desync & Replan Loop** | `bot.js` or OBS drops leaving `connected=True`; `bot.js` leaks `setInterval`; 0ms MC polling triggers infinite 25s `StrategyReplanner` loop (`goals.json` bloat); `REPLANNED` goals never complete. | `REPRODUCED` in Chaos E1/E2 & `03_cognitive_architecture.md`; `[GAME-CRIT-002]`, `[GAME-HIGH-002]`, `[COG-CRIT-001/002]`, `[COG-HIGH-001]` | **High** | **High** | **CRITICAL** | Reset connection state on socket drop + clear `bot.js` timers + auto-reconnect (`H0-07`); exclude `REPLANNED` from denominator & cap `MAX_REPLAN_ATTEMPTS=3` (`H0-08`); async telemetry delta (`H1-06`). | Games / Cognition (`H0-07`, `H0-08`, `H1-06`) |
| **Scenario F: Prompt Injection to OS / XSS Pivot** | Public chatters inject prompts (dead `strict_mode` / `prompt_injection_filter`, unsanitized `user`/`donation_amount`); unauthenticated `/ws` + `/settings` stored XSS steals `maybeai_creator_token` to invoke desktop/clip actions. | `VERIFIED` in `06_security.md` & `07_frontend_ux.md`; `[SEC-CRIT-001]`, `[SEC-HIGH-004]`, `[UI-HIGH-001]`, `[SEC-MED-003]` | **High** | **Critical** | **CRITICAL** | Gate all `/ws` mutations & `/api/*` GETs (`H0-01`); escape all `/settings` HTML (`H0-02`); enforce `strict_mode`, sanitize metadata, XML-delimit chat (`H0-09`). | Security / Frontend (`H0-01`, `H0-02`, `H0-09`) |

---

## 2. Strategic & Operational Risk Register (Non-Chaos Risks)

| Risk ID | Risk Description | Linked Findings | Likelihood | Impact | Mitigation & Contingency | Owner |
|---|---|---|---|---|---|---|
| **RISK-OPS-01** | **Docker / LAN Auth Lockout:** Creators deploying `docker-compose.yml` cannot use `/` or `/deck` privileged actions due to `_is_ws_creator_authorized` loopback-first check and missing token UI. | `[SEC-HIGH-001]`, `[UI-HIGH-002]` | **High** | **High** | Check `MAYBEAI_CREATOR_TOKEN` before loopback in `_is_ws_creator_authorized`; add shared token modal to `/` and `/settings` (`H0-01`, `H0-02`). | Platform / Frontend |
| **RISK-OPS-02** | **LLM API Cost Spike / Outage:** Unbounded 3.5K–6K token prompts inflate cloud spend; single-provider outage drops Eve straight to offline mock text mid-stream. | `[COG-HIGH-002]`, `03_cognitive_architecture.md` | **High** | **Medium** | Implement `ContextBudgetManager` (`H1-05`) and cross-provider failover Gemini → OpenAI → Ollama → Mock (`H2-01`). | AI / Cognition |
| **RISK-OPS-03** | **Live Audio / Avatar Desync on Stream:** Whisper STT blocks WS receive loop; synthetic 80ms square wave fights browser `AnalyserNode` RMS in `output_mode="both"`. | `[AUDIO-CRIT-002]`, `[AUDIO-HIGH-001]` | **High** | **Medium** | Offload STT to background task (`H1-01`); extract real RMS envelope and arbitrate browser vs. server lip-sync (`H1-02`). | Audio / UX |
| **RISK-OPS-04** | **Chess Session Corruption:** `asyncio.to_thread(alpha_beta)` mutates shared `chess.Board` concurrently with event-loop moves/resigns. | `[GAME-CRIT-001]` | **Medium** | **High** | Clone `self.board.copy(stack=False)` before search and guard transitions with `asyncio.Lock` (`H0-07`). | Games |
| **RISK-OPS-05** | **Test Suite & CI Blind Spots:** 100% mocked external adapters (OBS, VTS, Mineflayer, `ffmpeg`) and 0% browser E2E tests hide integration regressions; tests mutate `data/`. | `08_qa_reliability.md`, `[QA-MED-003]` | **High** | **Medium** | Isolate tests to `TemporaryDirectory()` (`H1-07`); add Playwright E2E and contract smoke tests (`H3-06`). | QA / Reliability |
| **RISK-OPS-06** | **Air-Gapped Stream Failure:** External CDN dependencies (`esm.sh`, Google Fonts) fail when streaming offline or behind strict firewalls. | `[UI-MED-004]` | **Medium** | **Medium** | Vendor Three.js, `@pixiv/three-vrm`, and local fonts in `web/vendor/` (`H2-05`). | Frontend |

---

## 3. Escalation & Review Cadence
- **Horizon 0 Gate Review:** Weekly until all 6 Chaos Scenarios (A–F) pass automated regression checks.
- **Soak & Cost Audit:** Bi-weekly token-spend and RSS memory check once Horizon 1 `ContextBudgetManager` and Horizon 2 observability are active.
