# MaybeAI Post-Implementation CTO Audit — 03: Real-Time Audio, Voice Duplex & Avatar Synchronization

**Auditor:** AGENT 2 (`ng-audio`)  
**Audit Scope:** Post-H0/H1/H2/H3 verification of `core/brain.py`, `core/tts.py`, `core/stt.py`, `core/tts_providers.py`, `core/vts_client.py`, `core/singer.py`, `core/orchestrator.py`, `web/app.js`, `web/overlay.js`, `web/audio-worklet-processor.js`, `run.py`, and `config/settings.json`.  
**Test Execution:** `.\.venv\Scripts\python.exe -W default -m unittest tests.test_tts tests.test_vts_client tests.test_voice_duplex tests.test_streaming_tts tests.test_neural_tts_rvc tests.test_audioworklet_deck tests.test_avatar_vts_and_telemetry tests.test_horizon1_upgrade tests.test_overlay_route tests.test_youtube_karaoke` → **66 tests passed in 9.416s (`OK`)**, with 3 asyncio slow-callback warnings (`>0.1s`).

---

## 1. Executive Summary & L0–L5 Maturity Scores

| Domain | Maturity Level | Score | Rationale |
| :--- | :---: | :---: | :--- |
| **Voice & Real-Time Audio** | **L3.5 — Integrated & Resilient** | **3.5 / 5** | Binary AudioWorklet 16 kHz PCM frames, bounded non-blocking `_voice_worker` STT offload, `EnergyVAD` onset barge-in, `CancelledError` propagation in `speak_stream()`, `Singer` BGM stop, multi-provider TTS + `RVCVoiceConverter` + `is_edge_tts_voice` fallback, and `ProviderCircuitBreaker` LLM streaming failover are all implemented and verified. Held back from L4 by: `ClientTimeout(total=1.8)` applying to full stream duration (not TTFB), `TTSEngine.speak()` still swallowing `_stop_requested` `CancelledError`, `stt_partial` hardcoded to `"Listening..."`, unused `tts.volume`, and unpiped `Singer` provider config in `reload_settings`. |
| **Avatar & Lip-Sync** | **L3.5 — Synchronized & Offline-Ready** | **3.5 / 5** | Real 50ms RMS audio-envelope extraction (`extract_rms_envelope_from_sound` / `extract_rms_envelope_from_wav`), browser `AnalyserNode` RMS arbitration (`if (!isLocalAudioPlaying)`), persistent VTS auth token (`data/vts_token.json`), exponential-backoff `auto_reconnect_loop()`, and multi-parameter `apply_mood_rig()` are implemented and verified. Held back from L4 by: `MouthSmile` vs `MouthForm` mismatch between `trigger_expression()` and `apply_mood_rig()`, duplicate `start_auto_reconnect()` calls in `VTSClient`, and no timestamped server-to-browser lip-sync frames for `VTSClient` when `output_mode="browser"`. |

---

## 2. Capability Classification Matrix

