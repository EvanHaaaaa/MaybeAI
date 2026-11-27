# MaybeAI — Product & Engineering Success Metrics (`strategy/SUCCESS_METRICS.md`)

**Author:** Agent 9 (`ng-strat-product`) — Product Vision & Innovation Strategist  
**Grounding Baseline:** [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md), [11_chaos_testing.md](file:///d:/projects/MaybeAI/audit/11_chaos_testing.md), [12_performance_analysis.md](file:///d:/projects/MaybeAI/audit/12_performance_analysis.md), [13_production_readiness.md](file:///d:/projects/MaybeAI/audit/13_production_readiness.md)

---

## 1. Reliability & Operational Stability KPIs

| KPI | Verified Post-H3 Baseline | Target (Horizon 4 / Pre-24/7 `GO`) | Target (Horizon 5+) | Measurement Source |
|---|---|---|---|---|
| **Automated Test Pass Rate** | `380/381` (`1` Playwright skipped) | `100%` (incl. Playwright E2E in CI) | `100%` + live adapter smoke suite | `unittest`, `test_guard_runner.js`, `test_e2e_browser.py` |
| **Python `ResourceWarning`s (`-W default`)** | Multiple unclosed `aiohttp`/socket warnings | `0` warnings | `0` warnings | `python -W default -m unittest` |
| **Unattended Soak Stability** | `8–12h` feasible under supervision (`12_performance_analysis.md`) | `24h` continuous soak, `<5%` RSS drift, `0` leaked `bg_tasks_active` | `72h+` unattended 24/7 `GO` | `/api/metrics` (`rss_mb`, `bg_tasks_active`) |
| **WS Stalled-Client Isolation** | `2.0s` per-client timeout without outbound queue | `0 ms` delay to healthy WS clients (`asyncio.Queue(maxsize=64)`) | `0 ms` delay at 100+ listeners | Chaos Probe / `FUT-015` |
| **Collab Disconnect Recovery** | `CHAOS-B-001`: `floor_state` stuck at `"listening"` | `100%` immediate reset to `"idle"` on disconnect | `100%` N-peer room recovery | Chaos Scenario B / `FUT-013` |
| **Structured Log Disk Bound** | Unbounded stdout `print()` | Bounded `RotatingFileHandler` (e.g., `50MB x 3`) | Bounded + `/api/health` deep probe | `core/logging_config.py`, `/api/health` |

---

## 2. Latency & Real-Time Performance KPIs

| KPI | Verified Post-H3 Baseline | Target (Horizon 4) | Target (Horizon 5+) | Measurement Source |
|---|---|---|---|---|
| **Moderation Latency** | `0.006 ms/msg` (`3.19 ms` / 500 msgs) | `< 5 ms` p95 | `< 5 ms` p95 | `Moderator.clean_text` benchmark |
| **`EventBus` Dispatch (50 msgs)** | `0.28 ms`, `0` errors (`Chaos A`) | `< 1 ms` p95 | `< 1 ms` p95 | `EventBus` chaos probe |
| **WS Fan-Out (10 / 100 clients)** | `0.074 ms` / `0.262 ms` per broadcast | `<= 0.1 ms` / `<= 0.5 ms` | `<= 0.5 ms` with bounded queues | `12_performance_analysis.md` |
| **Barge-In Cancellation Latency** | Sub-second (`speak_stream()`), `speak()` swallows `CancelledError` | `<= 100 ms` across `speak()`, `speak_stream()`, and `Singer` | `<= 50 ms` with `silero-vad` | `Orchestrator.barge_in()` + `FUT-007` |
| **LLM Stream Completion** | `ClientTimeout(total=1.8)` truncates >1.8s replies (`AUDIO-MED-001`) | `0%` healthy-stream truncation; `<1.8s` TTFB failover | `<1.0s` TTFB with SLM/LLM router | `Brain` + `MetricsCollector` |
| **Vector Memory Search (`vector_search`)** | `13.54 ms` (100 rows) -> `45.32 ms` (2,000 rows) | `< 50 ms` (2,000 rows) | `<= 20 ms` p95 at `10,000+` rows (`sqlite-vec`) | `MemoryDatabase.vector_search` / `FUT-004` |

---

## 3. Memory, Cognitive & Identity Continuity KPIs

| KPI | Verified Post-H3 Baseline | Target (Horizon 4) | Target (Horizon 5+) | Measurement Source |
|---|---|---|---|---|
| **Recall Coverage Beyond 2,000 Rows** | `0%` dense vector recall past 2,000th row (FTS5 only) | `100%` FTS5 + `2,000` vector | `>= 85%` Recall@5 across `10,000+` rows | `FUT-004` / `EXP-004` eval set |
| **Promise Fulfillment Rate** | `0%` automated (`fulfill_promise()` uncalled) | `>= 90%` tracked promises resolved/archived | `>= 95%` + `promises.md` bounded `<=20` rows | `MemoryDatabase` / `FUT-003` |
| **Causal Learning Utilization** | `0%` (`Goal.reflection` write-only) | `100%` `Goal.reflection` queried on replan/decompose | `>= 30%` reduction in repeat domain failures | `StrategyReplanner` / `FUT-001` |
| **Fake Progress Fabrication** | Chess falls back to `simulated: True` when disconnected | `0` fabricated completions (`0%`) | `0%` across all L2–L4 domains | `AutonomousMissionExecutor` / `FUT-008` |
| **Persona Invariant Integrity** | Bounded `[0.05, 0.98]` 5-trait sliders | `100%` Creator invariants preserved | `100%` invariants + inspectable `IdentityAnchor`s | `PersonalityEvolutionEngine` / `FUT-005` |

---

## 4. Security & Safety KPIs

| KPI | Verified Post-H3 Baseline | Target (Horizon 4) | Target (Horizon 5+) | Measurement Source |
|---|---|---|---|---|
| **WS Token Exposure** | `?token=` in `buildWsUrl()` + `localStorage` (`SEC-GAP-001`) | `0` `?token=` URLs; `Sec-WebSocket-Protocol` + `sessionStorage` | `0` client token leaks | `web/shared-client.js`, `run.py` / `FUT-014` |
| **Windows Plugin Sandbox Containment** | Bypassable Python monkeypatches (`SEC-GAP-002`) | OS Restricted Token / AppContainer blocks `.env` read | `100%` OS-jailed external plugins | `tests/test_plugin_sandbox*` / `FUT-012` |
| **Indirect VLM/OCR Injection Defense** | `obs.summary` raw in system prompt (`SEC-GAP-003`) | `100%` sanitized + delimited | `100%` sanitized across all perception feeds | `core/conversation/engine.py` / `FUT-006` |
| **Secret Masking Coverage** | `8/8` secret fields masked in `ConfigManager` | `8/8` + `0` secrets in logs | `100%` masked | `tests/test_config_manager.py` |

---

## 5. Product Engagement & Creator Adoption KPIs

| KPI | Verified Post-H3 Baseline | Target (Horizon 4) | Target (Horizon 5+) | Measurement Source |
|---|---|---|---|---|
| **Supervised Localhost Readiness** | **`GO`** | **`GO`** | **`GO`** | `13_production_readiness.md` |
| **Authenticated LAN / Docker Readiness** | **`CONDITIONAL GO`** | **`GO`** | **`GO`** | `13_production_readiness.md` |
| **Unattended 24/7 Public Readiness** | **`NO-GO`** | **`CONDITIONAL GO`** | **`GO`** | `13_production_readiness.md` |
| **Frontend Accessibility & Reliability** | `5` unguarded `ws.readyState`; `0` `:focus-visible` rules | `0` null WS errors; `:focus-visible` + `reduced-motion` | Unified Studio Shell + consistent locale | `web/app.js`, `web/style.css` / `FUT-014` |
| **Multi-Agent Collab Capacity** | `2-peer` scalar (`L2.5`) | `2-peer` bidirectional (`duet`/`emote`/`chess`) | `3–6` peer `PeerSession` mesh (`L4`) | `CollabManager` / `FUT-013` |
| **Post-Stream Content Automation** | Manual `/api/clips` + `YYYY-MM-DD.md` VOD | `.get_status()` + race-free `replay_saved` | Auto-queued 9:16 shorts + VOD chapters | `HighlightDetector`, `ClipPipeline` / `FUT-011` |
