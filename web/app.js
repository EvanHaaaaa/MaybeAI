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

  // Donation Alert Elements
  const donationAlertBanner = document.getElementById("donation-alert-banner");
  const donUser = document.getElementById("don-user");
  const donAmount = document.getElementById("don-amount");
  const donText = document.getElementById("don-text");
  let donationTimer = null;

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
  let ws = null;
  let reconnectTimer = null;

  function connectWs() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      wsStatus.textContent = "Connected";
      wsStatus.className = "badge badge-online";
    };

    ws.onclose = () => {
      wsStatus.textContent = "Reconnecting...";
      wsStatus.className = "badge";
      reconnectTimer = setTimeout(connectWs, 2000);
    };

    ws.onerror = () => {
      try { ws.close(); } catch (e) {}
    };

    ws.onmessage = handleWsMessage;
  }

  function handleWsMessage(event) {
    const msg = JSON.parse(event.data);

    if (msg.type === "chat_received") {
      let author = msg.data.source === "minecraft" ? `🎮 [MC] ${msg.data.user}` : msg.data.user;
      if (msg.data.source === "mic") {
        author = `🎙️ [Mic] ${msg.data.user}`;
      }
      if (msg.data.is_donation) {
        author = `🎁 [SUPERCHAT ${msg.data.donation_amount}] ${msg.data.user}`;
      }
      addChatMessage(author, msg.data.text, false, msg.data.is_donation);
    } else if (msg.type === "donation_received") {
      showDonationAlert(msg.data.user, msg.data.amount, msg.data.text);
    } else if (msg.type === "ai_response") {
      const author = msg.data.user || "Eve";
      addChatMessage(author, msg.data.speech, true);
      subtitles.textContent = `"${msg.data.speech}"`;
      if (author === "Eve (Chess)" && chessCommentaryText) {
        chessCommentaryText.textContent = `"${msg.data.speech}"`;
      }
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
    } else if (msg.type === "chess_state") {
      updateChessUi(msg.data);
    } else if (msg.type === "mood_updated") {
      updateMoodUi(msg.data);
    } else if (msg.type === "goal_updated") {
      updateGoalUi(msg.data);
    } else if (msg.type === "goal_completed") {
      showGoalCompletedAlert(msg.data);
    } else if (msg.type === "strategy_adapted") {
      showStrategyPivotAlert(msg.data);
    } else if (msg.type === "goal_agenda_data") {
      if (goalAgendaContent) goalAgendaContent.textContent = msg.data.markdown || "No agenda.";
    } else if (msg.type === "memory_updated") {
      updateMemoryStats(msg.data);
    } else if (msg.type === "memory_search_results") {
      renderMemoryCards(memSearchResults, msg.data);
    } else if (msg.type === "memory_recent_data") {
      renderMemoryCards(memRecentResults, msg.data);
    } else if (msg.type === "memory_journal_data") {
      if (memJournalContent) memJournalContent.textContent = msg.data.markdown || "No journal entries.";
    } else if (msg.type === "memory_user_profile_data") {
      renderDossierCard(msg.data);
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
  }

  // Connect WebSocket initially
  connectWs();

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

  function showDonationAlert(user, amount, text) {
    if (!donationAlertBanner) return;
    if (donUser) donUser.textContent = user;
    if (donAmount) donAmount.textContent = amount;
    if (donText) donText.textContent = `"${text}"`;

    donationAlertBanner.style.display = "flex";
    if (donationTimer) clearTimeout(donationTimer);
    donationTimer = setTimeout(() => {
      donationAlertBanner.style.display = "none";
    }, 6000);
  }

  function addChatMessage(author, text, isAi = false, isDonation = false) {
    const div = document.createElement("div");
    div.className = `chat-msg ${isAi ? "neuro-msg" : ""} ${isDonation ? "donation-msg" : ""}`;
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
      if (msg) {
        sendMessage("ChatUser", msg);
      }
    });
  });

  // Real-Time Chat Interaction Simulation Buttons
  const btnDonationUsd = document.getElementById("btn-quick-donation-usd");
  const btnDonationIdr = document.getElementById("btn-quick-donation-idr");
  const btnQuickDebate = document.getElementById("btn-quick-debate");

  if (btnDonationUsd) {
    btnDonationUsd.addEventListener("click", () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: "donation",
          user: "GigaChadViewer",
          amount: "$10.00",
          currency: "USD",
          text: "Eve, ini saweran buat beli pendingin GPU baru biar gak kepanasan!"
        }));
      }
    });
  }

  if (btnDonationIdr) {
    btnDonationIdr.addEventListener("click", () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: "donation",
          user: "SultanLokal",
          amount: "Rp 50.000",
          currency: "IDR",
          text: "Eve jajan martabak manis dulu gih biar makin ceria stream-nya!"
        }));
      }
    });
  }

  if (btnQuickDebate) {
    btnQuickDebate.addEventListener("click", () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: "bulk_chat",
          messages: [
            { user: "KucingMania", text: "Kucing adalah hewan paling superior di dunia, setuju kan Eve?" },
            { user: "DogLover99", text: "Nggak lah, anjing jauh lebih pintar dan bisa diajak main bola!" }
          ]
        }));
      }
    });
  }

  function sendMessage(user, text, source = "web") {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "user_message", user: user, text: text, source: source }));
    }
  }

  // --- Microphone Voice Listening (Speech-to-Text) ---
  const btnToggleMicHeader = document.getElementById("btn-toggle-mic-header");
  const btnChatMic = document.getElementById("btn-chat-mic");
  const micStatusBar = document.getElementById("mic-status-bar");
  const micTranscriptPreview = document.getElementById("mic-transcript-preview");
  const micLangSelect = document.getElementById("micLangSelect");

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let isListeningMic = false;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = micLangSelect ? micLangSelect.value : "id-ID";

    if (micLangSelect) {
      micLangSelect.addEventListener("change", () => {
        if (recognition) {
          recognition.lang = micLangSelect.value;
          if (isListeningMic) {
            recognition.stop();
            setTimeout(() => { if (isListeningMic) recognition.start(); }, 150);
          }
        }
      });
    }

    recognition.onstart = () => {
      isListeningMic = true;
      updateMicUiState(true);
      if (micTranscriptPreview) micTranscriptPreview.textContent = "Mendengarkan suaramu... silakan bicara!";
    };

    recognition.onresult = (event) => {
      let interimTranscript = "";
      let finalTranscript = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      if (interimTranscript && micTranscriptPreview) {
        micTranscriptPreview.textContent = `"${interimTranscript.trim()}"`;
      }

      if (finalTranscript.trim()) {
        const spokenText = finalTranscript.trim();
        if (micTranscriptPreview) micTranscriptPreview.textContent = `Terkirim: "${spokenText}"`;
        sendMessage("Creator", spokenText, "mic");
      }
    };

    recognition.onerror = (event) => {
      console.log("[Mic Recognition Notice]", event.error);
      if (event.error === "not-allowed") {
        alert("Akses mikrofon ditolak oleh browser. Silakan klik ikon gembok pada address bar browser Anda dan pilih 'Allow' untuk mikrofon.");
        stopMic();
      }
    };

    recognition.onend = () => {
      if (isListeningMic) {
        try {
          recognition.start();
        } catch (e) {}
      } else {
        updateMicUiState(false);
      }
    };
  }

  function updateMicUiState(listening) {
    if (btnToggleMicHeader) {
      btnToggleMicHeader.textContent = listening ? "🔴 Mic: LISTENING" : "🎙️ Mic: OFF";
      if (listening) {
        btnToggleMicHeader.classList.add("active");
      } else {
        btnToggleMicHeader.classList.remove("active");
      }
    }
    if (btnChatMic) {
      if (listening) {
        btnChatMic.classList.add("active");
        btnChatMic.textContent = "🔴";
      } else {
        btnChatMic.classList.remove("active");
        btnChatMic.textContent = "🎙️";
      }
    }
    if (micStatusBar) {
      micStatusBar.style.display = listening ? "flex" : "none";
    }
  }

  function startMic() {
    if (!SpeechRecognition) {
      alert("Browser Anda belum mendukung SpeechRecognition API. Silakan buka MaybeAI menggunakan Google Chrome atau Microsoft Edge untuk menggunakan mic.");
      return;
    }
    isListeningMic = true;
    try {
      recognition.start();
    } catch (e) {
      updateMicUiState(true);
    }
  }

  function stopMic() {
    isListeningMic = false;
    if (recognition) {
      try { recognition.stop(); } catch (e) {}
    }
    updateMicUiState(false);
  }

  function toggleMic() {
    if (isListeningMic) {
      stopMic();
    } else {
      startMic();
    }
  }

  if (btnToggleMicHeader) {
    btnToggleMicHeader.addEventListener("click", toggleMic);
  }
  if (btnChatMic) {
    btnChatMic.addEventListener("click", toggleMic);
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
    if (state.second_brain) {
      updateMemoryStats(state.second_brain);
    }
  }

  // --- Minecraft Controls ---
  const mcModeBadge = document.getElementById("mc-mode-badge");
  const mcTimerBadge = document.getElementById("mc-timer-badge");
  const mcHpBadge = document.getElementById("mc-hp-badge");
  const mcPhaseDesc = document.getElementById("mcPhaseDesc");
  const btnMcSantai = document.getElementById("btn-mc-santai");
  const btnMcGuard = document.getElementById("btn-mc-guard");
  const btnMcKompe = document.getElementById("btn-mc-kompe");
  const btnMcNext = document.getElementById("btn-mc-next");
  const mcGuardBadge = document.getElementById("mc-guard-badge");

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
      if (btnMcGuard) btnMcGuard.classList.remove("active");
      btnMcKompe.classList.remove("active");
      if (mcGuardBadge) mcGuardBadge.style.display = "none";
      mcPhaseDesc.textContent = "Status: Exploring peacefully & socializing with players.";
    } else if (state.mode === "guard") {
      mcModeBadge.textContent = "Mode: Guard (Bodyguard)";
      mcModeBadge.className = "badge badge-accent";
      btnMcNext.style.display = "none";
      if (btnMcGuard) btnMcGuard.classList.add("active");
      btnMcSantai.classList.remove("active");
      btnMcKompe.classList.remove("active");
      const targetPlayer = (state.guard && state.guard.target) || "Nearest Player";
      const killCount = (state.guard && state.guard.kills) || 0;
      if (mcGuardBadge) {
        mcGuardBadge.style.display = "inline-block";
        mcGuardBadge.textContent = `🛡️ Guarding: ${targetPlayer} (Kills: ${killCount})`;
      }
      mcPhaseDesc.textContent = `Bodyguard Active: Protecting ${targetPlayer} from all hostiles!`;
    } else if (state.mode === "kompe") {
      mcModeBadge.textContent = "Mode: Kompe (Speedrun)";
      mcModeBadge.className = "badge badge-accent";
      btnMcNext.style.display = "inline-block";
      btnMcKompe.classList.add("active");
      btnMcSantai.classList.remove("active");
      if (btnMcGuard) btnMcGuard.classList.remove("active");
      if (mcGuardBadge) mcGuardBadge.style.display = "none";
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

  if (btnMcGuard) {
    btnMcGuard.addEventListener("click", () => {
      sendMinecraftAction({ action: "set_mode", mode: "guard" });
    });
  }

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

  const simThreat = document.getElementById("sim-threat");
  if (simThreat) {
    simThreat.addEventListener("click", () => {
      sendMinecraftAction({ action: "simulate_event", event: "guard_threat", mob: "Zombie", target: "Steve" });
    });
  }

  const simCreeper = document.getElementById("sim-creeper");
  if (simCreeper) {
    simCreeper.addEventListener("click", () => {
      sendMinecraftAction({ action: "simulate_event", event: "guard_threat", mob: "Creeper", target: "Steve" });
    });
  }

  // --- Chess Live Arena Controller ---
  const chessCard = document.getElementById("chessCard");
  const chessBoard = document.getElementById("chess-board");
  const chessStatusBadge = document.getElementById("chess-status-badge");
  const chessEloBadge = document.getElementById("chess-elo-badge");
  const chessTurnBadge = document.getElementById("chess-turn-badge");
  const chessEvalBadge = document.getElementById("chess-eval-badge");
  const evalBarFill = document.getElementById("eval-bar-fill");
  const chessEloRange = document.getElementById("chessEloRange");
  const chessEloVal = document.getElementById("chess-elo-val");
  const chessColorSelect = document.getElementById("chessColorSelect");
  const btnChessNew = document.getElementById("btn-chess-new");
  const btnChessResign = document.getElementById("btn-chess-resign");
  const chessCommentaryText = document.getElementById("chess-commentary-text");
  const chessMoveCount = document.getElementById("chess-move-count");
  const chessMoveList = document.getElementById("chess-move-list");

  let currentChessState = null;
  let selectedSquare = null;
  let lastMoveSquares = [];

  const CHESS_PIECES = {
    'P': { glyph: '♙', color: 'white' },
    'N': { glyph: '♘', color: 'white' },
    'B': { glyph: '♗', color: 'white' },
    'R': { glyph: '♖', color: 'white' },
    'Q': { glyph: '♕', color: 'white' },
    'K': { glyph: '♔', color: 'white' },
    'p': { glyph: '♟', color: 'black' },
    'n': { glyph: '♞', color: 'black' },
    'b': { glyph: '♝', color: 'black' },
    'r': { glyph: '♜', color: 'black' },
    'q': { glyph: '♛', color: 'black' },
    'k': { glyph: '♚', color: 'black' }
  };

  function sendChessAction(actionData) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "chess_action", ...actionData }));
    }
  }

  function parseFenSquares(fen) {
    const squares = {};
    if (!fen) return squares;
    const parts = fen.split(" ");
    const rows = parts[0].split("/");
    const files = ["a", "b", "c", "d", "e", "f", "g", "h"];
    for (let r = 0; r < 8; r++) {
      const rankNum = 8 - r;
      const rowStr = rows[r];
      let fileIdx = 0;
      for (let c = 0; c < rowStr.length; c++) {
        const char = rowStr[c];
        if (char >= '1' && char <= '8') {
          fileIdx += parseInt(char, 10);
        } else {
          const sq = files[fileIdx] + rankNum;
          squares[sq] = char;
          fileIdx++;
        }
      }
    }
    return squares;
  }

  function getEloRankName(elo) {
    if (elo < 800) return "Noob";
    if (elo < 1200) return "Casual";
    if (elo < 1600) return "Streamer";
    if (elo < 2000) return "Sweaty";
    return "Grandmaster";
  }

  function updateChessUi(state) {
    currentChessState = state;

    // Badges
    if (state.is_game_over) {
      chessStatusBadge.textContent = `Game Over (${state.result})`;
      chessStatusBadge.className = "badge";
    } else if (state.is_active) {
      chessStatusBadge.textContent = "Match Active";
      chessStatusBadge.className = "badge badge-online";
    } else {
      chessStatusBadge.textContent = "Standby";
      chessStatusBadge.className = "badge";
    }

    if (chessEloBadge) chessEloBadge.textContent = `Eve ELO: ${state.elo}`;
    if (chessEloVal) {
      chessEloVal.textContent = `${state.elo} ELO (${getEloRankName(state.elo)})`;
    }
    if (chessEloRange) {
      chessEloRange.value = state.elo;
    }

    if (chessTurnBadge) {
      const t = state.turn ? state.turn.toUpperCase() : "WHITE";
      const isPlayerTurn = (state.turn === state.player_color);
      chessTurnBadge.textContent = `Turn: ${t} ${isPlayerTurn ? "(You)" : "(Eve)"}`;
      chessTurnBadge.className = isPlayerTurn ? "badge badge-accent" : "badge";
    }

    // Eval Score & Meter
    if (chessEvalBadge && evalBarFill) {
      const centipawns = state.eval !== undefined ? state.eval : 0;
      const evalPawns = (centipawns / 100).toFixed(1);
      const evalFormatted = centipawns > 0 ? `+${evalPawns}` : `${evalPawns}`;
      chessEvalBadge.textContent = `Eval: ${evalFormatted}`;

      // Convert centipawns to percentage: 0cp = 50%, +1000cp = 95%, -1000cp = 5%
      const clampedPct = Math.max(5, Math.min(95, 50 + (centipawns / 20)));
      evalBarFill.style.height = `${clampedPct}%`;
    }

    // Move count & Move list
    if (chessMoveCount) {
      chessMoveCount.textContent = `${state.move_count || 0} moves`;
    }
    if (chessMoveList) {
      chessMoveList.innerHTML = "";
      const history = state.move_history || [];
      if (history.length === 0) {
        chessMoveList.innerHTML = `<div class="chess-empty-moves">No moves yet. Start a game!</div>`;
      } else {
        for (let i = 0; i < history.length; i += 2) {
          const moveNum = Math.floor(i / 2) + 1;
          const whiteMove = history[i] || "";
          const blackMove = history[i + 1] || "";
          const rowDiv = document.createElement("div");
          rowDiv.className = "chess-move-row";
          rowDiv.innerHTML = `<span class="move-num">${moveNum}.</span><span class="move-white">${whiteMove}</span><span class="move-black">${blackMove}</span>`;
          chessMoveList.appendChild(rowDiv);
        }
        chessMoveList.scrollTop = chessMoveList.scrollHeight;
      }
    }

    renderChessBoard();
  }

  function renderChessBoard() {
    if (!chessBoard) return;
    chessBoard.innerHTML = "";

    const state = currentChessState || {
      fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
      turn: "white",
      player_color: "white",
      legal_moves: [],
      is_check: false,
      is_active: false
    };

    const squaresMap = parseFenSquares(state.fen);
    const isFlipped = (state.player_color === "black");

    const ranks = isFlipped ? [1, 2, 3, 4, 5, 6, 7, 8] : [8, 7, 6, 5, 4, 3, 2, 1];
    const files = isFlipped ? ["h", "g", "f", "e", "d", "c", "b", "a"] : ["a", "b", "c", "d", "e", "f", "g", "h"];

    // Find legal destinations for selected square
    const legalDests = new Set();
    if (selectedSquare && state.legal_moves) {
      for (const m of state.legal_moves) {
        if (m.startsWith(selectedSquare)) {
          legalDests.add(m.slice(2, 4));
        }
      }
    }

    for (let rIdx = 0; rIdx < 8; rIdx++) {
      const rank = ranks[rIdx];
      for (let fIdx = 0; fIdx < 8; fIdx++) {
        const file = files[fIdx];
        const sqName = file + rank;
        const fileNum = file.charCodeAt(0) - 97;
        const isLight = ((fileNum + rank) % 2 === 1);

        const sqDiv = document.createElement("div");
        sqDiv.className = `chess-square ${isLight ? "light" : "dark"}`;
        sqDiv.dataset.square = sqName;

        const pieceChar = squaresMap[sqName];
        const pieceInfo = pieceChar ? CHESS_PIECES[pieceChar] : null;

        if (sqName === selectedSquare) {
          sqDiv.classList.add("selected");
        }
        if (lastMoveSquares.includes(sqName)) {
          sqDiv.classList.add("last-move");
        }
        if (legalDests.has(sqName)) {
          sqDiv.classList.add("legal-dest");
          if (pieceInfo) sqDiv.classList.add("has-piece");
        }
        if (state.is_check && pieceInfo && pieceInfo.glyph === (state.turn === "white" ? "♔" : "♚")) {
          sqDiv.classList.add("in-check");
        }

        // Coordinate labels
        if (rIdx === 7) {
          const fileLabel = document.createElement("span");
          fileLabel.className = "coord-label coord-file";
          fileLabel.textContent = file;
          sqDiv.appendChild(fileLabel);
        }
        if (fIdx === 0) {
          const rankLabel = document.createElement("span");
          rankLabel.className = "coord-label coord-rank";
          rankLabel.textContent = rank;
          sqDiv.appendChild(rankLabel);
        }

        // Piece element
        if (pieceInfo) {
          const pieceSpan = document.createElement("span");
          pieceSpan.className = `chess-piece ${pieceInfo.color}`;
          pieceSpan.textContent = pieceInfo.glyph;
          sqDiv.appendChild(pieceSpan);
        }

        // Click handler
        sqDiv.addEventListener("click", () => handleSquareClick(sqName, pieceInfo));

        chessBoard.appendChild(sqDiv);
      }
    }
  }

  function handleSquareClick(sqName, pieceInfo) {
    if (!currentChessState) return;
    const isPlayerTurn = (currentChessState.turn === currentChessState.player_color);

    // 1. If clicking a legal destination of the already selected square:
    if (selectedSquare && currentChessState.legal_moves) {
      let matchedMove = null;
      for (const m of currentChessState.legal_moves) {
        if (m.startsWith(selectedSquare + sqName)) {
          if (m.length === 5 && m.endsWith("q")) {
            matchedMove = m;
            break;
          } else if (m.length === 4) {
            matchedMove = m;
          }
        }
      }

      if (matchedMove) {
        sendChessAction({ action: "make_move", move: matchedMove });
        lastMoveSquares = [selectedSquare, sqName];
        selectedSquare = null;
        renderChessBoard();
        return;
      }
    }

    // 2. If clicking on the same square: deselect
    if (selectedSquare === sqName) {
      selectedSquare = null;
      renderChessBoard();
      return;
    }

    // 3. If clicking player's piece on player's turn: select it
    if (isPlayerTurn && pieceInfo && pieceInfo.color === currentChessState.player_color) {
      selectedSquare = sqName;
      renderChessBoard();
      return;
    }

    // 4. Otherwise deselect
    selectedSquare = null;
    renderChessBoard();
  }

  // Preset ELO pill buttons
  document.querySelectorAll(".elo-preset-pills .pill").forEach(pill => {
    pill.addEventListener("click", () => {
      const elo = parseInt(pill.dataset.elo, 10);
      if (elo) {
        if (chessEloRange) chessEloRange.value = elo;
        if (chessEloVal) chessEloVal.textContent = `${elo} ELO (${getEloRankName(elo)})`;
        sendChessAction({ action: "set_elo", elo: elo });
      }
    });
  });

  if (chessEloRange) {
    chessEloRange.addEventListener("input", () => {
      const val = parseInt(chessEloRange.value, 10);
      if (chessEloVal) chessEloVal.textContent = `${val} ELO (${getEloRankName(val)})`;
    });
    chessEloRange.addEventListener("change", () => {
      const val = parseInt(chessEloRange.value, 10);
      sendChessAction({ action: "set_elo", elo: val });
    });
  }

  if (btnChessNew) {
    btnChessNew.addEventListener("click", () => {
      const color = chessColorSelect ? chessColorSelect.value : "white";
      const elo = chessEloRange ? parseInt(chessEloRange.value, 10) : 1200;
      selectedSquare = null;
      lastMoveSquares = [];
      sendChessAction({
        action: "start_game",
        player_name: "Creator",
        player_color: color,
        elo: elo
      });
    });
  }

  if (btnChessResign) {
    btnChessResign.addEventListener("click", () => {
      sendChessAction({ action: "resign" });
    });
  }

  // Initial dummy board render
  renderChessBoard();

  // --- Second Brain & Episodic Memory Controller (Andrej Karpathy Style) ---
  const memCountBadge = document.getElementById("mem-count-badge");
  const memUsersBadge = document.getElementById("mem-users-badge");
  const memPromisesBadge = document.getElementById("mem-promises-badge");
  const memTabs = document.querySelectorAll(".mem-tab");
  const memTabPanels = document.querySelectorAll(".mem-tab-panel");
  const memSearchInput = document.getElementById("memSearchInput");
  const btnMemSearch = document.getElementById("btn-mem-search");
  const memSearchResults = document.getElementById("memSearchResults");
  const memRecentResults = document.getElementById("memRecentResults");
  const btnRefreshRecent = document.getElementById("btn-refresh-recent");
  const memJournalContent = document.getElementById("memJournalContent");
  const btnRefreshJournal = document.getElementById("btn-refresh-journal");
  const dossierUsernameInput = document.getElementById("dossierUsernameInput");
  const btnLoadDossier = document.getElementById("btn-load-dossier");
  const dossierDisplay = document.getElementById("dossierDisplay");
  const addMemoryForm = document.getElementById("addMemoryForm");

  function sendMemoryAction(actionData) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "memory_action", ...actionData }));
    }
  }

  function updateMemoryStats(stats) {
    if (!stats) return;
    if (memCountBadge && stats.total_memories !== undefined) {
      memCountBadge.textContent = `Memories: ${stats.total_memories}`;
    }
    if (memUsersBadge && stats.known_users !== undefined) {
      memUsersBadge.textContent = `Viewers: ${stats.known_users}`;
    }
    if (memPromisesBadge && stats.pending_promises !== undefined) {
      memPromisesBadge.textContent = `Promises: ${stats.pending_promises}`;
    }
  }

  // Tab switching
  memTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      memTabs.forEach(t => t.classList.remove("active"));
      memTabPanels.forEach(p => p.classList.remove("active"));
      tab.classList.add("active");
      const targetId = tab.dataset.tab;
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) targetPanel.classList.add("active");

      // Auto-load tab data
      if (targetId === "tab-recent") {
        sendMemoryAction({ action: "get_recent" });
      } else if (targetId === "tab-journal") {
        sendMemoryAction({ action: "get_journal" });
      }
    });
  });

  function getBadgeClassForType(epType) {
    const t = (epType || "").toLowerCase();
    if (t.includes("gift")) return "badge-gift";
    if (t.includes("guard")) return "badge-guard";
    if (t.includes("chess")) return "badge-chess";
    if (t.includes("donation")) return "badge-donation";
    if (t.includes("promise") || t.includes("challenge")) return "badge-promise";
    return "badge-general";
  }

  function renderMemoryCards(container, memories) {
    if (!container) return;
    container.innerHTML = "";
    if (!memories || memories.length === 0) {
      container.innerHTML = `<div class="mem-empty-hint">Tidak ada memori ditemukan.</div>`;
      return;
    }

    memories.forEach(mem => {
      const card = document.createElement("div");
      card.className = "mem-card-item";
      const badgeCls = getBadgeClassForType(mem.episode_type || "general");
      const dateStr = (mem.date_str || "").slice(0, 16);
      const userStr = mem.user || "Chat";
      const emotionStr = mem.emotional_tag || "neutral";

      card.innerHTML = `
        <div class="mem-card-header">
          <span class="mem-card-title">${escapeHtml(mem.title || "Memori Episodik")}</span>
          <span class="mem-card-badge ${badgeCls}">${escapeHtml(mem.episode_type || "general")}</span>
        </div>
        <div class="mem-card-body">"${escapeHtml(mem.content || "")}"</div>
        <div class="mem-card-footer">
          <span>👤 <strong>${escapeHtml(userStr)}</strong> (${emotionStr})</span>
          <span>⏱️ ${dateStr}</span>
        </div>
      `;
      container.appendChild(card);
    });
  }

  function renderDossierCard(profile) {
    if (!dossierDisplay) return;
    if (!profile) {
      dossierDisplay.style.display = "block";
      dossierDisplay.innerHTML = `<div class="mem-empty-hint">Profil penonton tidak ditemukan.</div>`;
      return;
    }

    dossierDisplay.style.display = "flex";
    const tags = (profile.tags || []).join(", ") || "New Chatter";
    const count = profile.interaction_count || 0;
    const prefs = profile.preferences || {};
    const notes = profile.notes || [];
    const games = profile.games_played || {};
    const winLoss = profile.win_loss || {};

    let prefsHtml = "";
    for (const [k, vals] of Object.entries(prefs)) {
      if (Array.isArray(vals) && vals.length > 0) {
        prefsHtml += `<li><strong>${escapeHtml(k)}:</strong> ${escapeHtml(vals.join(", "))}</li>`;
      }
    }
    if (!prefsHtml) prefsHtml = "<li>Belum ada preferensi tercatat</li>";

    let notesHtml = "";
    notes.slice(-5).forEach(n => {
      notesHtml += `<li>${escapeHtml(n)}</li>`;
    });
    if (!notesHtml) notesHtml = "<li>Belum ada catatan khusus</li>";

    let gamesHtml = "";
    for (const [g, cnt] of Object.entries(games)) {
      gamesHtml += `<li><strong>${escapeHtml(g)}:</strong> ${cnt}x dimainkan</li>`;
    }
    for (const [k, cnt] of Object.entries(winLoss)) {
      gamesHtml += `<li><strong>${escapeHtml(k)}:</strong> ${cnt}</li>`;
    }
    if (!gamesHtml) gamesHtml = "<li>Belum pernah main bareng</li>";

    dossierDisplay.innerHTML = `
      <div class="dossier-header">
        <span class="dossier-user-name">👤 ${escapeHtml(profile.username)}</span>
        <span class="badge badge-accent">${escapeHtml(tags)} (${count} interaksi)</span>
      </div>
      <div class="dossier-details">
        <div class="dossier-section">
          <h4>🌟 Preferensi Penonton:</h4>
          <ul>${prefsHtml}</ul>
        </div>
        <div class="dossier-section">
          <h4>🎮 Game & Mabar:</h4>
          <ul>${gamesHtml}</ul>
        </div>
        <div class="dossier-section">
          <h4>📌 Catatan Memori:</h4>
          <ul>${notesHtml}</ul>
        </div>
      </div>
    `;
  }

  // Search button
  if (btnMemSearch) {
    btnMemSearch.addEventListener("click", () => {
      const q = memSearchInput ? memSearchInput.value.trim() : "";
      if (q) {
        sendMemoryAction({ action: "search", query: q });
      }
    });
  }

  if (memSearchInput) {
    memSearchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const q = memSearchInput.value.trim();
        if (q) sendMemoryAction({ action: "search", query: q });
      }
    });
  }

  // Quick tag search buttons
  document.querySelectorAll(".mem-search-quick-tags .pill").forEach(p => {
    p.addEventListener("click", () => {
      const q = p.dataset.search;
      if (memSearchInput) memSearchInput.value = q;
      sendMemoryAction({ action: "search", query: q });
    });
  });

  if (btnRefreshRecent) {
    btnRefreshRecent.addEventListener("click", () => {
      sendMemoryAction({ action: "get_recent" });
    });
  }

  if (btnRefreshJournal) {
    btnRefreshJournal.addEventListener("click", () => {
      sendMemoryAction({ action: "get_journal" });
    });
  }

  if (btnLoadDossier) {
    btnLoadDossier.addEventListener("click", () => {
      const uname = dossierUsernameInput ? dossierUsernameInput.value.trim() : "";
      if (uname) {
        sendMemoryAction({ action: "get_user_profile", username: uname });
      }
    });
  }

  if (addMemoryForm) {
    addMemoryForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const title = document.getElementById("memNewTitle").value;
      const user = document.getElementById("memNewUser").value;
      const type = document.getElementById("memNewType").value;
      const emotion = document.getElementById("memNewEmotion").value;
      const content = document.getElementById("memNewContent").value;

      sendMemoryAction({
        action: "add_memory",
        title: title,
        user: user,
        episode_type: type,
        emotional_tag: emotion,
        content: content
      });

      addMemoryForm.reset();
      alert("Memori berhasil dicatat ke dalam Second Brain Eve!");
    });
  }

  // --- Dynamic Mood & Personality Engine UI ---
  const moodDominantBadge = document.getElementById("mood-dominant-badge");
  const moodTempBadge = document.getElementById("mood-temp-badge");
  const moodHappinessBar = document.getElementById("mood-happiness-bar");
  const moodHappinessVal = document.getElementById("mood-happiness-val");
  const moodAnnoyanceBar = document.getElementById("mood-annoyance-bar");
  const moodAnnoyanceVal = document.getElementById("mood-annoyance-val");
  const moodCuriosityBar = document.getElementById("mood-curiosity-bar");
  const moodCuriosityVal = document.getElementById("mood-curiosity-val");
  const moodExcitementBar = document.getElementById("mood-excitement-bar");
  const moodExcitementVal = document.getElementById("mood-excitement-val");
  const moodCompetitiveBar = document.getElementById("mood-competitive-bar");
  const moodCompetitiveVal = document.getElementById("mood-competitive-val");
  const moodDirectiveText = document.getElementById("mood-directive-text");
  const btnMoodReset = document.getElementById("btn-mood-reset");

  function updateMoodUi(data) {
    if (!data) return;
    const dims = data.dimensions || {};
    const dom = data.dominant_mood || "CHILL_NEUTRAL";
    const tempMod = data.temperature_modifier || 0.0;
    const directive = data.behavioral_directive || "";

    if (moodDominantBadge) {
      moodDominantBadge.textContent = `Mood: ${dom}`;
      if (dom.includes("HAPPY") || dom.includes("PLAYFUL")) {
        moodDominantBadge.className = "badge badge-online";
      } else if (dom.includes("ANNOYED") || dom.includes("POUTY")) {
        moodDominantBadge.className = "badge badge-danger";
      } else if (dom.includes("COMPETITIVE") || dom.includes("HYPE")) {
        moodDominantBadge.className = "badge badge-accent";
      } else {
        moodDominantBadge.className = "badge";
      }
    }

    if (moodTempBadge) {
      const sign = tempMod >= 0 ? "+" : "";
      moodTempBadge.textContent = `Temp Mod: ${sign}${tempMod.toFixed(2)}`;
    }

    const setGauge = (bar, valElem, val) => {
      const pct = Math.round((val || 0) * 100);
      if (bar) bar.style.width = `${pct}%`;
      if (valElem) valElem.textContent = `${pct}%`;
    };

    setGauge(moodHappinessBar, moodHappinessVal, dims.happiness);
    setGauge(moodAnnoyanceBar, moodAnnoyanceVal, dims.annoyance);
    setGauge(moodCuriosityBar, moodCuriosityVal, dims.curiosity);
    setGauge(moodExcitementBar, moodExcitementVal, dims.excitement);
    setGauge(moodCompetitiveBar, moodCompetitiveVal, dims.competitiveness);

    if (moodDirectiveText && directive) {
      moodDirectiveText.textContent = directive;
    }
  }

  function sendMoodAction(actionPayload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "mood_action",
        ...actionPayload
      }));
    }
  }

  document.querySelectorAll(".btn-stimulus").forEach(btn => {
    btn.addEventListener("click", () => {
      const stim = btn.dataset.stimulus;
      if (stim) {
        sendMoodAction({ action: "apply_stimulus", stimulus: stim, intensity: 1.0 });
      }
    });
  });

  if (btnMoodReset) {
    btnMoodReset.addEventListener("click", () => {
      sendMoodAction({ action: "reset" });
    });
  }

  // --- Autonomous Goal & Planning Engine Elements ---
  const goalActiveBadge = document.getElementById("goal-active-badge");
  const goalStatsBadge = document.getElementById("goal-stats-badge");
  const goalTierBadge = document.getElementById("goal-tier-badge");
  const goalCurrentTitle = document.getElementById("goal-current-title");
  const goalCurrentDesc = document.getElementById("goal-current-desc");
  const goalProgressText = document.getElementById("goal-progress-text");
  const goalProgressBar = document.getElementById("goal-progress-bar");
  const goalStrategyText = document.getElementById("goal-strategy-text");
  const goalSubtasksList = document.getElementById("goal-subtasks-list");
  const goalPivotAlert = document.getElementById("goal-pivot-alert");
  const goalPivotDesc = document.getElementById("goal-pivot-desc");
  const goalTiersGrid = document.getElementById("goalTiersGrid");
  const goalAgendaContent = document.getElementById("goalAgendaContent");
  const btnGoalAdvance = document.getElementById("btn-goal-advance");
  const btnGoalComplete = document.getElementById("btn-goal-complete");
  const btnGoalReplan = document.getElementById("btn-goal-replan");
  const btnGoalAutonomous = document.getElementById("btn-goal-autonomous");
  const btnRefreshAgenda = document.getElementById("btn-refresh-agenda");
  const addGoalForm = document.getElementById("addGoalForm");

  let currentGoalData = null;

  function sendGoalAction(actionPayload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "goal_action",
        ...actionPayload
      }));
    }
  }

  function updateGoalUi(data) {
    if (!data) return;
    currentGoalData = data;

    const activeGoal = data.active_goal;
    const activeSub = data.active_subtask;
    const total = data.total_goals || 0;
    const completed = data.completed_goals || 0;

    if (goalStatsBadge) {
      goalStatsBadge.textContent = `Goals: ${total} | Selesai: ${completed}`;
    }

    if (activeGoal) {
      const pct = Math.round((activeGoal.progress || 0) * 100);
      if (goalActiveBadge) goalActiveBadge.textContent = `Active: ${activeGoal.title} [${pct}%]`;
      if (goalTierBadge) goalTierBadge.textContent = `${(activeGoal.tier || "daily").toUpperCase()} GOAL`;
      if (goalCurrentTitle) goalCurrentTitle.textContent = activeGoal.title;
      if (goalCurrentDesc) goalCurrentDesc.textContent = activeGoal.description || "";
      if (goalProgressText) goalProgressText.textContent = `${pct}%`;
      if (goalProgressBar) goalProgressBar.style.width = `${pct}%`;

      if (goalStrategyText) {
        const strat = activeSub ? activeSub.strategy : "Evaluasi pencapaian akhir misi";
        goalStrategyText.textContent = `Strategi: ${strat}`;
      }

      // Render Subtasks list
      if (goalSubtasksList) {
        goalSubtasksList.innerHTML = "";
        const subs = activeGoal.subtasks || [];
        subs.forEach((s, idx) => {
          const isCurrent = activeSub && activeSub.id === s.id;
          const div = document.createElement("div");
          div.className = `subtask-item ${isCurrent ? 'active-subtask' : ''}`;

          let icon = "⏳";
          let badgeClass = "badge-sub-pending";
          let badgeText = "Pending";

          if (s.status === "completed") {
            icon = "✅";
            badgeClass = "badge-sub-completed";
            badgeText = "Done";
          } else if (s.status === "in_progress") {
            icon = "⚡";
            badgeClass = "badge-sub-progress";
            badgeText = "In Progress";
          } else if (s.status === "replanned" || s.status === "failed") {
            icon = "🔄";
            badgeClass = "badge-sub-replanned";
            badgeText = "Plan B (Replanned)";
          }

          const currentCount = s.current_count !== undefined ? s.current_count : 0;
          const targetCount = s.target_count || 1;
          const unit = s.unit || "step";

          div.innerHTML = `
            <div class="subtask-left">
              <span class="subtask-icon">${icon}</span>
              <div class="subtask-info">
                <span class="subtask-title">Step ${idx + 1}: ${escapeHtml(s.title)}</span>
                <span class="subtask-strat">${escapeHtml(s.strategy || s.description || "")}</span>
              </div>
            </div>
            <div class="subtask-right">
              <span class="badge ${badgeClass}">${currentCount}/${targetCount} ${escapeHtml(unit)}</span>
              <span class="subtask-badge ${badgeClass}">${badgeText}</span>
            </div>
          `;
          goalSubtasksList.appendChild(div);
        });
      }
    } else {
      if (goalActiveBadge) goalActiveBadge.textContent = "Tidak ada goal aktif";
      if (goalCurrentTitle) goalCurrentTitle.textContent = "Semua Agenda Selesai";
      if (goalCurrentDesc) goalCurrentDesc.textContent = "Eve sedang bersiap memilih agenda mandiri berikutnya.";
      if (goalProgressText) goalProgressText.textContent = "100%";
      if (goalProgressBar) goalProgressBar.style.width = "100%";
      if (goalSubtasksList) goalSubtasksList.innerHTML = "<div class='subtask-item'>Semua misi aktif tuntas! Klik 'Autonomous Agenda Step' untuk memulai misi baru.</div>";
    }

    // Pivot alert check
    if (data.last_strategy_pivot && goalPivotAlert && goalPivotDesc) {
      const p = data.last_strategy_pivot;
      goalPivotAlert.style.display = "flex";
      goalPivotDesc.innerHTML = `
        <strong>Subtask Terhambat:</strong> ${escapeHtml(p.failed_subtask)}<br>
        <strong>Alasan Kegagalan:</strong> ${escapeHtml(p.reason)}<br>
        <strong>Plan B Diadopsi:</strong> ${escapeHtml(p.new_subtask)} (${escapeHtml(p.strategy || "")})
      `;
    }

    // Render Categorized Grid (tab-goal-all)
    if (goalTiersGrid && data.goals_by_tier) {
      goalTiersGrid.innerHTML = "";
      const tierTitles = {
        "daily": "📅 Daily Goals (Tujuan Hari Ini)",
        "short_term": "⚡ Short-Term Goals (Tujuan Berikutnya)",
        "weekly": "🏆 Weekly Milestones (Tujuan Mingguan)",
        "social": "🤝 Social Goals (Tujuan Sosial)"
      };

      for (const [tierKey, goalsList] of Object.entries(data.goals_by_tier)) {
        const card = document.createElement("div");
        card.className = "goal-tier-card";
        let listHtml = "";

        goalsList.forEach(g => {
          const isActive = activeGoal && activeGoal.id === g.id;
          const pct = Math.round((g.progress || 0) * 100);
          listHtml += `
            <div class="tier-goal-item ${isActive ? 'is-active-goal' : ''}" data-goal-id="${g.id}">
              <div class="tier-goal-header">
                <span>${escapeHtml(g.title)}</span>
                <span class="goal-prog-pct" style="font-size: 12px;">${pct}%</span>
              </div>
              <div class="tier-goal-bar">
                <div class="tier-goal-bar-fill" style="width: ${pct}%;"></div>
              </div>
            </div>
          `;
        });

        if (!listHtml) listHtml = "<div class='subtasks-hint'>Belum ada goal di kategori ini.</div>";

        card.innerHTML = `
          <div class="tier-card-header">
            <span class="tier-card-title">${tierTitles[tierKey] || tierKey}</span>
            <span class="badge badge-sm">${goalsList.length}</span>
          </div>
          ${listHtml}
        `;
        goalTiersGrid.appendChild(card);
      }

      // Allow clicking tier goal items to switch active goal
      document.querySelectorAll(".tier-goal-item").forEach(item => {
        item.addEventListener("click", () => {
          const gid = item.dataset.goalId;
          if (gid) {
            sendGoalAction({ action: "set_active", goal_id: gid });
          }
        });
      });
    }
  }

  function showGoalCompletedAlert(data) {
    const g = data.goal || {};
    addChatMessage("Eve (Achievement 🏆)", `Horeee! Misi '${g.title || 'Utama'}' berhasil kita selesaikan tuntas secara mandiri! [action: giggle] [emotion: happy]`, true);
  }

  function showStrategyPivotAlert(data) {
    if (data.speech) {
      addChatMessage("Eve (Plan B 🔄)", data.speech, true);
    }
  }

  // Tab switching for goal tabs
  document.querySelectorAll(".goal-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".goal-tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".goal-tab-panel").forEach(p => p.classList.remove("active"));
      tab.classList.add("active");
      const targetPanel = document.getElementById(tab.dataset.tab);
      if (targetPanel) targetPanel.classList.add("active");
      if (tab.dataset.tab === "tab-goal-agenda") {
        sendGoalAction({ action: "get_agenda" });
      }
    });
  });

  // Goal Control Buttons
  if (btnGoalAdvance) {
    btnGoalAdvance.addEventListener("click", () => {
      if (currentGoalData && currentGoalData.active_subtask) {
        sendGoalAction({
          action: "advance_subtask",
          subtask_id: currentGoalData.active_subtask.id,
          delta: 1.0
        });
      }
    });
  }

  if (btnGoalComplete) {
    btnGoalComplete.addEventListener("click", () => {
      sendGoalAction({ action: "complete_subtask" });
    });
  }

  if (btnGoalReplan) {
    btnGoalReplan.addEventListener("click", () => {
      const reason = prompt("Masukkan alasan kendala/kegagalan subtask (misal: 'Diserang creeper di gua', 'Kayu di sekitar habis', 'Pemain menolak sapaan'):", "Diserang monster tak terduga");
      if (reason) {
        sendGoalAction({ action: "replan_subtask", reason: reason });
      }
    });
  }

  if (btnGoalAutonomous) {
    btnGoalAutonomous.addEventListener("click", () => {
      sendGoalAction({ action: "autonomous_select" });
    });
  }

  if (btnRefreshAgenda) {
    btnRefreshAgenda.addEventListener("click", () => {
      sendGoalAction({ action: "get_agenda" });
    });
  }

  if (addGoalForm) {
    addGoalForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const title = document.getElementById("goalNewTitle").value;
      const tier = document.getElementById("goalNewTier").value;
      const cat = document.getElementById("goalNewCategory").value;
      const priority = document.getElementById("goalNewPriority").value;
      const desc = document.getElementById("goalNewDesc").value;

      sendGoalAction({
        action: "add_goal",
        title: title,
        tier: tier,
        category: cat,
        priority: priority,
        description: desc
      });

      addGoalForm.reset();
      alert("Goal baru berhasil ditambahkan dan didekomposisi menjadi subtask!");
    });
  }

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
