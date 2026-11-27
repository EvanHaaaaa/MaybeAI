# MaybeAI — Release Strategy & Continuous Governance (`strategy/RELEASE_STRATEGY.md`)

**Owner:** AGENT 12 (`ng-strat-roadmap` — CTO Strategy & Roadmap Manager)  
**Baseline Grounding:** [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md) (`HEAD` `96b7315`), [09_qa_reliability.md](file:///d:/projects/MaybeAI/audit/09_qa_reliability.md), [12_performance_analysis.md](file:///d:/projects/MaybeAI/audit/12_performance_analysis.md), [13_production_readiness.md](file:///d:/projects/MaybeAI/audit/13_production_readiness.md).

---

## 1. Release Train & Readiness Tiers

MaybeAI releases progress through three promotion tiers aligned with `13_production_readiness.md`:
1. **Tier 1 — Supervised Localhost (`127.0.0.1:7860`):** Currently **GO**. Every PR must preserve this tier.
2. **Tier 2 — Authenticated LAN / Docker (`MAYBEAI_HEADLESS=1`):** Currently **CONDITIONAL GO** (requires strong `MAYBEAI_CREATOR_TOKEN`, log rotation, minimal `granted_permissions`).
3. **Tier 3 — Unattended 24/7 Public Internet / Autonomous Studio:** Currently **NO-GO**; **unlocked only upon Pre-H4 Remediation completion (`PH4-01..PH4-06`)**.

---

## 2. Mandatory CI/CD Pipeline Gates (Every PR & Release Candidate)

No PR or horizon milestone may merge to `main` unless all 6 automated checks pass:

1. **Python Unit & Integration Suite (Zero Warnings Gate):**
   - Command: `.venv\Scripts\python.exe -W default -m unittest discover -s tests -p "test_*.py"`
   - Gate: **100% pass** (post-`PH4-06`, Playwright E2E `TestPlaywrightBrowserE2E` must be **0 skipped** in CI) and **0 `ResourceWarning`s / `asyncio` slow callbacks** under `-W default`.
2. **JavaScript & Node Guardrails:**
   - Command: `node --check web/app.js web/overlay.js web/settings.js web/deck.js web/shared-client.js web/audio-worklet-processor.js` + `node tests/test_guard_runner.js`.
   - Gate: Exit code `0`.
3. **Security & Static Hygiene Gate:**
   - Verify zero `?token=` in `buildWsUrl()`, zero `localStorage` token persistence (`PH4-01`), zero external CDN URLs in `web/`, `Moderator` prompt-injection & `obs.summary` sanitization tests passing (`PH4-03`), and clean `git status --short data/` after test runs.
4. **Chaos Regression Gate (Scenarios A–H):**
   - Automated chaos probes (`11_chaos_testing.md`) must pass **8/8** (including **Scenario B** `CollabManager.disconnect_peer()` floor reset and **Scenario E** clean `aiohttp`/log hygiene).
5. **Latency & Resource Budget Gate:**
   - `Moderator.clean_text` `<5 ms`, `MemoryDatabase.vector_search` `<50 ms` (or `<20 ms` post-`H4-01`), `EventBus` WS fan-out `<10 ms` (stalled client `<5 ms` impact on healthy peers post-`PH4-04`).
6. **Container Build & Healthcheck Smoke:**
   - `docker build` succeeds; container starts with `MAYBEAI_HEADLESS=1` and `/api/health` (and `/api/health?deep=1` post-`H5-05`) returns `200 OK`.

---

## 3. Canary & Soak Validation Gates (Per-Horizon Promotion)

Before tagging a Horizon release (`v0.4-ph4`, `v0.5-h4`, ..., `v1.0-h8`):

| Horizon | Soak Duration | Canary Workload | Exit Criteria |
|---|---|---|---|
| **Pre-H4 (`PH4-01..06`)** | **8–12 hours** (Docker `MAYBEAI_HEADLESS=1`) | Continuous chat + TTS + periodic WS reconnects + Collab connect/drop | RSS drift `<5%`, `bg_tasks_active` returns to baseline, **0** `ResourceWarning`s, bounded rotating logs. |
| **Horizon 4** | **12 hours** | 50k-row ANN vector queries + background memory consolidation + causal replanning | `<20 ms` p95 vector recall, zero corrupted creator-verified facts, `promises.md <= 20` completed rows. |
| **Horizon 5** | **12 hours** | Unified Studio + `/overlay` + `/deck` + OBS/MC forced disconnects + adaptive VLM | OBS/MC auto-reconnect `<15s`, `<500 ms` clause TTS p95, zero WS teardown on settings access. |
| **Horizon 6** | **8 hours** | 3-peer simulated Collab + signed plugins + Collab Chess/Karaoke | Zero floor split-brain, runaway plugin killed at cgroup/JobObject cap without Orchestrator crash. |
| **Horizon 7** | **24 hours** | Post-stream 9:16 clip batch + `PresenceScheduler` dry-run + `telemetry.db` | Disk usage stays under `clips.max_storage_gb`, zero unapproved outbound posts. |
| **Horizon 8** | **24 hours** | Split-node Control Plane + GPU Worker + `.maybeai` export/import + `H8-04` evals | Control Plane `<250 MB` RAM, 100% `.maybeai` round-trip fidelity, safety evals `0` bypasses. |

---

## 4. Automated Rollback Triggers & Procedures

Every Horizon 4–8 capability ships behind a **runtime config feature flag** (`config/settings.json`) so rollback does not require an emergency code revert during a live stream:

- **Trigger 1 — P0 Security Regression:** Any auth bypass, XSS, or plugin sandbox escape $\rightarrow$ **Immediate `git revert` + block release**, revoke affected plugin signatures (`H6-02`).
- **Trigger 2 — Latency / Audio Budget Breach:** Voice turn p95 `>1,500 ms` or `barge_in()` `>100 ms` over 5 consecutive turns $\rightarrow$ Toggle `tts.clause_streaming=false` / `vision.adaptive_fusion=false` via `/settings` or `/api/config`.
- **Trigger 3 — Memory Leak / Soak Failure:** `rss_mb` grows `>15%` per hour or `bg_tasks_active` climbs monotonically $\rightarrow$ Restart container, disable `memory.consolidation_enabled=false` (`H4-02`), inspect `/api/metrics` & `/api/eventbus/stats`.
- **Trigger 4 — Autonomous Loop / Brand Risk:** Repeated mission failures (`>3` replans) or unexpected outbound draft $\rightarrow$ Hit `/deck` emergency stop (`autonomy.showrunner_enabled=false`, `autonomy.outbound_posting_enabled=false`).

---

## 5. Continuous Strategy & Architecture Review (§18)

To prevent strategy/docs drift (such as the pre-H0 `strategy/` drift noted in `FINAL_POST_IMPLEMENTATION_AUDIT.md` §3), MaybeAI enforces a **Continuous Strategy & Architecture Review** cadence:

### 5.1 Review Triggers
1. **Horizon Exit Gate:** Mandatory review upon completing Pre-H4 and each Horizon (H4–H8).
2. **Audit / Chaos Failure:** Any new **CRITICAL** or **HIGH** security/chaos finding triggers an immediate out-of-band review.
3. **Architecture Drift:** Adding a new top-level `core/` subpackage, external binary dependency, or `/api` / `/ws` contract change.
4. **Cost / Quota Variance:** Monthly cloud API spend exceeding `COST_AND_RESOURCE_PLAN.md` estimates by `>25%`.

### 5.2 Strategy & Architecture Review Log Template

| Date (UTC) | Trigger | Scope Reviewed | Key Decisions / Roadmap Adjustments | Owner | Linked Commit / Audit |
|---|---|---|---|---|---|
| `2026-11-27` | Post-H3 Audit (`96b7315`) | Pre-H4 Remediation + H4–H8 Plan | Established Pre-H4 P0/P1/P2 sprint (`PH4-01..06`) to clear §13 blockers before H4 cognitive expansion. | `ng-strat-roadmap` | `FINAL_POST_IMPLEMENTATION_AUDIT.md` |
| `YYYY-MM-DD` | `<Horizon Exit / Drift / Incident>` | `<Modules / Docs>` | `<Decision & Flag/PERT update>` | `<Agent / Lead>` | `<SHA / Report>` |
