# MaybeAI CTO Audit — 02: Real-Time Audio, Voice Duplex & Avatar Synchronization

**Auditor:** AGENT 2 (`cto-audio`)  
**Scope:** End-to-end audio/voice latency pipeline (`mic/chat -> VAD -> STT -> LLM stream -> SentenceChunker -> TTS -> Audio playback/WS -> VTS/VRM/2D lip-sync`), barge-in race conditions, TTS provider/RVC fallback reality, optional dependency handling, and audio buffer/resource cleanup.  
**Source of Truth:** Direct inspection of `core/tts.py`, `core/tts_providers.py`, `core/stt.py`, `core/singer.py`, `core/vts_client.py`, `core/orchestrator.py`, `core/brain.py`, `run.py`, `web/audio-worklet-processor.js`, `web/app.js`, `web/deck.js`, `web/overlay.js`, `config/settings.json`, and `pyproject.toml`.

---

## 1. Capability Classification Matrix

| Capability | Classification | Verified Reality in Code |
| :--- | :--- | :--- |
| **Browser 16 kHz PCM Capture (`AudioWorklet`)** | **Current Capability** | `web/audio-worklet-processor.js` (`MaybeAIPCMProcessor`) downsamples to 16 kHz mono Int16 PCM (512-sample / 32 ms frames) and streams base64 over `/ws` (`voice_audio_chunk`), with `SpeechRecognition` fallback in `web/app.js:1080-1095` and `web/deck.js:160-200`. |
| **Energy-based VAD (`EnergyVAD`) & Utterance Buffering** | **Current Capability** | `core/stt.py:23-118, 369-500` implements `EnergyVAD` (RMS threshold, `min_speech_frames=2`, `hangover_frames=8`) and `StreamingSTTSession` (pre-roll deque, 30 s max buffer, in-memory WAV encoding). |
| **Streaming LLM -> Sentence Chunking -> Pipelined TTS** | **Current Capability** | `core/brain.py:240-292` streams OpenAI SSE, Gemini SSE (`streamGenerateContent?alt=sse`), Ollama NDJSON, or mock chunks into `SentenceChunker` (`core/tts.py:20-135`), which feeds a bounded `asyncio.Queue(maxsize=4)` in `TTSEngine.speak_stream()` (`core/tts.py:462-619`). |
| **Multi-Provider TTS & RVC Client** | **Partially Implemented** | `core/tts_providers.py` implements `EdgeTTSProvider`, `KokoroTTSProvider` (HTTP + local `kokoro`/`kokoro_onnx`), `ElevenLabsTTSProvider`, `CustomNeuralTTSProvider` (GPT-SoVITS / Fish Speech HTTP), and `RVCVoiceConverter`. However, `EdgeTTSProvider` fallback uses incompatible `self.voice`, MIME/filename are hardcoded to `audio/mpeg` / `input.mp3`, `Singer` bypasses providers, and `tts.volume` is unused. |
| **Full-Duplex Barge-In** | **Partially Implemented** | `Orchestrator.barge_in()` (`core/orchestrator.py:609-672`) stops `TTSEngine` and cancels `_active_interaction_task`, and browser clients clear `AudioContext` queues on `voice_barge_in`. However, `speak_stream()` swallows `CancelledError` when `_stop_requested` is set, `Singer` BGM (`pygame.mixer.music`) is not stopped, and `transcribe_wav_bytes()` blocks the WS receive loop. |
| **Server-Side Audio-Envelope Lip-Sync** | **Planned Capability** | **Does not exist.** `TTSEngine._play_and_lipsync()` (`core/tts.py:675-682`) and `Singer.sing()` (`core/singer.py:208-216`) emit a fixed 80 ms synthetic square wave (`0.95`/`0.50` or `0.70`/`0.20`), not audio-amplitude/envelope-driven values. Browser `web/overlay.js` and `web/app.js` do compute real `AnalyserNode` RMS, but it collides with server `avatar_state` broadcasts. |
| **Streaming Partial STT Transcripts** | **Planned Capability** | `core/orchestrator.py:490-502` checks `res.get("partial") or res.get("partial_transcript")`, but `StreamingSTTSession.feed_pcm_chunk()` (`core/stt.py:422-470`) never produces partial transcripts; `stt_partial` always broadcasts `"Listening..."`. |
| **VTube Studio Integration & Auto-Reconnect** | **Partially Implemented** | `VTSClient` (`core/vts_client.py`) authenticates and injects `InjectParameterDataRequest` (`apply_mood_rig`, `update_mouth`, `trigger_expression`). `auth_token` is never persisted, `auto_reconnect: true` in `config/settings.json:88` has no reconnect loop, and `Orchestrator` mixes `trigger_expression` (`MouthSmile`) with `apply_mood_rig` (`MouthForm`). |
| **OBS `/overlay` Audio & Avatar Sync (2D + VRM)** | **Current Capability** (with sync caveats) | `web/overlay.js` renders 2D Canvas or Three.js `@pixiv/three-vrm`, decodes `audio_chunk` via Web Audio API FIFO queue, and drives `targetMouthOpen` via `AnalyserNode` RMS—though server `avatar_state` overwrites `targetMouthOpen` in `both` mode. |
| **Proposed Innovation (Not in Codebase)** | **Proposed Innovation** | Unified server-side PCM/MP3 RMS envelope extraction with timestamped sync frames, Silero/WebRTC VAD + AEC, persistent `aiohttp.ClientSession` pooling, and true streaming PCM/chunked audio over binary WebSocket frames. |

