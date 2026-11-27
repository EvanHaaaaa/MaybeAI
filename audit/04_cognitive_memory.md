# 04 — Cognitive Architecture & Memory Post-Implementation CTO Audit

**Auditor:** Agent 3 (`ng-cognition`) — Cognitive Architecture & Memory Auditor  
**Scope:** Post-H1/H2 verification across `core/brain.py`, `core/memory/`, `core/conversation/`, `core/planning/`, `core/personality/`, `core/mood/`, and `core/relationship/`.  
**Verification Baseline:** Direct source inspection + full test suite execution (`.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`: **381 tests in 34.092s — `OK (skipped=1)`**).

---

## 1. Executive Verdict: Does Eve Genuinely Learn or Merely Retrieve?

**Verdict:** Eve **retrieves previously stored information and mutates bounded scalar state**, rather than genuinely learning from lived experiences.

1. **Episodic Memory (`core/memory/`):** Operates as a **retrieve-and-inject RAG pipeline**. `MemoryRetriever` fetches up to `top_k=3` episodes via hybrid FTS5 + cosine search and formats them into `[🧠 EVE'S SECOND BRAIN & EPISODIC MEMORY RECALL]`. Stored episodes never update behavioral policies, scoring weights, or world models, and there is no hierarchical consolidation (e.g., episodic-to-semantic distillation or memory decay/pruning).
2. **Cognitive Reasoning & Planning (`core/brain.py`, `core/planning/`):** `StrategyReplanner` selects `[Plan B]` via keyword matching on `failure_reason` (`"creeper"`, `"habis"`, `"kacang"`, `"blunder"`) rather than causal diagnosis. `Goal.reflection` (`core/planning/replanner.py:35, 139`; `core/planning/executor.py:614`) is **write-only**: it is serialized to `goals.json`/`agenda.md` and never fed back into `GoalDecomposer` or future mission selection, so Eve repeats identical failed strategies across goals.
3. **Personality & Relationship (`core/personality/`, `core/relationship/`):** `PersonalityEvolutionEngine.record_experience()` applies hardcoded `experience_matrix` deltas to 5 trait floats (bounded `[0.05, 0.98]`), and `RelationshipEngine.record_chat_interaction()` nudges 5 affinity floats via keyword heuristics. These are **parametric state sliders**, not learned behavioral abstractions.
4. **Emotional Continuity (`core/mood/engine.py`):** A reactive homeostatic state machine with exponential decay toward personality baselines and sampling temperature modulation (`get_temperature_modifier()`).

---

## 2. L0–L5 Maturity Scorecard

| Dimension | Score | Maturity Level | Justification |
|---|---|---|---|
| **Memory** | **L2** | Structured Hybrid Retrieval | Hybrid FTS5 + dense vector cosine search with shared `EmbeddingEngine` and dimension-mismatch guard, but constrained by a 2000-row linear Python vector scan, un-wired promise fulfillment, and zero hierarchical memory consolidation. |
| **Cognitive Reasoning** | **L2** | Bounded Contextual Reasoning | `ContextBudgetManager` enforces per-provider token budgets, `ProviderCircuitBreaker` handles cross-provider failover, and `is_creator` authority is plumbed end-to-end; lacks causal self-reflection, multi-step planning critique, or policy learning. |
| **Personality** | **L2** | Bounded Parametric Evolution | Asymptotically bounded 5-trait evolution (`[0.05, 0.98]`) with milestone unlocks and baseline sync to `MoodEngine`, but mutations are driven by a static `experience_matrix` rather than learned experience synthesis. |
| **Emotional Continuity** | **L3** | Homeostatic Affective Continuity | Continuous 5-dimension `MoodEngine` with exponential baseline decay, `get_temperature_modifier()` LLM sampling coupling, and multi-metric `RelationshipEngine` dossiers with inside jokes; lacks long-horizon emotional memory weighting. |
| **Autonomous Missions** | **L2** | Supervised Closed-Loop Execution | `REPLANNED` progress fix, `MAX_REPLAN_ATTEMPTS = 3` cap, `approval_timeout_sec` TTL, and Minecraft telemetry polling prevent infinite loops and false completion; replanning remains keyword-templated and `goal.reflection` is write-only. |

---

## 3. Post-H1/H2 Verification Matrix

