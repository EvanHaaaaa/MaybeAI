# MaybeAI — Dependency Graph & Critical Path (`strategy/DEPENDENCY_GRAPH.md`)

**Owner:** AGENT 12 (`ng-strat-roadmap` — CTO Strategy & Roadmap Manager)  
**Baseline Grounding:** [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md) (`HEAD` `96b7315`) & [DEVELOPMENT_ROADMAP.md](file:///d:/projects/MaybeAI/strategy/DEVELOPMENT_ROADMAP.md)

---

## 1. Cross-Horizon Dependency Graph (Pre-H4 through Horizon 8)

> [!IMPORTANT]
> **Horizons 0–3 are already complete** (`4c4e473`..`96b7315`). The graph below starts at the **Pre-Horizon 4 Remediation Sprint (`PH4-01..PH4-06`)** and maps all hard technical, security, and architectural dependencies through **Horizon 8 (`H8-01..H8-04`)**.

```mermaid
flowchart LR
    subgraph PH4 ["Pre-Horizon 4: Critical Remediation Sprint (P0/P1/P2)"]
        PH4_01["PH4-01: WS Subprotocol Auth (SEC-GAP-001)"]
        PH4_02["PH4-02: Windows OS Plugin Sandbox (SEC-GAP-002)"]
        PH4_03["PH4-03: VLM Prompt Sanitization & SSRF/Media Caps"]
        PH4_04["PH4-04: Per-WS Queue, LLM Timeout & TTS/Singer Fix"]
        PH4_05["PH4-05: Collab Disconnect Reset & promises.md Hook"]
        PH4_06["PH4-06: app.js Guards, ResourceWarnings & Logging"]
    end

    subgraph H4 ["Horizon 4: Cognitive & Companion Intelligence"]
        H4_01["H4-01: Indexed ANN Vector Memory"]
        H4_02["H4-02: Hierarchical Memory Consolidation"]
        H4_03["H4-03: Causal Self-Reflection & Policy Loop"]
        H4_04["H4-04: Exact ContextBudget & Dead Config Wiring"]
        H4_05["H4-05: Narrative Affective Memory & Trait Synthesis"]
    end

    subgraph H5 ["Horizon 5: Multimodal & Autonomous Evolution"]
        H5_01["H5-01: Unified Creator Studio & Avatar Modules"]
        H5_02["H5-02: Proactive Showrunner & OBS/MC Auto-Reconnect"]
        H5_03["H5-03: Sub-500ms Clause TTS & Avatar Blending"]
        H5_04["H5-04: Adaptive Multimodal Context Fusion"]
        H5_05["H5-05: Prometheus /metrics & Deep Health Probes"]
    end

    subgraph H6 ["Horizon 6: Social & Multi-Agent Ecosystem"]
        H6_01["H6-01: N-Peer Mesh Collab & Auto-Sync"]
        H6_02["H6-02: Signed Plugins & Resource Quotas"]
        H6_03["H6-03: Multi-Platform Social Graph & Co-Play Queue"]
        H6_04["H6-04: Live Collab Games & Beat-Synced Duets"]
    end

    subgraph H7 ["Horizon 7: Autonomous Content & Digital Presence"]
        H7_01["H7-01: Captioned 9:16 Clip Factory & Disk Quota"]
        H7_02["H7-02: Scheduled Autonomous Presence & VOD Recap"]
        H7_03["H7-03: Creator Analytics & Cost Dashboard"]
        H7_04["H7-04: GPU Hardware Media Accel (NVENC/CUDA)"]
    end

    subgraph H8 ["Horizon 8: Long-Term Digital Companion Ecosystem"]
        H8_01["H8-01: Split-Node Control Plane + GPU Workers"]
        H8_02["H8-02: Encrypted .maybeai Identity Backup"]
        H8_03["H8-03: Versioned Companion SDK v1"]
        H8_04["H8-04: Continuous Safety & Soak Eval Suite"]
    end

    %% Pre-H4 internal & H4 edges
    PH4_01 --> PH4_06
    PH4_05 --> H4_01
    PH4_05 --> H4_03
    PH4_04 --> H4_02
    PH4_04 --> H4_04
    PH4_04 --> H5_03
    PH4_03 --> H5_02
    PH4_03 --> H5_04
    PH4_03 --> H6_03
    PH4_03 --> H7_01
    PH4_02 --> H6_02
    PH4_06 --> H5_01
    PH4_06 --> H5_05

    %% H4 internal & H5 edges
    H4_01 --> H4_02
    H4_02 --> H4_03
    H4_02 --> H4_05
    H4_02 --> H7_02
    H4_02 --> H8_02
    H4_03 --> H5_02
    H4_03 --> H8_04
    H4_04 --> H5_04
    H4_05 --> H6_03
    H4_05 --> H8_02

    %% H5 internal & H6/H7/H8 edges
    H5_01 --> H5_03
    H5_01 --> H7_03
    H5_01 --> H8_03
    H5_02 --> H6_04
    H5_02 --> H7_01
    H5_02 --> H7_02
    H5_03 --> H6_01
    H5_05 --> H7_03
    H5_05 --> H8_01
    H5_05 --> H8_04

    %% H6 & H7 to H8 edges
    H6_01 --> H6_04
    H6_01 --> H8_01
    H6_02 --> H8_03
    H7_01 --> H7_04
    H7_03 --> H8_04
    H7_04 --> H8_01
```

---

## 2. Critical Path Analysis

The **Critical Path** is the longest sequential chain of dependent work packages from **Pre-Horizon 4** to **Horizon 8 (`L5 Platform`)**. Any slip on these nodes directly delays final platform completion:

| Step | Work Package | PERT Expected ($E$) | Rationale on Critical Path |
|---|---|---:|---|
| 1 | **`PH4-04`** (Per-WS Queue, LLM Timeout & TTS/Singer Fix) | **2.1 d** | Unblocks reliable streaming LLM calls required by memory consolidation (`H4-02`) and clause TTS (`H5-03`). |
| 2 | **`H4-02`** (Hierarchical Memory Consolidation) | **5.3 d** | Depends on `PH4-04` (and `H4-01` ANN index); foundational for causal reflection (`H4-03`). |
| 3 | **`H4-03`** (Causal Self-Reflection & Policy Loop) | **4.7 d** | Depends on `H4-02`; required before enabling autonomous showrunner (`H5-02`). |
| 4 | **`H5-02`** (Proactive Showrunner & OBS/MC Auto-Reconnect) | **5.2 d** | Depends on `H4-03`; unlocks automated clip factory (`H7-01`) and live collab games (`H6-04`). |
| 5 | **`H7-01`** (Captioned 9:16 Clip Factory & Disk Quota) | **6.2 d** | Depends on `H5-02`; feeds GPU hardware media acceleration (`H7-04`). |
| 6 | **`H7-04`** (GPU Hardware Media Accel) | **3.9 d** | Depends on `H7-01`; establishes worker offload interfaces needed for `H8-01`. |
| 7 | **`H8-01`** (Split-Node Control Plane + GPU Workers) | **9.8 d** | Longest single package in H8; depends on `H7-04`, `H6-01`, and `H5-05`. |

- **Critical Path Sequential Sum:** $2.1 + 5.3 + 4.7 + 5.2 + 6.2 + 3.9 + 9.8 = \mathbf{37.2\text{ person-days}}$ (plus gate soak/verification buffers).
- **Parallelizable Secondary Paths:**
  - **Security & Ecosystem Track:** `PH4-02` (2.6d) $\rightarrow$ `H6-02` (6.2d) $\rightarrow$ `H8-03` (7.7d) = **16.5 person-days** (runs in parallel with H4–H7).
  - **Frontend & Analytics Track:** `PH4-01` (1.6d) $\rightarrow$ `PH4-06` (4.0d) $\rightarrow$ `H5-01` (6.8d) $\rightarrow$ `H7-03` (5.2d) $\rightarrow$ `H8-04` (5.7d) = **23.3 person-days** (runs in parallel with Cognitive/Media).

---

## 3. Hard Gate Rules Across Horizons

1. **No H4+ Expansion Before Pre-H4 P0s (`PH4-01`, `PH4-02`, `PH4-03`):** Unattended 24/7 or LAN deployments remain blocked until WS subprotocol auth, Windows OS plugin isolation, and VLM prompt sanitization pass regression tests.
2. **No Autonomous Showrunner (`H5-02`) Before Causal Reflection (`H4-03`):** Prevents Eve from repeating failed autonomous strategies in unattended loops.
3. **No Outbound Scheduled Posting (`H7-02`) Without Approval Queue:** Creator approval gate is mandatory by default to prevent unmoderated social posting.