---

## 2. End-to-End Latency & Synchronization Architecture

```text
[Browser Mic]
  └─ AudioWorklet (512 samples @ 16kHz = 32ms) ─(JSON base64 over /ws)─> run.py:1534
       └─ await orchestrator.process_voice_chunk() [core/orchestrator.py:465]
            ├─ EnergyVAD (min_speech_frames=2 -> 64ms onset; hangover=8 -> 256ms tail)
            ├─ speech_started -> await barge_in() [core/orchestrator.py:487]
            └─ speech_ended -> await stt.transcribe_wav_bytes() [BLOCKS WS LOOP]
                 └─ chat.put_message(source="mic") -> _process_chat_loop()
                      └─ Brain.generate_response_stream() [SSE / NDJSON]
                           └─ SentenceChunker (min_chars=8, max_chars=240)
                                └─ TTSEngine.speak_stream() [Queue maxsize=4]
                                     ├─ _synthesize_audio() -> Provider -> (optional RVC)
                                     ├─ _on_tts_audio_ready() -> WS "audio_chunk" (base64)
                                     │    └─ Browser decodeAudioData() -> AudioContext FIFO -> AnalyserNode RMS
                                     └─ _play_and_lipsync() -> pygame.mixer.Sound() + 80ms fake square wave
                                          ├─ VTSClient.update_mouth() (WS InjectParameterDataRequest)
                                          └─ WS "avatar_state" (overwrites browser targetMouthOpen!)
```

---

## 3. Detailed Audit Findings

