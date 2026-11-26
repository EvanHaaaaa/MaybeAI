# MaybeAI — Structured R&D Program (`strategy/RESEARCH_PLAN.md`)

**Owner:** AGENT 10 — Future AI & Research Architect (`strat-ai`)  
**Grounding Baseline:** `audit/FINAL_AUDIT_REPORT.md`, `audit/02_realtime_audio.md`, `audit/03_cognitive_architecture.md`, `audit/05_game_engines.md`, `audit/11_performance_analysis.md`

---

## 1. R&D Philosophy & Sequencing Rules

MaybeAI's audit (`audit/FINAL_AUDIT_REPORT.md`) established that **production hardening (`[SEC-CRIT-001/002]`, `[PERF-HIGH-001]`, `[AUDIO-CRIT-001/002]`, `[COG-CRIT-001/002]`, `[GAME-CRIT-001/002]`) must precede or gate new AI feature expansion**. Consequently, this R&D program is structured around three high-leverage, de-risked experiments (`EXP-001`–`EXP-003`) that directly resolve verified `CRITICAL`/`HIGH` architectural gaps while validating **TRIAL** technologies before they become production defaults.

No **TRIAL** or **ASSESS** technology may ship into `core/` default paths without passing its explicit **Go/No-Go Gate** below.

---

## 2. R&D Portfolio Overview

| Experiment | Title | Target Audit Findings | Technologies Evaluated | Primary Owner(s) |
|---|---|---|---|---|
| **EXP-001** | Real-Time Duplex Voice & True Audio-Envelope Lip-Sync | `[AUDIO-CRIT-001/002]`, `[AUDIO-HIGH-001/002/003/004]`, `[AUDIO-LOW-001]`, `[PERF-MED-002]` | Silero-VAD (ONNX), non-blocking `faster-whisper`, sentence-chunked `kokoro-onnx` vs `Edge-TTS`, server PCM/RMS envelope + browser arbitration | Audio & Frontend |
| **EXP-002** | Hybrid Cognitive Memory & Bounded Prompt Budgeting | `[COG-HIGH-002/003/004/005]`, `[COG-MED-002/003/004]` | `sqlite-vec` / `hnswlib` vs 300-row scan, BM25 (FTS5) + vector RRF, `FastEmbed` vs Gemini/OpenAI/Hash, `ContextBudgetManager` | Cognition & Memory |
| **EXP-003** | Closed-Loop Autonomous Agency & Verified World State | `[COG-CRIT-001/002]`, `[COG-HIGH-001]`, `[COG-MED-001]`, `[GAME-CRIT-002]` | Bounded HTN/FSM replanning (`MAX_REPLAN_ATTEMPTS`), Mineflayer cross-tick telemetry ACK, Node.js bridge supervisor | Agency & Games |

---

## 3. Hypotheses, Success Metrics & Go/No-Go Gates

### Track 1: Voice Duplex, STT & Lip-Sync (`EXP-001`)
- **Core Hypothesis:** Replacing `EnergyVAD` + blocking `transcribe_wav_bytes()` + disk-roundtrip `Edge-TTS` + synthetic 80ms square-wave lip-sync with `Silero-VAD` + async STT worker + in-memory `Kokoro-82M`/`Edge-TTS` + server-side PCM/RMS envelope extraction will cut end-to-end voice TTFA below `700 ms` (local) / `1100 ms` (cloud), eliminate `/ws` receive-loop stalls, and achieve `0` post-barge-in side effects.
- **Key Metrics:**
  - `barge_in` cancellation latency (`<= 50 ms` to audio stop & `mouth=0.0`; `0` post-cancel `ai_response`/Discord/MC emissions).
  - `/ws` frame-ack p99 during STT transcription (`< 15 ms` vs current `150–3000 ms` stall).
  - VAD False-Trigger Rate (FTR) under BGM/keyboard noise (`< 2%` vs `EnergyVAD` baseline).
  - Lip-sync RMS correlation `r >= 0.85` against ground-truth audio waveform; `0` jitter collisions in `output_mode="both"`.
- **Go/No-Go Gate:** `Silero-VAD` + `faster-whisper` + `kokoro-onnx` must stay within Profile B resource budget (`<= 2.5 GB` VRAM, `< 15%` sustained CPU on 8-core) and pass Chaos Scenario B (100 consecutive barge-in interrupts with `0` leaked temp files or post-cancel broadcasts).

