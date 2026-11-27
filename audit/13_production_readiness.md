# Post-Implementation Audit — 13: Production Readiness & Maturity Assessment

**Auditor:** `ng-qa` (Agent 8)  
**Scope:** L0–L5 Maturity scoring for QA, Reliability, and Observability + Production Readiness verdict per deployment profile.

---

## 1. L0–L5 Maturity Scorecard

| Domain | Score | Justification (Verified Evidence) |
|---|---|---|
| **QA & Automated Testing** | **L3.5 (Defined → Quantitatively Managed)** | `381` tests across `43` modules (`380` passed, `1` skipped: Playwright), plus `node tests/test_guard_runner.js` and `node --check` on all 7 JS files. Live `uvicorn` contract tests exist (`test_e2e_browser.py`), though Playwright browser E2E is optional/skipped when not installed and `ResourceWarning`s/`asyncio` slow callbacks remain in test runs. |
| **Reliability & Fault Tolerance** | **L3.5 (Defined → Quantitatively Managed)** | `ProviderCircuitBreaker` (closed/open/half-open), TTS/LLM failover chains, `EventBus` per-handler timeout & exception isolation, `PluginRegistry` OS-isolated subprocesses (`windows_job_object` / `bwrap`), and bounded queues/buffers. Minor gap: `CollabManager.disconnect_peer()` does not reset `floor_state` from `"listening"` to `"idle"`. |
| **Observability & Operations** | **L3.0 (Defined)** | `/api/health` (Docker `HEALTHCHECK`), auth-gated `/api/metrics` (`MetricsCollector` with `rss_mb`, `uptime_sec`, counters, gauges, `p50`/`p95` histograms), and `/api/eventbus/stats`. Lacks structured JSON logging with `RotatingFileHandler` and Prometheus text exposition. |

---

## 2. Production Readiness Verdict by Deployment Profile

### Profile 1: Supervised Localhost (`127.0.0.1:7860`, Creator Present)
- **Verdict:** **READY (GO)**
- **Rationale:** Origin checks + optional `MAYBEAI_CREATOR_TOKEN` protect mutating/sensitive endpoints; all 380 unit/integration tests pass; VTS/OBS/TTS degrade gracefully when offline; `MemoryDatabase` WAL + `vector_scan_limit=2000` keeps latency `< 50 ms`.

### Profile 2: Authenticated LAN / Docker (`MAYBEAI_HEADLESS=1`, `MAYBEAI_CREATOR_TOKEN` set, Reverse Proxy)
- **Verdict:** **READY WITH CONDITIONS (CONDITIONAL GO)**
- **Conditions:**
  1. Set a strong `MAYBEAI_CREATOR_TOKEN` (never expose `0.0.0.0:7860` unauthenticated).
  2. Configure Docker log rotation (`logging: driver: json-file`, `max-size: "50m"`, `max-file: "3"`) and container memory limits in `docker-compose.yml` since core uses stdout `print()`.
  3. Keep `plugins.granted_permissions` minimal and `collab.allow_private_peers=false` unless explicitly needed.

### Profile 3: Unattended 24/7 Public Internet Exposure
- **Verdict:** **NOT READY (NO-GO)**
- **Blocking Gaps:**
  1. **Collab state recovery:** `CollabManager.disconnect_peer()` leaves `floor_state` in `"listening"` on abrupt disconnect (requires manual/event reset).
  2. **ResourceWarning / session hygiene:** Unclosed `aiohttp.ClientSession` / transport warnings observed under `-W default` indicate potential FD/memory drift over multi-day unattended runs.
  3. **Logging & alerting:** No structured log rotation, no `/api/health` deep dependency probe (SQLite/EventBus), and no external alerting/Prometheus endpoint.
  4. **Browser E2E:** Playwright E2E suite (`TestPlaywrightBrowserE2E`) is skipped without Playwright installed in the runtime environment.
