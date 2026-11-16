// MaybeAI Frontend App & Virtual Avatar Renderer
document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.getElementById("avatarCanvas");
  const ctx = canvas.getContext("2d");
  const meterFill = document.getElementById("meter-fill");
  const emotionBadge = document.getElementById("emotion-badge");
  const subtitles = document.getElementById("subtitles");
  const chatHistory = document.getElementById("chatHistory");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const vtsStatus = document.getElementById("vts-status");
  const wsStatus = document.getElementById("ws-status");
  const llmStatus = document.getElementById("llm-status");
  const llmProviderSelect = document.getElementById("llmProviderSelect");
  const convTopicBadge = document.getElementById("conv-topic-badge");
  const convRoleplayBadge = document.getElementById("conv-roleplay-badge");

  // State
  let mouthOpen = 0.0;
  let targetMouthOpen = 0.0;
  let emotion = "neutral";
  let eyeBlink = 0.0;
  let blinkTimer = 0;
  let headTilt = 0;
  let time = 0;
  let isSinging = false;
  let musicNotes = [];

  // --- WebSocket Connection ---
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    wsStatus.textContent = "Connected";
    wsStatus.className = "badge badge-online";
  };

  ws.onclose = () => {
    wsStatus.textContent = "Disconnected";
    wsStatus.className = "badge";
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    if (msg.type === "chat_received") {
      const author = msg.data.source === "minecraft" ? `🎮 [MC] ${msg.data.user}` : msg.data.user;
      addChatMessage(author, msg.data.text, false);
    } else if (msg.type === "ai_response") {
      const author = msg.data.user || "Eve";
      addChatMessage(author, msg.data.speech, true);
      subtitles.textContent = `"${msg.data.speech}"`;
      if (msg.data.emotions && msg.data.emotions.length > 0) {
        setEmotion(msg.data.emotions[0]);
      }
    } else if (msg.type === "avatar_state") {
      targetMouthOpen = msg.data.mouth_open || 0.0;
      if (msg.data.emotion) {
        setEmotion(msg.data.emotion);
      }
      if (msg.data.is_singing !== undefined) {
        isSinging = msg.data.is_singing;
      }
    } else if (msg.type === "song_started") {
      isSinging = true;
      subtitles.textContent = `🎵 Playing: "${msg.data.title}" 🎵`;
      addChatMessage("Eve", `[Singing: ${msg.data.title}]`, true);
    } else if (msg.type === "lyric_line") {
      isSinging = true;
      subtitles.textContent = `♪ ${msg.data.text} ♪`;
      if (msg.data.emotion) {
        setEmotion(msg.data.emotion);
      }
      spawnMusicNote();
    } else if (msg.type === "song_ended") {
      isSinging = false;
    } else if (msg.type === "minecraft_state") {
      updateMinecraftHud(msg.data);
    } else if (msg.type === "conversation_state") {
      updateConversationState(msg.data);
    } else if (msg.type === "llm_provider_changed") {
      const prov = (msg.data.provider || "gemini").toLowerCase();
      if (llmProviderSelect) {
        llmProviderSelect.value = prov;
      }
      if (llmStatus) {
        llmStatus.textContent = `LLM: ${prov.toUpperCase()}`;
        if (prov === "gemini" || prov === "openai") {
          llmStatus.className = "badge badge-accent";
        } else if (prov === "ollama") {
          llmStatus.className = "badge badge-online";
        } else {
          llmStatus.className = "badge";
        }
      }
    }
  };

  // LLM Provider Switcher Listener
  if (llmProviderSelect) {
    llmProviderSelect.addEventListener("change", () => {
      const selected = llmProviderSelect.value;
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "set_llm_provider", provider: selected }));
      }
    });
  }

  function setEmotion(newEmotion) {
    emotion = newEmotion.toLowerCase();
    emotionBadge.textContent = emotion.charAt(0).toUpperCase() + emotion.slice(1);
    if (emotion === "smug") headTilt = -0.1;
    else if (emotion === "confused") headTilt = 0.15;
    else if (emotion === "angry") headTilt = 0.05;
    else headTilt = 0.0;
  }

  function addChatMessage(author, text, isAi = false) {
    const div = document.createElement("div");
    div.className = `chat-msg ${isAi ? "neuro-msg" : ""}`;
    div.innerHTML = `<span class="author">${author}:</span><span class="text">${escapeHtml(text)}</span>`;
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
  }

  function escapeHtml(string) {
    const el = document.createElement("div");
    el.innerText = string;
    return el.innerHTML;
  }

  // --- Chat Submit ---
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    sendMessage("ChatUser", text);
    chatInput.value = "";
  });

  // Quick prompt pills
  document.querySelectorAll(".pill").forEach(pill => {
    pill.addEventListener("click", () => {
      const msg = pill.getAttribute("data-msg");
      sendMessage("ChatUser", msg);
    });
  });

  function sendMessage(user, text) {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "user_message", user: user, text: text }));
    }
  }

  function updateConversationState(state) {
    if (!state) return;
    if (convTopicBadge && state.current_topic) {
      convTopicBadge.textContent = `Topic: ${state.current_topic}`;
    }
    if (convRoleplayBadge) {
      if (state.active_roleplay) {
        convRoleplayBadge.textContent = `🎭 ${state.active_roleplay}`;
        convRoleplayBadge.style.display = "inline-block";
      } else {
        convRoleplayBadge.style.display = "none";
      }
    }
  }

  // --- Minecraft Controls ---
  const mcModeBadge = document.getElementById("mc-mode-badge");
  const mcTimerBadge = document.getElementById("mc-timer-badge");
  const mcHpBadge = document.getElementById("mc-hp-badge");
  const mcPhaseDesc = document.getElementById("mcPhaseDesc");
  const btnMcSantai = document.getElementById("btn-mc-santai");
  const btnMcKompe = document.getElementById("btn-mc-kompe");
  const btnMcNext = document.getElementById("btn-mc-next");

  // Server Manager Elements
  const mcServerSelect = document.getElementById("mcServerSelect");
  const btnMcConnect = document.getElementById("btn-mc-connect");
  const btnMcDisconnect = document.getElementById("btn-mc-disconnect");
  const btnToggleAddServer = document.getElementById("btn-toggle-add-server");
  const btnCancelAddServer = document.getElementById("btn-cancel-add-server");
  const addServerForm = document.getElementById("addServerForm");

  // POV Viewer Elements
  const mcViewerFrame = document.getElementById("mcViewerFrame");
  const mcViewerPlaceholder = document.getElementById("mc-viewer-placeholder");
  const mcViewerBadge = document.getElementById("mc-viewer-badge");
  const btnReloadPov = document.getElementById("btn-reload-pov");
  const btnOpenPovTab = document.getElementById("btn-open-pov-tab");

  function sendMinecraftAction(actionData) {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "minecraft_action", ...actionData }));
    }
  }

  let cachedServersJson = "";

  function updateMinecraftHud(state) {
    // Update Mode
    if (state.mode === "santai") {
      mcModeBadge.textContent = "Mode: Santai (Casual)";
      mcModeBadge.className = "badge badge-online";
      btnMcNext.style.display = "none";
      btnMcSantai.classList.add("active");
      btnMcKompe.classList.remove("active");
      mcPhaseDesc.textContent = "Status: Exploring peacefully & socializing with players.";
    } else if (state.mode === "kompe") {
      mcModeBadge.textContent = "Mode: Kompe (Speedrun)";
      mcModeBadge.className = "badge badge-accent";
      btnMcNext.style.display = "inline-block";
      btnMcKompe.classList.add("active");
      btnMcSantai.classList.remove("active");
      if (state.speedrun) {
        mcTimerBadge.textContent = `⏱️ ${state.speedrun.split_time || "00:00"}`;
        mcPhaseDesc.textContent = `Target: ${state.speedrun.phase_name || "Speedrun"}`;
      }
    }
    mcHpBadge.textContent = `❤️ ${state.health || 20}/20`;

    // Update Server Dropdown
    if (state.servers && JSON.stringify(state.servers) !== cachedServersJson) {
      cachedServersJson = JSON.stringify(state.servers);
      const currentVal = mcServerSelect.value;
      mcServerSelect.innerHTML = "";
      state.servers.forEach(srv => {
        const opt = document.createElement("option");
        opt.value = srv.id;
        opt.textContent = `${srv.name} (${srv.host}:${srv.port})`;
        if (state.active_server && state.active_server.id === srv.id) {
          opt.selected = true;
        }
        mcServerSelect.appendChild(opt);
      });
      if (currentVal && Array.from(mcServerSelect.options).some(o => o.value === currentVal)) {
        mcServerSelect.value = currentVal;
      }
    }

    // Update Connection Status
    if (state.connection_status === "connected") {
      btnMcConnect.textContent = "🟢 In Server";
      btnMcConnect.style.background = "#2e6b38";
      btnMcDisconnect.disabled = false;
    } else {
      btnMcConnect.textContent = "🚀 Join Server";
      btnMcConnect.style.background = "";
      btnMcDisconnect.disabled = true;
    }

    // Update 3D POV Viewer Stream
    if (mcViewerFrame && mcViewerPlaceholder && mcViewerBadge) {
      const isConnected = state.connection_status === "connected";
      const viewerUrl = state.viewer_url || (isConnected ? "http://localhost:3007" : null);

      if (isConnected && viewerUrl) {
        if (!mcViewerFrame.src || mcViewerFrame.src === "about:blank" || (!mcViewerFrame.src.includes(":3007") && mcViewerFrame.src !== viewerUrl)) {
          mcViewerFrame.src = viewerUrl;
        }
        mcViewerFrame.style.display = "block";
        mcViewerPlaceholder.style.display = "none";
        mcViewerBadge.textContent = "🟢 Live 3D POV";
        mcViewerBadge.className = "badge badge-online";
        if (btnOpenPovTab) btnOpenPovTab.href = viewerUrl;
      } else {
        if (mcViewerFrame.src && mcViewerFrame.src !== "about:blank") {
          mcViewerFrame.src = "about:blank";
        }
        mcViewerFrame.style.display = "none";
        mcViewerPlaceholder.style.display = "flex";
        mcViewerBadge.textContent = "Standby";
        mcViewerBadge.className = "badge";
      }
    }
  }

  // Refresh POV View Button
  if (btnReloadPov) {
    btnReloadPov.addEventListener("click", () => {
      if (mcViewerFrame && mcViewerFrame.style.display !== "none") {
        const curSrc = mcViewerFrame.src || "http://localhost:3007";
        mcViewerFrame.src = "about:blank";
        setTimeout(() => {
          mcViewerFrame.src = curSrc;
        }, 150);
      }
    });
  }

  // Server Action Listeners
  btnMcConnect.addEventListener("click", () => {
    const srvId = mcServerSelect.value;
    sendMinecraftAction({ action: "connect_server", server_id: srvId });
  });

  btnMcDisconnect.addEventListener("click", () => {
    sendMinecraftAction({ action: "disconnect_server" });
  });

  btnToggleAddServer.addEventListener("click", () => {
    addServerForm.style.display = addServerForm.style.display === "none" ? "flex" : "none";
  });

  btnCancelAddServer.addEventListener("click", () => {
    addServerForm.style.display = "none";
  });

  addServerForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const name = document.getElementById("newSrvName").value;
    const host = document.getElementById("newSrvHost").value;
    const port = document.getElementById("newSrvPort").value;
    const version = document.getElementById("newSrvVersion").value;

    sendMinecraftAction({
      action: "add_server",
      name: name,
      host: host,
      port: parseInt(port) || 25565,
      version: version || "1.20.1"
    });

    addServerForm.reset();
    addServerForm.style.display = "none";
  });

  btnMcSantai.addEventListener("click", () => {
    sendMinecraftAction({ action: "set_mode", mode: "santai" });
  });

  btnMcKompe.addEventListener("click", () => {
    sendMinecraftAction({ action: "set_mode", mode: "kompe" });
  });

  btnMcNext.addEventListener("click", () => {
    sendMinecraftAction({ action: "advance_speedrun" });
  });

  // Real in-game movement buttons
  const btnFollowNearest = document.getElementById("btn-follow-nearest");
  const btnStopMoving = document.getElementById("btn-stop-moving");
  const btnJump = document.getElementById("btn-jump");
  const btnCrouch = document.getElementById("btn-crouch");

  if (btnFollowNearest) {
    btnFollowNearest.addEventListener("click", () => {
      sendMinecraftAction({ action: "follow_nearest" });
    });
  }
  if (btnStopMoving) {
    btnStopMoving.addEventListener("click", () => {
      sendMinecraftAction({ action: "stop_moving" });
    });
  }
  if (btnJump) {
    btnJump.addEventListener("click", () => {
      sendMinecraftAction({ action: "jump" });
    });
  }
  if (btnCrouch) {
    btnCrouch.addEventListener("click", () => {
      sendMinecraftAction({ action: "crouch" });
    });
  }

  document.getElementById("sim-nearby").addEventListener("click", () => {
    sendMinecraftAction({ action: "simulate_event", event: "nearby", target: "Steve" });
  });
  document.getElementById("sim-attack").addEventListener("click", () => {
    sendMinecraftAction({ action: "simulate_event", event: "attack", target: "Alex" });
  });
  document.getElementById("sim-gift").addEventListener("click", () => {
    sendMinecraftAction({ action: "simulate_event", event: "gift", target: "Viewer42", item: "Diamond" });
  });

  // --- 2D Animated Avatar Renderer ---
  function render() {
    time += 0.03;

    // Smooth mouth interpolation
    mouthOpen += (targetMouthOpen - mouthOpen) * 0.4;
    meterFill.style.width = `${Math.min(100, Math.round(mouthOpen * 100))}%`;

    // Blink timer
    blinkTimer += 1;
    if (blinkTimer > 180 + Math.random() * 80) {
      eyeBlink = 1.0;
      blinkTimer = 0;
    }
    eyeBlink = Math.max(0, eyeBlink - 0.15);

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2 + Math.sin(time) * 4; // Idle breathe float

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

    // 6. Eyes
    const eyeScaleY = 1.0 - eyeBlink;
    drawEye(-35, -5, eyeScaleY);
    drawEye(35, -5, eyeScaleY);

    // Eyebrows
    drawEyebrows();

    // 7. Mouth (Lip-sync dynamic)
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

    requestAnimationFrame(render);
  }

  const NOTE_CHARS = ["♪", "♫", "♬", "♩"];
  function spawnMusicNote() {
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

    // Iris (Cyan/Digital like Eve)
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

  render();
});