| Capability | Capability Status | Claim Verification | Verified Implementation Evidence |
| :--- | :---: | :---: | :--- |
| **Gemini/OpenAI SSE & Ollama NDJSON Streaming + `ProviderCircuitBreaker`** | `EXISTING` | `VERIFIED` | `core/brain.py:14-95, 296-320, 559-630, 819-860, 976-1005, 1132-1175` — `streamGenerateContent?alt=sse`, OpenAI `data:` SSE, Ollama `/api/chat` NDJSON, and `ProviderCircuitBreaker` (`failure_threshold=3`, `cooldown_sec=30.0`). |
| **Multi-Provider TTS (Edge/Kokoro/ElevenLabs/Custom) & Fallback Voice** | `EXISTING` | `VERIFIED` | `core/tts_providers.py:232-626`, `core/tts.py:340-352`, `core/singer.py:159-171` — `is_edge_tts_voice()` guards fallback to `self.fallback_voice` (`en-US-AriaNeural`). |
| **RVC Post-Processing Client** | `EXISTING` | `VERIFIED` | `core/tts_providers.py:67-78, 629-709` — `detect_audio_format()` sets dynamic MIME/extension, SSRF-validated via `validate_outbound_url()`, persistent session, graceful fallback to original audio. |
| **AudioWorklet 16 kHz Binary PCM Frames** | `EXISTING` | `VERIFIED` | `web/audio-worklet-processor.js:6-122`, `web/app.js:1216-1241`, `run.py:1125-1134` — `MaybeAIPCMProcessor` downsamples to 16 kHz Int16 PCM (512-sample / 32ms frames) and sends binary WS frames with JSON base64 fallback. |
| **Non-Blocking STT Offload & `EnergyVAD`** | `EXISTING` | `VERIFIED` | `run.py:975-999, 1102-1118`, `core/stt.py:23-119, 389-520` — Bounded `voice_queue` (`maxsize=64`, drop-oldest) + `_voice_worker` task prevents WS receive loop blocking during `transcribe_wav_bytes()`. |
| **Full-Duplex `barge_in` + `Singer` BGM Stop** | `EXISTING` | `VERIFIED` | `core/tts.py:615-625`, `core/singer.py:195-208`, `core/orchestrator.py:753-824` — `speak_stream()` re-raises `CancelledError`; `barge_in()` stops `tts`, `singer` (`pygame.mixer.music.stop()`), and cancels `_active_interaction_task`. |
| **Real RMS Audio-Envelope Lip-Sync** | `EXISTING` | `VERIFIED` | `core/tts_providers.py:86-184`, `core/tts.py:694-730`, `core/singer.py:306-370, 436-468` — 50ms RMS envelope extracted from `pygame.mixer.Sound` or WAV bytes, locked to `channel.get_busy()` / monotonic clock. |
| **Browser `AnalyserNode` Arbitration** | `EXISTING` | `VERIFIED` | `web/app.js:284-397, 600-609`, `web/overlay.js:33-163, 262-265` — `avatar_state.mouth_open` is ignored when `isLocalAudioPlaying` is `true`, eliminating `output_mode="both"` jitter. |
| **VTS Persistent Token & Auto-Reconnect** | `EXISTING` | `VERIFIED` | `core/vts_client.py:10-18, 66-140, 188-276` — Persists `authenticationToken` to `data/vts_token.json`, clears rejected tokens, and runs exponential-backoff `auto_reconnect_loop()`. |
| **Streaming Partial STT Transcripts** | `INCOMPLETE` | `VERIFIED` | `core/orchestrator.py:587-599` checks `res.get("partial")`, but `StreamingSTTSession.feed_pcm_chunk()` (`core/stt.py:442-490`) never emits partials; UI always receives `"Listening..."`. |
| **TTS Volume Control (`tts.volume`)** | `INCOMPLETE` | `VERIFIED` | `config/settings.json:69` defines `"volume": "+0%"`, but `TTSEngine` and `EdgeTTSProvider` never read or apply it. |
| **Local Neural STT/TTS Backends** | `EXPERIMENTAL` | `VERIFIED` | `faster-whisper`, `openai-whisper`, `kokoro`, `kokoro_onnx` are absent from `.venv`; runtime falls back to `[STT Mock]` (unless `OPENAI_API_KEY` is set) or remote HTTP/Edge-TTS. |

---

## 3. Detailed Post-Implementation Audit Findings

### `[AUDIO-MED-001]` `failover_timeout_sec` (`1.8s`) Applied as Total Stream Timeout Instead of Connect/TTFB Timeout
- **Severity:** MEDIUM
- **Claim Classification:** `VERIFIED`
- **Capability Status:** `EXISTING` (with latency/truncation caveat)
- **Location:** `core/brain.py:284-286, 608-627, 832, 983, 1146`, `config/settings.json:24`
- **Symptom:** A healthy LLM stream that begins responding within 500 ms but takes >1.8 s to finish generating a full reply is aborted mid-sentence by `aiohttp.ClientTimeout(total=1.8)`. Because `yielded_candidate` is already `True` (`core/brain.py:625-626`), the circuit breaker records a failure and stops without failing over, leaving a truncated response.
- **Root Cause:** `_try_stream_openai()`, `_try_stream_ollama()`, and `_try_stream_gemini()` pass `aiohttp.ClientTimeout(total=self._get_failover_timeout_sec())` (default `1.8s`) to `session.post()`. In `aiohttp`, `total` bounds the entire request+response body lifetime, unlike `sock_connect` + `sock_read` (inter-chunk/TTFB timeout).
- **Blast Radius:** Streaming LLM responses (`streaming_enabled: true`) exceeding 1.8 s total generation time.
- **Recommended Fix:** Use `aiohttp.ClientTimeout(connect=1.8, sock_read=5.0)` (or enforce `failover_timeout_sec` only until the first chunk is yielded) so slow TTFB triggers failover while active streams are not truncated.

---

