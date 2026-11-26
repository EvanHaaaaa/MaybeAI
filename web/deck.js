// MaybeAI Mobile/Tablet Creator Stream Deck
document.addEventListener("DOMContentLoaded", () => {
  const CREATOR_TOKEN_KEY = "maybeai_creator_token";

  function getCreatorToken() {
    try {
      const urlToken = new URLSearchParams(window.location.search).get("token");
      if (urlToken && urlToken.trim()) {
        const clean = urlToken.trim();
        try {
          localStorage.setItem(CREATOR_TOKEN_KEY, clean);
        } catch (e) {}
        return clean;
      }
    } catch (e) {}
    try {
      return localStorage.getItem(CREATOR_TOKEN_KEY) || localStorage.maybeai_creator_token || "";
    } catch (e) {
      return "";
    }
  }

  getCreatorToken();

  function authFetch(url, options = {}) {
    const token = getCreatorToken();
    const headers = Object.assign({}, options.headers || {});
    if (token) {
      headers["X-Creator-Token"] = token;
      headers["Authorization"] = `Bearer ${token}`;
    }
    return fetch(url, Object.assign({}, options, { headers }));
  }

  const badgeWs = document.getElementById("badge-ws");
  const badgeMood = document.getElementById("badge-mood");
  const badgeMission = document.getElementById("badge-mission");
  const badgeBargeIn = document.getElementById("badge-barge-in");
  const deckFeedbackText = document.getElementById("deckFeedbackText");

  const deckAuthBar = document.getElementById("deck-auth-bar");
  const deckTokenInput = document.getElementById("deckTokenInput");
  const btnSaveToken = document.getElementById("btnSaveToken");

  const btnBargeIn = document.getElementById("btn-deck-barge-in");
  const btnMic = document.getElementById("btn-deck-mic");
  const deckMicLabel = document.getElementById("deck-mic-label");
  const deckMicSub = document.getElementById("deck-mic-sub");
  const btnMute = document.getElementById("btn-deck-mute");
  const deckMuteIcon = document.getElementById("deck-mute-icon");
  const deckMuteLabel = document.getElementById("deck-mute-label");
  const btnMissionStep = document.getElementById("btn-deck-mission-step");
  const btnMissionLoop = document.getElementById("btn-deck-mission-loop");
  const deckLoopIcon = document.getElementById("deck-loop-icon");
  const deckLoopLabel = document.getElementById("deck-loop-label");
  const btnSing = document.getElementById("btn-deck-sing");
  const btnImprov = document.getElementById("btn-deck-improv");
  const btnCollab = document.getElementById("btn-deck-collab");
  const btnStopSpeech = document.getElementById("btn-deck-stop-speech");

  const collabDrawer = document.getElementById("deck-collab-drawer");
  const collabTopicInput = document.getElementById("deckCollabTopicInput");
  const btnSendCollabTopic = document.getElementById("btnSendCollabTopic");
  const btnCancelCollabTopic = document.getElementById("btnCancelCollabTopic");

  let ws = null;
  let reconnectTimer = null;
  let bargeInCount = 0;
  let missionLoopActive = false;
  let audioMuted = false;

  function setFeedback(text) {
    if (deckFeedbackText) deckFeedbackText.textContent = text;
  }

  function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  // --- Browser Audio Output (optional mute toggle) ---
  let audioCtx = null;
  const audioQueue = [];
  let isPlayingAudio = false;
  let currentAudioSource = null;

  function ensureAudioContext() {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return null;
    if (!audioCtx) audioCtx = new AudioCtx();
    if (audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
    return audioCtx;
  }

  function stopAudioOutput() {
    audioQueue.length = 0;
    isPlayingAudio = false;
    if (currentAudioSource) {
      try { currentAudioSource.onended = null; currentAudioSource.stop(); } catch (e) {}
      currentAudioSource = null;
    }
  }

  function playNextChunk() {
    if (audioMuted || isPlayingAudio || audioQueue.length === 0) return;
    const ctx = ensureAudioContext();
    if (!ctx) return;
    const buf = audioQueue.shift();
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    currentAudioSource = src;
    isPlayingAudio = true;
    src.onended = () => {
      if (currentAudioSource === src) currentAudioSource = null;
      isPlayingAudio = false;
      playNextChunk();
    };
    try {
      src.start(0);
    } catch (e) {
      isPlayingAudio = false;
      currentAudioSource = null;
    }
  }

  async function enqueueAudioChunk(b64) {
    if (audioMuted || !b64) return;
    const ctx = ensureAudioContext();
    if (!ctx) return;
    try {
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const decoded = await ctx.decodeAudioData(bytes.buffer);
      audioQueue.push(decoded);
      playNextChunk();
    } catch (e) {}
  }

  // --- Mic Streaming via AudioWorklet (with SpeechRecognition fallback) ---
  let isMicActive = false;
  let micStream = null;
  let micWorkletCtx = null;
  let micWorkletNode = null;
  let recognition = null;

  function updateMicButton(active) {
    isMicActive = active;
    if (btnMic) btnMic.classList.toggle("is-active", active);
    if (deckMicLabel) deckMicLabel.textContent = active ? "Mic: LIVE" : "Mic: OFF";
    if (deckMicSub) deckMicSub.textContent = active ? "Streaming 16kHz PCM" : "Tap to Stream PCM";
  }

  async function startDeckMic() {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const canWorklet = Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && AudioCtx && AudioCtx.prototype && "audioWorklet" in AudioCtx.prototype);

    if (canWorklet) {
      try {
        micStream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
        });
        micWorkletCtx = new AudioCtx();
        await micWorkletCtx.audioWorklet.addModule("/static/audio-worklet-processor.js");
        const src = micWorkletCtx.createMediaStreamSource(micStream);
        micWorkletNode = new AudioWorkletNode(micWorkletCtx, "maybeai-pcm-processor", {
          processorOptions: { targetSampleRate: 16000, frameSize: 512 }
        });
        micWorkletNode.port.onmessage = (event) => {
          if (!isMicActive || !event.data || event.data.type !== "pcm16") return;
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: "voice_audio_chunk",
              audio_b64: arrayBufferToBase64(event.data.buffer),
              sample_rate: 16000,
              user: "Creator"
            }));
          }
        };
        const silentGain = micWorkletCtx.createGain();
        silentGain.gain.value = 0;
        src.connect(micWorkletNode);
        micWorkletNode.connect(silentGain);
        silentGain.connect(micWorkletCtx.destination);
        updateMicButton(true);
        setFeedback("🎙️ AudioWorklet mic streaming active (16kHz PCM).");
        return;
      } catch (err) {
        stopDeckMic();
      }
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setFeedback("⚠️ Mic unavailable (requires AudioWorklet or SpeechRecognition).");
      return;
    }
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "id-ID";
    recognition.onresult = (event) => {
      let finalTxt = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) finalTxt += event.results[i][0].transcript;
      }
      if (finalTxt.trim() && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "chat_message", user: "Creator", text: finalTxt.trim(), source: "mic", is_creator: true }));
      }
    };
    recognition.onend = () => {
      if (isMicActive) {
        try { recognition.start(); } catch (e) {}
      }
    };
    recognition.start();
    updateMicButton(true);
    setFeedback("🎙️ Fallback SpeechRecognition mic active.");
  }

  function stopDeckMic() {
    updateMicButton(false);
    if (micWorkletNode) {
      try { micWorkletNode.port.postMessage({ type: "stop" }); } catch (e) {}
      try { micWorkletNode.disconnect(); } catch (e) {}
      micWorkletNode = null;
    }
    if (micWorkletCtx) {
      try { micWorkletCtx.close(); } catch (e) {}
      micWorkletCtx = null;
    }
    if (micStream) {
      try { micStream.getTracks().forEach((t) => t.stop()); } catch (e) {}
      micStream = null;
    }
    if (recognition) {
      try { recognition.stop(); } catch (e) {}
      recognition = null;
    }
    setFeedback("🎙️ Mic stopped.");
  }

  // --- Status Updates & WebSocket ---
  function updateMissionBadge(st) {
    if (!st || !badgeMission) return;
    const isRunning = Boolean(st.is_running && !st.is_paused);
    missionLoopActive = isRunning;
    const hasPending = Boolean(st.pending_approval);
    if (hasPending) {
      badgeMission.textContent = "Mission: Approval";
      badgeMission.className = "status-pill status-accent";
    } else if (isRunning) {
      badgeMission.textContent = `Mission: Running (${st.step_count || 0})`;
      badgeMission.className = "status-pill status-online";
    } else {
      badgeMission.textContent = `Mission: Paused (${st.step_count || 0})`;
      badgeMission.className = "status-pill";
    }
    if (btnMissionLoop) btnMissionLoop.classList.toggle("is-active", isRunning);
    if (deckLoopIcon) deckLoopIcon.textContent = isRunning ? "⏸" : "▶";
    if (deckLoopLabel) deckLoopLabel.textContent = isRunning ? "Pause Loop" : "Mission Loop";
  }

  async function refreshStatus() {
    try {
      const [mRes, vRes] = await Promise.all([
        authFetch("/api/missions/status"),
        authFetch("/api/voice/status")
      ]);
      if (mRes.status === 401 || mRes.status === 403 || vRes.status === 401 || vRes.status === 403) {
        if (deckAuthBar) deckAuthBar.style.display = "flex";
      }
      if (mRes.ok) updateMissionBadge(await mRes.json());
      if (vRes.ok) {
        const vData = await vRes.json();
        if (typeof vData.barge_in_count === "number") {
          bargeInCount = vData.barge_in_count;
          if (badgeBargeIn) badgeBargeIn.textContent = `Barge-In: ${bargeInCount}`;
        }
      }
    } catch (e) {}
  }

  function connectWs() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const token = getCreatorToken();
    let wsUrl = `${protocol}//${window.location.host}/ws`;
    if (token) wsUrl += `?token=${encodeURIComponent(token)}`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      if (badgeWs) {
        badgeWs.textContent = "WS: Online";
        badgeWs.className = "status-pill status-online";
      }
      refreshStatus();
    };

    ws.onclose = () => {
      if (badgeWs) {
        badgeWs.textContent = "WS: Reconnecting";
        badgeWs.className = "status-pill status-offline";
      }
      reconnectTimer = setTimeout(connectWs, 2000);
    };

    ws.onerror = () => {
      try { ws.close(); } catch (e) {}
    };

    ws.onmessage = (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch (e) { return; }
      const data = msg.data || {};
      if (msg.type === "error" && data.code === "forbidden") {
        if (deckAuthBar) deckAuthBar.style.display = "flex";
        setFeedback(`🔒 ${data.error || "Creator token required"}`);
      } else if (msg.type === "avatar_state" && data.emotion) {
        if (badgeMood) badgeMood.textContent = `Mood: ${data.emotion}`;
      } else if (msg.type === "mood_updated" && data.mood) {
        if (badgeMood) badgeMood.textContent = `Mood: ${data.mood}`;
      } else if (msg.type === "mission_status") {
        updateMissionBadge(data);
      } else if (msg.type === "mission_step" && data.status) {
        updateMissionBadge(data.status);
      } else if (msg.type === "voice_barge_in") {
        stopAudioOutput();
        bargeInCount = typeof data.barge_in_count === "number" ? data.barge_in_count : bargeInCount + 1;
        if (badgeBargeIn) {
          badgeBargeIn.textContent = `Barge-In: ${bargeInCount}`;
          badgeBargeIn.classList.add("status-flash");
          setTimeout(() => badgeBargeIn.classList.remove("status-flash"), 1600);
        }
      } else if (msg.type === "audio_chunk") {
        const b64 = data.audio_b64 || data.audio || data.data || data.chunk;
        if (b64) enqueueAudioChunk(b64);
      } else if (msg.type === "stt_partial") {
        const txt = data.text || data.transcript || "";
        if (txt) setFeedback(`🎙️ "${txt}"`);
      } else if (msg.type === "stt_final") {
        const txt = data.text || data.transcript || "";
        if (txt) setFeedback(`✅ Sent: "${txt}"`);
      }
    };
  }

  function sendWs(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
      return true;
    }
    setFeedback("⚠️ WebSocket offline — reconnecting...");
    return false;
  }

  // --- Button Handlers ---
  if (btnSaveToken) {
    btnSaveToken.addEventListener("click", () => {
      const val = deckTokenInput ? deckTokenInput.value.trim() : "";
      if (!val) return;
      try { localStorage.setItem(CREATOR_TOKEN_KEY, val); } catch (e) {}
      if (deckAuthBar) deckAuthBar.style.display = "none";
      if (ws) try { ws.close(); } catch (e) {}
      connectWs();
      setFeedback("🔑 Creator token saved.");
    });
  }

  if (btnBargeIn) {
    btnBargeIn.addEventListener("click", () => {
      stopAudioOutput();
      if (sendWs({ type: "barge_in", reason: "creator_deck" })) {
        setFeedback("⚡ Barge-In triggered!");
      }
    });
  }

  if (btnMic) {
    btnMic.addEventListener("click", () => {
      if (isMicActive) stopDeckMic();
      else startDeckMic();
    });
  }

  if (btnMute) {
    btnMute.addEventListener("click", () => {
      audioMuted = !audioMuted;
      if (audioMuted) stopAudioOutput();
      else ensureAudioContext();
      btnMute.classList.toggle("is-muted", audioMuted);
      if (deckMuteIcon) deckMuteIcon.textContent = audioMuted ? "🔇" : "🔊";
      if (deckMuteLabel) deckMuteLabel.textContent = audioMuted ? "Audio: MUTED" : "Audio: ON";
      setFeedback(audioMuted ? "🔇 Browser audio muted." : "🔊 Browser audio unmuted.");
    });
  }

  if (btnMissionStep) {
    btnMissionStep.addEventListener("click", async () => {
      setFeedback("⏩ Running mission step...");
      try {
        const res = await authFetch("/api/missions/step", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "step" })
        });
        if (res.ok) {
          const data = await res.json();
          if (data.status) updateMissionBadge(data.status);
          setFeedback(`⏩ Mission step: ${data.status_text || data.result || "executed"}`);
        } else {
          sendWs({ type: "mission_action", action: "step" });
        }
      } catch (e) {
        sendWs({ type: "mission_action", action: "step" });
      }
    });
  }

  if (btnMissionLoop) {
    btnMissionLoop.addEventListener("click", async () => {
      try {
        const res = await authFetch("/api/missions/toggle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: !missionLoopActive })
        });
        if (res.ok) {
          const data = await res.json();
          updateMissionBadge(data.status || data);
          setFeedback(missionLoopActive ? "▶ Mission loop started." : "⏸ Mission loop paused.");
        } else {
          sendWs({ type: "mission_action", action: "toggle" });
        }
      } catch (e) {
        sendWs({ type: "mission_action", action: "toggle" });
      }
    });
  }

  if (btnSing) {
    btnSing.addEventListener("click", async () => {
      setFeedback("🎵 Starting AI Idol performance...");
      try {
        const res = await authFetch("/api/performance/start", { method: "POST" });
        if (res.ok) setFeedback("🎵 Singing started!");
      } catch (e) {}
    });
  }

  if (btnImprov) {
    btnImprov.addEventListener("click", () => {
      if (sendWs({ type: "trigger_improv" })) {
        setFeedback("🎭 Improv triggered!");
      }
    });
  }

  if (btnCollab) {
    btnCollab.addEventListener("click", () => {
      if (!collabDrawer) return;
      const open = collabDrawer.style.display === "flex";
      collabDrawer.style.display = open ? "none" : "flex";
      if (!open && collabTopicInput) collabTopicInput.focus();
    });
  }

  if (btnCancelCollabTopic) {
    btnCancelCollabTopic.addEventListener("click", () => {
      if (collabDrawer) collabDrawer.style.display = "none";
    });
  }

  if (btnSendCollabTopic) {
    btnSendCollabTopic.addEventListener("click", async () => {
      const topic = collabTopicInput ? collabTopicInput.value.trim() : "";
      if (!topic) return;
      try {
        const res = await authFetch("/api/collab/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "initiate", topic, prompt: topic })
        });
        if (res.ok) {
          setFeedback(`🤝 Collab topic sent: "${topic}"`);
          if (collabTopicInput) collabTopicInput.value = "";
          if (collabDrawer) collabDrawer.style.display = "none";
        }
      } catch (e) {}
    });
  }

  if (btnStopSpeech) {
    btnStopSpeech.addEventListener("click", () => {
      stopAudioOutput();
      if (sendWs({ type: "barge_in", reason: "stop_speech" })) {
        setFeedback("🛑 Speech & singing stopped.");
      }
    });
  }

  connectWs();
});
