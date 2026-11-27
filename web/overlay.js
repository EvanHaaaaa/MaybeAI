// MaybeAI Dedicated OBS Stage Overlay
// Transparent Browser Source renderer: Virtual Avatar, Floating Subtitles & Donation Alerts
document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.getElementById("avatarCanvas");
  const ctx = canvas ? canvas.getContext("2d") : null;
  const vrmContainer = document.getElementById("vrmContainer");
  const subtitlesEl = document.getElementById("subtitles");

  const donationAlertBanner = document.getElementById("donation-alert-banner");
  const donUser = document.getElementById("don-user");
  const donAmount = document.getElementById("don-amount");
  const donText = document.getElementById("don-text");

  // Query parameter flags (?hide_avatar=1, ?hide_subs=1, ?muted=1)
  const initialParams = new URLSearchParams(window.location.search);
  const isTruthyParam = (val) => val === "1" || val === "true" || val === "yes";
  if (isTruthyParam(initialParams.get("hide_avatar"))) {
    document.body.classList.add("hide-avatar");
  }
  if (isTruthyParam(initialParams.get("hide_subs"))) {
    document.body.classList.add("hide-subs");
  }
  const browserAudioEnabled = !isTruthyParam(initialParams.get("muted"));
  const requestedRenderer = (initialParams.get("renderer") || "2d").toLowerCase();
  const requestedVrmUrl = (initialParams.get("vrm_url") || "").trim();
  let latestVtsParams = null;
  let vrmInstance = null;
  let vrmRenderer = null;
  let vrmScene = null;
  let vrmCamera = null;
  let vrmLoaded = false;

  // Web Audio API FIFO Queue + AnalyserNode RMS Lip-Sync (unmuted by default for OBS)
  let audioCtx = null;
  let audioAnalyser = null;
  let audioAnalyserData = null;
  const audioQueue = [];
  let isPlayingAudioQueue = false;
  let isLocalAudioPlaying = false;
  let currentAudioSource = null;
  let audioLipSyncRaf = null;

  function ensureAudioContext() {
    if (!browserAudioEnabled) return null;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return null;
    if (!audioCtx) {
      audioCtx = new AudioCtx();
      audioAnalyser = audioCtx.createAnalyser();
      audioAnalyser.fftSize = 256;
      audioAnalyserData = new Uint8Array(audioAnalyser.frequencyBinCount);
      audioAnalyser.connect(audioCtx.destination);
    }
    if (audioCtx.state === "suspended") {
      audioCtx.resume().catch(() => {});
    }
    return audioCtx;
  }

  if (browserAudioEnabled) {
    const resumeOnce = () => {
      if (audioCtx && audioCtx.state === "suspended") {
        audioCtx.resume().catch(() => {});
      }
    };
    window.addEventListener("pointerdown", resumeOnce, { once: true });
    window.addEventListener("keydown", resumeOnce, { once: true });
  }

  function decodeBase64ToArrayBuffer(b64) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  }

  function updateAudioLipSync() {
    if (!isPlayingAudioQueue || !audioAnalyser || !audioAnalyserData) {
      audioLipSyncRaf = null;
      return;
    }
    audioAnalyser.getByteTimeDomainData(audioAnalyserData);
    let sumSq = 0;
    for (let i = 0; i < audioAnalyserData.length; i++) {
      const sample = (audioAnalyserData[i] - 128) / 128;
      sumSq += sample * sample;
    }
    const rms = Math.sqrt(sumSq / audioAnalyserData.length);
    targetMouthOpen = Math.min(1.0, Math.max(0.0, rms * 5.0));
    audioLipSyncRaf = requestAnimationFrame(updateAudioLipSync);
  }

  function playNextAudioChunk() {
    if (!browserAudioEnabled || isPlayingAudioQueue || audioQueue.length === 0) return;
    const ctxAudio = ensureAudioContext();
    if (!ctxAudio || !audioAnalyser) return;

    const buffer = audioQueue.shift();
    const source = ctxAudio.createBufferSource();
    source.buffer = buffer;
    source.connect(audioAnalyser);

    currentAudioSource = source;
    isPlayingAudioQueue = true;

    source.onended = () => {
      if (currentAudioSource === source) {
        currentAudioSource = null;
      }
      isPlayingAudioQueue = false;
      if (audioQueue.length > 0 && browserAudioEnabled) {
        playNextAudioChunk();
      } else {
        isLocalAudioPlaying = false;
        targetMouthOpen = 0.0;
      }
    };

    try {
      source.start(0);
      isLocalAudioPlaying = true;
      if (!audioLipSyncRaf) {
        audioLipSyncRaf = requestAnimationFrame(updateAudioLipSync);
      }
    } catch (e) {
      isPlayingAudioQueue = false;
      isLocalAudioPlaying = audioQueue.length > 0 && browserAudioEnabled;
      currentAudioSource = null;
      if (!isLocalAudioPlaying) {
        targetMouthOpen = 0.0;
      }
    }
  }

  async function enqueueAudioChunk(b64) {
    if (!browserAudioEnabled || !b64) return;
    const ctxAudio = ensureAudioContext();
    if (!ctxAudio) return;
    try {
      const arrayBuf = decodeBase64ToArrayBuffer(b64);
      const decoded = await ctxAudio.decodeAudioData(arrayBuf);
      audioQueue.push(decoded);
      playNextAudioChunk();
    } catch (e) {}
  }

  function stopBrowserAudioOutput() {
    audioQueue.length = 0;
    isPlayingAudioQueue = false;
    isLocalAudioPlaying = false;
    if (audioLipSyncRaf) {
      cancelAnimationFrame(audioLipSyncRaf);
      audioLipSyncRaf = null;
    }
    if (currentAudioSource) {
      try { currentAudioSource.onended = null; currentAudioSource.stop(); } catch (e) {}
      currentAudioSource = null;
    }
    targetMouthOpen = 0.0;
    mouthOpen = 0.0;
  }

  // Avatar animation state
  let mouthOpen = 0.0;
  let targetMouthOpen = 0.0;
  let emotion = "neutral";
  let eyeBlink = 0.0;
  let blinkTimer = 0;
  let headTilt = 0.0;
  let time = 0;
  let isSinging = false;
  const musicNotes = [];

  // UI timers
  let donationTimer = null;
  let subtitleTimer = null;

  // --- WebSocket Connection (supports ?token= and exponential backoff reconnect) ---
  const clientLib = window.MaybeAIClient || {};
  const CreatorAuth = clientLib.CreatorAuth;
  let wsClient = null;

  function buildOverlayWsUrl() {
    if (CreatorAuth && typeof CreatorAuth.buildWsUrl === "function") {
      return CreatorAuth.buildWsUrl("/ws");
    }
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const urlParams = new URLSearchParams(window.location.search);
    const urlToken = urlParams.get("token");
    let storedToken = null;
    try {
      storedToken = localStorage.getItem("maybeai_creator_token") || null;
    } catch (e) {}
    const token = urlToken || storedToken;
    let wsUrl = `${protocol}//${window.location.host}/ws`;
    if (token) {
      wsUrl += `?token=${encodeURIComponent(token)}`;
    }
    return wsUrl;
  }

  function resyncOverlayState() {
    if (!isLocalAudioPlaying) {
      targetMouthOpen = 0.0;
    }
    if (wsClient && wsClient.isOpen) {
      wsClient.send(JSON.stringify({ type: "request_state", scope: "overlay" }));
    }
    const fetcher = CreatorAuth && CreatorAuth.authFetch ? (u, o) => CreatorAuth.authFetch(u, o) : fetch;
    fetcher("/api/voice/status").then((res) => {
      if (!res.ok) return null;
      return res.json();
    }).then((vst) => {
      if (!vst || typeof vst !== "object") return;
      if (vst.emotion) setEmotion(vst.emotion);
      if (typeof vst.is_singing === "boolean") {
        isSinging = vst.is_singing;
        if (subtitlesEl) subtitlesEl.classList.toggle("is-singing", isSinging);
      }
    }).catch(() => {});
  }

  function connectWs() {
    if (clientLib.ReconnectingWebSocket) {
      wsClient = new clientLib.ReconnectingWebSocket(buildOverlayWsUrl, {
        minDelayMs: 1000,
        maxDelayMs: 30000,
        onopen: () => {
          resyncOverlayState();
        },
        onmessage: handleWsMessage
      });
      wsClient.connect();
      return;
    }
    const ws = new WebSocket(buildOverlayWsUrl());
    ws.onopen = () => {
      if (!isLocalAudioPlaying) targetMouthOpen = 0.0;
      try { ws.send(JSON.stringify({ type: "request_state", scope: "overlay" })); } catch (e) {}
    };
    ws.onclose = () => {
      setTimeout(connectWs, 2000);
    };
    ws.onerror = () => {
      try { ws.close(); } catch (e) {}
    };
    ws.onmessage = handleWsMessage;
  }

  function handleWsMessage(event) {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (e) {
      return;
    }

    const data = msg.data || {};

    if (msg.type === "avatar_state") {
      if (!isLocalAudioPlaying) {
        targetMouthOpen = data.mouth_open || 0.0;
      }
      if (data.vts_params && typeof data.vts_params === "object") {
        latestVtsParams = data.vts_params;
      }
      if (data.emotion) {
        setEmotion(data.emotion);
      }
      if (data.is_singing !== undefined) {
        isSinging = Boolean(data.is_singing);
        if (subtitlesEl) {
          subtitlesEl.classList.toggle("is-singing", isSinging);
        }
      }
    } else if (msg.type === "ai_response") {
      if (data.speech) {
        showSubtitle(`"${data.speech}"`, false, 10000);
      }
      if (Array.isArray(data.emotions) && data.emotions.length > 0) {
        setEmotion(data.emotions[0]);
      }
    } else if (msg.type === "ai_chunk") {
      if (data.chunk) {
        showSubtitle(`"${data.chunk}"`, false, 10000);
      }
      if (data.emotion) {
        setEmotion(data.emotion);
      }
    } else if (msg.type === "audio_chunk") {
      const b64 = data.audio_b64 || data.audio || data.data || data.chunk;
      if (b64) {
        enqueueAudioChunk(b64);
      }
    } else if (msg.type === "voice_barge_in") {
      isSinging = false;
      stopBrowserAudioOutput();
      if (subtitlesEl) {
        subtitlesEl.classList.remove("is-singing");
      }
    } else if (msg.type === "donation_received") {
      showDonationAlert(data.user || "Viewer", data.amount || "", data.text || "");
    } else if (msg.type === "song_started") {
      isSinging = true;
      showSubtitle(`🎵 Playing: "${data.title || "Live Song"}" 🎵`, true, 0);
    } else if (msg.type === "lyric_line") {
      isSinging = true;
      showSubtitle(`♪ ${data.text || ""} ♪`, true, 0);
      if (data.emotion) {
        setEmotion(data.emotion);
      }
      spawnMusicNote();
    } else if (msg.type === "song_ended") {
      isSinging = false;
      if (subtitlesEl) {
        subtitlesEl.classList.remove("is-singing");
      }
      scheduleSubtitleHide(4000);
    } else if (msg.type === "mood_updated") {
      if (data.mood) {
        setEmotion(data.mood);
      }
    } else if (msg.type === "avatar_movement") {
      applyChoreography(data.movement);
    }
  }

  function setEmotion(newEmotion) {
    if (!newEmotion) return;
    emotion = String(newEmotion).toLowerCase();
    if (emotion === "smug") headTilt = -0.1;
    else if (emotion === "confused") headTilt = 0.15;
    else if (emotion === "angry") headTilt = 0.05;
    else headTilt = 0.0;
  }

  function applyChoreography(movement) {
    if (movement === "sway_left") headTilt = -0.06;
    else if (movement === "sway_right") headTilt = 0.06;
    else if (movement === "bounce") headTilt = 0.0;
    else if (movement === "head_tilt") headTilt = 0.1;
    else if (movement === "sparkle_pose") headTilt = -0.04;
  }

  function showSubtitle(text, singingMode = false, autoHideMs = 10000) {
    if (!subtitlesEl) return;
    subtitlesEl.textContent = text;
    subtitlesEl.classList.remove("is-hidden");
    subtitlesEl.classList.toggle("is-singing", singingMode);

    if (subtitleTimer) {
      clearTimeout(subtitleTimer);
      subtitleTimer = null;
    }
    if (autoHideMs > 0) {
      scheduleSubtitleHide(autoHideMs);
    }
  }

  function scheduleSubtitleHide(delayMs) {
    if (subtitleTimer) clearTimeout(subtitleTimer);
    subtitleTimer = setTimeout(() => {
      if (!isSinging && subtitlesEl) {
        subtitlesEl.classList.add("is-hidden");
      }
    }, delayMs);
  }

  function showDonationAlert(user, amount, text) {
    if (!donationAlertBanner) return;
    if (donUser) donUser.textContent = user;
    if (donAmount) donAmount.textContent = amount;
    if (donText) donText.textContent = text ? `"${text}"` : "";

    // Restart slide-in animation cleanly for back-to-back alerts
    donationAlertBanner.style.display = "none";
    void donationAlertBanner.offsetWidth;
    donationAlertBanner.style.display = "flex";

    if (donationTimer) clearTimeout(donationTimer);
    donationTimer = setTimeout(() => {
      donationAlertBanner.style.display = "none";
    }, 6000);
  }

  // --- 2D Animated Avatar Renderer ---
  const NOTE_CHARS = ["♪", "♫", "♬", "♩"];

  function spawnMusicNote() {
    if (!canvas) return;
    musicNotes.push({
      x: canvas.width / 2 + (Math.random() - 0.5) * 200,
      y: canvas.height / 2 + 50,
      vx: (Math.random() - 0.5) * 1.5,
      vy: -1.2 - Math.random() * 1.8,
      char: NOTE_CHARS[Math.floor(Math.random() * NOTE_CHARS.length)],
      opacity: 1.0,
      size: 18 + Math.random() * 14,
      color: Math.random() > 0.5 ? "#ff4d8d" : "#00f0ff"
    });
  }

  function drawEye(x, y, scaleY) {
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(1, Math.max(0.08, scaleY));

    // Eye white
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.ellipse(0, 0, 17, 24, 0, 0, Math.PI * 2);
    ctx.fill();

    // Iris
    ctx.fillStyle = "#00f0ff";
    ctx.beginPath();
    ctx.ellipse(0, 2, 12, 18, 0, 0, Math.PI * 2);
    ctx.fill();

    // Pupil
    ctx.fillStyle = "#112233";
    ctx.beginPath();
    ctx.arc(0, 2, 6, 0, Math.PI * 2);
    ctx.fill();

    // Catchlight
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(-4, -4, 4, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
  }

  function drawEyebrows() {
    ctx.strokeStyle = "#5a4d70";
    ctx.lineWidth = 3.5;
    ctx.lineCap = "round";

    let leftAngle = 0;
    let rightAngle = 0;

    if (emotion === "smug") {
      leftAngle = -0.15;
      rightAngle = 0.1;
    } else if (emotion === "angry") {
      leftAngle = 0.25;
      rightAngle = -0.25;
    } else if (emotion === "confused") {
      leftAngle = -0.2;
      rightAngle = 0.2;
    }

    // Left Brow
    ctx.beginPath();
    ctx.moveTo(-50, -38 + leftAngle * 20);
    ctx.quadraticCurveTo(-35, -45 - leftAngle * 10, -20, -38);
    ctx.stroke();

    // Right Brow
    ctx.beginPath();
    ctx.moveTo(20, -38);
    ctx.quadraticCurveTo(35, -45 - rightAngle * 10, 50, -38 + rightAngle * 20);
    ctx.stroke();
  }

  function drawMouth() {
    const openH = Math.max(2, mouthOpen * 28);
    const width = 22 + (emotion === "happy" || emotion === "smug" ? 8 : 0);

    ctx.save();
    ctx.translate(0, 36);

    if (openH > 5) {
      // Open mouth (speaking)
      ctx.fillStyle = "#cc3355";
      ctx.beginPath();
      ctx.ellipse(0, 0, width / 2, openH / 2, 0, 0, Math.PI * 2);
      ctx.fill();

      // Tongue
      ctx.fillStyle = "#ff75a0";
      ctx.beginPath();
      ctx.ellipse(0, openH / 4, width / 3, openH / 4, 0, 0, Math.PI);
      ctx.fill();

      // Teeth
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(-width / 3, -openH / 2, (width * 2) / 3, openH * 0.35);
    } else {
      // Closed mouth
      ctx.strokeStyle = "#803040";
      ctx.lineWidth = 3;
      ctx.lineCap = "round";
      ctx.beginPath();
      if (emotion === "smug" || emotion === "happy") {
        ctx.arc(0, -6, 12, 0.2 * Math.PI, 0.8 * Math.PI);
      } else if (emotion === "angry") {
        ctx.arc(0, 10, 10, 1.2 * Math.PI, 1.8 * Math.PI);
      } else {
        ctx.moveTo(-8, 0);
        ctx.lineTo(8, 0);
      }
      ctx.stroke();
    }

    ctx.restore();
  }

  function drawHair() {
    ctx.fillStyle = "#aa9ec2";

    // Center Bangs
    ctx.beginPath();
    ctx.moveTo(0, -85);
    ctx.quadraticCurveTo(-15, -40, -10, -15);
    ctx.quadraticCurveTo(-5, -35, 0, -20);
    ctx.quadraticCurveTo(5, -35, 10, -15);
    ctx.quadraticCurveTo(15, -40, 0, -85);
    ctx.fill();

    // Left Bangs
    ctx.beginPath();
    ctx.moveTo(-50, -70);
    ctx.quadraticCurveTo(-80, -20, -75, 45);
    ctx.quadraticCurveTo(-60, 0, -45, -30);
    ctx.fill();

    // Right Bangs
    ctx.beginPath();
    ctx.moveTo(50, -70);
    ctx.quadraticCurveTo(80, -20, 75, 45);
    ctx.quadraticCurveTo(60, 0, 45, -30);
    ctx.fill();

    // Hair Ribbons / Clips
    ctx.fillStyle = "#ff4d8d";
    ctx.fillRect(-65, -60, 14, 8);
    ctx.fillRect(51, -60, 14, 8);
  }

  function render() {
    if (!ctx || !canvas) return;

    time += 0.03;

    // Smooth mouth interpolation
    mouthOpen += (targetMouthOpen - mouthOpen) * 0.4;

    // Blink timer
    blinkTimer += 1;
    if (blinkTimer > 180 + Math.random() * 80) {
      eyeBlink = 1.0;
      blinkTimer = 0;
    }
    eyeBlink = Math.max(0, eyeBlink - 0.15);

    // Clear canvas (stays fully transparent for OBS)
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2 + Math.sin(time) * 4;

    ctx.save();
    ctx.translate(centerX, centerY);
    ctx.rotate(headTilt + Math.sin(time * 0.5) * 0.02);

    // 1. Hair Back
    ctx.fillStyle = "#8a7ba7";
    ctx.beginPath();
    ctx.arc(0, -20, 115, 0, Math.PI * 2);
    ctx.fill();

    // 2. Neck
    ctx.fillStyle = "#ffe0d6";
    ctx.fillRect(-22, 50, 44, 45);

    // 3. Body / Clothes
    ctx.fillStyle = "#2d2338";
    ctx.beginPath();
    ctx.moveTo(-70, 150);
    ctx.lineTo(70, 150);
    ctx.lineTo(40, 85);
    ctx.lineTo(-40, 85);
    ctx.closePath();
    ctx.fill();

    // Tie / Collar
    ctx.fillStyle = "#ff4d8d";
    ctx.beginPath();
    ctx.moveTo(0, 95);
    ctx.lineTo(-12, 130);
    ctx.lineTo(0, 145);
    ctx.lineTo(12, 130);
    ctx.closePath();
    ctx.fill();

    // 4. Face Base
    ctx.fillStyle = "#fff0eb";
    ctx.beginPath();
    ctx.arc(0, 0, 85, 0, Math.PI * 2);
    ctx.fill();

    // 5. Blush
    if (emotion === "blush" || emotion === "happy" || emotion === "smug") {
      ctx.fillStyle = "rgba(255, 77, 141, 0.4)";
      ctx.beginPath();
      ctx.ellipse(-48, 18, 16, 9, 0, 0, Math.PI * 2);
      ctx.ellipse(48, 18, 16, 9, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    // 6. Eyes & Eyebrows
    const eyeScaleY = 1.0 - eyeBlink;
    drawEye(-35, -5, eyeScaleY);
    drawEye(35, -5, eyeScaleY);
    drawEyebrows();

    // 7. Mouth
    drawMouth();

    // 8. Front Hair / Bangs
    drawHair();

    ctx.restore();

    // 9. Floating Karaoke Musical Notes
    if (isSinging && Math.random() < 0.1) {
      spawnMusicNote();
    }
    for (let i = musicNotes.length - 1; i >= 0; i--) {
      const n = musicNotes[i];
      n.x += n.vx;
      n.y += n.vy;
      n.opacity -= 0.015;

      ctx.save();
      ctx.globalAlpha = Math.max(0, n.opacity);
      ctx.fillStyle = n.color;
      ctx.font = `bold ${n.size}px sans-serif`;
      ctx.fillText(n.char, n.x, n.y);
      ctx.restore();

      if (n.opacity <= 0) {
        musicNotes.splice(i, 1);
      }
    }

    if (vrmLoaded && vrmInstance && vrmRenderer && vrmScene && vrmCamera) {
      const em = vrmInstance.expressionManager;
      if (em) {
        em.setValue("aa", Math.max(0, Math.min(1, mouthOpen)));
        em.setValue("blink", Math.max(0, Math.min(1, eyeBlink)));
        const emoMap = {
          happy: "happy",
          excited: "happy",
          sad: "sad",
          angry: "angry",
          annoyed: "angry",
          surprised: "surprised",
          smug: "relaxed",
          blush: "happy"
        };
        ["happy", "sad", "angry", "surprised", "relaxed"].forEach((k) => {
          em.setValue(k, emoMap[emotion] === k ? 0.85 : 0.0);
        });
      }
      const head = vrmInstance.humanoid && vrmInstance.humanoid.getNormalizedBoneNode("head");
      if (head) {
        const vp = latestVtsParams || {};
        const degToRad = Math.PI / 180;
        const yaw = Number.isFinite(Number(vp.FaceAngleX)) ? Number(vp.FaceAngleX) * degToRad * 0.5 : Math.sin(time * 0.8) * 0.05;
        const pitch = Number.isFinite(Number(vp.FaceAngleY)) ? Number(vp.FaceAngleY) * degToRad * 0.4 : 0;
        const roll = Number.isFinite(Number(vp.FaceAngleZ)) ? Number(vp.FaceAngleZ) * degToRad * 0.4 : headTilt;
        head.rotation.set(pitch, yaw, roll);
      }
      vrmInstance.update(0.016);
      vrmRenderer.render(vrmScene, vrmCamera);
    }

    requestAnimationFrame(render);
  }

  async function initOverlayVrm() {
    if (requestedRenderer !== "vrm" || !requestedVrmUrl || !vrmContainer) return;
    try {
      const [THREE, vrmMod] = await Promise.all([
        import("/static/vendor/three.module.js"),
        import("/static/vendor/three-vrm.module.js")
      ]);
      const GLTFLoader = vrmMod.GLTFLoader || THREE.GLTFLoader;
      vrmRenderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
      vrmRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      vrmRenderer.setSize(480, 480);
      vrmContainer.innerHTML = "";
      vrmContainer.appendChild(vrmRenderer.domElement);

      vrmScene = new THREE.Scene();
      vrmCamera = new THREE.PerspectiveCamera(30, 1, 0.1, 20);
      vrmCamera.position.set(0, 1.35, 1.45);
      const light = new THREE.DirectionalLight(0xffffff, 1.4);
      light.position.set(1, 2, 2);
      vrmScene.add(light);
      vrmScene.add(new THREE.AmbientLight(0xffffff, 0.7));

      const loader = new GLTFLoader();
      loader.register((parser) => new vrmMod.VRMLoaderPlugin(parser));
      const gltf = await loader.loadAsync(requestedVrmUrl);
      const vrm = gltf.userData && gltf.userData.vrm;
      if (!vrm) throw new Error("Invalid VRM");
      vrmInstance = vrm;
      vrmInstance.scene.rotation.y = Math.PI;
      vrmScene.add(vrmInstance.scene);

      vrmLoaded = true;
      if (canvas) canvas.style.display = "none";
      vrmContainer.style.display = "block";
    } catch (e) {
      // Graceful fallback to 2D Canvas
      vrmLoaded = false;
      if (canvas) canvas.style.display = "block";
      if (vrmContainer) vrmContainer.style.display = "none";
    }
  }

  initOverlayVrm();
  connectWs();
  render();
});
