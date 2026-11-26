# 03 — Cognitive Architecture & Autonomous Intelligence Audit

**Auditor:** Agent 3 (`cto-cognition`) — MaybeAI CTO Audit Swarm  
**Scope:** Multi-provider LLM routing & context window management, embedding generation/fallback & vector retrieval accuracy, Second Brain persistence, mood/personality/relationship state transitions, and closed-loop autonomous mission planning/execution/replanning.  
**Verification Baseline:** Source code inspection across `core/brain.py`, `core/conversation/`, `core/memory/`, `core/mood/`, `core/personality/`, `core/relationship/`, `core/planning/`, `core/orchestrator.py`, `core/minecraft/controller.py`, plus `.venv\Scripts\python.exe -m unittest` (79 tests across 8 cognitive test modules: `OK` in 2.537s) and direct reproduction checks.

---

## 1. Capability Maturity Matrix

| Capability | Classification | Evidence Summary |
|---|---|---|
| Multi-provider LLM routing (OpenAI, Gemini, Ollama, Mock) & SSE/NDJSON streaming | **Current Capability** | Implemented in `core/brain.py` (`generate_response`, `generate_response_stream`) with shared `aiohttp.ClientSession` reuse (`_get_session`) and `x-goog-api-key` header auth. |
| Hybrid Second Brain memory (SQLite FTS5 + dense vector cosine + Karpathy Markdown sync) | **Current Capability** | Implemented in `core/memory/` (`MemoryDatabase`, `EmbeddingEngine`, `MemoryRetriever`, `MemoryExtractor`, `MarkdownBrainSync`). |
| Multi-dimensional MoodEngine with exponential baseline decay | **Current Capability** | Implemented in `core/mood/engine.py` with 5 continuous dimensions, stimulus deltas, and `sync_to_mood_baselines` from `PersonalityEvolutionEngine`. |
| Bounded Personality Evolution & Relationship Archetypes | **Current Capability** | Implemented in `core/personality/evolution.py` (`[0.05, 0.98]` asymptotic dampening) and `core/relationship/engine.py` (5 tiers, inside jokes, JSON + Markdown dossiers). |
| Hierarchical GoalEngine & StrategyReplanner | **Partially Implemented** | Goals decompose into subtasks and replan on failure, **but** replanned goals can never reach `COMPLETED` (`core/planning/models.py:109`) and replanning has no retry cap. |
| Closed-loop AutonomousMissionExecutor | **Partially Implemented** | Loop lifecycle, human approval gate, and EventBus emissions work, **but** disconnected/unverified domains fabricate progress (`simulated: True`), real Minecraft telemetry checks inventory 0ms after `toggle_wander()` causing stall/replan loops, and approval gates have no timeout. |
| Context window & token budget management | **Planned Capability** | No token estimator, prompt budgeter, or dynamic history truncation exists; `MasterPromptBuilder` concatenates 11+ subsystem directives unconditionally. |
| Cross-provider LLM failover & circuit breaking | **Planned Capability** | Provider errors immediately drop to offline `generate_mock_response` instead of failing over (e.g., Gemini → OpenAI → Ollama → Mock). |
| Mood-modulated LLM sampling temperature | **Partially Implemented** | `MoodEngine.get_temperature_modifier()` (`core/mood/engine.py:231`) is implemented and unit-tested, **but** never called by `Brain`. |
| Bidirectional Second Brain Markdown → SQLite sync & promise fulfillment | **Planned Capability** | Markdown files are write-only/append-only mirrors; `fulfill_promise()` exists in `MemoryDatabase` (`core/memory/database.py:608`) but is never wired into chat/mission evaluation or `promises.md` updates. |
| **Proposed Innovation:** Adaptive Cognitive Budgeter & Telemetry-Verified Action Supervisor | **Proposed Innovation** | Token-aware directive pruning + async action-completion watcher (waiting for actual Mineflayer inventory/position deltas before crediting or replanning). |

---

## 2. Detailed Findings

### 2.1 Closed-Loop Autonomous Mission Planning & Execution

