# MaybeAI — Strategic & Operational Risk Register (`strategy/RISK_REGISTER.md`)

**Owner:** AGENT 12 (`ng-strat-roadmap` — CTO Strategy & Roadmap Manager)  
**Baseline Grounding:** [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md) (`HEAD` `96b7315`), [07_security.md](file:///d:/projects/MaybeAI/audit/07_security.md), [11_chaos_testing.md](file:///d:/projects/MaybeAI/audit/11_chaos_testing.md), [13_production_readiness.md](file:///d:/projects/MaybeAI/audit/13_production_readiness.md).

---

## 1. Horizon 0–3 Risk Disposition (Verified Baseline)

- **Remediated in H0–H3:** Unauthenticated mutating `/ws` & `/api/*` routes (`H0-01`), `/settings` stored XSS (`H0-02`), `ClipPipeline` path traversal (`H0-03`), Collab HMAC replay/SSRF (`H0-04`), `EventBus` blocking & untracked tasks (`H0-05`), `barge_in()` `CancelledError` & `Singer` stop (`H0-06`), Chess thread-safety (`H0-07`), Goal `REPLANNED` denominator & retry cap (`H0-08`), `Moderator` injection drop (`H0-09`), `ProviderCircuitBreaker` (`H2-01`), offline `web/vendor/` (`H2-05`).
- **Carried Forward to Pre-H4:** `SEC-GAP-001` (`?token=` + `localStorage`), `SEC-GAP-002` (Windows Python monkeypatch sandbox), `SEC-GAP-003` (raw `obs.summary` prompt injection), `INFRA-MED-001-RES` (missing per-WS outbound queue), `AUDIO-MED-001` (`1.8s` LLM stream timeout), `CHAOS-B-001` (`CollabManager.disconnect_peer()` stuck `floor_state`), `FE-REL-001` (5 unguarded `ws.readyState` calls in `app.js`), `OPS-001` (`ResourceWarning`s & no `RotatingFileHandler`).

---

## 2. Pre-Horizon 4 & Horizons 4–8 Risk Register

| Risk ID | Category | Horizon | Risk Description & Evidence | Likelihood | Impact | Rating | Mitigation & Contingency (Roadmap ID) |
|---|---|---|---|---|---|---|---|
| **RISK-SEC-01** | Security | **Pre-H4** | **WS Token Leakage (`SEC-GAP-001`):** `shared-client.js` appends `?token=` to WS URLs and stores tokens in `localStorage`, exposing credentials in logs/history/XSS. | High | High | **CRITICAL** | Migrate to `Sec-WebSocket-Protocol` auth + `sessionStorage`/cookie (`PH4-01`). |
| **RISK-SEC-02** | Security | **Pre-H4** | **Windows Plugin Sandbox Bypass (`SEC-GAP-002`):** Python monkeypatches in `sandbox_worker.py` are bypassable via `ctypes`/`subprocess`. | Medium | Critical | **CRITICAL** | Enforce Windows Restricted Token/AppContainer or Docker jail; ban `inprocess` for external plugins (`PH4-02`). |
| **RISK-SEC-03** | Security | **Pre-H4** | **Indirect VLM/OCR Prompt Injection (`SEC-GAP-003`):** Untrusted on-screen text in `obs.summary` enters LLM prompts raw. | High | High | **CRITICAL** | Route VLM/OCR text through `Moderator.sanitize_metadata()` + untrusted delimiters (`PH4-03`). |
| **RISK-SEC-04** | Security | **Pre-H4** | **DNS-Rebinding TOCTOU & Unbounded `yt-dlp` (`SEC-GAP-004/005`):** Separate DNS check in `validate_outbound_url`; `yt-dlp` lacks `--max-filesize` & concurrency cap. | Medium | High | **HIGH** | Pin resolved IP in HTTP connector; enforce `--max-filesize` + `Semaphore(2)` (`PH4-03`). |
| **RISK-REL-01** | Technical | **Pre-H4** | **WS Head-of-Line Stall & Stream Truncation (`INFRA-MED-001-RES`, `AUDIO-MED-001`):** Single slow WS client stalls up to `2.0s`; `ClientTimeout(total=1.8)` aborts >1.8s LLM streams. | High | High | **HIGH** | Add per-WS `asyncio.Queue(maxsize=64)` + sender task; use `ClientTimeout(connect=1.8, sock_read=5.0)` (`PH4-04`). |
| **RISK-REL-02** | Technical | **Pre-H4** | **Collab Floor Deadlock & `ResourceWarning`s (`CHAOS-B-001`, `OPS-001`):** `disconnect_peer()` leaves `floor_state="listening"`; unclosed `aiohttp` sessions & stdout `print()` risk 24/7 FD/disk exhaustion. | High | Medium | **HIGH** | Reset `floor_state="idle"` in `disconnect_peer()`, wire `on_hello`, close sessions cleanly, add `RotatingFileHandler` (`PH4-05`, `PH4-06`). |
| **RISK-COG-01** | Technical | **H4** | **Memory Consolidation Hallucination / Fact Corruption:** `H4-02` background distillation could overwrite creator-verified facts or inject false memories. | Medium | High | **HIGH** | Tag memories with provenance (`source_episode_ids`, `is_creator_verified`); never overwrite verified facts (`H4-02`); feature-flag `memory.consolidation_enabled`. |
| **RISK-COG-02** | Technical | **H4** | **2000-Row Recall Blindness & ANN Migration Failure:** Older memories are invisible today; native `sqlite-vec` wheel could fail on some Windows setups. | Medium | Medium | **MEDIUM** | Provide pure-Python/HNSW fallback and `memory.ann_backend="linear"` rollback (`H4-01`). |
| **RISK-AUT-01** | Autonomy | **H4–H5** | **Runaway Autonomous Loops / Persona Drift:** `startAutonomyLoop()` (`H5-02`) or dynamic trait synthesis (`H4-05`) could spam chat/actions or drift persona over weeks. | Medium | High | **HIGH** | Require `H4-03` causal reflection before `H5-02`, enforce cooldown budgets, `[0.05, 0.98]` trait bounds, and nightly safety evals (`H8-04`). |
| **RISK-AUT-02** | Autonomy | **H7** | **Unapproved Outbound Social Posting (`H7-02`):** Scheduled autonomous posts could publish off-brand or unsafe content. | Medium | Critical | **CRITICAL** | Mandatory `pending_approval` creator gate by default + global `autonomy.outbound_posting_enabled=false` kill-switch (`H7-02`). |
| **RISK-COST-01** | Cost | **H5–H7** | **VLM & Cloud API Spend Spike:** Adaptive VLM fusion (`H5-04`) or unbudgeted consolidation (`H4-02`) could multiply monthly cloud bills. | Medium | Medium | **MEDIUM** | Hard per-minute VLM rate cap, exact `tiktoken` `ContextBudgetManager` (`H4-04`), and Studio cost dashboard (`H7-03`). |
| **RISK-OPS-01** | Operational | **H6** | **N-Peer Collab Split-Brain (`H6-01`):** Concurrent floor claims across 3+ AI peers could cause overlapping speech or deadlocked turns. | Medium | High | **HIGH** | Single-owner floor lease with TTL expiration + `collab.max_peers=2` compatibility fallback (`H6-01`). |
| **RISK-OPS-02** | Operational | **H7** | **Disk Exhaustion from Clips & Telemetry:** Automated 9:16 clip rendering (`H7-01`) + `telemetry.db` (`H7-03`) could fill creator SSDs during 24/7 runs. | Medium | Medium | **MEDIUM** | Enforce `clips.max_storage_gb` LRU eviction (`H7-01`) and deep `/api/health?deep=1` disk threshold `500 MB` (`H5-05`). |
| **RISK-UX-01** | Technical | **H5** | **Frontend Modularization Regression (`H5-01`):** Refactoring `app.js` (5,896 lines) into ES modules could break Studio, `/overlay`, or `/deck`. | Medium | High | **HIGH** | Gate behind full Playwright E2E (`test_e2e_browser.py`) + `node --check` + keep legacy `/settings` fallback during soak (`H5-01`). |
| **RISK-ARCH-01** | Operational | **H8** | **Split-Node Network Jitter (`H8-01`):** Offloading STT/TTS/LLM to a remote GPU worker over WAN adds latency beyond the `<800 ms` interactive budget. | Medium | Medium | **MEDIUM** | Target LAN/WireGuard for split-node; retain `workers.mode="inprocess"` default with automatic local fallback (`H8-01`). |

---

## 3. Risk Escalation & Review Cadence
- **Pre-H4 Exit Review:** Weekly until all **CRITICAL** Pre-H4 risks (`RISK-SEC-01..03`, `RISK-REL-01..02`) are closed and `381/381` tests pass with **0** `ResourceWarning`s.
- **Per-Horizon Gate Review:** Mandatory before promoting any Horizon 4–8 release candidate (see [RELEASE_STRATEGY.md](file:///d:/projects/MaybeAI/strategy/RELEASE_STRATEGY.md)).
