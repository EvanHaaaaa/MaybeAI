// MaybeAI Mobile/Tablet Creator Stream Deck
document.addEventListener("DOMContentLoaded", () => {
  const clientLib = window.MaybeAIClient || {};
  const CreatorAuth = clientLib.CreatorAuth;
  const CREATOR_TOKEN_KEY = (CreatorAuth && CreatorAuth.TOKEN_KEY) || "maybeai_creator_token";

  function getCreatorToken() {
    if (CreatorAuth && typeof CreatorAuth.getToken === "function") {
      return CreatorAuth.getToken();
    }
    try {
      const params = new URLSearchParams(window.location.search);
      const hasTokenParam = params.has("token");
      const urlToken = params.get("token");
      if (hasTokenParam && window.history && typeof window.history.replaceState === "function") {
        try {
          const nextUrl = new URL(window.location.href);
          nextUrl.searchParams.delete("token");
          const cleanPath = nextUrl.pathname + (nextUrl.searchParams.toString() ? `?${nextUrl.searchParams.toString()}` : "") + (nextUrl.hash || "");
          window.history.replaceState(null, "", cleanPath);
        } catch (e) {}
      }
      if (urlToken && urlToken.trim()) {
        const clean = urlToken.trim();
        try { localStorage.removeItem(CREATOR_TOKEN_KEY); } catch (e) {}
        try { sessionStorage.setItem(CREATOR_TOKEN_KEY, clean); } catch (e) {}
        return clean;
      }
    } catch (e) {}
    try {
      return sessionStorage.getItem(CREATOR_TOKEN_KEY) || "";
    } catch (e) {
      return "";
    }
  }

  getCreatorToken();

  function authFetch(url, options = {}) {
    if (CreatorAuth && typeof CreatorAuth.authFetch === "function") {
      return CreatorAuth.authFetch(url, options);
    }
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
  const deckScenePill = document.getElementById("deck-scene-pill");
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

  let wsClient = null;
  let binaryPcmEnabled = clientLib.binaryPcm !== false;
  let bargeInCount = 0;
  let missionLoopActive = false;
  let audioMuted = false;

  function sendAudioPcmFrame(buffer) {
    if (!buffer || !wsClient || !wsClient.isOpen) return;
    if (binaryPcmEnabled) {
      try {
        const pcmView = buffer instanceof Int16Array ? buffer : new Int16Array(buffer);
        if (wsClient.send(pcmView)) return;
      } catch (e) {
        binaryPcmEnabled = false;
      }
    }
    wsClient.send(JSON.stringify({
      type: "voice_audio_chunk",
      audio_b64: arrayBufferToBase64(buffer),
      sample_rate: 16000,
      user: "Creator"
    }));
  }

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
          if ((!isMicActive && !(event.data && event.data.final)) || !event.data || event.data.type !== "pcm16") return;
          sendAudioPcmFrame(event.data.buffer);
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
      if (finalTxt.trim() && wsClient && wsClient.isOpen) {
        wsClient.send(JSON.stringify({ type: "chat_message", user: "Creator", text: finalTxt.trim(), source: "mic", is_creator: true }));
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
    const node = micWorkletNode;
    const ctx = micWorkletCtx;
    micWorkletNode = null;
    micWorkletCtx = null;
    if (node) {
      try { node.port.postMessage({ type: "stop" }); } catch (e) {}
      setTimeout(() => {
        try { node.disconnect(); } catch (e) {}
        if (ctx) {
          try { ctx.close(); } catch (e) {}
        }
      }, 60);
    } else if (ctx) {
      try { ctx.close(); } catch (e) {}
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
      const [mRes, vRes, oRes] = await Promise.all([
        authFetch("/api/missions/status"),
        authFetch("/api/voice/status"),
        authFetch("/api/obs/status")
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
      if (oRes.ok && deckScenePill) {
        const oData = await oRes.json();
        const scene = oData.current_scene || oData.scene || "Standby";
        deckScenePill.textContent = `Scene: ${scene}`;
      }
    } catch (e) {}
  }

  function buildDeckWsUrl() {
    if (CreatorAuth && typeof CreatorAuth.buildWsUrl === "function") {
      return CreatorAuth.buildWsUrl("/ws");
    }
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/ws`;
  }

  function connectWs() {
    const onMessage = (event) => {
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
      } else if (msg.type === "obs_scene_changed") {
        const scene = data.scene || data.scene_name || data.current_scene || "Standby";
        if (deckScenePill) deckScenePill.textContent = `Scene: ${scene}`;
      } else if (msg.type === "highlight_marked") {
        setFeedback(`📸 Highlight marked: ${data.reason || data.label || "manual"}`);
      }
    };

    if (clientLib.ReconnectingWebSocket) {
      wsClient = new clientLib.ReconnectingWebSocket(buildDeckWsUrl, {
        minDelayMs: 1000,
        maxDelayMs: 30000,
        onopen: () => {
          if (badgeWs) {
            badgeWs.textContent = "WS: Online";
            badgeWs.className = "status-pill status-online";
          }
          refreshStatus();
        },
        onclose: () => {
          if (badgeWs) {
            badgeWs.textContent = "WS: Reconnecting";
            badgeWs.className = "status-pill status-offline";
          }
        },
        onmessage: onMessage
      });
      wsClient.connect();
      return;
    }

    const token = getCreatorToken();
    const protocols = token ? [`maybeai.token.${token}`] : [];
    const rawWs = protocols.length > 0 ? new WebSocket(buildDeckWsUrl(), protocols) : new WebSocket(buildDeckWsUrl());
    wsClient = {
      get isOpen() { return rawWs.readyState === WebSocket.OPEN; },
      send(d) {
        if (rawWs.readyState === WebSocket.OPEN) { rawWs.send(d); return true; }
        return false;
      },
      reconnectNow() {
        try { rawWs.close(); } catch (e) {}
        connectWs();
      }
    };
    rawWs.onopen = () => {
      if (badgeWs) {
        badgeWs.textContent = "WS: Online";
        badgeWs.className = "status-pill status-online";
      }
      refreshStatus();
    };
    rawWs.onclose = () => {
      if (badgeWs) {
        badgeWs.textContent = "WS: Reconnecting";
        badgeWs.className = "status-pill status-offline";
      }
      setTimeout(connectWs, 2000);
    };
    rawWs.onerror = () => { try { rawWs.close(); } catch (e) {} };
    rawWs.onmessage = onMessage;
  }

  function sendWs(payload) {
    if (wsClient && wsClient.send(JSON.stringify(payload))) {
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
      if (CreatorAuth && typeof CreatorAuth.setToken === "function") {
        CreatorAuth.setToken(val);
      } else {
        try { localStorage.removeItem(CREATOR_TOKEN_KEY); } catch (e) {}
        try { sessionStorage.setItem(CREATOR_TOKEN_KEY, val); } catch (e) {}
      }
      if (deckAuthBar) deckAuthBar.style.display = "none";
      if (wsClient && typeof wsClient.reconnectNow === "function") {
        wsClient.reconnectNow();
      } else {
        connectWs();
      }
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

  const btnMarkHighlight = document.getElementById("btn-deck-mark-highlight");
  if (btnMarkHighlight) {
    btnMarkHighlight.addEventListener("click", async () => {
      setFeedback("📸 Marking highlight...");
      try {
        const res = await authFetch("/api/highlights/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "mark", reason: "stream_deck", source: "deck" })
        });
        if (res.ok) {
          setFeedback("📸 Highlight marked!");
        } else {
          setFeedback("⚠️ Failed to mark highlight.");
        }
      } catch (e) {
        setFeedback("⚠️ Network error marking highlight.");
      }
    });
  }

  connectWs();
});