#### `[COG-CRIT-001]` Replanned Goals Can Never Reach `COMPLETED` Status
- **Severity:** Critical
- **Evidence Classification:** `REPRODUCED`
- **Location:** `core/planning/models.py:109-112`, `core/planning/replanner.py:24`
- **Symptom:** Any goal that experiences even a single subtask failure and replan (`StrategyReplanner.replan_subtask`) remains permanently stuck in `in_progress` with `progress < 1.0`, even after every active/replacement subtask is completed.
- **Root Cause:** `StrategyReplanner.replan_subtask` sets `failed_subtask.status = GoalStatus.REPLANNED.value` (`core/planning/replanner.py:24`) and inserts `new_subtask` right after it. However, `Goal.recalculate_progress()` (`core/planning/models.py:107-112`) averages `s.progress` across **all** `self.subtasks` and checks:
  ```python
  if all(s.status == GoalStatus.COMPLETED.value for s in self.subtasks):
      self.status = GoalStatus.COMPLETED.value
  ```
  Because the `REPLANNED` subtask retains `status == "replanned"` and `progress < 1.0`, the condition can never evaluate to `True`.
- **Verification Steps:** Executed via `.venv\Scripts\python.exe`:
  ```python
  ge = GoalEngine(storage_dir=d)
  g = ge.create_goal('Test Goal', tier='daily', category='social')
  ge.set_active_goal(g.id)
  ge.fail_and_replan_active_subtask('kacang')
  [ge.complete_current_subtask() for _ in range(len(g.subtasks))]
  # Observed output:
  # status: in_progress progress: 0.8 subtask_statuses: ['replanned', 'completed', 'completed', 'completed', 'completed']
  ```
- **Blast Radius:** All autonomous goals that ever hit a failure/replan permanently stall in `in_progress`, never emit `goal_completed`, never award `challenge_completed` personality EXP, and never record an achievement episode.
- **Recommended Fix:** Exclude `GoalStatus.REPLANNED.value` subtasks from completion denominator and status checks in `Goal.recalculate_progress()` (e.g., filter `active_subs = [s for s in self.subtasks if s.status != GoalStatus.REPLANNED.value]`).

---

#### `[COG-CRIT-002]` Infinite Replan Loop & Unbounded Goal File Growth on Repeated Failure
- **Severity:** Critical
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/planning/executor.py:568-603`, `core/planning/replanner.py:43,59,75,91,107`
- **Symptom:** When a domain action fails repeatedly (e.g., `observed_delta <= 0` in Minecraft, `performance_runner` returning `success: False`, or an exception in `chess.start_game`), `AutonomousMissionExecutor` triggers `fail_and_replan_active_subtask()` on every 25s tick indefinitely, appending a new `[Plan B]` subtask each tick without ever aborting or switching goals.
- **Root Cause:** `StrategyReplanner.replan_subtask` increments `attempts=failed_subtask.attempts + 1`, but neither `GoalEngine`, `StrategyReplanner`, nor `AutonomousMissionExecutor` checks a `max_attempts` threshold or transitions the subtask/goal to `FAILED`/`ABANDONED`. Every tick also fires `mood_engine.apply_stimulus("goal_strategy_failed")` and writes `goals.json` + `agenda.md`.
- **Verification Steps:** Inspected `core/planning/executor.py:568-603` and `core/planning/replanner.py:14-120`. Confirmed `attempts` is written on `Subtask` creation and never read in any conditional.
- **Blast Radius:** Unbounded growth of `data/goals/goals.json` and `data/goals/agenda.md`, continuous annoyance spikes in `MoodEngine`, and repeated TTS failure announcements every 25 seconds.
- **Recommended Fix:** Enforce `MAX_REPLAN_ATTEMPTS = 3` in `GoalEngine.fail_and_replan_active_subtask()` / `AutonomousMissionExecutor`; on exhaustion, mark the goal `FAILED` (or `ABANDONED`) and call `autonomous_select_next_activity()` to pivot to a viable goal.

---

#### `[COG-HIGH-001]` Zero-Delay Telemetry Check Causes False Failures; Disconnected Mode Fabricates Progress
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/planning/executor.py:273-356`, `core/planning/executor.py:394-406`, `core/planning/executor.py:427-457`
- **Symptom:**
  1. When `minecraft.connection_status == "connected"` and `use_real_telemetry` is `True`, `_execute_minecraft` calls `toggle_wander()` / `jump()` and **immediately** (0ms later) checks `get_inventory_count(item_terms)` (`executor.py:300-312`). Because a Mineflayer bot cannot gather blocks in 0ms, `observed_delta <= 0` fails on every tick.
  2. Conversely, when `minecraft` is disconnected (`is_connected == False`), or for `speedrun_advance`/`guard` even when connected, or when `chess`/`performance_runner` are `None`, `AutonomousMissionExecutor` speaks a line and **unconditionally credits real progress** (`{"simulated": True, "delta": delta}` or fallback `mission_subtask_executed` at lines 351–355, 401–405, 435–439, 452–456).