### `[AUDIO-CRIT-001]` Barge-In `CancelledError` Swallowing in `speak_stream()` Causes Post-Interruption Side Effects
- **Severity:** CRITICAL
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/tts.py:588-600`, `core/orchestrator.py:632-648, 1531-1567, 1625-1634`
- **Symptom:** When a creator interrupts Eve mid-stream via barge-in, the interrupted interaction can still broadcast the partial `ai_response`, send partial text to Minecraft/Discord chat, and emit a trailing `avatar_state` reset after `voice_barge_in` was already sent.
- **Root Cause:**
  1. `Orchestrator.barge_in()` calls `self.tts.stop()` (`core/orchestrator.py:632`), which sets `self._stop_requested = True` and cancels `producer_task` and `consumer_task` (`core/tts.py:360-372`).
  2. In `TTSEngine.speak_stream()` (`core/tts.py:588-600`), `except asyncio.CancelledError:` catches the cancellation, and if `self._stop_requested` is `True`, **returns `"".join(raw_parts).strip()` instead of re-raising `CancelledError`** (`core/tts.py:598-599`).
  3. Although `barge_in()` also cancels `self._active_interaction_task` at `core/orchestrator.py:638`, `speak_stream()` has already suppressed the cancellation on the inner await; if the outer task has not yet hit another `await` suspension point before `speak_stream` returns, `_execute_interaction()` executes `raw_response = "".join(raw_chunks).strip()`, `broadcast("ai_response", ...)`, `minecraft.send_chat()`, and `discord_adapter.send_message()` (`core/orchestrator.py:1541-1567`).
- **Verification Steps:** Trigger `barge_in()` during an active `speak_stream()` session with `streaming_enabled: true` and inspect WebSocket frames emitted after `voice_barge_in`.
- **Blast Radius:** All streaming LLM+TTS interactions (`_execute_interaction`); causes duplicate/aborted responses in chat UI, Minecraft, and Discord after barge-in.
- **Recommended Fix:** Re-raise `asyncio.CancelledError` from `speak_stream()` (and `speak()`) whenever the outer task was cancelled, or check `self.tts.was_interrupted` / `asyncio.current_task().cancelling()` in `_execute_interaction()` immediately after `speak_stream()` returns before broadcasting `ai_response` or dispatching platform replies.

---

### `[AUDIO-CRIT-002]` Server Lip-Sync Is a Synthetic Square Wave & Collides with Browser `AnalyserNode` RMS
- **Severity:** CRITICAL
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/tts.py:646-685`, `core/singer.py:208-230`, `core/orchestrator.py:296-305, 1523-1529`, `web/overlay.js:78-92, 219-221`, `web/app.js:218-231, 449-450`
- **Symptom:** VTube Studio (`VTSClient`) mouth movements do not match actual speech cadence/syllables, often keep flapping after short sentences end, and in `output_mode="both"` the OBS `/overlay` and main dashboard avatars jitter as two conflicting lip-sync sources overwrite `targetMouthOpen`.
- **Root Cause:**
  1. `TTSEngine._play_and_lipsync()` (`core/tts.py:675-682`) computes no audio envelope; it alternates `val = 0.5 + 0.45 * (1 if step % 2 == 0 else 0)` (`0.95` / `0.50`) every `0.08` s (`Singer.sing()` alternates `0.7` / `0.2`).
  2. The `while` loop condition (`core/tts.py:675`) is `(channel is not None and channel.get_busy() in (True, 1)) or elapsed < est_duration`, where `est_duration = max(1.0, words / 2.6)`. Short utterances finish playing in `pygame` before `1.0` s, yet the mouth keeps flapping until `elapsed >= est_duration`.
  3. In `output_mode="both"` (`config/settings.json:60`), the server sends `audio_chunk` over WS (`_on_tts_audio_ready`), then runs `_play_and_lipsync()` which broadcasts `avatar_state` (`mouth_open: 0.95/0.50`) every 80 ms. Meanwhile, `web/overlay.js:90` and `web/app.js:226` run `requestAnimationFrame` with `AnalyserNode` (`targetMouthOpen = rms * 5.0`), while `handleWsMessage` (`web/overlay.js:220`, `web/app.js:450`) unconditionally overwrites `targetMouthOpen = data.mouth_open || 0.0`. Because browser playback lags server playback by WS transfer + `decodeAudioData()` latency, the two signals fight and desynchronize.
- **Verification Steps:** Enable `output_mode="both"`, send a 2-word message, and observe `avatar_state` WS messages vs `AnalyserNode` `targetMouthOpen` in `web/overlay.js`.
- **Blast Radius:** All VTS Live2D, 2D Canvas, and 3D VRM avatars across `/overlay` and `/`.
- **Recommended Fix:** Extract a real PCM/RMS amplitude envelope from synthesized audio on the server (or drive VTS from pre-computed envelope frames synchronized with playback start), and in `output_mode="browser"` / `"both"` ignore `avatar_state.mouth_open` on browser clients whenever `isPlayingAudioQueue` is active.

