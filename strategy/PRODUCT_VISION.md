# MaybeAI — Long-Term Product Vision & Strategy (`strategy/PRODUCT_VISION.md`)

**Author:** Agent 9 — Product Vision & Innovation Strategist (`strat-product`)  
**Grounding Baseline:** `audit/FINAL_AUDIT_REPORT.md` and `audit/00_repository_inventory.md` through `audit/11_performance_analysis.md`  
**Current Readiness Verdict:** `NO-GO` for unattended/public/Docker/LAN streams; `CONDITIONAL GO` for supervised localhost creator streams pending P0 hardening.

---

## 1. Executive Vision: From Multi-Feature AI VTuber to Autonomous Digital Companion

Today, MaybeAI (personified by **Eve**) is an ambitious, feature-dense **AI VTuber runtime** spanning 94 Python modules in `core/`, a FastAPI/WebSocket server (`run.py`), 4 browser surfaces (`/`, `/settings`, `/overlay`, `/deck`), a Node.js Mineflayer bridge (`minecraft/`), and integrations with OBS Studio, VTube Studio, `python-chess`, and multi-platform chat (Twitch, YouTube Live, Discord, TikTok).

Its long-term transformation is to evolve from a **creator-triggered, multi-feature stream toy** into a **persistent, trustworthy, autonomous digital companion**—an entity with:
1. **Coherent Intelligence:** Bounded, token-budgeted reasoning across local and cloud LLMs with graceful cross-provider failover.
2. **Continuous Personality & Memory:** A living Second Brain where episodic memories, promises, inside jokes, mood baselines, and personality traits evolve consistently across sessions without corrupting or drifting uncontrollably.
3. **Genuine Social & Emotional Awareness:** Audience-aware curation, multi-user relationship continuity, and Creator-vs-Viewer authority boundaries that hold across every LLM path and surface.
4. **Grounded Agency:** Closed-loop autonomous missions that act only on verified world/game state—never fabricating offline progress or trapping themselves in infinite replan loops.
5. **Real-Time Presence & Adaptability:** Sub-second full-duplex voice barge-in, true audio-envelope lip-sync across 2D/3D/VTS avatars, and safe extensibility via isolated plugins and multi-AI collaborations.

> **Core Strategic Thesis:** MaybeAI does not win by adding more disconnected mini-features. Its architectural moat already exists in `EventBus` + Second Brain + multi-surface studio/overlay/deck + game/world bridges. Winning requires **hardening the core loop into a reliable, secure, low-latency nervous system** first, then compounding those subsystems into a cohesive companion.

---

## 2. Current-State Reality vs. Target Transformation

Every capability claim below is strictly classified against verified audit evidence (`audit/FINAL_AUDIT_REPORT.md` & `audit/00..11`).