- **Root Cause:** No async action-completion window or telemetry delta subscription exists between dispatching a Mineflayer command and evaluating its outcome; disconnected/unwired paths credit `GoalEngine` as if real work succeeded.
- **Verification Steps:** Inspected `core/planning/executor.py:259-457` and `core/minecraft/controller.py:139-181`. Confirmed `get_inventory_count` reads `self.latest_telemetry.get("inventory", {})` synchronously with no wait after `send_bridge_cmd`.
- **Blast Radius:** Either Eve falsely "completes" Minecraft/Chess/Performance goals while offline/disconnected, or she enters an infinite `[COG-CRIT-002]` replan loop when connected to Minecraft.
- **Recommended Fix:** Separate `simulated/commentary` mode from `verified_execution` mode; for live Minecraft tasks, track `baseline_count` across ticks (evaluating delta on the *next* tick or via `mc_telemetry` events) instead of 0ms inline polling, and pause/skip progress credit when `is_connected` is `False` unless `allow_simulated_progress=True`.

---

#### `[COG-MED-001]` Human Approval Gate Stalls Mission Loop Indefinitely Without Expiry
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/planning/executor.py:509-520`, `core/planning/executor.py:610`
- **Symptom:** When `human_approval_required=True`, `_run_loop` sets `self.pending_approval` once and skips all subsequent ticks (`if self.pending_approval is not None: continue`) until `approve_pending()` or `reject_pending()` is called.
- **Root Cause:** `pending_approval` has a `created_at` timestamp (`executor.py:214`) but no TTL/timeout or stale-goal invalidation check (e.g., if the active goal changes while approval is pending).
- **Verification Steps:** Inspected `core/planning/executor.py:509-520, 610`.
- **Blast Radius:** If the streamer misses an approval prompt in the UI, autonomous mission execution halts for the rest of the stream.
- **Recommended Fix:** Add an `approval_timeout_sec` (e.g. 120s) to expire stale `pending_approval` requests and verify `pending_approval["goal_id"] == active_goal.id` before `approve_pending()` executes.

---

### 2.2 Multi-Provider LLM Routing & Context Window Management

#### `[COG-HIGH-002]` Unbounded System Prompt Assembly & Missing Token Budget Management
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/conversation/engine.py:259-318`, `core/conversation/prompts.py:22-170`, `core/brain.py:382-417, 577-610`
- **Symptom:** Every LLM call builds a monolithic system prompt concatenating character bio, full `character.lore` JSON, 10 Conversational Pillars, `rolling_summary`, `memory_recall_block`, `chat_digest`, `social_context`, plus **11 subsystem directives** (`mood`, `goal`, `relationship`, `vision`, `multiplayer`, `desktop`, `minigame`, `storytelling`, `performance`, `personality`, and `special_event`/`roleplay`/`story`), alongside 16 turns of raw conversation history and optional base64 images.
- **Root Cause:** Neither `ConversationEngine` nor `Brain` performs token estimation, context-window ceiling checks, or priority-based directive pruning. Additionally, `Brain._build_openai_payload` defaults `max_tokens` to `150` (`core/brain.py:389`), whereas `_build_gemini_payload` defaults `max_tokens` to `800` (`core/brain.py:601`).
- **Verification Steps:** Inspected `core/conversation/engine.py:259-318`, `core/conversation/prompts.py:100-169`, and `core/brain.py:382-610`.
- **Blast Radius:** High latency and token cost per turn; risk of context overflow on smaller local Ollama models (e.g. 4K–8K context); inconsistent response truncation between OpenAI (150 tokens) and Gemini (800 tokens).
- **Recommended Fix:** Introduce a `ContextBudgetManager` that estimates token count (e.g. `len(text) // 4` or `tiktoken`), enforces per-provider context budgets, omits inactive subsystem directives (e.g. `minigame`/`storytelling`/`desktop` when idle), and harmonizes `max_tokens` defaults.

---