---

### `[AUDIO-HIGH-001]` `process_voice_chunk()` Awaits Whisper Transcription Inside the WebSocket Receive Loop
- **Severity:** HIGH
- **Evidence Classification:** `VERIFIED`
- **Location:** `run.py:1534-1549`, `core/orchestrator.py:465-512`, `core/stt.py:448-462`
- **Symptom:** When a creator finishes speaking (`speech_ended`), all subsequent WebSocket messages from that client—including `barge_in` and new `voice_audio_chunk` frames—stall until STT transcription completes.
- **Root Cause:** `run.py:1544` directly `await`s `orchestrator.process_voice_chunk(...)`, which `await`s `self.voice_session.feed_pcm_chunk(...)` (`core/orchestrator.py:475`). On `speech_ended` or `hit_max`, `feed_pcm_chunk()` awaits `self.stt.transcribe_wav_bytes(...)` (`core/stt.py:460`), which can take hundreds of milliseconds (local Whisper) or up to 30 s (`aiohttp.ClientTimeout(total=30)` for OpenAI Whisper API at `core/stt.py:247`).
- **Verification Steps:** Stream PCM chunks over `/ws` with `faster-whisper` or OpenAI Whisper API enabled and send a `barge_in` message immediately after `speech_ended`; observe `voice_chunk_ack` and `barge_in` processing blocked until transcription returns.
- **Blast Radius:** Full-duplex voice responsiveness on the creator WebSocket connection.
- **Recommended Fix:** Offload `transcribe_wav_bytes()` to a background `asyncio.Task` (with per-session ordering/queueing) so `feed_pcm_chunk()` returns VAD state immediately and the WebSocket loop remains non-blocking.

---

### `[AUDIO-HIGH-002]` Barge-In Does Not Stop Karaoke BGM (`Singer`) or Background Speech Callers
- **Severity:** HIGH
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/orchestrator.py:632-648, 925, 1020`, `core/singer.py:89-99, 142-145, 250-261`
- **Symptom:** Triggering `barge_in()` during karaoke (`perform_song()`) leaves the instrumental backing track (`pygame.mixer.music`) playing indefinitely, and barge-in during background speech (`_run_improv`, `_speak_visual_commentary`, `_speak_mission_commentary`) leaves post-speech avatar/broadcast code running.
- **Root Cause:**
  1. `Orchestrator.barge_in()` (`core/orchestrator.py:632`) calls `self.tts.stop()`, not `self.singer.stop()`. Even when `_active_interaction_task` is cancelled, `Singer.sing()`'s `finally` block (`core/singer.py:250-261`) cleans up `created_vocal_files` and resets mouth, but never stops `pygame.mixer.music` or `self._active_channel`.
  2. Background speech paths (`_run_improv`, `_speak_visual_commentary`, `_speak_mission_commentary`, `_on_collab_reply_needed`) are not stored in `self._active_interaction_task`, so `barge_in()` cancels `tts._active_speak_task` but not the enclosing coroutine.
- **Verification Steps:** Start `!sing`, trigger `POST`/`WS` `barge_in`, and observe `pygame.mixer.music.get_busy()` remains `True`.
- **Blast Radius:** Karaoke mode and autonomous/vision/mission commentary barge-in.
- **Recommended Fix:** Call `self.singer.stop()` inside `Orchestrator.barge_in()`, and add `self.stop()` / `pygame.mixer.music.stop()` cleanup in `Singer.sing()`'s `finally` block when cancelled.

---

### `[AUDIO-HIGH-003]` TTS Provider Fallback Voice Mismatch, Hardcoded MIME/RVC Types, and `Singer` Provider Bypass
- **Severity:** HIGH
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/tts.py:321-335`, `core/tts_providers.py:229, 452`, `core/orchestrator.py:301`, `core/singer.py:174`
- **Symptom:** Failing over from Kokoro/ElevenLabs/Custom TTS to `EdgeTTSProvider` fails when `self.voice` is non-Edge; browser `AudioContext.decodeAudioData()` or RVC endpoints receive mislabeled WAV bytes as `audio/mpeg` / `input.mp3`; karaoke ignores non-Edge providers.
- **Root Cause:**
  1. `TTSEngine._synthesize_audio()` (`core/tts.py:324-330`) passes `voice=self.voice` to `self._fallback_provider.synthesize(...)` (`EdgeTTSProvider`). If `self.voice` is e.g. `af_heart` (Kokoro) or an ElevenLabs voice ID, `edge-tts` rejects it.
  2. `_on_tts_audio_ready()` (`core/orchestrator.py:301`) hardcodes `"mime": "audio/mpeg"`, while local `KokoroTTSProvider` (`core/tts_providers.py:197, 207`) produces WAV (`audio/wav`) and `KokoroTTSProvider` HTTP mode requests `"response_format": "mp3"` (`core/tts_providers.py:229`).
  3. `RVCVoiceConverter.convert()` (`core/tts_providers.py:452`) hardcodes `filename="input.mp3", content_type="audio/mpeg"` regardless of actual audio format.
  4. `Singer.sing()` (`core/singer.py:174`) instantiates `edge_tts.Communicate(...)` directly instead of using `create_tts_provider()`.