### Track 2: Hybrid Memory & Token Budgeting (`EXP-002`)
- **Core Hypothesis:** Replacing the 300-row linear vector scan with `sqlite-vec` (or `hnswlib` fallback) + FTS5 BM25 Reciprocal Rank Fusion (RRF), enforcing `embedding_backend`/`embedding_dim` schema versioning, and introducing `ContextBudgetManager` will enable `10,000+`-row recall in `< 15 ms`, reduce prompt token usage by `>= 30%`, and eliminate silent 128-d hash overwrites.
- **Key Metrics:**
  - `Recall@5` and `MRR@5` on a curated 500-episode / 100-query VTuber memory benchmark (`>= +15%` over 300-row baseline when target facts are at index `> 300`).
  - `arecall()` p95 latency at `10,000` rows (`<= 15 ms`, `0` event-loop stalls `> 5 ms`).
  - Prompt assembly token count under 11 active/idle subsystems (`<= 1,800` input tokens for 4K/8K Ollama safety; `100%` `[CREATOR VERIFIED]` retention).
- **Go/No-Go Gate:** Zero corruption of existing `data/second_brain/memory.db` during migration; `0` hash-fallback overwrites of cloud vectors; deterministic pass of `tests/test_memory.py` + `tests/test_brain.py` + `EXP-002` benchmark harness.

### Track 3: Closed-Loop Autonomous Agency (`EXP-003`)
- **Core Hypothesis:** Fixing `Goal.recalculate_progress()` (`REPLANNED` excluded), capping replans (`MAX_REPLAN_ATTEMPTS = 3`), replacing 0ms Minecraft polling with cross-tick `mc_telemetry` delta verification, and adding Node.js bridge supervision will reduce infinite replan loops to `0` and achieve `>= 90%` verified state consistency over a 2-hour Minecraft soak test.
- **Key Metrics:**
  - Infinite replan loop count over 50 injected failures (`0` loops; `100%` transition to `FAILED`/`ABANDONED` + pivot within `3` attempts).
  - False-positive completion rate when Minecraft is disconnected (`0%` unless `allow_simulated_progress=True`).
  - Bridge crash recovery time (`<= 10 s` auto-reconnect with `0` leaked `setInterval` timers in `bot.js`).
- **Go/No-Go Gate:** 2-hour automated Mineflayer + `AutonomousMissionExecutor` soak test with injected server kicks, `bot.js` `SIGKILL`, and impossible-goal failures completes with bounded `goals.json` size and accurate `connection_status`.

---

## 4. Benchmark Datasets & Test Harnesses (To Be Built in `tests/` / `scratch/` During Execution)

| Dataset / Harness | Used By | Composition & Ground Truth |
|---|---|---|
| **MaybeAI-Voice-Bench-v1** | `EXP-001` | 50 utterances (English + Indonesian code-switching, 2-word to 25-word sentences) + 30 min background noise/BGM/keyboard mix (`AudioWorklet` 16 kHz PCM), plus 20 forced mid-sentence barge-in timestamps. |
| **MaybeAI-Memory-Bench-v1** | `EXP-002` | Synthetic 10,000-episode SQLite DB (viewer inside jokes, promises, game events, timestamps spanning 90 days) + 100 natural-language queries with human-labeled ground-truth episode IDs (30% placed beyond row 300). |
| **MaybeAI-Agency-Fault-Bench-v1** | `EXP-003` | Deterministic mock + live Mineflayer test harness injecting: (a) 0-delta gather failures, (b) delayed 5s–15s inventory deltas, (c) `bot.js` `SIGKILL` / `EADDRINUSE`, (d) disconnected `MinecraftController` ticks. |

---

## 5. R&D Cadence & Promotion Path

1. **Horizon 0 (Pre-R&D Prerequisite):** Land P0 security & concurrency fixes (`[SEC-CRIT-001/002]`, `[PERF-HIGH-001]`, `[AUDIO-CRIT-001]`, `[COG-CRIT-001/002]`, `[GAME-CRIT-001/002]`).
2. **Horizon 1 (Weeks 1–3):** Execute `EXP-001` (Audio/Lip-Sync) and `EXP-002` (Memory/Budgeting) in parallel; promote passing **TRIAL** items to **ADOPT**.
3. **Horizon 2 (Weeks 3–5):** Execute `EXP-003` (Closed-Loop Agency & MC Supervision) and Karaoke Audio-Clock Pre-Synthesis validation.
4. **Horizon 3 (Post-Stabilization):** Evaluate **ASSESS** items (Local VLM `qwen2.5vl:3b`, Binary WS audio frames, Local Three-VRM bundle) only after Profile B VRAM headroom is confirmed.