#### `[COG-HIGH-003]` `is_creator` Flag Dropped on All Live LLM Paths & Error Fallbacks
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/brain.py:187-238`, `core/brain.py:240-292`, `core/brain.py:419-446`
- **Symptom:** `Brain.generate_response(..., is_creator=True)` and `generate_response_stream(..., is_creator=True)` only pass `is_creator` to `generate_mock_response` (`core/brain.py:233, 372`). Live LLM calls (`openai`, `ollama`, `gemini`) and `abuild_system_prompt()` never receive `is_creator`, and when a live provider errors out and falls back to `generate_mock_response` (lines 426, 443, 446, 538, 540, 619, 642, 646, 649), `is_creator` is also omitted.
- **Root Cause:** `is_creator` was added to `Brain.generate_response` and `generate_mock_response` without plumbing it into `abuild_system_prompt()`, `_generate_*`, or `_stream_*` fallback calls.
- **Verification Steps:** Inspected `core/brain.py:187-292, 419-703` and `core/conversation/engine.py:259-371`.
- **Blast Radius:** In live LLM mode, Eve cannot reliably distinguish the Creator from a regular viewer via system prompt authority; on API fallback, Creator desktop commands in `generate_mock_response` (`core/conversation/engine.py:539`) are rejected as non-creator.
- **Recommended Fix:** Pass `is_creator` into `abuild_system_prompt()` (injecting a `[CREATOR VERIFIED]` directive) and forward `is_creator` to every `generate_mock_response` / `_stream_mock` fallback call.

---

#### `[COG-MED-002]` Hardcoded Gemini `thinkingConfig` & Lack of Cross-Provider Failover
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/brain.py:605-609`, `core/brain.py:424-649`
- **Symptom:**
  1. `_build_gemini_payload` unconditionally injects `"thinkingConfig": {"thinkingBudget": 50}` into `generationConfig`. Models that do not support `thinkingConfig` (e.g., `gemini-1.5-flash` or `gemini-pro` if configured) return HTTP 400.
  2. Any non-200 HTTP status or timeout on `openai`, `ollama`, or `gemini` immediately drops to `generate_mock_response` with zero retries, zero exponential backoff, and no fallback chain to secondary configured providers.
- **Root Cause:** Single-shot `session.post` per provider with hardcoded Gemini 2.5/3 preview config and direct mock fallback.
- **Verification Steps:** Inspected `core/brain.py:577-649`.
- **Blast Radius:** Transient 429/503 errors or misconfigured model names silently degrade live stream responses to canned mock text.
- **Recommended Fix:** Gate `thinkingConfig` behind model-capability detection (e.g. `gemini-2.5`/`gemini-3`), add 1 retry on 429/5xx, and support an optional fallback provider order in `settings.json`.

---

#### `[COG-LOW-001]` Naive Rolling Summary Truncation & Unbounded In-Memory `UserMemory`
- **Severity:** Low
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/conversation/memory.py:44-56, 105-118`, `core/conversation/chat_curator.py:197-212`
- **Symptom:**
  1. `ContextMemory._update_rolling_summary` splits by `" | "` and slices `lines[-4:]`, dropping the `"Earlier in stream: "` header after 4 evictions and retaining only 4 × 60-char fragments (240 chars total).
  2. `UserMemory.users` is an unbounded in-memory dict (separate from SQLite `user_profiles`) with no eviction or persistence across restarts.
  3. `ChatCurator.select_next_interaction` (`chat_curator.py:197-212`) classifies **any** 2+ unresponded messages from ≥2 users within 30s as `"group_debate"`, even simple greetings.
- **Root Cause:** Heuristic string slicing and time-window grouping without semantic/topic overlap checks.
- **Verification Steps:** Inspected `core/conversation/memory.py:41-138` and `core/conversation/chat_curator.py:195-213`.
- **Blast Radius:** Loss of conversational thread continuity on long streams and occasional false `"debate"` framing in `MasterPromptBuilder`.
- **Recommended Fix:** Preserve a fixed summary prefix, cap `UserMemory.users` with LRU eviction, and require contrasting markers or shared topic keywords before triggering `group_debate`.

---

### 2.3 Semantic Memory, Embeddings & Second Brain Persistence

#### `[COG-HIGH-004]` Duplicate `EmbeddingEngine` Instantiation in `EpisodicMemoryStore`
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/memory/__init__.py:15-20`, `core/memory/database.py:19-23`
- **Symptom:** `EpisodicMemoryStore.__init__` instantiates `self.embedder = EmbeddingEngine()` on line 16, then instantiates `self.db = MemoryDatabase(db_path=db_path)` on line 17, which instantiates a **second** `self.embedder = EmbeddingEngine(provider=embedding_provider)`.
- **Root Cause:** `MemoryDatabase` does not accept an injected `embedder` instance, and `EpisodicMemoryStore.embedder` is never used by `db`, `retriever`, or `extractor`.
- **Verification Steps:** Inspected `core/memory/__init__.py:15-20` and `core/memory/database.py:19-23`.
- **Blast Radius:** If `local` ML embeddings (`sentence-transformers` / `fastembed`) are active, the model is loaded into RAM/VRAM **twice** at startup, doubling memory footprint and initialization latency. Calling `store.embedder.set_provider(...)` also has no effect on `store.db.embedder`.
- **Recommended Fix:** Pass `embedder: Optional[EmbeddingEngine] = None` into `MemoryDatabase.__init__` and share `self.embedder` from `EpisodicMemoryStore`.