- **Verification Steps:** Configure `tts.provider = "kokoro"` with local `kokoro_onnx` or an unreachable `kokoro_url` and `voice = "af_heart"`, then call `TTSEngine.speak()`.
- **Blast Radius:** All non-Edge TTS deployments (`kokoro`, `elevenlabs`, `gpt_sovits`, `fish_speech`), RVC post-processing, and karaoke.
- **Recommended Fix:** Maintain a dedicated `fallback_voice` (default `"en-US-AnaNeural"`) for Edge-TTS fallback, detect WAV (`RIFF` header) vs MP3 dynamically for MIME and RVC upload headers, and route `Singer` through `create_tts_provider()`.

---

### `[AUDIO-HIGH-004]` Double Temp-File Disk I/O & Unpooled `aiohttp.ClientSession` Per Sentence
- **Severity:** HIGH
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/tts_providers.py:103-119, 233, 315, 379, 457`, `core/tts.py:409-417, 508-509, 561`, `core/stt.py:248, 330-332`
- **Symptom:** Every synthesized sentence incurs redundant disk writes/reads and fresh TCP+TLS connection setup, inflating time-to-first-audio (TTFA) and risking temp-file churn under load.
- **Root Cause:**
  1. `EdgeTTSProvider.synthesize()` writes to `edge_tts_*.mp3`, reads it into `bytes`, and unlinks it (`core/tts_providers.py:103-119`). `TTSEngine.speak()` / `speak_stream()` writes those `bytes` to `speech_*.mp3`, then reads them back for `_on_tts_audio_ready` (`core/tts.py:409, 561`)—even when `output_mode == "browser"` (where no server `pygame` file path is needed).
  2. `KokoroTTSProvider`, `ElevenLabsTTSProvider`, `CustomNeuralTTSProvider`, `RVCVoiceConverter`, and `STTEngine._transcribe_with_openai_api()` each create and close a new `aiohttp.ClientSession` per call.
- **Verification Steps:** Inspect `core/tts_providers.py:103-119` and `core/tts.py:508-561`.
- **Blast Radius:** End-to-end TTS/STT latency on every sentence/utterance.
- **Recommended Fix:** Stream `edge_tts.Communicate.stream()` directly into memory (`BytesIO`), skip writing `speech_*.mp3` when `output_mode == "browser"`, and share a persistent `aiohttp.ClientSession` across provider/RVC/STT calls (closed on `shutdown()`).

---

### `[AUDIO-MED-001]` Fire-and-Forget `asyncio.create_task(on_mouth_update(val))` Causes Out-of-Order VTS/WS Updates
- **Severity:** MEDIUM
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/orchestrator.py:925, 1020, 1622, 1679, 1734, 1761, 1797, 1857`
- **Symptom:** Non-streaming `tts.speak()` and `singer.sing()` callers wrap `on_mouth_update` in `lambda val: asyncio.create_task(on_mouth_update(val))` (unlike `speak_stream()` which awaits `on_stream_mouth_update` directly). Tasks are never tracked or awaited, allowing a delayed `0.95` update to land after `0.0` mouth-close or barge-in reset.
- **Root Cause:** Unawaited `asyncio.create_task()` inside synchronous lambda callbacks.
- **Verification Steps:** Compare `core/orchestrator.py:1535` (`on_mouth_update=on_stream_mouth_update`) with `core/orchestrator.py:1622` (`lambda val: asyncio.create_task(...)`), noting `TTSEngine._invoke_callback` (`core/tts.py:343-348`) already supports `async` callbacks.
- **Blast Radius:** All non-streaming `speak()` and `sing()` VTS/browser avatar updates.
- **Recommended Fix:** Pass `on_mouth_update` directly as an `async def` callback (matching `speak_stream()`), since `TTSEngine._invoke_callback` and `Singer.sing` both `await` awaitable results.