| Capability Area | Classification | Verified Current Reality | Target Companion State |
|---|---|---|---|
| **Event-Driven Core & Config** | **Current Capability** | Typed async `EventBus`, FastAPI `lifespan`, `ConfigManager` atomic writes (`os.replace`), 110-field `/settings` schema (`audit/01`). | Backpressure-safe concurrent `EventBus`, tracked background tasks, full secret masking (`llm.*_api_key`), runtime concurrency limits. |
| **Voice Duplex & Audio Pipeline** | **Partially Implemented** | Browser 16 kHz `AudioWorklet` + `EnergyVAD` + `SentenceChunker` work, but `speak_stream()` swallows `CancelledError` (`[AUDIO-CRIT-001]`), `Singer` BGM ignores barge-in (`[AUDIO-HIGH-002]`), and `transcribe_wav_bytes()` blocks WS (`[AUDIO-HIGH-001]`). | Sub-second clean barge-in across speech + karaoke, non-blocking STT worker pool, persistent HTTP session pooling. |
| **Avatar Lip-Sync & Visual Presence** | **Planned Capability** | Server emits a fixed 80 ms square wave (`0.95`/`0.50`) that collides with browser `AnalyserNode` RMS (`[AUDIO-CRIT-002]`); VRM relies on external `esm.sh` CDN (`[UI-MED-004]`). | Unified server-computed RMS audio-envelope lip-sync frames, conflict-free browser playback, offline-bundled VRM/fonts. |
| **Memory, Mood & Personality** | **Current Capability** (with gaps) | SQLite FTS5 + cosine vector search + Markdown sync, 5-dim `MoodEngine`, bounded `PersonalityEvolutionEngine`, 5-tier `RelationshipEngine` (`audit/03`). | Hybrid vector/FTS5 retrieval beyond 300-row cap (`[COG-HIGH-005]`), wired `fulfill_promise()` & mood temperature, LRU `UserMemory`. |
| **LLM Routing & Context Budgeting** | **Planned Capability** | Unbounded prompt concatenation across 11+ directives (`[COG-HIGH-002]`), `is_creator` dropped on live LLM paths (`[COG-HIGH-003]`), zero cross-provider failover (`[COG-MED-002]`). | Token-aware `ContextBudgetManager`, verified `[CREATOR VERIFIED]` authority propagation, automatic provider failover chain. |
| **Autonomous Missions & Agency** | **Partially Implemented** | `AutonomousMissionExecutor` & approval gate exist, but replanned goals never reach `COMPLETED` (`[COG-CRIT-001]`), replanning loops infinitely (`[COG-CRIT-002]`), and 0ms MC polling / offline simulation distort progress (`[COG-HIGH-001]`). | Telemetry-verified action completion, capped replanning (`MAX_REPLAN_ATTEMPTS`), expiring approval gates (`[COG-MED-001]`). |
| **Gaming & Interactive Worlds** | **Current Capability** (with gaps) | Mineflayer bridge (`santai`/`kompe`/`guard`), `python-chess`, 6 mini-games, RPG storytelling, OBS Showrunner, `ffmpeg` 9:16 highlights (`audit/05`). | Thread-safe `chess.Board` cloning (`[GAME-CRIT-001]`), Node bridge crash recovery (`[GAME-CRIT-002]`), OBS reconnect (`[GAME-HIGH-002]`), audio-clock-locked karaoke. |
| **AI-to-AI Collaboration** | **Partially Implemented** | HMAC-SHA256 `CollabEnvelope` & `/ws/collab` exist, but lack replay protection (`[COLLAB-CRIT-001]`), cooldown auto-recovery (`[COLLAB-HIGH-003]`), and bidirectional `duet_sync`/`emote_sync`/`game_move` (`audit/04`). | Replay-safe, capability-negotiated multi-AI floor arbitration with Web Dashboard Collab UI and bidirectional game/emote/duet sync. |
| **Plugin Ecosystem & Security** | **Partially Implemented** | Subprocess `sandbox_worker.py` strips env vars (`leaks=[]`) and kills on timeout, but lacks OS filesystem/network jail (`[SEC-CRIT-002]`) and `/ws` + `GET /api/*` have auth gaps (`[SEC-CRIT-001]`, `[SEC-HIGH-002]`). | Full Creator auth across `/ws`, REST, and Docker/LAN (`[SEC-HIGH-001]`), XSS-free UI (`[UI-HIGH-001]`), OS-jailed capability-enforced plugins. |

---

## 3. Target Personas

### Persona 1: Solo Streamer ("Maya")
- **Profile:** Variety/Just-Chatting/Minecraft VTuber streaming on Twitch/YouTube/TikTok with OBS Studio and VTube Studio or `/overlay` (2D/VRM) on a single Windows PC.
- **Core Needs:** Zero-fuss startup (`start.bat`), expressive lip-sync that matches her AI co-host's actual voice, instant voice barge-in when she talks over the AI, automated 9:16 highlight clips + VOD summaries, and a mobile `/deck` to trigger karaoke, improv, or mute without alt-tabbing.
- **Current Friction (Audit-Grounded):** Square-wave lip-sync jitter (`[AUDIO-CRIT-002]`), post-barge-in ghost replies (`[AUDIO-CRIT-001]`), OBS disconnect stale state (`[GAME-HIGH-002]`), and offline VRM failure when CDN is unreachable (`[UI-MED-004]`).
- **Value Unlocked:** A dependable, low-latency AI co-host that feels alive on camera, never talks over her after she interrupts, and turns every stream into ready-to-post clips.

### Persona 2: Technical Creator ("Alex")
- **Profile:** Developer/power-user running MaybeAI in Docker or across a LAN (headless server + separate gaming PC / OBS machine), customizing local LLMs (Ollama), local TTS/STT (Kokoro, Faster-Whisper, RVC), and writing custom `plugins/*.py`.
- **Core Needs:** Secure LAN/Docker authentication (`MAYBEAI_CREATOR_TOKEN`), strict prompt-injection defense against hostile chatters, clean APIs/SDKs for plugins, token-budgeted prompts for 8K-context local models, and reliable diagnostics.
- **Current Friction (Audit-Grounded):** Broken Docker/LAN WS auth (`[SEC-HIGH-001]`), unauthenticated `/ws` & `GET /api/*` (`[SEC-CRIT-001]`, `[SEC-HIGH-002]`), `/settings` XSS & missing token UI (`[UI-HIGH-001]`, `[UI-HIGH-002]`), dead `strict_mode` prompt-injection flags (`[SEC-HIGH-004]`), and 4K/8K prompt bloat (`[COG-HIGH-002]`).
- **Value Unlocked:** A self-hostable, LAN-safe, hackable companion platform where local models run fast and third-party plugins cannot exfiltrate `.env` or `data/memory.db`.