---

#### `[COG-HIGH-005]` Vector Search Blind Beyond 300 Most Recent Memories & Unsafe Dimension Re-encoding
- **Severity:** High
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/memory/database.py:233, 275`, `core/memory/database.py:238-252, 280-294`
- **Symptom:**
  1. `vector_search()` and `avector_search()` only fetch `self.get_recent_memories(limit=300, user=user)`. Any episodic memory older than the 300 most recent rows is completely invisible to dense vector retrieval.
  2. When a dimension mismatch is detected (e.g., 128-d `hash` vs 768-d `gemini`), `vector_search` / `avector_search` synchronously/asynchronously re-encodes each mismatched row one-by-one in a loop (up to 300 sequential REST API calls on a single chat turn) and overwrites the DB blob. Worse, if the active cloud embedder transiently fails and `encode()` falls back to 128-d `_encode_hash` while `q_vec` is 128-d, it can overwrite high-quality 768-d/1536-d DB embeddings with 128-d hash vectors.
- **Root Cause:** Linear scan capped at 300 rows without an embedding-model/dimension column or background batch re-indexing.
- **Verification Steps:** Inspected `core/memory/database.py:214-301`.
- **Blast Radius:** Long-term memories disappear from semantic recall after 300 episodes; provider switches can trigger 300 sequential HTTP calls blocking a single chat response.
- **Recommended Fix:** Add an `embedding_backend` / `embedding_dim` column to `episodic_memories`, cap inline re-encoding to a small budget (e.g. 5 rows per query) or run it in a background task, and never overwrite cloud embeddings with fallback `hash` vectors.

---

#### `[COG-MED-003]` Per-Call `aiohttp.ClientSession` & SQLite Connection Churn
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/memory/embedding.py:329, 390`, `core/memory/database.py:25-30`
- **Symptom:**
  1. `_encode_gemini_async` and `_encode_openai_async` create and close a new `aiohttp.ClientSession` on every single `aencode()` call.
  2. `MemoryDatabase._get_connection()` opens a new `sqlite3.connect` and runs `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;` on every single read/write operation.
  3. `MemoryRetriever.arecall()` (`core/memory/retriever.py:144, 156, 162`) calls synchronous SQLite methods (`get_or_create_user`, `get_recent_memories`, `get_pending_promises`) directly on the asyncio event loop.
- **Root Cause:** Lack of shared `aiohttp.ClientSession` in `EmbeddingEngine` and lack of connection reuse / `asyncio.to_thread` wrapping in `MemoryDatabase` / `MemoryRetriever`.
- **Verification Steps:** Inspected `core/memory/embedding.py:320-401`, `core/memory/database.py:25-30`, and `core/memory/retriever.py:132-168`.
- **Blast Radius:** Unnecessary TLS handshake latency on cloud embeddings and potential event-loop stalls under concurrent chat load.
- **Recommended Fix:** Reuse a lazy `aiohttp.ClientSession` in `EmbeddingEngine` (with `close()`), set `WAL` mode once in `_init_db()`, and run SQLite queries in `asyncio.to_thread` inside `arecall()`.

---

