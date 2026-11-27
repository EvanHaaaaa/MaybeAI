# MaybeAI — Next-Generation Feature Backlog & Prioritization (`strategy/FEATURE_BACKLOG.md`)

**Author:** Agent 9 (`ng-strat-product`) — Product Vision & Innovation Strategist  
**Grounding Baseline:** [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md) (`HEAD` `96b7315`) & [INNOVATION_PORTFOLIO.md](file:///d:/projects/MaybeAI/strategy/INNOVATION_PORTFOLIO.md)

---

## 1. §10 7-Criterion Weighted Scoring Rubric (1–10 Scale)

Every `FUT-*` proposal is scored **1–10** on each of the 7 criteria (for **Maintainability & Safety**, **10 = highest safety / lowest maintenance burden**):

| Criterion | Code | Weight | Scoring Anchor (1 -> 10) |
|---|---|---:|---|
| **User Value** | `UV` | **20%** | 1 = Marginal polish -> 10 = High daily creator/viewer impact or unblocks 24/7 operation |
| **Strategic Alignment** | `SA` | **20%** | 1 = Tangential -> 10 = Directly closes post-H3 blockers or advances Autonomous Companion vision |
| **Feasibility** | `FE` | **15%** | 1 = High R&D / OS risk -> 10 = Surgical, well-scoped change in existing modules |
| **Differentiation** | `DF` | **15%** | 1 = Commodity hygiene -> 10 = Distinct AI companion, memory, or multi-AI moat |
| **Long-Term Potential** | `LP` | **15%** | 1 = Short-lived -> 10 = Foundational compounding platform capability |
| **Cost Efficiency** | `CE` | **10%** | 1 = High token/VRAM/CPU cost -> 10 = Zero/minimal runtime cost or actively reduces spend |
| **Maintainability & Safety** | `MS` | **5%** | 1 = High maintenance / security risk -> 10 = Reduces debt and strengthens safety boundaries |

**Formula:** `Total = 0.20*UV + 0.20*SA + 0.15*FE + 0.15*DF + 0.15*LP + 0.10*CE + 0.05*MS` (Max = `10.00`).

---

## 2. Scored `FUT-001`..`FUT-015` Backlog

| ID | Feature Name | Status | `UV` (20%) | `SA` (20%) | `FE` (15%) | `DF` (15%) | `LP` (15%) | `CE` (10%) | `MS` (5%) | Total Score | Classification Bucket |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `FUT-003` | Hierarchical Episodic-to-Semantic Consolidation & Promise Loop | `PLANNED` | 9 | 9 | 8 | 9 | 9 | 8 | 8 | **8.70** | **Strategic Differentiation** |
| `FUT-001` | Causal Self-Reflection & Experience-Driven Replanner | `PLANNED` | 8 | 9 | 8 | 9 | 9 | 9 | 8 | **8.60** | **Strategic Differentiation** |
| `FUT-008` | Autonomy L2–L3 Goal Supervisor & Telemetry-Verified Agency | `PLANNED` | 8 | 9 | 8 | 8 | 9 | 8 | 8 | **8.35** | **Core Evolution** |
| `FUT-015` | Per-WS Bounded Outbound Queues & Structured Telemetry Ops | `PLANNED` | 9 | 10 | 9 | 4 | 8 | 9 | 9 | **8.30** | **Quick Wins** |
| `FUT-006` | Sanitized Scene-Change VLM Ring Buffer & Live Commentary | `PLANNED` | 8 | 9 | 8 | 8 | 8 | 8 | 9 | **8.25** | **Quick Wins** |
| `FUT-014` | Unified Creator Studio Shell & Hardened Session Auth | `PLANNED` | 9 | 9 | 8 | 6 | 8 | 9 | 9 | **8.25** | **Core Evolution** |
| `FUT-012` | OS-Enforced Plugin Capability Jail & Typed `PluginSDK` | `PLANNED` | 8 | 10 | 6 | 8 | 9 | 8 | 8 | **8.25** | **Core Evolution** |
| `FUT-010` | Unified Showrunner & Multi-Modal Stage Sync (Karaoke + Games) | `PLANNED` | 9 | 8 | 8 | 8 | 8 | 8 | 8 | **8.20** | **Core Evolution** |
| `FUT-013` | Multi-Peer `PeerSession` Mesh & `RoomFloorArbitrator` | `PLANNED` | 8 | 9 | 6 | 9 | 9 | 8 | 7 | **8.15** | **Strategic Differentiation** |
| `FUT-011` | Automated Highlight-to-Short & VOD Chapter Pipeline | `PLANNED` | 9 | 8 | 9 | 7 | 7 | 8 | 9 | **8.10** | **Quick Wins** |
| `FUT-002` | Hybrid SLM/LLM Tiered Router & Token-Exact Budgeting | `PROPOSED` | 8 | 8 | 7 | 7 | 8 | 9 | 8 | **7.80** | **Core Evolution** |
| `FUT-004` | Hybrid `sqlite-vec` + FTS5 RRF Scaled Retrieval | `PROPOSED` | 7 | 8 | 7 | 7 | 9 | 9 | 8 | **7.75** | **Experimental Research** |
| `FUT-007` | ONNX `silero-vad` + Streaming Partial STT + AEC Duplex | `PROPOSED` | 8 | 8 | 6 | 8 | 8 | 7 | 7 | **7.55** | **Experimental Research** |
| `FUT-005` | Narrative Identity Graph & Cross-Session Persona Coherence | `PROPOSED` | 7 | 8 | 5 | 9 | 9 | 7 | 6 | **7.45** | **Long-Term Vision** |
| `FUT-009` | Multi-Platform Audience Graph & Longitudinal Relationship Memory | `PROPOSED` | 7 | 7 | 6 | 8 | 8 | 7 | 6 | **7.10** | **Long-Term Vision** |

---

## 3. Classification Buckets & Execution Grouping

### A. Quick Wins (High Impact, Low-to-Medium Effort `2–5d`, Immediate Pre-H4 Blockers)
- **`FUT-015` (8.30):** Per-WS bounded outbound queues (`INFRA-MED-001-RES`), `RotatingFileHandler`, `aiohttp` `ResourceWarning` cleanup, and 4 dead config keys. Unblocks `GO` for Unattended 24/7.
- **`FUT-006` (8.25):** Sanitize `obs.summary` (`SEC-GAP-003`) + scene-change VLM ring buffer. Eliminates indirect prompt injection while unlocking live visual commentary.
- **`FUT-011` (8.10):** Fix async `replay_saved` race, add `.get_status()` to `ClipPipeline`/`VODSummarizer`, and automate 9:16 highlight batching.

### B. Core Evolution (Foundational Hardening & Platform Spine)
- **`FUT-008` (8.35):** Autonomy L2–L3 Goal Supervisor, remove `simulated: True` Chess fabrication, wire `startAutonomyLoop()`.
- **`FUT-014` (8.25):** `Sec-WebSocket-Protocol` + `sessionStorage` auth (`SEC-GAP-001`), guard 5 `ws.readyState` nulls (`FE-REL-001`), Studio/Settings integration & accessibility.
- **`FUT-012` (8.25):** Windows Restricted Token / AppContainer plugin jail (`SEC-GAP-002`), disable external `inprocess`, capability approval UI.
- **`FUT-010` (8.20):** Forward `Singer` config in `reload_settings()` (`AUDIO-MED-003`), OBS/MC auto-reconnect, YouTube `--max-filesize` (`SEC-GAP-005`).
- **`FUT-002` (7.80):** Fix `ClientTimeout` TTFB truncation (`AUDIO-MED-001`), token-exact budgeting, hybrid SLM/LLM routing.

### C. Strategic Differentiation (Competitive Moat Builders)
- **`FUT-003` (8.70):** Hierarchical episodic-to-semantic memory consolidation & automated `promises.md` fulfillment loop.
- **`FUT-001` (8.60):** Causal self-reflection (`Goal.reflection` feedback) & experience-driven replanning.
- **`FUT-013` (8.15):** Fix `CHAOS-B-001` `disconnect_peer()`, wire `on_hello` & outbound sync, scale `CollabManager` to N-agent `PeerSession` mesh.

### D. Experimental Research (Gated Behind R&D Benchmarks)
- **`FUT-004` (7.75):** `sqlite-vec` ANN + FTS5 RRF scaling beyond 2,000 rows (gated by `EXP-004` latency/recall probe).
- **`FUT-007` (7.55):** ONNX `silero-vad` + streaming partial STT + `AUDIO-MED-002` `CancelledError` fix.

### E. Long-Term Vision (Horizons 6–8)
- **`FUT-005` (7.45):** Narrative Identity Graph & cross-session persona coherence (depends on `FUT-003`).
- **`FUT-009` (7.10):** Multi-platform Audience Graph & longitudinal relationship memory (depends on `FUT-003`).

### F. Defer
- **Multi-Language Studio i18n Packs (`DEFER`):** Unify existing mixed Indonesian/English UI copy to clean English first inside `FUT-014`; defer full multi-locale i18n packs until core Studio shell is modularized.
- **External Prometheus / Grafana Sidecar (`DEFER`):** `/api/metrics` JSON + `RotatingFileHandler` (`FUT-015`) is sufficient for single-node creators.

### G. Reject
- **Premature Microservices / Kubernetes Split (`REJECTED`):** Adds network serialization latency and operational complexity that hurts solo streamers; Modular Monolith + isolated plugin/media subprocesses is superior.
- **External Neo4j / Qdrant Vector DBs (`REJECTED`):** Violates single-file SQLite WAL simplicity; `sqlite-vec` + FTS5 RRF (`FUT-004`) handles 50,000+ memories in-process.
- **Unconstrained OS "Computer Use" (`REJECTED`):** High blast radius; all desktop/OBS actions must remain gated by `PermissionManager`.
- **Monolithic End-to-End Speech-to-Speech Replacement (`REJECTED`):** Bypasses `Moderator`, `RVCVoiceConverter`, `barge_in()`, and Second Brain memory extraction.