---

### `[AUDIO-MED-002]` `VTSClient` Lacks Token Persistence, Auto-Reconnect Loop, and Expression Consistency
- **Severity:** MEDIUM
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/vts_client.py:18, 80-127, 155-156, 192-193, 306-332`, `config/settings.json:88`
- **Symptom:** VTube Studio requires manual plugin re-approval on every app restart; dropped VTS WebSocket connections never auto-reconnect despite `"auto_reconnect": true` in `config/settings.json:88`; `_authenticate()` can hang indefinitely on `ws.recv()`; `trigger_expression()` and `apply_mood_rig()` target different Live2D parameter sets (`MouthSmile`/`CheekPuff` vs `MouthForm`/`BrowLeftY`).
- **Root Cause:** `self.auth_token` is memory-only (`core/vts_client.py:18`), `set_parameter()`/`set_parameters()` only set `self.connected = False` on exception without scheduling reconnect, `ws.recv()` has no `asyncio.wait_for` timeout, and `Orchestrator` calls `trigger_expression()` in `barge_in()`, `_run_improv()`, `_speak_visual_commentary()`, and `_on_minecraft_commentary()` while calling `_apply_vts_mood_rig()` elsewhere.
- **Verification Steps:** Inspect `core/vts_client.py:18-127, 155-193, 306-332` and `config/settings.json:88`.
- **Blast Radius:** VTube Studio Live2D reliability across restarts and transient disconnects.
- **Recommended Fix:** Persist `auth_token` in config/state, wrap `_authenticate()` `recv()` calls in `asyncio.wait_for(..., timeout=5.0)`, implement a bounded backoff reconnect task when `auto_reconnect` is enabled, and standardize all emotion paths on `_apply_vts_mood_rig()`.

---

### `[AUDIO-MED-003]` Blocking `pygame.mixer` Calls on Event Loop & Unused `tts.volume` / `karaoke.vocal_volume`
- **Severity:** MEDIUM
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/tts.py:663-666`, `core/singer.py:137-143, 203`, `config/settings.json:64, 93-94`
- **Symptom:** `pygame.mixer.init()` and `pygame.mixer.Sound(file_path)` block the `asyncio` event loop during device initialization and MP3/WAV decoding; `tts.volume` (`"+0%"`) and `karaoke.vocal_volume` (`100`) in `config/settings.json` have no effect.
- **Root Cause:** Synchronous `pygame` calls execute directly inside `async def` methods (`_play_and_lipsync`, `sing`), and neither `TTSEngine` nor `Singer` reads `tts.volume` / `karaoke.vocal_volume`.
- **Verification Steps:** Inspect `core/tts.py:661-669`, `core/singer.py:137-205`, and `config/settings.json:64, 93-94`.
- **Blast Radius:** Event-loop jitter during audio playback start and dead settings in UI/config.
- **Recommended Fix:** Run `pygame.mixer.init()` and `pygame.mixer.Sound()` via `asyncio.to_thread()`, and wire `tts.volume` / `karaoke.vocal_volume` to `sound.set_volume()`.