#### `[COG-LOW-002]` Unwired Promise Fulfillment & Append-Only `promises.md`
- **Severity:** Low
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/memory/database.py:608-613`, `core/memory/markdown_sync.py:108-113`
- **Symptom:** `MemoryDatabase.fulfill_promise(promise_id)` is never called anywhere in `core/`, and `MarkdownBrainSync.sync_promise` only appends rows to `data/second_brain/promises.md` without updating existing rows when fulfilled.
- **Root Cause:** No promise-fulfillment detector or API/orchestrator hook exists, and `MarkdownBrainSync` lacks an in-place table update method.
- **Verification Steps:** Grepped/inspected `core/memory/database.py` and `core/memory/markdown_sync.py`.
- **Blast Radius:** Pending promises accumulate indefinitely in `promises_challenges` and are repeatedly injected into `MemoryRecallResult.to_prompt_text()`.
- **Recommended Fix:** Expose promise fulfillment in `EpisodicMemoryStore` / Web UI and rewrite `promises.md` from DB state on status changes.

---

### 2.4 Mood, Personality Evolution & Relationship State Transitions

#### `[COG-MED-004]` `MoodEngine.get_temperature_modifier()` Is Dead Code
- **Severity:** Medium
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/mood/engine.py:231-240`, `core/brain.py:388, 600`
- **Symptom:** `MoodEngine.get_temperature_modifier()` computes a `[-0.15, +0.15]` LLM temperature delta from `excitement`, `curiosity`, and `competitiveness`, **but** `Brain` never calls it and instead uses static `self.settings["llm"]["temperature"]`.
- **Root Cause:** Implemented in `MoodEngine` and tested in `tests/test_mood.py`, but never wired into `Brain._build_openai_payload` or `Brain._build_gemini_payload`.
- **Verification Steps:** Searched all `core/**/*.py` for `get_temperature_modifier`; only definition at `core/mood/engine.py:231` matched.
- **Blast Radius:** Mood changes affect prompt text and VTS expressions, but do not dynamically modulate LLM sampling creativity/focus as designed.
- **Recommended Fix:** Clamp `base_temp + self.mood.get_temperature_modifier()` in `Brain` payload builders.

---

#### `[COG-LOW-003]` Synchronous Disk Writes on Every Chat Turn in `RelationshipEngine` & `PersonalityEvolutionEngine`
- **Severity:** Low
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/relationship/engine.py:176-177`, `core/personality/evolution.py:285`
- **Symptom:** Every single incoming chat message triggers `RelationshipEngine.record_chat_interaction()` → `save()` (full JSON dump of all viewer profiles) + `sync_to_markdown()`, and keyword-matched turns trigger `PersonalityEvolutionEngine.record_experience()` → `save_profile()` + `sync_to_second_brain()` synchronously on the main thread.
- **Root Cause:** Immediate non-batched file I/O without debouncing or atomic temp-file writes (`os.replace`).
- **Verification Steps:** Inspected `core/relationship/engine.py:129-178, 354-363` and `core/personality/evolution.py:113-119, 285`.
- **Blast Radius:** Under high chat velocity, synchronous JSON/Markdown writes block the event loop and risk partial-write corruption on crash.
- **Recommended Fix:** Debounce disk persistence (or offload to `asyncio.to_thread`) and use atomic temp-file + `os.replace` writes (matching `Brain._atomic_write_settings`).

---

## 3. Summary of Prioritized Remediation Plan

1. **P0 (Critical):** Fix `Goal.recalculate_progress()` to ignore `REPLANNED` subtasks (`[COG-CRIT-001]`) and add `MAX_REPLAN_ATTEMPTS` capping with goal-failure transition (`[COG-CRIT-002]`).
2. **P1 (High):** Replace 0ms inline Minecraft inventory polling with cross-tick/event telemetry verification and stop fabricating progress when disconnected (`[COG-HIGH-001]`); add `ContextBudgetManager` for prompt/history token budgeting (`[COG-HIGH-002]`); plumb `is_creator` to live LLM prompts and all fallbacks (`[COG-HIGH-003]`); share a single `EmbeddingEngine` in `EpisodicMemoryStore` (`[COG-HIGH-004]`); remove the 300-row cap and guard against overwriting cloud embeddings with hash fallbacks (`[COG-HIGH-005]`).
3. **P2 (Medium/Low):** Add approval TTL (`[COG-MED-001]`), gate Gemini `thinkingConfig` + add provider failover (`[COG-MED-002]`), reuse `aiohttp.ClientSession` & offload async SQLite calls (`[COG-MED-003]`), wire `MoodEngine.get_temperature_modifier()` (`[COG-MED-004]`), and debounce/atomize JSON+Markdown persistence (`[COG-LOW-003]`).