| Item / Claim | Claim Status | Capability Status | Evidence & File References |
|---|---|---|---|
| `ContextBudgetManager` per-provider token budgeting & priority truncation | `VERIFIED` | `EXISTING` | `core/brain.py:97-244` defines `ContextBudgetManager` (`openai: 1800`, `gemini: 1800`, `ollama: 1600`, `mock: 1800`; priority drop order: `lore` → `memories` → oldest `history` → `mood_personality` → `creator_safety` → `system_core` char cap). Wired into `_build_openai_payload` (`core/brain.py:734`), `_build_ollama_payload` (`core/brain.py:934`), and `_build_gemini_payload` (`core/brain.py:1060`). `max_tokens` harmonized to `800` for OpenAI (`:728`) and Gemini (`:1083`). Note: uses `(len(text) + 3) // 4` heuristic, not tokenizer-exact `tiktoken`. |
| `is_creator` end-to-end plumbing (live LLM + streaming + fallbacks) | `VERIFIED` | `EXISTING` | Passed from `Brain.generate_response` (`core/brain.py:491`) and `Brain.generate_response_stream` (`core/brain.py:569`) into `abuild_system_prompt(..., is_creator=is_creator)` (`core/brain.py:510, 591`), which injects `[CREATOR VERIFIED]` in `MasterPromptBuilder.build_system_prompt` (`core/conversation/prompts.py:56-61`). Also forwarded to all `generate_mock_response` / `_stream_mock` fallback calls (`core/brain.py:525, 552, 598`, etc.) and tracked in `ChatCurator` (`core/conversation/chat_curator.py:14, 71, 125, 172`). |
| Cross-provider `ProviderCircuitBreaker` failover | `VERIFIED` | `EXISTING` | `ProviderCircuitBreaker` (`core/brain.py:14-95`) implements `closed` → `open` (`cooldown_sec=30.0`) → `half_open` probe state machine after `failure_threshold=3`. Wired into `generate_response` (`core/brain.py:514-542`) and `generate_response_stream` (`core/brain.py:595-626`) via `_get_failover_chain` (`core/brain.py:296-320`) with `failover_timeout_sec=1.8` (`core/brain.py:284-286`). |
| `MoodEngine.get_temperature_modifier()` wired into `Brain` | `VERIFIED` | `EXISTING` | `MoodEngine.get_temperature_modifier()` (`core/mood/engine.py:231-240`, clamped `[-0.15, +0.15]`) is called by `Brain._get_effective_temperature()` (`core/brain.py:272-282`, clamped `[0.2, 1.2]`) and applied to OpenAI (`:727`), Ollama (`:951`), and Gemini (`:1082`). |
| Shared `EmbeddingEngine` & dimension-mismatch guard | `VERIFIED` | `EXISTING` | `EpisodicMemoryStore` (`core/memory/__init__.py:20-28`) shares a single `EmbeddingEngine` instance with `MemoryDatabase` and `MemoryRetriever`. `MemoryDatabase._can_persist_reencoded_embedding()` (`core/memory/database.py:221-239`) blocks overwriting higher-dim (>128-d) embeddings with 128-d hash fallbacks during `vector_search` (`:268-288`) and `avector_search` (`:318-338`). `EmbeddingEngine.cosine_similarity` (`core/memory/embedding.py:489`) safely returns `0.0` on mismatched dimensions. |
| `promises.md` archival sync & fulfillment | `PARTIALLY VERIFIED` | `INCOMPLETE` | `MarkdownBrainSync` (`core/memory/markdown_sync.py:118-241`) implements bounded `promises.md` (`max_completed_rows=20`) with overflow archival to `promises_archive.md`, and `MemoryDatabase` (`core/memory/database.py:677-697`) + `EpisodicMemoryStore` (`core/memory/__init__.py:105-114`) expose `fulfill_promise()`, `archive_old_promises()`, and `sync_promises()`. **Gap:** None of these fulfillment/archival methods are called anywhere in `core/conversation/`, `core/planning/`, `core/brain.py`, or `web/`, and `sync_promises_from_db` is one-way (SQLite → Markdown), not bidirectional. |
| `Goal.recalculate_progress()` with `REPLANNED` status | `VERIFIED` | `EXISTING` | `Goal.recalculate_progress()` (`core/planning/models.py:101-119`) filters `active_subtasks = [s for s in self.subtasks if s.status != GoalStatus.REPLANNED.value]`, resolving the pre-H1/H2 bug where replanned goals could never reach `COMPLETED`. |
| `MAX_REPLAN_ATTEMPTS = 3` retry cap | `VERIFIED` | `EXISTING` | `MAX_REPLAN_ATTEMPTS = 3` (`core/planning/replanner.py:6, 16`) is enforced in both `StrategyReplanner.replan_subtask` (`:31-42`) and `AutonomousMissionExecutor.step_once` (`core/planning/executor.py:610-652`), transitioning exhausted subtasks and goals to `FAILED`. |
| `approval_timeout_sec` TTL on human approval gate | `VERIFIED` | `EXISTING` | `AutonomousMissionExecutor` (`core/planning/executor.py:35, 51`) defaults `approval_timeout_sec = 300.0`, stamps `plan["expires_at"]` (`:548-549`), and calls `_expire_stale_approval()` (`:501-523, 536`) at the start of `step_once()` to clear expired gates. |

---

## 4. Remaining Architectural Gaps & Risks

1. **2000-Row Linear Vector Scan (`core/memory/database.py:24, 262-263, 312-313`):**  
   - **Status:** `VERIFIED` (`EXISTING` limitation).  
   - **Detail:** `vector_search()` and `avector_search()` fetch the most recent `vector_scan_limit` (default `2000`) rows via `get_recent_memories()` and compute cosine similarity in a Python `for` loop. There is no ANN index (e.g., `sqlite-vec`, FAISS, or HNSW). Any memory older than the 2,000th most recent row is **invisible to dense vector search**, and latency scales linearly up to 2,000 deserializations per query.

2. **No Hierarchical Memory Consolidation (`core/memory/`, `core/conversation/memory.py`):**  
   - **Status:** `VERIFIED` (`PLANNED` / unimplemented).  
   - **Detail:** `EpisodicMemoryStore` stores flat episodic rows in SQLite and daily Markdown journals, while `ContextMemory` (`core/conversation/memory.py:87-117`) only retains a 16-turn buffer plus a 4-snippet string-concatenated `rolling_summary`. There is no periodic consolidation pipeline to distill daily episodes into semantic facts, merge duplicates, or prune low-importance noise.

3. **No Causal Self-Reflection Loop (`core/planning/`):**  
   - **Status:** `VERIFIED` (`PLANNED` / unimplemented).  
   - **Detail:** `Goal.reflection` (`core/planning/replanner.py:35, 139`) is never read by `GoalDecomposer`, `GoalEngine.autonomous_select_next_activity()`, or `AutonomousMissionExecutor`. Additionally, `AutonomousMissionExecutor._execute_chess` still falls back to `{"simulated": True}` progress when `self.chess is None` (`core/planning/executor.py:406-410`), though `_execute_minecraft` now properly blocks when disconnected (`:352-360`) and polls telemetry when connected (`:312-336`).
