# MaybeAI — Next-Generation Innovation Portfolio (`strategy/INNOVATION_PORTFOLIO.md`)

**Author:** Agent 9 (`ng-strat-product`) — Product Vision & Innovation Strategist  
**Grounding Baseline:** [FINAL_POST_IMPLEMENTATION_AUDIT.md](file:///d:/projects/MaybeAI/audit/FINAL_POST_IMPLEMENTATION_AUDIT.md) (`HEAD` `96b7315`) & `audit/00..13`  
**Coverage:** `FUT-001`..`FUT-015` across §9.1–9.10 (every entry includes all 19 mandatory §10 specification fields).

---

## Portfolio Overview Matrix (§9.1–9.10)

| Feature ID | Name | Category (§) | Status | Complexity | Effort (O/M/P, person-days) |
|---|---|---|---|---|---|
| `FUT-001` | Causal Self-Reflection & Experience-Driven Replanner | §9.1 Cognitive Intelligence | `PLANNED` | Medium | `3 / 5 / 8` |
| `FUT-002` | Hybrid SLM/LLM Tiered Router & Token-Exact Budgeting | §9.1 Cognitive Intelligence | `PROPOSED` | Medium-High | `4 / 7 / 11` |
| `FUT-003` | Hierarchical Episodic-to-Semantic Consolidation & Promise Loop | §9.2 Advanced Memory | `PLANNED` | Medium | `4 / 6 / 10` |
| `FUT-004` | Hybrid `sqlite-vec` + FTS5 RRF Scaled Retrieval | §9.2 Advanced Memory | `PROPOSED` | Medium | `3 / 5 / 9` |
| `FUT-005` | Narrative Identity Graph & Cross-Session Persona Coherence | §9.3 Persistent Identity | `PROPOSED` | High | `6 / 9 / 14` |
| `FUT-006` | Sanitized Scene-Change VLM Ring Buffer & Live Commentary | §9.4 Multimodal Perception | `PLANNED` | Medium | `3 / 5 / 8` |
| `FUT-007` | ONNX `silero-vad` + Streaming Partial STT + AEC Duplex | §9.4 Multimodal Perception | `PROPOSED` | Medium-High | `5 / 8 / 12` |
| `FUT-008` | Autonomy L2–L3 Goal Supervisor & Telemetry-Verified Agency | §9.5 Autonomous Companion | `PLANNED` | Medium | `4 / 6 / 9` |
| `FUT-009` | Multi-Platform Audience Graph & Longitudinal Relationship Memory | §9.6 Social Intelligence | `PROPOSED` | Medium-High | `5 / 8 / 13` |
| `FUT-010` | Unified Showrunner & Multi-Modal Stage Sync (Karaoke + Games) | §9.7 Entertainment | `PLANNED` | Medium | `3 / 5 / 8` |
| `FUT-011` | Automated Highlight-to-Short & VOD Chapter Pipeline | §9.8 Content Production | `PLANNED` | Low-Medium | `2 / 4 / 6` |
| `FUT-012` | OS-Enforced Plugin Capability Jail & Typed `PluginSDK` | §9.9 Plugin Ecosystem | `PLANNED` | High | `5 / 8 / 13` |
| `FUT-013` | Multi-Peer `PeerSession` Mesh & `RoomFloorArbitrator` | §9.10 Multi-Agent Ecosystem | `PLANNED` | High | `5 / 8 / 12` |
| `FUT-014` | Unified Creator Studio Shell & Hardened Session Auth | Cross-Cutting UX & Auth | `PLANNED` | Medium | `4 / 6 / 9` |
| `FUT-015` | Per-WS Bounded Outbound Queues & Structured Telemetry Ops | Cross-Cutting Reliability | `PLANNED` | Low-Medium | `2 / 4 / 6` |

---

## Detailed Feature Specifications (§10 Required Fields)

### `FUT-001` — Causal Self-Reflection & Experience-Driven Replanner
- **Feature ID:** `FUT-001`
- **Name:** Causal Self-Reflection & Experience-Driven Replanner
- **Category:** §9.1 Cognitive Intelligence
- **Status:** `PLANNED`
- **Problem Statement:** `Goal.reflection` (`core/planning/replanner.py:35, 139`; `executor.py:614`) is write-only, and `StrategyReplanner` selects `[Plan B]` via static keyword matching (`"creeper"`, `"habis"`, `"kacang"`, `"blunder"`), causing Eve to repeat identical failed strategies across goals (`04_cognitive_memory.md`).
- **Current Capability:** `EXISTING` `Goal.recalculate_progress()` with `REPLANNED`, `MAX_REPLAN_ATTEMPTS = 3`, `approval_timeout_sec = 300.0`, and `Goal.reflection` serialization to `goals.json` / `agenda.md`.
- **Current Limitation:** `GoalDecomposer`, `GoalEngine.autonomous_select_next_activity()`, and `StrategyReplanner` never read past `Goal.reflection` entries or failure causes.
- **Expected Behavior:** On subtask/goal failure or completion, structured causal lessons (`domain`, `precondition_failed`, `avoid_strategy`, `recommended_action`) are stored in SQLite/Markdown and queried before decomposing or replanning future goals.
- **User Value:** Eve visibly learns from mistakes (e.g., crafting armor before nightfall, avoiding repeated chess blunders) instead of looping on identical failed plans.
- **Technical Design:** Add a `LessonRecord` table/query in `MemoryDatabase` + `StrategyReplanner`; inject top-3 relevant domain lessons into `GoalDecomposer` and `StrategyReplanner.replan_subtask()` prompts with a deterministic fallback when LLM is offline.
- **Affected Modules:** `core/planning/replanner.py`, `core/planning/executor.py`, `core/planning/decomposer.py`, `core/planning/engine.py`, `core/memory/database.py`.
- **Dependencies:** None (builds on existing `MAX_REPLAN_ATTEMPTS=3` and `MemoryDatabase`).
- **Complexity:** Medium
- **Effort (O/M/P):** `3 / 5 / 8` person-days
- **Runtime Cost:** Negligible (`<5 ms` SQLite query per goal decomposition; +100–150 prompt tokens only during planning turns).
- **Security Risks:** Low; lessons are generated from internal telemetry/goal states, though any chat-derived failure reason must be sanitized via `Moderator.sanitize_metadata()`.
- **Maintenance Cost:** Low; deterministic unit tests over `StrategyReplanner` and `GoalDecomposer`.
- **Acceptance Criteria:** (1) `Goal.reflection` entries are read on subsequent `GoalDecomposer` calls; (2) repeated identical failure in the same domain selects a different strategy on attempt 2+; (3) 100% of existing `tests/test_planning*` pass.
- **Future Expansion:** Feed causal lesson outcomes into `FUT-005` (Narrative Identity) and `FUT-008` (L3 Showrunner activity selection).

---

### `FUT-002` — Hybrid SLM/LLM Tiered Router & Token-Exact Budgeting
- **Feature ID:** `FUT-002`
- **Name:** Hybrid SLM/LLM Tiered Router & Token-Exact Budgeting
- **Category:** §9.1 Cognitive Intelligence
- **Status:** `PROPOSED`
- **Problem Statement:** `Brain` applies `aiohttp.ClientTimeout(total=1.8)` to entire LLM streams (`AUDIO-MED-001`), truncating healthy replies >1.8s, and `ContextBudgetManager` uses a rough `(len(text) + 3) // 4` heuristic while routing every classification/reflex task to the primary conversational LLM.
- **Current Capability:** `EXISTING` `ContextBudgetManager` (`openai: 1800`, `gemini: 1800`, `ollama: 1600`) and `ProviderCircuitBreaker` (`closed` → `open` → `half_open`) in `core/brain.py`.
- **Current Limitation:** Stream lifetime timeout aborts long replies; heuristic token estimation can under-estimate dense CJK/Indonesian/JSON payloads; small reflex tasks (promise detection, highlight tagging) incur full LLM latency/cost.
- **Expected Behavior:** Separate connect/TTFB timeout (`connect=1.8, sock_read=5.0`) from total stream duration; route lightweight classification/extraction tasks to a fast local/cheap SLM tier (`llm.fast_model` / Ollama) while keeping main dialogue on the primary tier.
- **User Value:** Zero mid-sentence stream cutoffs, lower cloud API spend, and faster background cognitive tasks without stalling live conversation.
- **Technical Design:** Fix `ClientTimeout` in `core/brain.py:832, 983, 1146`; add optional `tiktoken` / model-aware token counter in `ContextBudgetManager`; introduce `TaskTier` (`DIALOGUE`, `REFLEX`, `PLANNING`) in `Brain.generate_response()`.
- **Affected Modules:** `core/brain.py`, `core/config_manager.py`, `config/settings.json`, `core/conversation/engine.py`.
- **Dependencies:** `AUDIO-MED-001` fix.
- **Complexity:** Medium-High
- **Effort (O/M/P):** `4 / 7 / 11` person-days
- **Runtime Cost:** Reduces cloud token spend by routing reflex calls to local SLM or Flash-tier; optional `tiktoken` adds ~10 MB RAM.
- **Security Risks:** Low; preserve `is_creator` and `ContextBudgetManager` priority-drop order (`lore` → `memories` → `history` → `mood_personality` → `creator_safety`).
- **Maintenance Cost:** Low-to-Medium; requires keeping `ProviderCircuitBreaker` per-tier metrics clean.
- **Acceptance Criteria:** (1) Healthy streams >1.8s complete without truncation; (2) TTFB >1.8s still triggers circuit-breaker failover; (3) `REFLEX` tasks route to configured fast tier when enabled.
- **Future Expansion:** Dynamic latency-aware routing based on `MetricsCollector` p95 histograms.

---

### `FUT-003` — Hierarchical Episodic-to-Semantic Consolidation & Promise Loop
- **Feature ID:** `FUT-003`
- **Name:** Hierarchical Episodic-to-Semantic Consolidation & Promise Loop
- **Category:** §9.2 Advanced Memory
- **Status:** `PLANNED`
- **Problem Statement:** `EpisodicMemoryStore` appends flat rows indefinitely (`04_cognitive_memory.md`), `ContextMemory` only keeps 16 turns + a 4-snippet `rolling_summary`, and `MemoryDatabase.fulfill_promise()` / `archive_old_promises()` are never called anywhere at runtime.
- **Current Capability:** `EXISTING` SQLite WAL + FTS5 + `MarkdownBrainSync` (`max_completed_rows=20` in `promises.md`); `INCOMPLETE` `fulfill_promise()` and `archive_old_promises()` methods exist in `core/memory/database.py:677-697`.
- **Current Limitation:** Raw chat episodes accumulate without distillation into durable semantic facts, and viewer promises remain unfulfilled forever in `promises.md`.
- **Expected Behavior:** A periodic background consolidator (idle/end-of-stream) distills daily episodes into deduplicated semantic facts with importance decay, and `MemoryExtractor` / `ConversationEngine` wires `fulfill_promise()` + `archive_old_promises()`.
- **User Value:** Eve remembers key viewer facts and keeps her promises across weeks of streams without prompt bloat or stale memory clutter.
- **Technical Design:** Add `semantic_facts` table + `consolidation_cursor` in `MemoryDatabase`; run an async idle/shutdown consolidation pass (using `FUT-002` `REFLEX` tier or deterministic summarizer) and wire post-turn promise resolution checks.
- **Affected Modules:** `core/memory/__init__.py`, `core/memory/database.py`, `core/memory/markdown_sync.py`, `core/conversation/memory.py`, `core/orchestrator.py`.
- **Dependencies:** `FUT-002` (optional for LLM distillation; deterministic fallback works standalone).
- **Complexity:** Medium
- **Effort (O/M/P):** `4 / 6 / 10` person-days
- **Runtime Cost:** Low; runs asynchronously during idle/shutdown windows, bounded by `_spawn_bg_task`.
- **Security Risks:** Low; ensure untrusted chat episodes are sanitized before semantic fact promotion so prompt injections are never persisted as permanent facts.
- **Maintenance Cost:** Low; SQLite migration + unit tests in `tests/test_memory*.py`.
- **Acceptance Criteria:** (1) `fulfill_promise()` and `archive_old_promises()` execute on promise completion; (2) 100+ raw episodes consolidate into compact semantic facts; (3) `promises.md` stays bounded at `<=20` completed rows.
- **Future Expansion:** Bidirectional Markdown-to-SQLite edits so creators can curate Eve's semantic facts directly in Obsidian.

---

### `FUT-004` — Hybrid `sqlite-vec` + FTS5 RRF Scaled Retrieval
- **Feature ID:** `FUT-004`
- **Name:** Hybrid `sqlite-vec` + FTS5 RRF Scaled Retrieval
- **Category:** §9.2 Advanced Memory
- **Status:** `PROPOSED`
- **Problem Statement:** `MemoryDatabase.vector_search()` (`core/memory/database.py:24, 262-263`) fetches at most `vector_scan_limit=2000` recent rows and computes cosine similarity in a Python loop (`45.32 ms` at 2,000 rows, `12_performance_analysis.md`). Memories older than 2,000 rows are invisible to dense vector search.
- **Current Capability:** `EXISTING` FTS5 `fts_memories` + 2,000-row linear Python vector scan + dimension-mismatch guard (`_can_persist_reencoded_embedding()`).
- **Current Limitation:** Linear `O(N)` scan prevents scaling past 2,000 episodic rows within the `<50 ms` latency budget.
- **Expected Behavior:** Sub-20ms semantic + lexical recall across `50,000+` memories using an embedded ANN index (`sqlite-vec` or pre-filtered FTS5 + `hnswlib`) combined via Reciprocal Rank Fusion (RRF), with automatic fallback to linear scan if the extension is absent.
- **User Value:** Long-running companions retain instant recall of memories from months ago, not just the last 2,000 rows.
- **Technical Design:** Add optional `sqlite-vec` virtual table (`vec_memories`) keyed by `embedding_dim`, fuse FTS5 BM25 rank and ANN cosine rank via RRF (`1/(k + rank)`), and keep Python linear scan as fallback.
- **Affected Modules:** `core/memory/database.py`, `core/memory/retriever.py`, `pyproject.toml`.
- **Dependencies:** `EXP-004` / `EXP-002` benchmark gate (`<=15 ms` p95 at 10,000+ rows).
- **Complexity:** Medium
- **Effort (O/M/P):** `3 / 5 / 9` person-days
- **Runtime Cost:** Minimal (~5–15 MB index RAM for 50,000 384-d vectors); preserves single-file SQLite simplicity.
- **Security Risks:** Low; local SQLite file only.
- **Maintenance Cost:** Low; graceful fallback ensures zero breakage if `sqlite-vec` binary wheel is unavailable on a host.
- **Acceptance Criteria:** (1) Recall@5 improves on memories beyond row 2,000; (2) p95 retrieval latency `<=20 ms` at 10,000 rows; (3) dimension-mismatch guard preserved.
- **Future Expansion:** Partitioned per-user and per-domain vector namespaces.

---

### `FUT-005` — Narrative Identity Graph & Cross-Session Persona Coherence
- **Feature ID:** `FUT-005`
- **Name:** Narrative Identity Graph & Cross-Session Persona Coherence
- **Category:** §9.3 Persistent Identity
- **Status:** `PROPOSED`
- **Problem Statement:** `PersonalityEvolutionEngine` mutates 5 trait floats (`[0.05, 0.98]`) via a static `experience_matrix` (`04_cognitive_memory.md`), and `VTSClient` splits `MouthSmile` vs `MouthForm` (`AUDIO-LOW-001`). Eve lacks a structured narrative self-model linking milestone memories to stable character invariants.
- **Current Capability:** `EXISTING` 5-trait `PersonalityEvolutionEngine` with milestone unlocks, 5-dim `MoodEngine` + `get_temperature_modifier()` (`L3`), and `VTSClient.apply_mood_rig()`.
- **Current Limitation:** Scalar floats cannot express *why* Eve has a preference, running gag, or boundary, and long-horizon emotional memory weighting is absent.
- **Expected Behavior:** Represent Eve's evolving identity as core immutable Creator-defined invariants + milestone-anchored narrative beliefs/preferences (`IdentityNode`s) stored in SQLite/Markdown, coupled with unified `MouthForm`/`MouthSmile` VTS expression mapping.
- **User Value:** Eve feels like a consistent, growing individual across months of streams rather than a stateless prompt with 5 drifting sliders.
- **Technical Design:** Add `IdentityAnchor` schema in `core/personality/` linking `PersonalityEvolutionEngine` milestones to `FUT-003` semantic facts; inject top-relevant active identity anchors into `ContextBudgetManager`; unify `VTSClient` `MouthForm`/`MouthSmile` parameters.
- **Affected Modules:** `core/personality/`, `core/mood/engine.py`, `core/vts_client.py`, `core/conversation/prompts.py`.
- **Dependencies:** `FUT-003` (Hierarchical Memory Consolidation).
- **Complexity:** High
- **Effort (O/M/P):** `6 / 9 / 14` person-days
- **Runtime Cost:** Negligible (~200 tokens in `ContextBudgetManager` `mood_personality` tier).
- **Security Risks:** Medium; immutable Creator invariants must be enforced so hostile chat cannot drift Eve's core persona or safety boundaries.
- **Maintenance Cost:** Medium; requires careful prompt-regression testing.
- **Acceptance Criteria:** (1) Core invariants cannot be mutated by viewer interactions; (2) milestone events create inspectable narrative anchors; (3) `VTSClient` uses consistent mouth expression parameters.
- **Future Expansion:** Exportable/portable `.eve-persona` identity snapshots.

---

### `FUT-006` — Sanitized Scene-Change VLM Ring Buffer & Live Commentary
- **Feature ID:** `FUT-006`
- **Name:** Sanitized Scene-Change VLM Ring Buffer & Live Commentary
- **Category:** §9.4 Multimodal Perception
- **Status:** `PLANNED`
- **Problem Statement:** `core/conversation/engine.py:316-325` interpolates `obs.summary` raw into the system prompt without sanitization (`SEC-GAP-003`, indirect OCR/VLM prompt injection), and `VisionEngine` relies on color heuristics while VLM output does not drive live commentary (`06_game_vision_entertainment.md`).
- **Current Capability:** `EXISTING` `VisualAnalyzer` `scene_label` fix and `MultimodalVisionModel` cooldown/structured output.
- **Current Limitation:** On-screen text in games/browsers can inject instructions into Eve's system prompt; VLM only patches `obs.summary` post-hoc.
- **Expected Behavior:** Sanitize all `obs.summary` and `obs.eve_commentary` strings via `Moderator.sanitize_metadata()` + untrusted-data delimiters; trigger VLM captioning only on scene-change pixel-diff spikes + cooldown, caching a 3-frame ring buffer for live `generate_commentary()`.
- **User Value:** Eve reacts naturally to on-screen events (bosses, errors, raids) without burning VLM quota or falling prey to screen-text prompt injection.
- **Technical Design:** Wrap `obs.summary` in `[UNTRUSTED_SCREEN_OCR]` delimiters after `Moderator.sanitize_metadata()`; add scene-delta threshold + 3-frame `deque(maxlen=3)` ring buffer in `VisionEngine` feeding `ContextBudgetManager` when vision is active.
- **Affected Modules:** `core/conversation/engine.py`, `core/vision/engine.py`, `core/vision/vlm.py`, `core/moderator.py`.
- **Dependencies:** None (remediates `SEC-GAP-003`).
- **Complexity:** Medium
- **Effort (O/M/P):** `3 / 5 / 8` person-days
- **Runtime Cost:** Bounded by VLM cooldown (`>=15s`–`30s`) and scene-change gate; zero cost when screen is static.
- **Security Risks:** **Mitigates `SEC-GAP-003`** (indirect VLM/OCR prompt injection).
- **Maintenance Cost:** Low.
- **Acceptance Criteria:** (1) Adversarial text in `obs.summary` is stripped of control/delimiter tokens and isolated in untrusted delimiters; (2) VLM calls trigger only on scene-change + cooldown; (3) `generate_commentary()` uses live VLM ring buffer.
- **Future Expansion:** Optional local Qwen-VL/Ollama vision backend when VRAM budget permits.

---

### `FUT-007` — ONNX `silero-vad` + Streaming Partial STT + AEC Duplex
- **Feature ID:** `FUT-007`
- **Name:** ONNX `silero-vad` + Streaming Partial STT + AEC Duplex
- **Category:** §9.4 Multimodal Perception
- **Status:** `PROPOSED`
- **Problem Statement:** `EnergyVAD` (`core/stt.py`) cannot distinguish human speech from speaker bleed or music, `StreamingSTTSession.feed_pcm_chunk()` never emits partial transcripts (UI always shows `"Listening..."`, `03_realtime_audio.md`), and `tts.volume` is unwired.
- **Current Capability:** `EXISTING` 16 kHz binary `AudioWorklet` PCM, bounded `voice_queue(maxsize=64)` + `_voice_worker`, `EnergyVAD` barge-in; `EXPERIMENTAL` `faster-whisper` / `kokoro-onnx` (absent in `.venv`).
- **Current Limitation:** False barge-ins from speaker bleed; zero live partial transcript feedback during speech; `TTSEngine.speak()` still swallows `CancelledError` (`AUDIO-MED-002`).
- **Expected Behavior:** Pluggable `silero-vad` (ONNX, <1 ms/frame) behind VAD interface, browser `echoCancellation: true` audio constraints, real streaming partial transcripts from `StreamingSTTSession`, `TTSEngine.speak()` `CancelledError` propagation, and wired `tts.volume`.
- **User Value:** Crisp, echo-resistant voice interruption and real-time live captions while the creator speaks.
- **Technical Design:** Fix `AUDIO-MED-002` in `core/tts.py`; add optional `SileroVAD` adapter in `core/stt.py` with `EnergyVAD` fallback; emit periodic partial decode events from `StreamingSTTSession` to `/ws`.
- **Affected Modules:** `core/stt.py`, `core/tts.py`, `core/orchestrator.py`, `web/app.js`, `web/deck.js`.
- **Dependencies:** `AUDIO-MED-002` fix; optional `onnxruntime` / `faster-whisper` extras.
- **Complexity:** Medium-High
- **Effort (O/M/P):** `5 / 8 / 12` person-days
- **Runtime Cost:** ~2 MB ONNX model + `<5%` single-core CPU for `silero-vad`; optional local STT uses ~1–2 GB VRAM if enabled.
- **Security Risks:** Low; local audio processing only.
- **Maintenance Cost:** Low-to-Medium; must maintain `EnergyVAD` fallback when `onnxruntime` is not installed.
- **Acceptance Criteria:** (1) `TTSEngine.speak()` re-raises `CancelledError`; (2) `StreamingSTTSession` emits real partial text; (3) `SileroVAD` reduces false speaker-bleed triggers vs `EnergyVAD` in test fixtures.
- **Future Expansion:** Multi-speaker diarization to distinguish Creator voice from room guests.

---

### `FUT-008` — Autonomy L2–L3 Goal Supervisor & Telemetry-Verified Agency
- **Feature ID:** `FUT-008`
- **Name:** Autonomy L2–L3 Goal Supervisor & Telemetry-Verified Agency
- **Category:** §9.5 Autonomous Companion
- **Status:** `PLANNED`
- **Problem Statement:** `minecraft/bot.js` defines `startAutonomyLoop()` (`L229-288`) but never invokes it, `AutonomousMissionExecutor._execute_chess` still returns `{"simulated": True}` when `self.chess is None` (`04_cognitive_memory.md`), and `ChessController._delayed_bot_move` is not cancelled on `start_game()`/`resign_game()`.
- **Current Capability:** `EXISTING` `AutonomousMissionExecutor` (`MAX_REPLAN_ATTEMPTS=3`, `approval_timeout_sec=300s`), `PermissionManager` risk tiers (`HIGH`/`MEDIUM`), Minecraft telemetry polling.
- **Current Limitation:** Idle autonomy in Minecraft is dead code; disconnected Chess fabricates simulated progress; no unified L2→L3 policy budget governing autonomous activity switching.
- **Expected Behavior:** Wire `startAutonomyLoop()` safely in `bot.js` (cleared on mode switch), remove `simulated: True` fabrication in `_execute_chess`, cancel pending `_delayed_bot_move` on game reset, and enforce `PermissionManager` L0–L3 autonomy budgets.
- **User Value:** Honest, grounded autonomous behavior where Eve never claims fake wins or gets stuck in stale game/bot loops.
- **Technical Design:** Invoke `startAutonomyLoop()` on `casual` mode entry in `bot.js`; return explicit `blocked_disconnected` status in `_execute_chess` when `self.chess is None`; track `_delayed_bot_move` task handle in `ChessController`; add `autonomy_level` (`L0`–`L3`) policy check in `GoalEngine`.
- **Affected Modules:** `minecraft/bot.js`, `core/planning/executor.py`, `core/planning/engine.py`, `core/chess/controller.py`, `core/desktop/permission_manager.py`.
- **Dependencies:** `FUT-001` (Causal Self-Reflection).
- **Complexity:** Medium
- **Effort (O/M/P):** `4 / 6 / 9` person-days
- **Runtime Cost:** Negligible; idle loops are event/timer-gated.
- **Security Risks:** Medium; `PermissionManager` must strictly gate `HIGH` risk desktop/OBS actions (`start_stream`, `stop_stream`, `change_stream_key`) behind Creator confirmation at L0–L3.
- **Maintenance Cost:** Low.
- **Acceptance Criteria:** (1) Zero `simulated: True` progress when `chess` is disconnected; (2) `startAutonomyLoop()` runs in `casual` mode and cleans up on `end`/`kicked`/mode switch; (3) `PermissionManager` blocks unapproved `HIGH` actions.
- **Future Expansion:** L4 24/7 companion scheduling with sleep/wake circadian cycles.

---

### `FUT-009` — Multi-Platform Audience Graph & Longitudinal Relationship Memory
- **Feature ID:** `FUT-009`
- **Name:** Multi-Platform Audience Graph & Longitudinal Relationship Memory
- **Category:** §9.6 Social Intelligence
- **Status:** `PROPOSED`
- **Problem Statement:** `RelationshipEngine.record_chat_interaction()` nudges 5 affinity floats via keyword heuristics (`04_cognitive_memory.md`), and chatters across Twitch, YouTube Live, Discord, and TikTok are tracked as isolated per-platform handles with no cohort or topic awareness.
- **Current Capability:** `EXISTING` 5-tier `RelationshipEngine` dossiers & inside jokes, `ChatCurator` (`is_creator` priority, `max_buffer_size=50`), `Moderator` injection & `strict_mode` filtering.
- **Current Limitation:** No longitudinal social graph connecting recurring viewers, shared stream moments, or cross-platform aliases; keyword heuristics are easily gamed by spam.
- **Expected Behavior:** Build an opt-in Audience Graph in SQLite linking viewer profiles, verified cross-platform aliases, shared inside jokes, and cohort topics, with rate-limited affinity updates resistant to chat-spam gaming.
- **User Value:** Eve recognizes regulars across platforms, recalls shared moments organically, and paces chat engagement naturally during raids or busy streams.
- **Technical Design:** Extend `RelationshipEngine` with `viewer_links` and `shared_moments` tables in `MemoryDatabase`; add spam-damped affinity scoring and cohort topic clustering in `ChatCurator`.
- **Affected Modules:** `core/relationship/`, `core/conversation/chat_curator.py`, `core/memory/database.py`.
- **Dependencies:** `FUT-003` (Hierarchical Memory Consolidation).
- **Complexity:** Medium-High
- **Effort (O/M/P):** `5 / 8 / 13` person-days
- **Runtime Cost:** Low (`<5 ms` SQLite lookup per curated message).
- **Security Risks:** Medium; viewer-supplied aliases must require Creator verification or OAuth platform IDs (never self-asserted chat claims to prevent impersonation of `is_creator` or VIPs).
- **Maintenance Cost:** Medium.
- **Acceptance Criteria:** (1) Self-asserted chat text cannot link to Creator/VIP profiles; (2) affinity updates are rate-limited against spam floods; (3) `ChatCurator` surfaces relevant viewer context within `ContextBudgetManager` limits.
- **Future Expansion:** Audience sentiment & engagement heatmaps in Studio UI.

---

### `FUT-010` — Unified Showrunner & Multi-Modal Stage Sync (Karaoke + Games)
- **Feature ID:** `FUT-010`
- **Name:** Unified Showrunner & Multi-Modal Stage Sync (Karaoke + Games)
- **Category:** §9.7 Entertainment
- **Status:** `PLANNED`
- **Problem Statement:** `Orchestrator.reload_settings()` omits `Singer` neural provider/fallback config (`AUDIO-MED-003`), `OBSWebSocketClient` and `MinecraftController` lack background auto-reconnect loops (`06_game_vision_entertainment.md`), and `YouTubeKaraokeProcessor` lacks `--max-filesize` and concurrent job caps (`SEC-GAP-005`).
- **Current Capability:** `EXISTING` `YouTubeKaraokeProcessor` (SSRF/VTT/cache/RVC), clock-locked `Singer` (`vocal_track`), `OBSWebSocketClient` error reset, `StoryEngine` showrunner hooks, `MinecraftController`, `ChessEngine`.
- **Current Limitation:** Runtime `/settings` TTS changes do not reach `Singer`; transient OBS/MC drops require manual reconnect; unbounded YouTube download sizes risk disk exhaustion.
- **Expected Behavior:** Forward all TTS provider/fallback fields to `Singer.update_config()`, add exponential-backoff auto-reconnect for enabled OBS/Minecraft bridges + `get_replay_buffer_status()` sync, and enforce `--max-filesize` + concurrent job cap (`<=2`) in `YouTubeKaraokeProcessor`.
- **User Value:** Seamless live shows where TTS voice changes apply to karaoke immediately, OBS/MC recover from hiccups automatically, and YouTube requests cannot fill disk.
- **Technical Design:** Update `Orchestrator.__init__` & `reload_settings()`; add `_auto_reconnect_loop` (matching `VTSClient`) to `OBSWebSocketClient` & `MinecraftController`; pass `--max-filesize 250M` and `asyncio.Semaphore(2)` in `YouTubeKaraokeProcessor`.
- **Affected Modules:** `core/orchestrator.py`, `core/singer.py`, `core/youtube_karaoke.py`, `core/desktop/obs_client.py`, `core/minecraft/controller.py`.
- **Dependencies:** None (resolves `AUDIO-MED-003` and `SEC-GAP-005`).
- **Complexity:** Medium
- **Effort (O/M/P):** `3 / 5 / 8` person-days
- **Runtime Cost:** Negligible; semaphore bounds concurrent `yt-dlp`/`demucs` CPU/disk spikes.
- **Security Risks:** **Mitigates `SEC-GAP-005`** (disk/CPU DoS via oversized YouTube downloads).
- **Maintenance Cost:** Low.
- **Acceptance Criteria:** (1) Changing TTS provider in `/settings` updates `Singer` immediately; (2) `OBSWebSocketClient` syncs `get_replay_buffer_status()` and reconnects on drop; (3) `YouTubeKaraokeProcessor` enforces `--max-filesize` and concurrency cap.
- **Future Expansion:** Audience-voted interactive setlists and multi-game tournament brackets.

---

### `FUT-011` — Automated Highlight-to-Short & VOD Chapter Pipeline
- **Feature ID:** `FUT-011`
- **Name:** Automated Highlight-to-Short & VOD Chapter Pipeline
- **Category:** §9.8 Content Production
- **Status:** `PLANNED`
- **Problem Statement:** In `HighlightDetector._record_marker()`, async `on_save_replay` callbacks mutate `marker.replay_saved` *after* `HIGHLIGHT_MARKED` is published (`06_game_vision_entertainment.md`), and `ClipPipeline` + `VODSummarizer` lack `.get_status()` (guarded by `hasattr` in `run.py:336-337`).
- **Current Capability:** `EXISTING` `HighlightDetector`, `ClipPipeline` (`is_relative_to()` confinement + filtergraph escaping), and `VODSummarizer` (`YYYY-MM-DD.md` export).
- **Current Limitation:** Subscribers to `HIGHLIGHT_MARKED` see `replay_saved: False` even when OBS saves the replay; Studio/diagnostics cannot inspect `ClipPipeline` or `VODSummarizer` queue/status; no automatic post-stream batching of 9:16 shorts + VOD chapters.
- **Expected Behavior:** Emit a follow-up `HIGHLIGHT_REPLAY_SAVED` event (or await bounded replay save) so UI/VOD state is consistent, implement `.get_status()` on `ClipPipeline` & `VODSummarizer`, and add an optional post-stream pipeline that queues top-N highlights for 9:16 captioned clipping + chaptered VOD markdown.
- **User Value:** Streamers finish a broadcast with ready-to-upload vertical Shorts and timestamped YouTube VOD chapters automatically prepared.
- **Technical Design:** Add `get_status()` to `core/highlights/clipper.py` and `VODSummarizer`; emit `HIGHLIGHT_REPLAY_SAVED` on async replay completion; add a bounded `asyncio.Queue` batch clip worker respecting `ClipPipeline` path confinement.
- **Affected Modules:** `core/highlights/detector.py`, `core/highlights/clipper.py`, `core/highlights/vod_summarizer.py`, `run.py`.
- **Dependencies:** `ffmpeg` on host for live clip rendering (graceful error otherwise).
- **Complexity:** Low-Medium
- **Effort (O/M/P):** `2 / 4 / 6` person-days
- **Runtime Cost:** Bounded CPU during post-stream `ffmpeg` render; zero impact during live conversation.
- **Security Risks:** Low; strictly preserves `ClipPipeline._resolve_confined_path()` (`data/clips`) and `_escape_ffmpeg_filter_path()`.
- **Maintenance Cost:** Low.
- **Acceptance Criteria:** (1) `ClipPipeline.get_status()` and `VODSummarizer.get_status()` return structured dicts; (2) async replay completion updates UI/VOD state; (3) path confinement tests remain 100% passing.
- **Future Expansion:** Auto-generated thumbnail frame selection via `VisualAnalyzer`.

---

### `FUT-012` — OS-Enforced Plugin Capability Jail & Typed `PluginSDK`
- **Feature ID:** `FUT-012`
- **Name:** OS-Enforced Plugin Capability Jail & Typed `PluginSDK`
- **Category:** §9.9 Plugin Ecosystem
- **Status:** `PLANNED`
- **Problem Statement:** On Windows, `sandbox_worker.py` relies on Python-level monkeypatches (`open`, `os.open`, 4 `socket` methods) that can be bypassed via `ctypes`, `subprocess.Popen`, or UDP `sendto` (`SEC-GAP-002`), and `sandbox_mode="inprocess"` remains accepted for external plugins.
- **Current Capability:** `EXISTING` AST manifest extraction, default-deny `granted_permissions`, stripped `_build_sandbox_env()`, Linux `bwrap` + `rlimit`, Windows Job Object (`512MB`, `ActiveProcessLimit=2`).
- **Current Limitation:** Malicious community plugins on Windows can read `.env`/`config/settings.json` or exfiltrate data; `/settings` lacks a dedicated per-plugin capability approval UI.
- **Expected Behavior:** Disallow `inprocess` for external plugins; enforce Windows Restricted Token / AppContainer (or deny `ctypes`/child-process creation at OS token level) + dedicated scratch working directory outside `REPO_ROOT`; expose a typed `PluginSDK` v2 and `/settings` capability approval panel.
- **User Value:** Creators can safely install third-party plugins on Windows and Linux without risking API key theft or Second Brain leaks.
- **Technical Design:** Update `core/plugins/registry.py` & `sandbox_worker.py` to enforce `RestrictedProcess` / `AppContainer` ACLs on Windows and mandatory `bwrap`/seccomp on Linux; reject `inprocess` unless `is_builtin=True`; add `/api/plugins/permissions` UI in `web/settings.js`.
- **Affected Modules:** `core/plugins/registry.py`, `core/plugins/sandbox_worker.py`, `core/plugins/sdk.py`, `run.py`, `web/settings.js`.
- **Dependencies:** None (remediates `SEC-GAP-002`).
- **Complexity:** High
- **Effort (O/M/P):** `5 / 8 / 13` person-days
- **Runtime Cost:** Negligible (~15–25 MB per isolated plugin subprocess, already bounded at 512 MB).
- **Security Risks:** **Mitigates `SEC-GAP-002`** (Windows sandbox escape). Must be tested on both Windows and Linux CI.
- **Maintenance Cost:** Medium (OS-specific process isolation code).
- **Acceptance Criteria:** (1) `ctypes`/`subprocess` read of `.env` fails inside Windows plugin sandbox test; (2) external `inprocess` mode is rejected; (3) Creator can grant/revoke plugin permissions from `/settings`.
- **Future Expansion:** Signed community plugin registry with automated manifest verification.

---

### `FUT-013` — Multi-Peer `PeerSession` Mesh & `RoomFloorArbitrator`
- **Feature ID:** `FUT-013`
- **Name:** Multi-Peer `PeerSession` Mesh & `RoomFloorArbitrator`
- **Category:** §9.10 Multi-Agent Ecosystem
- **Status:** `PLANNED`
- **Problem Statement:** `CollabManager.disconnect_peer()` leaves `floor_state="listening"` (`CHAOS-B-001`), `Orchestrator._on_collab_hello` is dead code (`05_collab_protocol.md`), outbound `duet_sync`/`emote_sync`/`game_move` are never emitted by subsystems, and `CollabManager` uses scalar 2-peer state (`_ws_client`, `connected_peer`, global `floor_state`).
- **Current Capability:** `EXISTING` HMAC-SHA256 `CollabEnvelope`, `±60s` skew, 1024-nonce LRU, `NaN` rejection, SSRF `validate_outbound_url`, `Sec-WebSocket-Protocol` / Bearer auth, Studio Collab UI.
- **Current Limitation:** Abrupt peer disconnect wedges floor state; 3+ agent shows cause split-brain sends and reply collisions; `sender_id` in nonce cache is self-reported rather than connection-bound.
- **Expected Behavior:** Immediately reset `floor_state="idle"` and clear `active_peer` in `disconnect_peer()`, wire `on_hello` and outbound subsystem emitters, and refactor `CollabManager` to `peers: Dict[str, PeerSession]` + `RoomFloorArbitrator` with `target_id` routing and connection-bound `sender_id`.
- **User Value:** Reliable 2-peer and N-agent AI VTuber shows with synchronized duets, emotes, and chess matches that never wedge on disconnect.
- **Technical Design:** Fix `CHAOS-B-001` and `on_hello` first; introduce `PeerSession` dataclass and `RoomFloorArbitrator` in `core/collab/manager.py`; add optional `target_id`/`room_id` to `CollabEnvelope`; wire `Singer`, `VTSClient`, and `ChessController` outbound hooks; bind `env.sender_id` to authenticated session ID.
- **Affected Modules:** `core/collab/manager.py`, `core/collab/protocol.py`, `core/orchestrator.py`, `core/singer.py`, `core/vts_client.py`, `core/chess/controller.py`, `run.py`.
- **Dependencies:** `CHAOS-B-001` fix.
- **Complexity:** High
- **Effort (O/M/P):** `5 / 8 / 12` person-days
- **Runtime Cost:** Negligible (`<1 ms` HMAC + routing per collab frame).
- **Security Risks:** Closes `sender_id` spoofing in multi-peer rooms and enforces `validate_outbound_url` + `allow_private_peers` config visibility in `/settings`.
- **Maintenance Cost:** Medium.
- **Acceptance Criteria:** (1) `disconnect_peer()` resets `floor_state="idle"`; (2) 3-peer simulated room routes `turn_yield` and `duet_sync` without reply collisions; (3) `on_hello` and outbound `duet_sync`/`emote_sync`/`game_move` are verified by unit tests.
- **Future Expansion:** Cross-node distributed multi-agent stage orchestration with shared game rooms.

---

### `FUT-014` — Unified Creator Studio Shell & Hardened Session Auth
- **Feature ID:** `FUT-014`
- **Name:** Unified Creator Studio Shell & Hardened Session Auth
- **Category:** Cross-Cutting UX & Auth (§9.1–9.10 Surface)
- **Status:** `PLANNED`
- **Problem Statement:** `web/shared-client.js` still appends `?token=` to WS URLs and stores tokens in `localStorage` (`SEC-GAP-001`), `web/app.js` has 5 unguarded `ws.readyState` calls (`FE-REL-001`) and incomplete `onopen` re-sync, navigation to `/settings` tears down the active mic/WS session, and `web/` has 0 `:focus-visible` or `prefers-reduced-motion` rules (`08_frontend_ux.md`).
- **Current Capability:** `EXISTING` `MaybeAIClient`, `/settings` XSS neutralization + `401/403` UI, `/overlay` re-sync, offline `web/vendor/` Three-VRM.
- **Current Limitation:** Tokens leak into WS URLs/localStorage; reconnect windows throw `TypeError` on `ws.readyState`; UI mixes English and Indonesian copy; accessibility is incomplete.
- **Expected Behavior:** Switch `CreatorAuth` / `ReconnectingWebSocket` to `Sec-WebSocket-Protocol: maybeai.token.<token>` + `sessionStorage` (removing `?token=`), guard all `ws.readyState` accesses, complete `app.js` `onopen` re-sync, embed `/settings` drawer or unified shell navigation without dropping audio, and add `:focus-visible` + `prefers-reduced-motion` + consistent localization.
- **User Value:** Zero token exposure in URLs/logs, crash-free reconnects, seamless settings edits mid-stream, and accessible keyboard navigation.
- **Technical Design:** Update `web/shared-client.js` + `run.py` (deprecate `?token=`); patch `web/app.js`, `web/style.css`, `web/settings.css`, `web/deck.css`; extract shared 2D/VRM/AudioQueue helpers from `app.js` (5,896 lines) and `overlay.js` (731 lines).
- **Affected Modules:** `web/shared-client.js`, `web/app.js`, `web/overlay.js`, `web/deck.js`, `web/settings.js`, `web/style.css`, `run.py`.
- **Dependencies:** None (remediates `SEC-GAP-001` & `FE-REL-001`).
- **Complexity:** Medium
- **Effort (O/M/P):** `4 / 6 / 9` person-days
- **Runtime Cost:** Zero runtime overhead; reduces duplicated JS bundle size.
- **Security Risks:** **Mitigates `SEC-GAP-001`** (WS token leakage & `localStorage` XSS exposure).
- **Maintenance Cost:** Reduces ongoing frontend maintenance by deduplicating `app.js`/`overlay.js` avatar & audio code.
- **Acceptance Criteria:** (1) Zero `?token=` in WS URLs and zero `localStorage` token writes; (2) `ws = null` during reconnect throws 0 `TypeError`s; (3) `node --check` and Playwright E2E pass.
- **Future Expansion:** Optional i18n language pack switcher (`en` / `id` / `ja`).

---

### `FUT-015` — Per-WS Bounded Outbound Queues & Structured Telemetry Ops
- **Feature ID:** `FUT-015`
- **Name:** Per-WS Bounded Outbound Queues & Structured Telemetry Ops
- **Category:** Cross-Cutting Reliability & Observability (§9.1–9.10 Spine)
- **Status:** `PLANNED`
- **Problem Statement:** `Orchestrator._dispatch_to_web_listeners` lacks per-WS outbound `asyncio.Queue(maxsize=64)` (`INFRA-MED-001-RES`), causing 2.0s HoL stalls on stalled clients; 4 config keys (`response_timeout_sec`, `max_concurrent_tasks`, `websocket_ping_interval_sec`, `audio_buffer_size_kb`) are dead (`INFRA-MED-002`); core uses `print()` without `RotatingFileHandler`; and `aiohttp` `ResourceWarning`s appear in teardown (`OPS-001`).
- **Current Capability:** `EXISTING` `EventBus` concurrent dispatch (`0.28ms` for 50 msgs), `/api/health`, `/api/metrics` (`MetricsCollector`), `/api/eventbus/stats`.
- **Current Limitation:** Blocks **`GO` for Unattended 24/7** (`13_production_readiness.md`).
- **Expected Behavior:** Give every WS connection a bounded `asyncio.Queue(maxsize=64)` + dedicated sender task (dropping oldest `avatar_state` on full), wire the 4 dead config keys, replace `print()` with structured `logging` + `RotatingFileHandler`, close all `aiohttp` sessions cleanly, and add deep SQLite/EventBus probes to `/api/health`.
- **User Value:** Unattended 24/7 stability with zero FD leaks, zero log disk exhaustion, and instant stalled-client isolation.
- **Technical Design:** Add `WebSocketOutboundSession` (`asyncio.Queue(maxsize=64)` + `_sender_task`) in `run.py` / `core/orchestrator.py`; wire `core/logging_config.py` (`RotatingFileHandler`); audit `aiohttp.ClientSession` lifecycles in `Brain`, `TTS`, `RVC`, and tests.
- **Affected Modules:** `run.py`, `core/orchestrator.py`, `core/brain.py`, `core/tts_providers.py`, `core/metrics.py`, `tests/`.
- **Dependencies:** None (resolves `INFRA-MED-001-RES`, `INFRA-MED-002`, `OPS-001`).
- **Complexity:** Low-Medium
- **Effort (O/M/P):** `2 / 4 / 6` person-days
- **Runtime Cost:** `<1 MB` RAM for bounded WS queues and log rotation buffers.
- **Security Risks:** Low; structured logs must continue redacting secrets.
- **Maintenance Cost:** Low; eliminates test `ResourceWarning` noise.
- **Acceptance Criteria:** (1) `python -W default -m unittest` produces 0 `ResourceWarning`s; (2) stalled WS client causes 0ms delay to healthy clients; (3) 12h soak test passes with bounded disk logs and flat RSS.
- **Future Expansion:** Optional Prometheus `/metrics` text exposition endpoint.