---

### `[AUDIO-LOW-001]` Dead `stt_partial` Transcript Path & Static `EnergyVAD` Threshold
- **Severity:** LOW
- **Evidence Classification:** `VERIFIED`
- **Location:** `core/stt.py:23-118, 422-470`, `core/orchestrator.py:489-502`
- **Symptom:** `stt_partial` WebSocket events always send `"Listening..."` rather than incremental speech text, and `EnergyVAD` relies on a fixed RMS threshold (`0.02`) with no adaptive noise floor.
- **Root Cause:** `StreamingSTTSession.feed_pcm_chunk()` only invokes `transcribe_wav_bytes()` on `speech_ended` or `max_buffer_seconds=30.0`, never populating `partial` / `partial_transcript`.
- **Verification Steps:** Inspect `core/stt.py:422-470` and `core/orchestrator.py:490-502`.
- **Blast Radius:** Creator mic UX during long utterances and noisy environments without browser AEC.
- **Recommended Fix:** Either implement periodic sliding-window partial decoding or remove the dead `partial_transcript` check; optionally add an adaptive noise-floor estimator or Silero VAD backend.

---

## 4. Optional Dependency & Environment Verification

Inspected `pyproject.toml` and probed `.venv\Scripts\python.exe` (without modifying any files):

| Package | `pyproject.toml` Extra | Installed in `.venv` | Fallback Behavior Verified in Code |
| :--- | :--- | :--- | :--- |
| `edge-tts`, `pygame`, `numpy`, `aiohttp`, `websockets` | Core `dependencies` | **Yes** | Primary runtime audio/WS stack. |
| `faster-whisper` | `stt-local` | **No** | `STTEngine` catches `ImportError` (`core/stt.py:273, 337`), falls back to `openai-whisper`, then OpenAI Whisper REST API (`OPENAI_API_KEY`), then deterministic `[STT Mock]` string. |
| `openai-whisper` (`whisper`) | `stt-local` | **No** | Same fallback chain as above. |
| `kokoro`, `kokoro-onnx` | `tts-local` | **No** | `KokoroTTSProvider._synthesize_local_sync()` raises `RuntimeError` (`core/tts_providers.py:190`), which `TTSEngine._synthesize_audio()` catches and falls back to `EdgeTTSProvider` (`core/tts.py:322-330`). |
| `obsws-python` | `obs` | **No** | Handled by `OBSWebSocketClient` (outside audio/VTS scope). |
| `pytest` | `dev` | **No** | Test runner not installed in `.venv` or system Python; findings above are `VERIFIED` via direct source inspection. |

---

## 5. Audio Buffer & Resource Cleanup Verification

- **Temp audio files (`TTSEngine`):** `self._active_temp_files` and `pending_files` are cleaned up in `TTSEngine.stop()`, `speak()` `finally`, and `speak_stream()` `finally` (`core/tts.py:384-386, 458-460, 605-618`). Edge-TTS temp files in `EdgeTTSProvider.synthesize()` are cleaned in `finally` (`core/tts_providers.py:114-119`).
- **Temp WAV files (`STTEngine`):** `transcribe_wav_bytes()` removes `tmp_path` in `finally` (`core/stt.py:361-366`).
- **Temp vocal files (`Singer`):** `created_vocal_files` are removed in `finally` (`core/singer.py:253-254`), **but** `pygame.mixer.music` and `_active_channel` are not stopped on `CancelledError`.
- **Browser audio & mic cleanup:** `web/app.js:877-908` (`stopVadMonitor`) and `web/deck.js` (`stopAudioOutput` / `stopDeckMic`) properly cancel `requestAnimationFrame`, post `"stop"` to `AudioWorkletNode`, stop `MediaStream` tracks, and close `AudioContext`.