### Persona 3: Multi-AI Collab Producer ("Ren")
- **Profile:** Creator/producer orchestrating multi-agent streams—two or more AI VTubers bantering, singing duets, reacting with synchronized emotes, or playing Chess/Minecraft together.
- **Core Needs:** Deterministic turn-taking without reply storms or permanent cooldown deadlocks, synchronized duet lyrics and emotes, bidirectional game moves, and a visual Collab control panel in the Studio Dashboard.
- **Current Friction (Audit-Grounded):** Permanent `"cooldown"` deadlock after `max_collab_turns` (`[COLLAB-HIGH-003]`), concurrent reply storms (`[COLLAB-HIGH-004]`), replayable envelopes (`[COLLAB-CRIT-001]`), one-way/partial `duet_sync`/`emote_sync`/`game_move`, and zero Collab UI in `web/` (`audit/04`).
- **Value Unlocked:** Reliable, choreographed multi-AI entertainment that scales from 1-on-1 banter to full collaborative shows.

---

## 4. Competitive Differentiation

| Dimension | Typical AI VTuber Bots | Generic LLM Chatbots | MaybeAI Differentiator |
|---|---|---|---|
| **Memory & Continuity** | Ephemeral sliding window; forgets viewers next stream. | Flat RAG chunks without emotional or social state. | **Second Brain + Social Graph:** SQLite FTS5 + vector recall + human-readable Markdown sync + 5-tier relationships + evolving personality & mood baselines. |
| **Embodied World Agency** | Text-only or scripted OBS hotkeys. | No game/stream world loop. | **Unified EventBus Agency:** Closed-loop `AutonomousMissionExecutor` bridging Mineflayer (`santai`/`kompe`/`guard`), `python-chess`, RPG storytelling, Desktop Companion, and OBS Showrunner. |
| **Voice & Stage Presence** | Sequential turn-based TTS; no interruption handling. | No real-time avatar or broadcast overlay. | **Full-Duplex Studio Stack:** 32 ms `AudioWorklet` PCM, `SentenceChunker` streaming TTS, built-in `/overlay` (2D + 3D VRM), VTS RPC, and `/deck` mobile control. |
| **Multi-AI & Extensibility** | Single-bot silo. | Closed SaaS plugins. | **Open Local-First Ecosystem:** Native `/ws/collab` AI-to-AI protocol + out-of-process `PluginRegistry` + multi-provider LLM/TTS/STT (cloud or 100% local). |

---

## 5. Core Product Pillars

### Pillar 1: Trustworthy & Secure Broadcast Core (`Secure-by-Default`)
Every control surface (`/`, `/settings`, `/overlay`, `/deck`, `/ws`, `/api/*`, `/ws/collab`) must enforce consistent Creator authentication, origin checks, XSS-safe rendering, prompt-injection filtering, and sandboxed plugin/subprocess boundaries—making Docker and LAN deployments genuinely `GO`.

### Pillar 2: Real-Time Duplex Presence (`Zero-Jank Voice & Avatar`)
Voice interaction must feel conversational: sub-second barge-in that cleanly cancels speech, BGM, and downstream broadcasts; non-blocking STT; and a single, conflict-free audio-envelope lip-sync pipeline driving VTS, 2D Canvas, and offline-capable 3D VRM.

### Pillar 3: Grounded Cognitive Continuity (`Memory That Earns Trust`)
Cognition must respect token budgets, preserve Creator authority across all providers, fail over gracefully when an API blips, and execute autonomous missions only against verified world telemetry—turning Second Brain memories, promises, and personality evolution into observable behavior.

### Pillar 4: Interactive Worlds & Multi-AI Stage (`Playable Entertainment`)
Games (Minecraft, Chess, Mini-Games, RPG Storytelling), Karaoke/Performance, Highlights/VOD, and AI-to-AI Collab must operate as resilient, reconnect-capable, bidirectional experiences—supported by an intuitive Studio & Deck UX.

---

## 6. Strategic Horizon Summary

1. **Phase 1 — Core Hardening (Weeks 1–4):** Resolve all P0/P1 audit blockers (`[SEC-CRIT-*]`, `[COLLAB-CRIT-001]`, `[AUDIO-CRIT-*]`, `[COG-CRIT-*]`, `[GAME-CRIT-*]`, `[PERF-HIGH-001]`, `[UI-HIGH-*]`) to achieve `GO` for both Supervised Localhost and Docker/LAN streams.
2. **Phase 2 — Adjacent Expansion (Months 2–3):** Ship `ContextBudgetManager`, cross-provider LLM failover, audio-envelope lip-sync, bidirectional Collab + Dashboard UI, offline VRM bundling, and OBS/Minecraft auto-recovery.
3. **Phase 3 — Horizon-3 Bets (Months 4–6+):** Introduce Silero/WebRTC VAD + binary WS audio, HNSW/sqlite-vec hybrid memory scaling, OS-level plugin sandboxing, live VLM-grounded commentary, and multi-party Collab capability negotiation.