### `[AUDIO-MED-002]` `TTSEngine.speak()` Still Swallows `CancelledError` on `stop()`, Affecting Non-Streaming Speech Callers
- **Severity:** MEDIUM
- **Claim Classification:** `VERIFIED`
- **Capability Status:** `INCOMPLETE`
- **Location:** `core/tts.py:459-470`, `core/orchestrator.py:611-627, 785-799`
- **Symptom:** While `speak_stream()` was fixed in H1 to re-raise `asyncio.CancelledError` (`core/tts.py:615-625`), single-shot `TTSEngine.speak()` still returns `None` when `self._stop_requested` is `True` (`core/tts.py:468-469`). Additionally, background speech callers (`_speak_mission_commentary`, `_speak_plugin_response`, `_run_improv`) do not register in `_active_interaction_task`.
- **Root Cause:** `TTSEngine.speak()` catches `CancelledError` and returns `None` if `self._stop_requested` is set, masking cancellation from any enclosing coroutine.
- **Blast Radius:** Non-streaming `speak()` invocations during `barge_in()`.
- **Recommended Fix:** Re-raise `asyncio.CancelledError` unconditionally in `TTSEngine.speak()` (matching `speak_stream()`) and handle `CancelledError` cleanly in callers.

---

### `[AUDIO-MED-003]` `Orchestrator.reload_settings()` Omits `Singer` Neural Provider & Fallback Voice Config
- **Severity:** MEDIUM
- **Claim Classification:** `VERIFIED`
- **Capability Status:** `INCOMPLETE`
- **Location:** `core/orchestrator.py:134-143, 873-894`, `core/singer.py:84-130`
- **Symptom:** Updating `tts.provider`, `tts.fallback_voice`, `tts.kokoro_url`, `tts.elevenlabs_voice_id`, or `tts.custom_tts_url` at runtime updates `self.tts`, but `self.singer.update_config()` (`core/orchestrator.py:888-894`) only receives `voice`, `output_mode`, `rvc_enabled`, `rvc_url`, and `rvc_pitch_shift`. `Orchestrator.reload_settings()` also omits `fallback_voice` for `self.tts.update_config()`.
- **Root Cause:** `Orchestrator.__init__` and `reload_settings` were only partially updated when `Singer` gained multi-provider support.
- **Blast Radius:** Runtime `/settings` changes to TTS provider or fallback voice do not propagate to `Singer` karaoke vocals.
- **Recommended Fix:** Forward `provider`, `fallback_voice`, `elevenlabs_voice_id`, `kokoro_url`, and `custom_tts_url` to both `self.tts.update_config()` and `self.singer.update_config()` in `reload_settings()` (and `Orchestrator.__init__`).

---

### `[AUDIO-LOW-001]` VTS `MouthSmile` vs `MouthForm` Parameter Split & Duplicate Reconnect Call
- **Severity:** LOW
- **Claim Classification:** `VERIFIED`
- **Capability Status:** `EXISTING` (minor inconsistency)
- **Location:** `core/vts_client.py:307-310, 348-351, 357-456, 464-490`, `core/orchestrator.py:728, 802`
- **Symptom:** `apply_mood_rig()` drives `MouthForm`, whereas `trigger_expression()` (called by `Orchestrator.barge_in()` at `core/orchestrator.py:802` and action tags at `728`) drives `MouthSmile`. Additionally, `VTSClient.set_parameter()` (`307-310`) and `set_parameters()` (`348-351`) each contain a duplicated `if self.auto_reconnect and not self._closing: self.start_auto_reconnect()` block.
- **Recommended Fix:** Remove the duplicate `if` blocks in `VTSClient`, and route `barge_in()` / action resets through `apply_mood_rig("neutral")` so `MouthForm` and `MouthSmile` do not drift.

---

### `[AUDIO-LOW-002]` Streaming Partial STT, Unused `tts.volume`, and Test Teardown `ResourceWarning`s / Slow Callbacks
- **Severity:** LOW
- **Claim Classification:** `VERIFIED`
- **Capability Status:** `INCOMPLETE`
- **Location:** `core/orchestrator.py:587-599`, `core/stt.py:442-490`, `config/settings.json:69`, `tests/test_voice_duplex.py`, `tests/test_audioworklet_deck.py`
- **Symptom:**
  1. `stt_partial` always emits `"Listening..."` because `StreamingSTTSession` has no incremental hypothesis decoder.
  2. `tts.volume` (`"+0%"` in `config/settings.json:69`) is never applied to `TTSEngine` or `EdgeTTSProvider`.
  3. Audio/duplex unit tests pass (`66/66`), but emit 3 asyncio slow-callback warnings (`>0.1s`) due to synchronous `pygame.mixer.init()` / `Sound` loading or `asyncio.sleep` polling in test cases, and full-suite `ResourceWarning`s occur where tests instantiate `TTSEngine`/`STTEngine` without calling `await close()` (production `Orchestrator.shutdown()` at `core/orchestrator.py:533-551` does close them).
- **Recommended Fix:** Offload `pygame.mixer.init()` cleanly, wire `tts.volume` to `EdgeTTSProvider` / `pygame` channel volume (`set_volume`), and ensure test fixtures `await close()` engines in `asyncTearDown`.
