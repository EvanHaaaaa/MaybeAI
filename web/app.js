// MaybeAI Frontend App & Virtual Avatar Renderer
document.addEventListener("DOMContentLoaded", () => {
  // --- Modular Studio Workspace Tabs (localStorage persisted) ---
  const WORKSPACE_STORAGE_KEY = "maybeai_active_workspace";
  const workspaceTabs = document.querySelectorAll(".workspace-tab");
  const workspacePanels = document.querySelectorAll(".workspace-panel");

  function switchWorkspaceTab(workspaceId, persist = true) {
    const validIds = Array.from(workspacePanels).map(p => p.getAttribute("data-workspace"));
    const targetId = validIds.includes(workspaceId) ? workspaceId : (validIds[0] || "stage");

    workspaceTabs.forEach(tab => {
      const isActive = tab.getAttribute("data-workspace") === targetId;
      tab.classList.toggle("active", isActive);
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
    });

    workspacePanels.forEach(panel => {
      const isActive = panel.getAttribute("data-workspace") === targetId;
      panel.classList.toggle("active", isActive);
      panel.hidden = !isActive;
    });

    if (persist) {
      try {
        localStorage.setItem(WORKSPACE_STORAGE_KEY, targetId);
      } catch (e) {}
    }
  }

  if (workspaceTabs.length > 0 && workspacePanels.length > 0) {
    workspaceTabs.forEach(tab => {
      tab.addEventListener("click", () => {
        const targetId = tab.getAttribute("data-workspace");
        switchWorkspaceTab(targetId, true);
      });
    });

    let savedWorkspace = "stage";
    try {
      savedWorkspace = localStorage.getItem(WORKSPACE_STORAGE_KEY) || "stage";
    } catch (e) {}
    switchWorkspaceTab(savedWorkspace, false);
  }

  const canvas = document.getElementById("avatarCanvas");
  const ctx = canvas.getContext("2d");
  const meterFill = document.getElementById("meter-fill");
  const emotionBadge = document.getElementById("emotion-badge");
  const subtitles = document.getElementById("subtitles");
  // Dual Chat Elements (Creator VIP vs Audience Stream)
  const tabCreatorChat = document.getElementById("tabCreatorChat");
  const tabAudienceChat = document.getElementById("tabAudienceChat");
  const audienceUnreadBadge = document.getElementById("audienceUnreadBadge");
  const panelCreatorChat = document.getElementById("panelCreatorChat");
  const panelAudienceChat = document.getElementById("panelAudienceChat");
  const chatHistoryCreator = document.getElementById("chatHistoryCreator");
  const chatHistoryAudience = document.getElementById("chatHistoryAudience");
  const chatHistory = chatHistoryCreator || document.getElementById("chatHistory");
  const creatorChatForm = document.getElementById("creatorChatForm");
  const creatorChatInput = document.getElementById("creatorChatInput");
  const audienceChatForm = document.getElementById("audienceChatForm");
  const audienceUsernameInput = document.getElementById("audienceUsernameInput");
  const audienceChatInput = document.getElementById("audienceChatInput");
  const chatForm = creatorChatForm || document.getElementById("chatForm");
  const chatInput = creatorChatInput || document.getElementById("chatInput");

  let activeChatTab = "creator";
  let unreadAudienceCount = 0;

  function switchChatTab(tab) {
    activeChatTab = tab;
    if (tab === "creator") {
      if (tabCreatorChat) tabCreatorChat.classList.add("active");
      if (tabAudienceChat) tabAudienceChat.classList.remove("active");
      if (panelCreatorChat) panelCreatorChat.style.display = "flex";
      if (panelAudienceChat) panelAudienceChat.style.display = "none";
      if (chatHistoryCreator) chatHistoryCreator.scrollTop = chatHistoryCreator.scrollHeight;
    } else {
      if (tabAudienceChat) tabAudienceChat.classList.add("active");
      if (tabCreatorChat) tabCreatorChat.classList.remove("active");
      if (panelAudienceChat) panelAudienceChat.style.display = "flex";
      if (panelCreatorChat) panelCreatorChat.style.display = "none";
      unreadAudienceCount = 0;
      if (audienceUnreadBadge) {
        audienceUnreadBadge.textContent = "0";
        audienceUnreadBadge.style.display = "none";
      }
      if (chatHistoryAudience) chatHistoryAudience.scrollTop = chatHistoryAudience.scrollHeight;
    }
  }

  if (tabCreatorChat) {
    tabCreatorChat.addEventListener("click", () => switchChatTab("creator"));
  }
  if (tabAudienceChat) {
    tabAudienceChat.addEventListener("click", () => switchChatTab("audience"));
  }
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
    const urlParams = new URLSearchParams(window.location.search);
    const urlToken = urlParams.get("token");
    let storedToken = null;
    try {
      storedToken = localStorage.getItem("maybeai_creator_token") || localStorage.maybeai_creator_token || null;
    } catch (e) {}
    const creatorToken = urlToken || storedToken;
    let wsUrl = `${protocol}//${window.location.host}/ws`;
    if (creatorToken) {
      wsUrl += `?token=${encodeURIComponent(creatorToken)}`;
    }
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
      const isCreator = Boolean(msg.data.is_creator || msg.data.channel === "creator" || msg.data.source === "mic" || msg.data.source === "creator");
      const channel = msg.data.channel || (isCreator ? "creator" : "audience");
      let author = msg.data.user;
      if (msg.data.source === "minecraft") {
        author = `🎮 [MC] ${msg.data.user}`;
      } else if (msg.data.source === "mic") {
        author = `🎙️ [Mic] ${msg.data.user}`;
      }
      if (msg.data.is_donation) {
        author = `🎁 [SUPERCHAT ${msg.data.donation_amount}] ${msg.data.user}`;
      }
      addChatMessage(author, msg.data.text, false, msg.data.is_donation, channel, isCreator);
    } else if (msg.type === "donation_received") {
      showDonationAlert(msg.data.user, msg.data.amount, msg.data.text);
    } else if (msg.type === "ai_response") {
      const author = msg.data.user || "Eve";
      const isCreator = Boolean(msg.data.is_creator);
      const channel = msg.data.channel || (isCreator ? "creator" : "audience");
      addChatMessage(author, msg.data.speech, true, false, channel, isCreator);
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
      addChatMessage("Eve", `[Singing: ${msg.data.title}]`, true, false, "creator", true);
      addChatMessage("Eve", `[Singing: ${msg.data.title}]`, true, false, "audience", false);
    } else if (msg.type === "lyric_line") {
      isSinging = true;
      subtitles.textContent = `♪ ${msg.data.text} ♪`;
      if (typeof perfLiveLyrics !== "undefined" && perfLiveLyrics) {
        perfLiveLyrics.textContent = `♪ "${msg.data.text}" ♪`;
      }
      if (typeof perfCrowdCallout !== "undefined" && perfCrowdCallout) {
        if (msg.data.crowd_callout) {
          perfCrowdCallout.textContent = `🎤 Eve: "${msg.data.crowd_callout}"`;
          perfCrowdCallout.style.display = "inline-block";
        } else {
          perfCrowdCallout.style.display = "none";
        }
      }
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
    } else if (msg.type === "relationship_updated") {
      updateRelationshipUi(msg.data);
    } else if (msg.type === "vision_updated") {
      updateVisionUi(msg.data);
    } else if (msg.type === "multiplayer_updated") {
      updateMultiplayerUi(msg.data);
    } else if (msg.type === "desktop_updated") {
      updateDesktopUi(msg.data);
    } else if (msg.type === "minigame_updated") {
      updateMinigameUi(msg.data);
    } else if (msg.type === "story_updated") {
      updateStoryUi(msg.data);
    } else if (msg.type === "performance_updated") {
      updatePerformanceUi(msg.data);
    } else if (msg.type === "personality_updated") {
      updatePersonalityUi(msg.data);
    } else if (msg.type === "audience_cheer") {
      triggerCheerEffect(msg.data);
    } else if (msg.type === "avatar_movement") {
      triggerAvatarChoreography(msg.data);
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

  function addChatMessage(author, text, isAi = false, isDonation = false, channel = "creator", isCreator = false) {
    const isTargetCreator = (channel === "creator" || isCreator);
    const targetHistory = isTargetCreator ? (chatHistoryCreator || chatHistory) : (chatHistoryAudience || chatHistory);

    const div = document.createElement("div");
    let msgClass = "chat-msg";
    if (isAi) {
      msgClass += " neuro-msg";
    } else if (isTargetCreator) {
      msgClass += " creator-msg";
    } else {
      msgClass += " audience-msg";
    }
    if (isDonation) {
      msgClass += " donation-msg";
    }

    div.className = msgClass;
    let authorDisplay = escapeHtml(author);
    if (!isAi && isTargetCreator && !authorDisplay.includes("👑")) {
      authorDisplay = `👑 ${authorDisplay}`;
    }
    div.innerHTML = `<span class="author">${authorDisplay}:</span><span class="text">${escapeHtml(text)}</span>`;

    if (targetHistory) {
      targetHistory.appendChild(div);
      targetHistory.scrollTop = targetHistory.scrollHeight;
    }

    // Unread badge for audience tab when user is on creator tab
    if (!isTargetCreator && activeChatTab !== "audience") {
      unreadAudienceCount++;
      if (audienceUnreadBadge) {
        audienceUnreadBadge.textContent = unreadAudienceCount > 99 ? "99+" : unreadAudienceCount;
        audienceUnreadBadge.style.display = "inline-block";
      }
    }
  }

  function escapeHtml(string) {
    const el = document.createElement("div");
    el.innerText = string;
    return el.innerHTML;
  }

  // --- Chat Submit Forms ---
  if (creatorChatForm) {
    creatorChatForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = creatorChatInput ? creatorChatInput.value.trim() : "";
      if (!text) return;
      sendMessage("Creator", text, "creator", true);
      if (creatorChatInput) creatorChatInput.value = "";
    });
  }

  if (audienceChatForm) {
    audienceChatForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const user = (audienceUsernameInput && audienceUsernameInput.value.trim()) || "PenontonStream";
      const text = audienceChatInput ? audienceChatInput.value.trim() : "";
      if (!text) return;
      sendMessage(user, text, "web", false);
      if (audienceChatInput) audienceChatInput.value = "";
    });
  }

  // Fallback for chatForm
  if (chatForm && chatForm !== creatorChatForm) {
    chatForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = chatInput ? chatInput.value.trim() : "";
      if (!text) return;
      sendMessage("Creator", text, "creator", true);
      if (chatInput) chatInput.value = "";
    });
  }

  // Quick prompt pills (Sends as Creator VIP)
  document.querySelectorAll(".pill").forEach(pill => {
    pill.addEventListener("click", () => {
      const msg = pill.getAttribute("data-msg");
      if (msg) {
        sendMessage("Creator", msg, "creator", true);
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

  function sendMessage(user, text, source = "web", isCreator = null) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      const payload = {
        type: "user_message",
        user: user,
        text: text,
        source: source
      };
      if (isCreator !== null) {
        payload.is_creator = isCreator;
      }
      ws.send(JSON.stringify(payload));
    }
  }

  // --- Microphone Voice Listening (Speech-to-Text) ---
  const btnToggleMicHeader = document.getElementById("btn-toggle-mic-header");
  const btnCreatorMic = document.getElementById("btn-creator-mic");
  const creatorMicLabel = document.getElementById("creator-mic-label");
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
        sendMessage("Creator", spokenText, "mic", true);
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
    if (btnCreatorMic) {
      if (listening) {
        btnCreatorMic.classList.add("active");
        if (creatorMicLabel) creatorMicLabel.textContent = "Mendengarkan... (Klik untuk stop)";
      } else {
        btnCreatorMic.classList.remove("active");
        if (creatorMicLabel) creatorMicLabel.textContent = "Bicara ke Eve (Mic: OFF)";
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
  if (btnCreatorMic) {
    btnCreatorMic.addEventListener("click", toggleMic);
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

  // --- Relationship System & Social Intelligence Elements ---
  const relCurrentBadge = document.getElementById("rel-current-badge");
  const relStatsBadge = document.getElementById("rel-stats-badge");
  const relUserSelect = document.getElementById("relUserSelect");
  const relUserName = document.getElementById("rel-user-name");
  const relUserNickname = document.getElementById("rel-user-nickname");
  const relTierBadge = document.getElementById("rel-tier-badge");
  const relInteractionCount = document.getElementById("rel-interaction-count");
  const relFamVal = document.getElementById("rel-fam-val");
  const relFamBar = document.getElementById("rel-fam-bar");
  const relTrustVal = document.getElementById("rel-trust-val");
  const relTrustBar = document.getElementById("rel-trust-bar");
  const relRivalryVal = document.getElementById("rel-rivalry-val");
  const relRivalryBar = document.getElementById("rel-rivalry-bar");
  const relGamingVal = document.getElementById("rel-gaming-val");
  const relGamingBar = document.getElementById("rel-gaming-bar");
  const relJokesList = document.getElementById("rel-jokes-list");
  const btnToggleAddJoke = document.getElementById("btn-toggle-add-joke");
  const addJokeForm = document.getElementById("addJokeForm");
  const btnCancelJoke = document.getElementById("btn-cancel-joke");
  const relExperiencesList = document.getElementById("rel-experiences-list");

  let currentRelData = null;
  let selectedRelUser = "Creator";

  function sendRelationshipAction(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "relationship_action",
        ...payload
      }));
    }
  }

  function updateRelationshipUi(data) {
    if (!data) return;
    currentRelData = data;

    const profiles = data.profiles || {};
    const totalCount = data.total_relationships || Object.keys(profiles).length;

    if (relStatsBadge) {
      relStatsBadge.textContent = `Profiles: ${totalCount}`;
    }

    // Populate or sync User Dropdown
    if (relUserSelect) {
      const currentSelected = selectedRelUser || relUserSelect.value || "Creator";
      const existingOptions = Array.from(relUserSelect.options).map(o => o.value);
      const userKeys = Object.keys(profiles);

      if (JSON.stringify(existingOptions.sort()) !== JSON.stringify(userKeys.sort())) {
        relUserSelect.innerHTML = "";
        userKeys.forEach(u => {
          const opt = document.createElement("option");
          opt.value = u;
          opt.textContent = `${u} (${(profiles[u].tier || "").replace("_", " ")})`;
          if (u === currentSelected) opt.selected = true;
          relUserSelect.appendChild(opt);
        });
      }
    }

    renderSelectedProfile();
  }

  function renderSelectedProfile() {
    if (!currentRelData || !currentRelData.profiles) return;
    const profiles = currentRelData.profiles;
    const profile = profiles[selectedRelUser] || profiles["Creator"] || Object.values(profiles)[0];
    if (!profile) return;

    const username = profile.username || selectedRelUser;

    if (relCurrentBadge) relCurrentBadge.textContent = `Viewer: ${username}`;
    if (relUserName) relUserName.textContent = username;
    if (relUserNickname) relUserNickname.textContent = `Title: ${profile.nickname || 'Kawan Stream'}`;

    if (relTierBadge) {
      const tier = profile.tier || "new_friend";
      const tierLabels = {
        "new_friend": "New Friend 🌱",
        "regular_viewer": "Regular Viewer ☕",
        "gaming_partner": "Gaming Partner 🎮",
        "rival": "Rival / Rivalitas ⚔️",
        "trusted_friend": "Trusted Friend 💖"
      };
      relTierBadge.textContent = tierLabels[tier] || tier;

      if (tier === "trusted_friend") {
        relTierBadge.className = "badge badge-online";
      } else if (tier === "rival") {
        relTierBadge.className = "badge badge-danger";
      } else if (tier === "gaming_partner") {
        relTierBadge.className = "badge badge-accent";
      } else if (tier === "regular_viewer") {
        relTierBadge.className = "badge";
      } else {
        relTierBadge.className = "badge";
      }
    }

    if (relInteractionCount) {
      relInteractionCount.textContent = `${profile.interaction_count || 0} interaksi`;
    }

    // Gauges
    const setGauge = (bar, valElem, val) => {
      const pct = Math.round(Math.min(1.0, Math.max(0.0, val || 0)) * 100);
      if (bar) bar.style.width = `${pct}%`;
      if (valElem) valElem.textContent = `${pct}%`;
    };

    setGauge(relFamBar, relFamVal, profile.familiarity);
    setGauge(relTrustBar, relTrustVal, profile.trust);
    setGauge(relRivalryBar, relRivalryVal, profile.rivalry);
    setGauge(relGamingBar, relGamingVal, profile.gaming_affinity);

    // Render inside jokes
    if (relJokesList) {
      relJokesList.innerHTML = "";
      const jokes = profile.inside_jokes || [];
      if (jokes.length === 0) {
        relJokesList.innerHTML = "<div class='subtasks-hint' style='font-style: italic;'>Belum ada candaan internal unik bersama penonton ini.</div>";
      } else {
        jokes.forEach(j => {
          const jokeEl = document.createElement("div");
          jokeEl.className = "rel-joke-pill";
          jokeEl.innerHTML = `
            <span class="rel-joke-topic">🎭 ${escapeHtml(j.topic || 'Joke')}</span>
            <span class="rel-joke-punchline">"${escapeHtml(j.punchline || '')}"</span>
          `;
          relJokesList.appendChild(jokeEl);
        });
      }
    }

    // Render shared experiences
    if (relExperiencesList) {
      relExperiencesList.innerHTML = "";
      const exps = profile.shared_experiences || [];
      if (exps.length === 0) {
        relExperiencesList.innerHTML = "<div class='subtasks-hint' style='font-style: italic;'>Belum ada riwayat momen spesial tercatat.</div>";
      } else {
        exps.slice().reverse().forEach(exp => {
          const item = document.createElement("div");
          item.className = "rel-exp-item";
          item.innerHTML = `
            <span class="badge badge-sm">${escapeHtml(exp.category || 'chat')}</span>
            <span class="rel-exp-summary">${escapeHtml(exp.summary || '')}</span>
            <span class="rel-exp-time">${escapeHtml(exp.timestamp ? exp.timestamp.substring(11, 16) : '')}</span>
          `;
          relExperiencesList.appendChild(item);
        });
      }
    }
  }

  // Dropdown change listener
  if (relUserSelect) {
    relUserSelect.addEventListener("change", () => {
      selectedRelUser = relUserSelect.value;
      renderSelectedProfile();
    });
  }

  // Quick pills listener
  document.querySelectorAll(".rel-quick-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      const u = pill.dataset.user;
      if (u) {
        selectedRelUser = u;
        if (relUserSelect) relUserSelect.value = u;
        document.querySelectorAll(".rel-quick-pill").forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        renderSelectedProfile();
      }
    });
  });

  // Toggle joke form
  if (btnToggleAddJoke && addJokeForm) {
    btnToggleAddJoke.addEventListener("click", () => {
      addJokeForm.style.display = addJokeForm.style.display === "none" ? "flex" : "none";
    });
  }

  if (btnCancelJoke && addJokeForm) {
    btnCancelJoke.addEventListener("click", () => {
      addJokeForm.style.display = "none";
    });
  }

  if (addJokeForm) {
    addJokeForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const topic = document.getElementById("jokeNewTopic").value.trim();
      const punchline = document.getElementById("jokeNewPunchline").value.trim();
      const context = document.getElementById("jokeNewContext").value.trim();

      if (!topic || !punchline) return;

      sendRelationshipAction({
        action: "add_inside_joke",
        username: selectedRelUser,
        topic: topic,
        punchline: punchline,
        context: context
      });

      addJokeForm.reset();
      addJokeForm.style.display = "none";
    });
  }

  // Relationship simulator buttons
  document.querySelectorAll(".btn-rel-sim").forEach(btn => {
    btn.addEventListener("click", () => {
      const eventType = btn.dataset.event;
      const game = btn.dataset.game || "general";
      if (eventType) {
        sendRelationshipAction({
          action: "simulate_event",
          username: selectedRelUser,
          event_type: eventType,
          game: game,
          details: { stimulated_by: "dashboard_sim" }
        });
      }
    });
  });

  // --- Visual Perception & Screen Awareness Elements ---
  const visionSceneBadge = document.getElementById("vision-scene-badge");
  const visionAutoBadge = document.getElementById("vision-auto-badge");
  const visionDiffBadge = document.getElementById("vision-diff-badge");
  const visionTimestamp = document.getElementById("vision-timestamp");
  const visionScreenImg = document.getElementById("visionScreenImg");
  const visionScreenPlaceholder = document.getElementById("visionScreenPlaceholder");
  const visionEventOverlay = document.getElementById("visionEventOverlay");
  const visionEventText = document.getElementById("visionEventText");
  const visionSceneLabel = document.getElementById("visionSceneLabel");
  const visionConfBar = document.getElementById("visionConfBar");
  const visionConfVal = document.getElementById("visionConfVal");
  const visionDiffBar = document.getElementById("visionDiffBar");
  const visionDiffVal = document.getElementById("visionDiffVal");
  const visionSummaryText = document.getElementById("visionSummaryText");
  const visionCommentaryText = document.getElementById("visionCommentaryText");
  const btnVisionSnap = document.getElementById("btn-vision-snap");
  const btnVisionToggleAuto = document.getElementById("btn-vision-toggle-auto");

  let currentVisionData = null;
  let isVisionAuto = true;

  function sendVisionAction(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "vision_action",
        ...payload
      }));
    }
  }

  function updateVisionUi(data) {
    if (!data) return;
    currentVisionData = data;
    isVisionAuto = data.is_auto_active !== undefined ? data.is_auto_active : isVisionAuto;

    if (visionAutoBadge) {
      visionAutoBadge.textContent = isVisionAuto ? "Auto-Perceive: ON" : "Auto-Perceive: OFF";
      visionAutoBadge.className = isVisionAuto ? "badge badge-online" : "badge";
    }

    if (btnVisionToggleAuto) {
      btnVisionToggleAuto.textContent = isVisionAuto ? "⏸️ Pause Auto-Perceive" : "▶️ Resume Auto-Perceive";
    }

    const obs = data.current_observation;
    if (!obs) return;

    if (visionSceneBadge) {
      visionSceneBadge.textContent = `Scene: ${obs.scene_label || obs.scene_type}`;
      if (obs.scene_type === "minecraft_defeat") {
        visionSceneBadge.className = "badge badge-danger";
      } else if (obs.scene_type === "minecraft_diamond") {
        visionSceneBadge.className = "badge badge-accent";
      } else if (obs.scene_type === "chess_gameover") {
        visionSceneBadge.className = "badge badge-online";
      } else {
        visionSceneBadge.className = "badge";
      }
    }

    const diffPct = Math.round((obs.change_delta || 0) * 100);
    if (visionDiffBadge) {
      visionDiffBadge.textContent = `Diff: ${diffPct}%`;
    }

    if (visionTimestamp && obs.formatted_time) {
      visionTimestamp.textContent = obs.formatted_time;
    }

    // Render image frame
    if (obs.thumbnail_base64 && visionScreenImg && visionScreenPlaceholder) {
      visionScreenImg.src = obs.thumbnail_base64;
      visionScreenImg.style.display = "block";
      visionScreenPlaceholder.style.display = "none";
    }

    // Event overlay check
    if (visionEventOverlay && visionEventText) {
      if (obs.is_event) {
        let evLabel = "EVENT DETECTED!";
        if (obs.event_type === "player_defeat") evLabel = "💀 PLAYER DEFEAT DETECTED (YOU DIED!)";
        else if (obs.event_type === "diamond_found") evLabel = "💎 DIAMOND VEIN DISCOVERED (Y=-58)";
        else if (obs.event_type === "checkmate") evLabel = "👑 CHECKMATE / GAME OVER!";
        else if (obs.event_type === "video_reaction") evLabel = "🎬 VIDEO STREAM MOMENT!";
        else if (obs.event_type === "scene_change") evLabel = "🔄 SIGNIFICANT SCENE TRANSITION!";

        visionEventText.textContent = evLabel;
        visionEventOverlay.style.display = "block";
      } else {
        visionEventOverlay.style.display = "none";
      }
    }

    // Telemetry
    if (visionSceneLabel) visionSceneLabel.textContent = obs.scene_label || obs.scene_type;

    const confPct = Math.round((obs.confidence || 0.85) * 100);
    if (visionConfVal) visionConfVal.textContent = `${confPct}%`;
    if (visionConfBar) visionConfBar.style.width = `${confPct}%`;

    if (visionDiffVal) visionDiffVal.textContent = `${diffPct}%`;
    if (visionDiffBar) visionDiffBar.style.width = `${diffPct}%`;

    if (visionSummaryText) visionSummaryText.textContent = obs.summary || "Layar termonitor.";
    if (visionCommentaryText && obs.eve_commentary) {
      visionCommentaryText.textContent = `"${obs.eve_commentary}"`;
    }
  }

  // Snap button
  if (btnVisionSnap) {
    btnVisionSnap.addEventListener("click", () => {
      sendVisionAction({ action: "perceive_now" });
    });
  }

  // Toggle auto
  if (btnVisionToggleAuto) {
    btnVisionToggleAuto.addEventListener("click", () => {
      sendVisionAction({ action: "toggle_auto", enabled: !isVisionAuto });
    });
  }

  // Preset buttons
  document.querySelectorAll(".btn-vision-preset").forEach(btn => {
    btn.addEventListener("click", () => {
      const scene = btn.dataset.scene;
      if (scene) {
        sendVisionAction({ action: "perceive_now", simulated_scene: scene });
      }
    });
  });

  // =========================================================================
  // --- Minecraft Multiplayer Social Intelligence UI ---
  // =========================================================================
  const mpSquadBadge = document.getElementById("mp-squad-badge");
  const mpPartnerBadge = document.getElementById("mp-partner-badge");
  const mpContributorsBadge = document.getElementById("mp-contributors-badge");
  const mpSquadName = document.getElementById("mpSquadName");
  const mpSquadMotto = document.getElementById("mpSquadMotto");
  const mpMembersList = document.getElementById("mpMembersList");
  const mpTreasuryItems = document.getElementById("mpTreasuryItems");

  const mpPartnerFitnessBadge = document.getElementById("mpPartnerFitnessBadge");
  const mpPartnerName = document.getElementById("mpPartnerName");
  const mpPartnerMission = document.getElementById("mpPartnerMission");
  const mpPartnerSpeech = document.getElementById("mpPartnerSpeech");
  const selectPartnerMission = document.getElementById("selectPartnerMission");
  const btnSelectPartner = document.getElementById("btn-select-partner");

  const mpContributorsList = document.getElementById("mpContributorsList");
  const mpBarterHistory = document.getElementById("mpBarterHistory");
  const mpTradeForm = document.getElementById("mpTradeForm");
  const tradeProposer = document.getElementById("tradeProposer");
  const tradeOffering = document.getElementById("tradeOffering");
  const tradeRequesting = document.getElementById("tradeRequesting");
  const btnTradeRipoffSim = document.getElementById("btn-trade-ripoff-sim");
  const mpGroupChatHistory = document.getElementById("mpGroupChatHistory");

  function sendMultiplayerAction(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "multiplayer_action",
        ...payload
      }));
    }
  }

  function parseItemInput(str) {
    if (!str) return {};
    str = str.trim();
    if (str.startsWith("{")) {
      try { return JSON.parse(str); } catch (e) {}
    }
    const result = {};
    const parts = str.split(",");
    for (const p of parts) {
      const match = p.trim().match(/^(\d+)\s+([a-zA-Z0-9_]+)$/);
      if (match) {
        result[match[2].toLowerCase()] = parseInt(match[1], 10);
      } else {
        const itemMatch = p.trim().match(/^([a-zA-Z0-9_]+)$/);
        if (itemMatch) {
          result[itemMatch[1].toLowerCase()] = 1;
        }
      }
    }
    return result;
  }

  function updateMultiplayerUi(data) {
    if (!data) return;

    // Badges
    if (mpSquadBadge && data.active_team) {
      mpSquadBadge.textContent = data.active_team.name || "Squad Maybe ✨";
    }
    if (mpPartnerBadge && data.selected_partner) {
      mpPartnerBadge.textContent = `Partner: ${data.selected_partner}`;
    }
    if (mpContributorsBadge && data.ledger) {
      mpContributorsBadge.textContent = `Tracked Players: ${data.ledger.length}`;
    }

    // Active Squad Box
    if (data.active_team) {
      if (mpSquadName) mpSquadName.textContent = data.active_team.name;
      if (mpSquadMotto) mpSquadMotto.textContent = `"${data.active_team.motto}"`;

      if (mpMembersList && data.active_team.members) {
        mpMembersList.innerHTML = "";
        data.active_team.members.forEach(mem => {
          const role = (data.active_team.member_roles && data.active_team.member_roles[mem]) || "member";
          const pill = document.createElement("div");
          const isLeader = (data.active_team.leader === mem);
          pill.className = `mp-member-pill ${isLeader ? "leader" : ""}`;

          const roleClass = `role-${role.toLowerCase()}`;
          pill.innerHTML = `
            <span class="member-name">${mem === "Eve" ? "👑 Eve" : mem}</span>
            <span class="role-badge ${roleClass}">${role}</span>
          `;
          mpMembersList.appendChild(pill);
        });
      }

      if (mpTreasuryItems && data.active_team.treasury) {
        mpTreasuryItems.innerHTML = "";
        const iconMap = {
          diamond: "💎",
          iron: "🧱",
          iron_ingot: "🧱",
          gold: "🪙",
          gold_ingot: "🪙",
          bread: "🍞",
          apple: "🍎",
          torch: "🕯️",
          netherite: "🛡️"
        };
        for (const [item, count] of Object.entries(data.active_team.treasury)) {
          const icon = iconMap[item.toLowerCase()] || "📦";
          const tag = document.createElement("span");
          tag.className = "treasury-tag";
          tag.textContent = `${icon} ${count} ${item.replace('_', ' ')}`;
          mpTreasuryItems.appendChild(tag);
        }
      }
    }

    // Partner Spotlight
    if (data.selected_partner) {
      if (mpPartnerName) mpPartnerName.textContent = data.selected_partner;
      if (mpPartnerMission) mpPartnerMission.textContent = `Misi: ${(data.partner_mission || "mining").toUpperCase()}`;
      if (mpPartnerFitnessBadge) {
        const score = Math.round(data.partner_score || 95);
        mpPartnerFitnessBadge.textContent = `Fitness: ${score}%`;
      }
      if (mpPartnerSpeech && data.partner_speech) {
        mpPartnerSpeech.textContent = `"${data.partner_speech}"`;
      }
      if (selectPartnerMission && data.partner_mission) {
        selectPartnerMission.value = data.partner_mission;
      }
    }

    // Contributors List
    if (mpContributorsList && data.ledger) {
      mpContributorsList.innerHTML = "";
      data.ledger.forEach(p => {
        const card = document.createElement("div");
        card.className = "contributor-card";

        let repClass = "rep-neutral";
        let repLabel = "Neutral";
        if (p.reputation >= 85) {
          repClass = "rep-hero";
          repLabel = "Hero ⭐";
        } else if (p.reputation >= 60) {
          repClass = "rep-trusted";
          repLabel = "Trusted";
        } else if (p.reputation < 30) {
          repClass = "rep-villain";
          repLabel = "Troublemaker ⚠️";
        }

        const donList = [];
        if (p.items_donated) {
          for (const [k, v] of Object.entries(p.items_donated)) {
            donList.push(`${v} ${k}`);
          }
        }
        const donStr = donList.length > 0 ? donList.join(", ") : "Belum ada";

        card.innerHTML = `
          <div class="contributor-header">
            <span class="contributor-name">👤 ${p.player_name} <small style="color:var(--text-muted); font-weight:normal;">(${p.role_specialty || "General"})</small></span>
            <span class="reputation-badge ${repClass}">Rep: ${Math.round(p.reputation)}/100 (${repLabel})</span>
          </div>
          <div class="contributor-stats">
            <span class="stat-pill">🎁 Donasi: ${donStr}</span>
            <span class="stat-pill">⚔️ Mob: ${p.mobs_killed_for_team || 0}</span>
            <span class="stat-pill">🏡 Bangun: ${p.structures_built || 0}</span>
            ${p.times_attacked_eve > 0 ? `<span class="stat-pill" style="color:#f87171;">⚠️ Serang Eve: ${p.times_attacked_eve}x</span>` : ""}
          </div>
          ${p.notes && p.notes.length > 0 ? `<div class="stat-notes">Catatan: "${p.notes[p.notes.length - 1]}"</div>` : ""}
        `;
        mpContributorsList.appendChild(card);
      });
    }

    // Barter History
    if (mpBarterHistory && data.recent_trades) {
      mpBarterHistory.innerHTML = "";
      if (data.recent_trades.length === 0) {
        mpBarterHistory.innerHTML = `<div class="trade-comment" style="color:var(--text-muted);">Belum ada riwayat tawaran barter.</div>`;
      } else {
        data.recent_trades.slice().reverse().forEach(tr => {
          const tCard = document.createElement("div");
          tCard.className = "trade-card";

          let vClass = "verdict-rejected";
          let vText = "Ditolak";
          if (tr.status === "accepted") {
            vClass = "verdict-accepted";
            vText = "Diterima ✅";
          } else if (tr.status === "counter") {
            vClass = "verdict-counter";
            vText = "Counter-Offer 🔄";
          } else {
            vText = "Ditolak ❌";
          }

          const offStr = Object.entries(tr.offering || {}).map(([k, v]) => `${v} ${k}`).join(", ");
          const reqStr = Object.entries(tr.requesting || {}).map(([k, v]) => `${v} ${k}`).join(", ");

          tCard.innerHTML = `
            <div class="trade-header">
              <span class="trade-proposer">⚖️ ${tr.proposer}</span>
              <span class="trade-verdict-badge ${vClass}">${vText}</span>
            </div>
            <div class="trade-items-row">
              <span>Tawarkan: ${offStr || "Kosong"}</span>
              <span class="trade-arrow">➔</span>
              <span>Minta: ${reqStr || "Kosong"}</span>
            </div>
            ${tr.eve_verdict ? `<p class="trade-comment">"${tr.eve_verdict}"</p>` : ""}
          `;
          mpBarterHistory.appendChild(tCard);
        });
      }
    }

    // Multi-Speaker Group Chat
    if (mpGroupChatHistory && data.group_chat) {
      mpGroupChatHistory.innerHTML = "";
      data.group_chat.forEach(turn => {
        const turnDiv = document.createElement("div");
        const spkKey = turn.speaker.toLowerCase().replace(/[^a-z0-9]/g, "");
        turnDiv.className = `mp-chat-turn turn-${spkKey}`;

        let avatar = "💬";
        if (spkKey.includes("eve")) avatar = "✨";
        else if (spkKey.includes("diamond")) avatar = "⛏️";
        else if (spkKey.includes("alex")) avatar = "🛡️";
        else if (spkKey.includes("steve")) avatar = "🏡";
        else if (spkKey.includes("garry")) avatar = "😈";

        const timeStr = turn.timestamp ? new Date(turn.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : "";

        turnDiv.innerHTML = `
          <span class="speaker-avatar">${avatar}</span>
          <div class="turn-content">
            <span class="speaker-name">${turn.speaker} <span class="turn-time">${timeStr}</span></span>
            <span class="turn-msg">${turn.message}</span>
          </div>
        `;
        mpGroupChatHistory.appendChild(turnDiv);
      });
      mpGroupChatHistory.scrollTop = mpGroupChatHistory.scrollHeight;
    }
  }

  // Partner Selector button
  if (btnSelectPartner && selectPartnerMission) {
    btnSelectPartner.addEventListener("click", () => {
      const mission = selectPartnerMission.value;
      sendMultiplayerAction({
        action: "choose_partner",
        mission_type: mission
      });
    });
  }

  // Trade form submit
  if (mpTradeForm) {
    mpTradeForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const pName = (tradeProposer && tradeProposer.value.trim()) || "Player";
      const offObj = parseItemInput(tradeOffering ? tradeOffering.value : "");
      const reqObj = parseItemInput(tradeRequesting ? tradeRequesting.value : "");
      sendMultiplayerAction({
        action: "propose_trade",
        player_name: pName,
        offering: offObj,
        requesting: reqObj
      });
    });
  }

  // Ripoff trade sim button
  if (btnTradeRipoffSim) {
    btnTradeRipoffSim.addEventListener("click", () => {
      sendMultiplayerAction({
        action: "propose_trade",
        player_name: "GrieferGarry",
        offering: { "dirt": 1 },
        requesting: { "diamond": 5 }
      });
    });
  }

  // Community action simulation buttons
  document.querySelectorAll(".btn-mp-sim").forEach(btn => {
    btn.addEventListener("click", () => {
      const act = btn.dataset.action;
      if (act === "donate_diamond") {
        sendMultiplayerAction({
          action: "record_donation",
          player_name: "DiamondHunter",
          item: "diamond",
          count: 3
        });
      } else if (act === "combat_aid") {
        sendMultiplayerAction({
          action: "record_combat",
          player_name: "Alex",
          mob: "Creeper"
        });
      } else if (act === "build_help") {
        sendMultiplayerAction({
          action: "record_build",
          player_name: "Steve",
          task: "Konstruksi Dinding Base"
        });
      } else if (act === "group_nether") {
        sendMultiplayerAction({
          action: "in_game_chat",
          sender: "Alex",
          message: "Ayo kawan-kawan kita serbu Nether cari Blaze rod bareng!"
        });
        setTimeout(() => {
          sendMultiplayerAction({
            action: "in_game_chat",
            sender: "Steve",
            message: "Siap, aku bawa 10 obsidian sama perlengkapan potion fire resistance!"
          });
        }, 800);
      }
    });
  });

  // =========================================================================
  // --- Desktop Companion & Computer Interaction UI ---
  // =========================================================================
  const dtMasterBadge = document.getElementById("dt-master-badge");
  const dtVolumeBadge = document.getElementById("dt-volume-badge");
  const dtMediaBadge = document.getElementById("dt-media-badge");
  const dtPendingBadge = document.getElementById("dt-pending-badge");

  const dtMasterToggle = document.getElementById("dtMasterToggle");
  const dtRequireHighRisk = document.getElementById("dtRequireHighRisk");
  const dtRequireMediumRisk = document.getElementById("dtRequireMediumRisk");

  const dtPendingAlert = document.getElementById("dtPendingAlert");
  const dtPendingTitle = document.getElementById("dtPendingTitle");
  const dtPendingDesc = document.getElementById("dtPendingDesc");
  const btnDtApprovePending = document.getElementById("btnDtApprovePending");
  const btnDtRejectPending = document.getElementById("btnDtRejectPending");

  const dtCurrentTrackBadge = document.getElementById("dtCurrentTrackBadge");
  const dtVolumeText = document.getElementById("dtVolumeText");
  const dtVolumeSlider = document.getElementById("dtVolumeSlider");
  const btnDtMuteToggle = document.getElementById("btnDtMuteToggle");
  const btnDtMediaPrev = document.getElementById("btnDtMediaPrev");
  const btnDtMediaPlayPause = document.getElementById("btnDtMediaPlayPause");
  const btnDtMediaNext = document.getElementById("btnDtMediaNext");

  const dtAllowedAppsList = document.getElementById("dtAllowedAppsList");
  const dtAddAppForm = document.getElementById("dtAddAppForm");
  const dtAppInput = document.getElementById("dtAppInput");

  const dtNotifsCount = document.getElementById("dtNotifsCount");
  const dtNotifsList = document.getElementById("dtNotifsList");
  const dtAuditList = document.getElementById("dtAuditList");

  let currentPendingActionId = null;

  function sendDesktopAction(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "desktop_action",
        ...payload
      }));
    }
  }

  function updateDesktopUi(data) {
    if (!data) return;

    // 1. Status Badges
    if (dtMasterBadge) {
      dtMasterBadge.textContent = data.master_enabled ? "Companion: ACTIVE" : "Companion: DISABLED";
      dtMasterBadge.className = data.master_enabled ? "badge badge-online" : "badge";
    }
    if (dtVolumeBadge) {
      dtVolumeBadge.textContent = `Vol: ${data.current_volume}% ${data.is_muted ? '(Muted)' : ''}`;
    }
    if (dtMediaBadge) {
      dtMediaBadge.textContent = `Media: ${data.media_state.toUpperCase()}`;
    }

    // 2. Pending Actions Alert
    if (data.pending_actions && data.pending_actions.length > 0) {
      const pending = data.pending_actions[0];
      currentPendingActionId = pending.id;
      if (dtPendingAlert) dtPendingAlert.style.display = "flex";
      if (dtPendingBadge) {
        dtPendingBadge.style.display = "inline-block";
        dtPendingBadge.textContent = `${data.pending_actions.length} Pending Approval`;
      }
      if (dtPendingTitle) {
        dtPendingTitle.textContent = `Konfirmasi Izin: ${pending.action_type.replace('_', ' ').toUpperCase()} (${pending.risk_level.toUpperCase()})`;
      }
      if (dtPendingDesc) {
        dtPendingDesc.textContent = `${pending.details} Target: ${JSON.stringify(pending.params || {})}`;
      }
    } else {
      currentPendingActionId = null;
      if (dtPendingAlert) dtPendingAlert.style.display = "none";
      if (dtPendingBadge) dtPendingBadge.style.display = "none";
    }

    // 3. Master & Policy Toggles
    if (dtMasterToggle) dtMasterToggle.checked = !!data.master_enabled;
    if (dtRequireHighRisk) dtRequireHighRisk.checked = !!data.require_confirmation_for_high;
    if (dtRequireMediumRisk) dtRequireMediumRisk.checked = !!data.require_confirmation_for_medium;

    // 4. Category Toggles
    if (data.categories) {
      document.querySelectorAll(".dt-perm-toggle").forEach(toggle => {
        const cat = toggle.dataset.category;
        if (cat in data.categories) {
          toggle.checked = !!data.categories[cat];
        }
      });
    }

    // 5. Volume & Media State
    if (dtVolumeText) dtVolumeText.textContent = `${data.current_volume}%`;
    if (dtVolumeSlider) dtVolumeSlider.value = data.current_volume;
    if (btnDtMuteToggle) {
      btnDtMuteToggle.textContent = data.is_muted ? "🔊 Unmute" : "🔇 Mute";
      btnDtMuteToggle.className = data.is_muted ? "btn btn-danger btn-xs" : "btn btn-secondary btn-xs";
    }
    if (dtCurrentTrackBadge) dtCurrentTrackBadge.textContent = data.current_track || "No media";
    if (btnDtMediaPlayPause) {
      btnDtMediaPlayPause.textContent = data.media_state === "playing" ? "⏸️ Pause" : "▶️ Play";
    }

    // 6. Whitelist Apps Tags
    if (dtAllowedAppsList && data.allowed_apps) {
      dtAllowedAppsList.innerHTML = "";
      data.allowed_apps.forEach(app => {
        const tag = document.createElement("span");
        tag.className = "dt-app-tag";
        tag.innerHTML = `
          <span>💻 ${app}</span>
          <span class="dt-app-remove" data-app="${app}" title="Hapus dari whitelist">✕</span>
        `;
        dtAllowedAppsList.appendChild(tag);
      });

      dtAllowedAppsList.querySelectorAll(".dt-app-remove").forEach(btn => {
        btn.addEventListener("click", () => {
          const appToRemove = btn.dataset.app;
          sendDesktopAction({ action: "remove_app", app_name: appToRemove });
        });
      });
    }

    // 7. Notifications
    if (dtNotifsList && data.notifications) {
      dtNotifsList.innerHTML = "";
      if (dtNotifsCount) dtNotifsCount.textContent = `${data.notifications.length} Notifikasi`;
      data.notifications.forEach(n => {
        const item = document.createElement("div");
        item.className = "dt-notif-item";
        item.innerHTML = `
          <div class="notif-header">
            <span class="notif-source">${n.source}</span>
            <span class="notif-time">${n.time_str || ''}</span>
          </div>
          <div class="notif-title">${n.title}</div>
          <div class="notif-body">${n.body}</div>
        `;
        dtNotifsList.appendChild(item);
      });
    }

    // 8. Audit Log
    if (dtAuditList && data.audit_log) {
      dtAuditList.innerHTML = "";
      data.audit_log.forEach(a => {
        const row = document.createElement("div");
        row.className = "dt-audit-item";
        const stClass = `audit-status-${(a.status || 'executed').toLowerCase()}`;
        row.innerHTML = `
          <div class="audit-left">
            <span class="audit-status-badge ${stClass}">${a.status}</span>
            <span class="audit-details"><strong>${a.action_type}</strong>: ${a.details}</span>
          </div>
          <span class="audit-time">${a.requested_at_str || ''}</span>
        `;
        dtAuditList.appendChild(row);
      });
    }
  }

  // --- Event Listeners for Desktop UI ---
  if (dtMasterToggle) {
    dtMasterToggle.addEventListener("change", (e) => {
      sendDesktopAction({ action: "toggle_master", enabled: e.target.checked });
    });
  }

  function sendPolicyUpdate() {
    sendDesktopAction({
      action: "set_policy",
      require_high: dtRequireHighRisk ? dtRequireHighRisk.checked : true,
      require_medium: dtRequireMediumRisk ? dtRequireMediumRisk.checked : false
    });
  }

  if (dtRequireHighRisk) dtRequireHighRisk.addEventListener("change", sendPolicyUpdate);
  if (dtRequireMediumRisk) dtRequireMediumRisk.addEventListener("change", sendPolicyUpdate);

  document.querySelectorAll(".dt-perm-toggle").forEach(toggle => {
    toggle.addEventListener("change", (e) => {
      const cat = e.target.dataset.category;
      sendDesktopAction({ action: "toggle_category", category: cat, enabled: e.target.checked });
    });
  });

  if (dtVolumeSlider) {
    dtVolumeSlider.addEventListener("input", (e) => {
      if (dtVolumeText) dtVolumeText.textContent = `${e.target.value}%`;
    });
    dtVolumeSlider.addEventListener("change", (e) => {
      sendDesktopAction({
        action: "request_action",
        category: "volume_control",
        action_type: "set_volume",
        params: { volume: parseInt(e.target.value, 10) }
      });
    });
  }

  if (btnDtMuteToggle) {
    btnDtMuteToggle.addEventListener("click", () => {
      sendDesktopAction({
        action: "request_action",
        category: "volume_control",
        action_type: "toggle_mute"
      });
    });
  }

  if (btnDtMediaPlayPause) {
    btnDtMediaPlayPause.addEventListener("click", () => {
      sendDesktopAction({
        action: "request_action",
        category: "media_control",
        action_type: "play_pause"
      });
    });
  }

  if (btnDtMediaNext) {
    btnDtMediaNext.addEventListener("click", () => {
      sendDesktopAction({
        action: "request_action",
        category: "media_control",
        action_type: "next"
      });
    });
  }

  if (btnDtMediaPrev) {
    btnDtMediaPrev.addEventListener("click", () => {
      sendDesktopAction({
        action: "request_action",
        category: "media_control",
        action_type: "prev"
      });
    });
  }

  if (btnDtApprovePending) {
    btnDtApprovePending.addEventListener("click", () => {
      if (currentPendingActionId) {
        sendDesktopAction({ action: "confirm_action", action_id: currentPendingActionId, approved: true });
      }
    });
  }

  if (btnDtRejectPending) {
    btnDtRejectPending.addEventListener("click", () => {
      if (currentPendingActionId) {
        sendDesktopAction({ action: "confirm_action", action_id: currentPendingActionId, approved: false });
      }
    });
  }

  if (dtAddAppForm && dtAppInput) {
    dtAddAppForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const val = dtAppInput.value.trim();
      if (val) {
        sendDesktopAction({ action: "add_app", app_name: val });
        dtAppInput.value = "";
      }
    });
  }

  // Quick Action Test Buttons
  document.querySelectorAll(".btn-dt-test").forEach(btn => {
    btn.addEventListener("click", () => {
      const testType = btn.dataset.test;
      if (testType === "vol_down") {
        sendDesktopAction({
          action: "request_action",
          category: "volume_control",
          action_type: "adjust_volume",
          params: { delta: -10 }
        });
      } else if (testType === "music_next") {
        sendDesktopAction({
          action: "request_action",
          category: "media_control",
          action_type: "next"
        });
      } else if (testType === "launch_notepad") {
        sendDesktopAction({
          action: "request_action",
          category: "app_launch",
          action_type: "launch_app",
          params: { app_name: "notepad.exe" }
        });
      } else if (testType === "read_notif") {
        sendDesktopAction({
          action: "request_action",
          category: "notifications_read",
          action_type: "read_notification"
        });
      } else if (testType === "risky_obs") {
        // High-Risk simulation: changing OBS scene or stopping stream
        sendDesktopAction({
          action: "request_action",
          category: "streaming_ops",
          action_type: "switch_scene",
          params: { scene_name: "Gaming Mode (Speedrun)" }
        });
      }
    });
  });

  // --- Interactive Mini-Game Engine & Crowd Play ---
  const mgStatusBadge = document.getElementById("mg-status-badge");
  const mgModeBadge = document.getElementById("mg-mode-badge");
  const mgRoundBadge = document.getElementById("mg-round-badge");
  const mgTimerBadge = document.getElementById("mg-timer-badge");
  const mgScoreBadge = document.getElementById("mg-score-badge");

  const selectMgRounds = document.getElementById("selectMgRounds");
  const btnMgStart = document.getElementById("btnMgStart");
  const btnMgNextRound = document.getElementById("btnMgNextRound");
  const btnMgHint = document.getElementById("btnMgHint");
  const btnMgStop = document.getElementById("btnMgStop");
  const mgHostSpeech = document.getElementById("mgHostSpeech");

  const viewMgTrivia = document.getElementById("viewMgTrivia");
  const mgTriviaCategory = document.getElementById("mgTriviaCategory");
  const mgTriviaQuestion = document.getElementById("mgTriviaQuestion");
  const mgTriviaOptions = document.getElementById("mgTriviaOptions");

  const viewMgGuessNumber = document.getElementById("viewMgGuessNumber");
  const mgNumRangeText = document.getElementById("mgNumRangeText");
  const mgNumBarFill = document.getElementById("mgNumBarFill");
  const mgLastGuessFeedback = document.getElementById("mgLastGuessFeedback");

  const viewMgWouldYouRather = document.getElementById("viewMgWouldYouRather");
  const mgWyrTopic = document.getElementById("mgWyrTopic");
  const wyrTextA = document.getElementById("wyrTextA");
  const wyrTextB = document.getElementById("wyrTextB");
  const wyrPctA = document.getElementById("wyrPctA");
  const wyrPctB = document.getElementById("wyrPctB");

  const viewMgRiddle = document.getElementById("viewMgRiddle");
  const mgRiddleText = document.getElementById("mgRiddleText");
  const mgHintsList = document.getElementById("mgHintsList");

  const viewMgWordAssociation = document.getElementById("viewMgWordAssociation");
  const mgThemeText = document.getElementById("mgThemeText");
  const mgWordChainList = document.getElementById("mgWordChainList");

  const viewMgGuessSong = document.getElementById("viewMgGuessSong");
  const mgSongGenre = document.getElementById("mgSongGenre");
  const mgSongClue = document.getElementById("mgSongClue");
  const mgSongHintsList = document.getElementById("mgSongHintsList");

  const mgLeaderboardList = document.getElementById("mgLeaderboardList");
  const mgChatSubmitForm = document.getElementById("mgChatSubmitForm");
  const mgChatUser = document.getElementById("mgChatUser");
  const mgChatMessage = document.getElementById("mgChatMessage");
  const mgEventHistoryList = document.getElementById("mgEventHistoryList");

  let selectedMiniGameMode = "trivia";
  let minigameTimerTicker = null;
  let minigameExpiresAt = 0;

  function sendMinigameAction(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "minigame_action",
        ...payload
      }));
    }
  }

  function switchMiniGameView(gameType) {
    const views = {
      "trivia": viewMgTrivia,
      "guess_number": viewMgGuessNumber,
      "would_you_rather": viewMgWouldYouRather,
      "riddle": viewMgRiddle,
      "word_association": viewMgWordAssociation,
      "guess_song": viewMgGuessSong
    };

    Object.entries(views).forEach(([type, el]) => {
      if (!el) return;
      if (type === gameType) {
        el.style.display = "block";
        el.classList.add("active");
      } else {
        el.style.display = "none";
        el.classList.remove("active");
      }
    });

    document.querySelectorAll(".btn-mg-mode").forEach(pill => {
      if (pill.dataset.game === gameType) {
        pill.classList.add("active");
      } else {
        pill.classList.remove("active");
      }
    });
  }

  function startMiniGameLocalTimer(remainingSec) {
    if (minigameTimerTicker) {
      clearInterval(minigameTimerTicker);
      minigameTimerTicker = null;
    }

    if (remainingSec <= 0) {
      if (mgTimerBadge) {
        mgTimerBadge.textContent = "⏱️ Waktu Habis!";
        mgTimerBadge.className = "badge";
      }
      return;
    }

    minigameExpiresAt = Date.now() + (remainingSec * 1000);

    const tick = () => {
      const leftMs = minigameExpiresAt - Date.now();
      const leftSec = Math.max(0, Math.ceil(leftMs / 1000));
      if (mgTimerBadge) {
        mgTimerBadge.textContent = `⏱️ ${leftSec}s`;
        if (leftSec > 10) {
          mgTimerBadge.className = "badge badge-online";
        } else if (leftSec > 0) {
          mgTimerBadge.className = "badge badge-accent";
        } else {
          mgTimerBadge.textContent = "⏱️ Waktu Habis!";
          mgTimerBadge.className = "badge";
          clearInterval(minigameTimerTicker);
          minigameTimerTicker = null;
        }
      }
    };

    tick();
    minigameTimerTicker = setInterval(tick, 1000);
  }

  function updateMinigameUi(data) {
    if (!data) return;
    const session = data.session || {};
    const gameType = session.game_type || selectedMiniGameMode || "trivia";
    selectedMiniGameMode = gameType;

    // 1. Status Badge
    if (mgStatusBadge) {
      const st = (session.status || "idle").toUpperCase();
      if (st === "ACTIVE") {
        mgStatusBadge.textContent = "Status: ACTIVE 🟢";
        mgStatusBadge.className = "badge badge-online";
      } else if (st === "ROUND_END") {
        mgStatusBadge.textContent = "Status: RONDE SELESAI ⏳";
        mgStatusBadge.className = "badge badge-accent";
      } else if (st === "GAME_OVER") {
        mgStatusBadge.textContent = "Status: GAME OVER 🏁";
        mgStatusBadge.className = "badge";
      } else {
        mgStatusBadge.textContent = "Status: IDLE 💤";
        mgStatusBadge.className = "badge";
      }
    }

    // 2. Mode Badge
    if (mgModeBadge) {
      const modeLabels = {
        "trivia": "TRIVIA QUIZ",
        "guess_number": "GUESS THE NUMBER",
        "would_you_rather": "WOULD YOU RATHER",
        "riddle": "TEKA-TEKI (RIDDLE)",
        "word_association": "SAMBUNG KATA",
        "guess_song": "TEBAK LAGU"
      };
      mgModeBadge.textContent = `Mode: ${modeLabels[gameType] || gameType.toUpperCase()}`;
    }

    // 3. Round Badge
    if (mgRoundBadge) {
      const rNum = session.round_number || 1;
      const rTot = session.total_rounds || 3;
      mgRoundBadge.textContent = `Round: ${rNum}/${rTot}`;
    }

    // 4. Scoreboard Badge
    if (mgScoreBadge) {
      const ai = session.ai_score !== undefined ? session.ai_score : (data.ai_score || 0);
      const chat = session.chat_score !== undefined ? session.chat_score : (data.chat_score || 0);
      mgScoreBadge.textContent = `Eve: ${ai} | Chat: ${chat}`;
    }

    // 5. Host Commentary Speech
    if (mgHostSpeech) {
      mgHostSpeech.textContent = session.last_host_commentary || "Ayo tebak atau kirim jawaban di chat!";
    }

    // 6. Action Control Buttons
    const isActive = session.status === "active";
    const isRoundEnd = session.status === "round_end";
    const isGameOver = session.status === "game_over" || session.status === "idle";

    if (btnMgStart) btnMgStart.disabled = isActive;
    if (btnMgNextRound) btnMgNextRound.disabled = !isRoundEnd;
    if (btnMgHint) {
      const canHint = isActive && (gameType === "riddle" || gameType === "guess_song");
      btnMgHint.disabled = !canHint;
    }
    if (btnMgStop) btnMgStop.disabled = isGameOver;

    // 7. Timer Handling
    if (isActive) {
      let rem = 35;
      if (session.start_time && session.time_limit_sec) {
        const elapsed = Math.floor((Date.now() / 1000) - session.start_time);
        rem = Math.max(0, session.time_limit_sec - elapsed);
      }
      startMiniGameLocalTimer(rem);
    } else {
      if (minigameTimerTicker) {
        clearInterval(minigameTimerTicker);
        minigameTimerTicker = null;
      }
      if (mgTimerBadge) {
        if (session.status === "round_end") {
          mgTimerBadge.textContent = "⏱️ Ronde Selesai";
          mgTimerBadge.className = "badge badge-accent";
        } else if (session.status === "game_over") {
          mgTimerBadge.textContent = "⏱️ Selesai";
          mgTimerBadge.className = "badge";
        } else {
          mgTimerBadge.textContent = "⏱️ Standby";
          mgTimerBadge.className = "badge";
        }
      }
    }

    // 8. Active Challenge Arena
    switchMiniGameView(gameType);
    const c = session.current_challenge || {};

    if (gameType === "trivia") {
      if (mgTriviaCategory) mgTriviaCategory.textContent = c.category || "General";
      if (mgTriviaQuestion) mgTriviaQuestion.textContent = c.question || "Menunggu soal trivia...";
      if (mgTriviaOptions && c.options) {
        mgTriviaOptions.innerHTML = "";
        Object.entries(c.options).forEach(([optKey, optText]) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "btn-trivia-opt";
          btn.dataset.opt = optKey;

          if (isRoundEnd || session.status === "game_over") {
            if (optKey.toUpperCase() === (c.answer || "").toUpperCase()) {
              btn.classList.add("correct");
            }
          }

          btn.innerHTML = `<span class="opt-key">${optKey}</span> <span class="opt-txt">${optText}</span>`;
          btn.addEventListener("click", () => {
            const user = mgChatUser ? (mgChatUser.value.trim() || "ChatterPro") : "ChatterPro";
            sendMinigameAction({
              action: "chat_input",
              user: user,
              message: optKey
            });
          });
          mgTriviaOptions.appendChild(btn);
        });
      }
    } else if (gameType === "guess_number") {
      const bounds = session.number_bounds || [1, 100];
      if (mgNumRangeText) mgNumRangeText.textContent = `[${bounds[0]} ... ${bounds[1]}]`;
      if (mgNumBarFill) {
        const span = Math.max(1, bounds[1] - bounds[0]);
        const pct = Math.min(100, Math.max(5, Math.round((span / 100) * 100)));
        mgNumBarFill.style.width = `${pct}%`;
      }
      if (mgLastGuessFeedback) {
        if (session.round_guesses && session.round_guesses.length > 0) {
          const lastG = session.round_guesses[session.round_guesses.length - 1];
          mgLastGuessFeedback.textContent = `Tebakan terakhir: ${lastG.user} menebak ${lastG.guess} -> ${lastG.feedback}`;
        } else {
          mgLastGuessFeedback.textContent = "Tebak angka antara 1 sampai 100 di chat!";
        }
      }
    } else if (gameType === "would_you_rather") {
      if (mgWyrTopic) mgWyrTopic.textContent = c.topic || "Dilema Kehidupan";
      if (wyrTextA) wyrTextA.textContent = c.option_a || "Pilihan A";
      if (wyrTextB) wyrTextB.textContent = c.option_b || "Pilihan B";

      const pcts = session.vote_percentages || { "A": 50, "B": 50 };
      const votes = session.votes || { "A": [], "B": [] };
      const pctA = Math.round(pcts.A || 50);
      const pctB = Math.round(pcts.B || 50);

      if (wyrPctA) wyrPctA.textContent = `${pctA}% (${(votes.A || []).length} vote)`;
      if (wyrPctB) wyrPctB.textContent = `${pctB}% (${(votes.B || []).length} vote)`;
    } else if (gameType === "riddle") {
      if (mgRiddleText) mgRiddleText.textContent = c.riddle || "Menunggu teka-teki dari Eve...";
      if (mgHintsList) {
        mgHintsList.innerHTML = "";
        const hints = session.revealed_hints || [];
        if (hints.length === 0) {
          mgHintsList.innerHTML = `<span class="hint-pill">Belum ada hint dibuka. Tekan 'Minta Hint'!</span>`;
        } else {
          hints.forEach(h => {
            const sp = document.createElement("span");
            sp.className = "hint-pill";
            sp.textContent = `💡 ${h}`;
            mgHintsList.appendChild(sp);
          });
        }
      }
    } else if (gameType === "word_association") {
      if (mgThemeText) mgThemeText.textContent = c.theme || "Gaming";
      if (mgWordChainList) {
        mgWordChainList.innerHTML = "";
        const chain = session.word_chain || ["Mulai"];
        chain.forEach((w, idx) => {
          const sp = document.createElement("span");
          sp.className = `chain-pill ${idx === 0 ? 'initial' : ''}`;
          sp.textContent = `${idx + 1}. ${w}`;
          mgWordChainList.appendChild(sp);
        });
      }
    } else if (gameType === "guess_song") {
      if (mgSongGenre) mgSongGenre.textContent = c.genre || "Anime Opening";
      if (mgSongClue) mgSongClue.textContent = `"${c.clue_lyrics || 'Lirik lagu rahasia...'}"`;
      if (mgSongHintsList) {
        mgSongHintsList.innerHTML = "";
        const hints = session.revealed_hints || [];
        if (hints.length === 0) {
          mgSongHintsList.innerHTML = `<span class="hint-pill">Belum ada hint. Minta hint jika kesulitan!</span>`;
        } else {
          hints.forEach(h => {
            const sp = document.createElement("span");
            sp.className = "hint-pill";
            sp.textContent = `🎵 ${h}`;
            mgSongHintsList.appendChild(sp);
          });
        }
      }
    }

    // 9. Audience Leaderboard (Hall of Fame)
    if (mgLeaderboardList && data.leaderboard) {
      mgLeaderboardList.innerHTML = "";
      const medals = ["🥇", "🥈", "🥉"];
      data.leaderboard.forEach((p, idx) => {
        const item = document.createElement("div");
        item.className = "mg-leaderboard-item";
        const medal = idx < 3 ? medals[idx] : `#${idx + 1}`;
        item.innerHTML = `
          <div class="mg-leader-rank">${medal}</div>
          <div class="mg-leader-info">
            <span class="mg-leader-name">${p.username}</span>
            <small class="mg-leader-sub">Benar: ${p.correct_answers || 0} • Menang: ${p.games_won || 0} • Streak: 🔥${p.streak || 0}</small>
          </div>
          <div class="mg-leader-pts"><strong>${p.score || 0}</strong> <small>pts</small></div>
        `;
        mgLeaderboardList.appendChild(item);
      });
    }

    // 10. Live Event History Ticker
    if (mgEventHistoryList && data.event_log) {
      mgEventHistoryList.innerHTML = "";
      data.event_log.forEach(ev => {
        const div = document.createElement("div");
        div.className = "mg-event-row";
        div.textContent = ev;
        mgEventHistoryList.appendChild(div);
      });
    }
  }

  // Event Listeners for Mini-Game Controls
  document.querySelectorAll(".btn-mg-mode").forEach(btn => {
    btn.addEventListener("click", () => {
      const mode = btn.dataset.game;
      if (mode) {
        selectedMiniGameMode = mode;
        switchMiniGameView(mode);
      }
    });
  });

  if (btnMgStart) {
    btnMgStart.addEventListener("click", () => {
      const rounds = selectMgRounds ? parseInt(selectMgRounds.value, 10) : 3;
      sendMinigameAction({
        action: "start",
        game_type: selectedMiniGameMode,
        total_rounds: rounds
      });
    });
  }

  if (btnMgNextRound) {
    btnMgNextRound.addEventListener("click", () => {
      sendMinigameAction({ action: "next_round" });
    });
  }

  if (btnMgHint) {
    btnMgHint.addEventListener("click", () => {
      sendMinigameAction({ action: "hint" });
    });
  }

  if (btnMgStop) {
    btnMgStop.addEventListener("click", () => {
      sendMinigameAction({ action: "stop" });
    });
  }

  // Would You Rather Vote Buttons
  document.querySelectorAll(".btn-wyr-vote").forEach(btn => {
    btn.addEventListener("click", () => {
      const voteChoice = btn.dataset.vote; // "A" or "B"
      const user = mgChatUser ? (mgChatUser.value.trim() || "Viewer") : "Viewer";
      sendMinigameAction({
        action: "chat_input",
        user: user,
        message: `!${voteChoice}`
      });
    });
  });

  // Chat Submission Form
  if (mgChatSubmitForm && mgChatMessage) {
    mgChatSubmitForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const user = mgChatUser ? (mgChatUser.value.trim() || "Chatter") : "Chatter";
      const msg = mgChatMessage.value.trim();
      if (msg) {
        sendMinigameAction({
          action: "chat_input",
          user: user,
          message: msg
        });
        mgChatMessage.value = "";
      }
    });
  }

  // Quick Simulation Buttons
  document.querySelectorAll(".btn-mg-quick").forEach(btn => {
    btn.addEventListener("click", () => {
      const user = btn.dataset.user || "Chatter";
      const msg = btn.dataset.msg || "";
      if (msg) {
        sendMinigameAction({
          action: "chat_input",
          user: user,
          message: msg
        });
      }
    });
  });

  // --- Dynamic Storytelling & Community Roleplay RPG ---
  const storyStatusBadge = document.getElementById("story-status-badge");
  const storyGenreBadge = document.getElementById("story-genre-badge");
  const storyRoleBadge = document.getElementById("story-role-badge");
  const storyHpBadge = document.getElementById("story-hp-badge");
  const storyGoldBadge = document.getElementById("story-gold-badge");

  const selectStoryPreset = document.getElementById("selectStoryPreset");
  const selectStoryRole = document.getElementById("selectStoryRole");
  const btnStoryStart = document.getElementById("btnStoryStart");
  const btnStoryAdvance = document.getElementById("btnStoryAdvance");
  const btnStoryRoll = document.getElementById("btnStoryRoll");
  const btnStoryEnd = document.getElementById("btnStoryEnd");

  const storySceneTitle = document.getElementById("storySceneTitle");
  const storyLocationBadge = document.getElementById("storyLocationBadge");
  const storySpeakerName = document.getElementById("storySpeakerName");
  const storyNarrativeText = document.getElementById("storyNarrativeText");
  const storyChoicesContainer = document.getElementById("storyChoicesContainer");

  const storyD20Target = document.getElementById("storyD20Target");
  const storyD20Dice = document.getElementById("storyD20Dice");
  const storyD20Outcome = document.getElementById("storyD20Outcome");

  const storyPartyName = document.getElementById("storyPartyName");
  const storyHpText = document.getElementById("storyHpText");
  const storyHpBar = document.getElementById("storyHpBar");
  const storyMoraleText = document.getElementById("storyMoraleText");
  const storyMoraleBar = document.getElementById("storyMoraleBar");
  const storyInventoryList = document.getElementById("storyInventoryList");

  const storyActionForm = document.getElementById("storyActionForm");
  const storyActionUser = document.getElementById("storyActionUser");
  const storyActionText = document.getElementById("storyActionText");
  const storySuggestionsList = document.getElementById("storySuggestionsList");
  const storyMemoriesList = document.getElementById("storyMemoriesList");
  const storyHistoryTable = document.getElementById("storyHistoryTable");

  function sendStoryAction(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "story_action",
        ...payload
      }));
    }
  }

  function animateD20Roll(finalVal, isSuccess, isCritSuccess, isCritFail) {
    if (!storyD20Dice) return;
    storyD20Dice.className = "d20-dice-die rolling";

    let rollTicks = 0;
    const interval = setInterval(() => {
      storyD20Dice.textContent = Math.floor(Math.random() * 20) + 1;
      rollTicks++;
      if (rollTicks > 8) {
        clearInterval(interval);
        storyD20Dice.textContent = finalVal;
        storyD20Dice.className = "d20-dice-die";
        if (isCritSuccess) {
          storyD20Dice.classList.add("nat20");
        } else if (isCritFail) {
          storyD20Dice.classList.add("nat1");
        }
      }
    }, 60);
  }

  function updateStoryUi(data) {
    if (!data) return;
    const session = data.session || {};
    const party = session.party || {};
    const curScene = session.current_scene || {};

    // 1. Status Badges
    if (storyStatusBadge) {
      const st = (session.status || "idle").toUpperCase();
      if (st === "VOTING" || st === "ACTIVE") {
        storyStatusBadge.textContent = "Status: ACTIVE (VOTING) 🟢";
        storyStatusBadge.className = "badge badge-online";
      } else if (st === "DICE_ROLL") {
        storyStatusBadge.textContent = "Status: DICE ROLL 🎲";
        storyStatusBadge.className = "badge badge-accent";
      } else if (st === "COMPLETED") {
        storyStatusBadge.textContent = "Status: COMPLETED 🏁";
        storyStatusBadge.className = "badge";
      } else {
        storyStatusBadge.textContent = "Status: IDLE 💤";
        storyStatusBadge.className = "badge";
      }
    }

    if (storyGenreBadge) {
      const g = (session.genre || "fantasy_rpg").replace('_', ' ').toUpperCase();
      storyGenreBadge.textContent = `Genre: ${g}`;
    }

    if (storyRoleBadge) {
      const r = (session.eve_role || "party_mage").replace('_', ' ').toUpperCase();
      storyRoleBadge.textContent = `Role: ${r}`;
    }

    if (storyHpBadge) {
      const hp = party.hp !== undefined ? party.hp : 100;
      const maxHp = party.max_hp || 100;
      storyHpBadge.textContent = `HP: ${hp}/${maxHp}`;
      if (hp > 50) {
        storyHpBadge.className = "badge badge-online";
      } else if (hp > 20) {
        storyHpBadge.className = "badge badge-accent";
      } else {
        storyHpBadge.className = "badge";
      }
    }

    if (storyGoldBadge) {
      storyGoldBadge.textContent = `💰 ${party.gold || 0}G`;
    }

    // 2. Control Buttons State
    const isActive = session.status === "active" || session.status === "voting" || session.status === "dice_roll";
    if (btnStoryStart) btnStoryStart.disabled = isActive;
    if (btnStoryAdvance) btnStoryAdvance.disabled = !isActive;
    if (btnStoryRoll) btnStoryRoll.disabled = !isActive;
    if (btnStoryEnd) btnStoryEnd.disabled = !isActive;

    // 3. Scene Theater
    if (storySceneTitle) {
      storySceneTitle.textContent = curScene.title || session.title || "Babak 1: Reruntuhan Kuno";
    }

    if (storyLocationBadge) {
      storyLocationBadge.textContent = `📍 ${party.current_location || "Ancient Ruins"}`;
    }

    if (storySpeakerName) {
      storySpeakerName.textContent = curScene.speaker_name || `Eve Maybe (${(session.eve_role || 'Party Host').replace('_', ' ').toUpperCase()}):`;
    }

    if (storyNarrativeText) {
      storyNarrativeText.textContent = curScene.narrative || "Pilih skenario petualangan dan mulai campaign untuk berpetualang bareng Guild Chat!";
    }

    // 4. Choices Cards
    if (storyChoicesContainer) {
      storyChoicesContainer.innerHTML = "";
      const choices = curScene.choices || [];
      const totalVotes = choices.reduce((acc, c) => acc + (c.votes ? c.votes.length : 0), 0);

      if (choices.length === 0) {
        storyChoicesContainer.innerHTML = `<div class="story-choice-card"><p class="choice-desc">Belum ada pilihan keputusan pada adegan ini.</p></div>`;
      } else {
        choices.forEach((c, idx) => {
          const card = document.createElement("div");
          card.className = "story-choice-card";
          const voteCount = c.votes ? c.votes.length : 0;
          const votePct = totalVotes > 0 ? Math.round((voteCount / totalVotes) * 100) : 0;
          const optKey = `!${idx + 1}`;

          card.innerHTML = `
            <div class="choice-header">
              <span class="choice-key-tag">${optKey}</span>
              <span class="choice-label">${c.label}</span>
              <span class="choice-dc-badge">DC ${c.dc_check || 10} (${c.stat_affinity || 'Luck'})</span>
            </div>
            <p class="choice-desc">${c.description}</p>
            <div class="choice-vote-row">
              <span>Votes: <strong>${voteCount}</strong> (${votePct}%)</span>
              <div class="choice-vote-bar">
                <div class="choice-vote-fill" style="width: ${votePct}%;"></div>
              </div>
              <button type="button" class="btn btn-secondary btn-sm btn-vote-choice" style="font-size: 10px; padding: 2px 8px;">Vote ${optKey}</button>
            </div>
          `;

          const voteBtn = card.querySelector(".btn-vote-choice");
          if (voteBtn) {
            voteBtn.addEventListener("click", (e) => {
              e.stopPropagation();
              const u = storyActionUser ? (storyActionUser.value.trim() || "Chatter") : "Chatter";
              sendStoryAction({
                action: "vote",
                user: u,
                choice_id: c.id
              });
            });
          }

          card.addEventListener("click", () => {
            const u = storyActionUser ? (storyActionUser.value.trim() || "Chatter") : "Chatter";
            sendStoryAction({
              action: "vote",
              user: u,
              choice_id: c.id
            });
          });

          storyChoicesContainer.appendChild(card);
        });
      }
    }

    // 5. D20 Dice Target & Last Roll
    if (storyD20Target) {
      const dc = curScene.dc_check || 12;
      const stat = curScene.stat_affinity || "Agility";
      storyD20Target.textContent = `Target: DC ${dc} (${stat})`;
    }

    if (session.last_dice_roll) {
      const r = session.last_dice_roll;
      if (storyD20Dice) {
        storyD20Dice.textContent = r.d20_value;
        storyD20Dice.className = "d20-dice-die";
        if (r.is_critical_success) storyD20Dice.classList.add("nat20");
        else if (r.is_critical_fail) storyD20Dice.classList.add("nat1");
      }
      if (storyD20Outcome) {
        storyD20Outcome.innerHTML = `
          <strong>${r.roller} melempar D20:</strong> [Dadu ${r.d20_value} + ${r.modifier} Bonus = <strong>${r.total}</strong> vs DC ${r.dc_target}]<br>
          <span style="color: ${r.is_success ? '#4ade80' : '#f87171'}; font-weight: 600;">${r.outcome_text}</span>
        `;
      }
    }

    // 6. Party Vitals
    if (storyPartyName) {
      storyPartyName.textContent = party.name || "Guild Chat & Eve";
    }

    if (storyHpText && storyHpBar) {
      const hp = party.hp !== undefined ? party.hp : 100;
      const maxHp = party.max_hp || 100;
      storyHpText.textContent = `${hp}/${maxHp}`;
      const hpPct = Math.min(100, Math.max(0, Math.round((hp / maxHp) * 100)));
      storyHpBar.style.width = `${hpPct}%`;
      if (hpPct <= 25) {
        storyHpBar.className = "gauge-bar-fill gauge-fill-annoy";
      } else {
        storyHpBar.className = "gauge-bar-fill gauge-fill-happy";
      }
    }

    if (storyMoraleText && storyMoraleBar) {
      const morale = party.morale !== undefined ? party.morale : 100;
      storyMoraleText.textContent = `${morale}%`;
      storyMoraleBar.style.width = `${Math.min(100, Math.max(0, morale))}%`;
    }

    if (storyInventoryList) {
      storyInventoryList.innerHTML = "";
      const inv = party.inventory || [];
      if (inv.length === 0) {
        storyInventoryList.innerHTML = `<span class="inv-pill">Tas Kosong</span>`;
      } else {
        inv.forEach(item => {
          const sp = document.createElement("span");
          sp.className = "inv-pill";
          sp.textContent = item;
          storyInventoryList.appendChild(sp);
        });
      }
    }

    // 7. Freeform Community Suggestions
    if (storySuggestionsList) {
      storySuggestionsList.innerHTML = "";
      const suggs = session.freeform_suggestions || [];
      if (suggs.length === 0) {
        storySuggestionsList.innerHTML = `<div class="suggestion-item">Belum ada usulan taktik bebas diajukan. Ketik !action di chat!</div>`;
      } else {
        suggs.forEach(s => {
          const div = document.createElement("div");
          div.className = "suggestion-item";
          div.innerHTML = `<strong>${s.user}</strong>: "${s.action}" <small style="color: #64748b;">(${s.time})</small>`;
          storySuggestionsList.appendChild(div);
        });
      }
    }

    // 8. Episodic Lore & Memories
    if (storyMemoriesList) {
      storyMemoriesList.innerHTML = "";
      const mems = session.key_memories || [];
      mems.forEach(m => {
        const li = document.createElement("li");
        li.textContent = m;
        storyMemoriesList.appendChild(li);
      });
    }

    // 9. Campaign History Table
    if (storyHistoryTable && data.campaigns_history) {
      storyHistoryTable.innerHTML = "";
      data.campaigns_history.forEach(h => {
        const row = document.createElement("div");
        row.className = "history-item-row";
        row.innerHTML = `
          <div class="history-meta">
            <span class="history-title">${h.title}</span>
            <small class="history-sub">${h.summary || ''}</small>
          </div>
          <div class="history-stats">${h.final_hp || '-'}HP | ${h.final_gold || '-'}G</div>
        `;
        storyHistoryTable.appendChild(row);
      });
    }
  }

  // Event Listeners for Story Controls
  if (btnStoryStart) {
    btnStoryStart.addEventListener("click", () => {
      const preset = selectStoryPreset ? selectStoryPreset.value : "petualangan_netherite";
      const role = selectStoryRole ? selectStoryRole.value : "party_mage";
      sendStoryAction({
        action: "start",
        preset: preset,
        eve_role: role
      });
    });
  }

  if (btnStoryAdvance) {
    btnStoryAdvance.addEventListener("click", () => {
      sendStoryAction({ action: "advance" });
    });
  }

  if (btnStoryRoll) {
    btnStoryRoll.addEventListener("click", () => {
      const u = storyActionUser ? (storyActionUser.value.trim() || "Chat") : "Chat";
      sendStoryAction({ action: "roll", roller: u });
    });
  }

  if (btnStoryEnd) {
    btnStoryEnd.addEventListener("click", () => {
      sendStoryAction({ action: "end" });
    });
  }

  // Freeform Action Proposal Form
  if (storyActionForm && storyActionText) {
    storyActionForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const u = storyActionUser ? (storyActionUser.value.trim() || "HeroChatter") : "HeroChatter";
      const txt = storyActionText.value.trim();
      if (txt) {
        sendStoryAction({
          action: "action",
          user: u,
          action_text: txt
        });
        storyActionText.value = "";
      }
    });
  }

  // Quick Action Simulation Buttons
  document.querySelectorAll(".btn-story-quick").forEach(btn => {
    btn.addEventListener("click", () => {
      const user = btn.dataset.user || "Chatter";
      const msg = btn.dataset.msg || "";
      if (msg.startsWith("!action ")) {
        const actTxt = msg.replace("!action ", "");
        sendStoryAction({
          action: "action",
          user: user,
          action_text: actTxt
        });
      } else if (msg === "!roll") {
        sendStoryAction({
          action: "roll",
          roller: user
        });
      } else {
        // Vote !1 or !2
        const choiceId = msg === "!1" ? "opt_1" : (msg === "!2" ? "opt_2" : "opt_3");
        sendStoryAction({
          action: "vote",
          user: user,
          choice_id: choiceId
        });
      }
    });
  });

  // --- Dynamic Performance Director & AI Idol Stage ---
  const perfStatusBadge = document.getElementById("perf-status-badge");
  const perfMoodBadge = document.getElementById("perf-mood-badge");
  const perfSongBadge = document.getElementById("perf-song-badge");
  const perfGlowsticksBadge = document.getElementById("perf-glowsticks-badge");
  const perfScoreBadge = document.getElementById("perf-score-badge");

  const selectPerfSong = document.getElementById("selectPerfSong");
  const perfDedicationInput = document.getElementById("perfDedicationInput");
  const btnPerfAutoPick = document.getElementById("btnPerfAutoPick");
  const btnPerfPlanSetlist = document.getElementById("btnPerfPlanSetlist");
  const btnPerfStart = document.getElementById("btnPerfStart");
  const btnPerfStop = document.getElementById("btnPerfStop");

  const perfCurrentTitle = document.getElementById("perfCurrentTitle");
  const perfMoodReason = document.getElementById("perfMoodReason");
  const perfSectionBadge = document.getElementById("perfSectionBadge");
  const perfLightingBadge = document.getElementById("perfLightingBadge");
  const perfMovementBadge = document.getElementById("perfMovementBadge");
  const perfEmotionBadge = document.getElementById("perfEmotionBadge");
  const perfActionBadge = document.getElementById("perfActionBadge");

  const perfStageMonitor = document.getElementById("perfStageMonitor");
  const perfLiveLyrics = document.getElementById("perfLiveLyrics");
  const perfCrowdCallout = document.getElementById("perfCrowdCallout");
  const perfMcBubble = document.getElementById("perfMcBubble");
  const perfMcText = document.getElementById("perfMcText");

  const perfSetlistContainer = document.getElementById("perfSetlistContainer");
  const btnPerfGlowstick = document.getElementById("btnPerfGlowstick");
  const btnPerfEncore = document.getElementById("btnPerfEncore");
  const perfHypeVal = document.getElementById("perfHypeVal");
  const perfGlowstickMeter = document.getElementById("perfGlowstickMeter");
  const perfCheersList = document.getElementById("perfCheersList");
  const perfHistoryTable = document.getElementById("perfHistoryTable");

  function sendPerformanceAction(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "performance_action",
        ...payload
      }));
    }
  }

  function triggerAvatarChoreography(data) {
    if (!data) return;
    const movement = data.movement || "sway_left";
    const lighting = data.lighting || "neon_cyan";

    // Update 2D canvas avatar motion
    if (movement === "sway_left") {
      headTilt = -0.06;
    } else if (movement === "sway_right") {
      headTilt = 0.06;
    } else if (movement === "bounce") {
      headTilt = 0.0;
    } else if (movement === "head_tilt") {
      headTilt = 0.1;
    } else if (movement === "sparkle_pose") {
      headTilt = -0.04;
    }

    // Apply stage monitor lighting class
    if (perfStageMonitor) {
      perfStageMonitor.className = `perf-screen-monitor lighting-${lighting}`;
    }
  }

  function triggerCheerEffect(data) {
    if (!perfStageMonitor) return;
    const isEncore = data.type === "encore";
    const icon = isEncore ? "💖 ENCORE!" : "🪄 ✨";

    const floater = document.createElement("div");
    floater.textContent = `${data.user}: ${icon}`;
    floater.style.position = "absolute";
    floater.style.left = `${Math.random() * 70 + 15}%`;
    floater.style.bottom = "10px";
    floater.style.fontSize = "13px";
    floater.style.fontWeight = "bold";
    floater.style.color = isEncore ? "#ec4899" : "#38bdf8";
    floater.style.textShadow = "0 0 8px rgba(0,0,0,0.8)";
    floater.style.pointerEvents = "none";
    floater.style.transition = "all 1.5s ease-out";
    floater.style.zIndex = "10";

    perfStageMonitor.appendChild(floater);

    requestAnimationFrame(() => {
      floater.style.transform = `translateY(-${Math.random() * 60 + 60}px) scale(1.2)`;
      floater.style.opacity = "0";
    });

    setTimeout(() => {
      floater.remove();
    }, 1600);
  }

  function updatePerformanceUi(data) {
    if (!data) return;
    const session = data.session || {};
    const step = session.current_step || {};

    // 1. Status Badges
    const isPerforming = session.status === "performing" || session.status === "mc_intro";
    if (perfStatusBadge) {
      const st = (session.status || "idle").toUpperCase();
      if (st === "PERFORMING") {
        perfStatusBadge.textContent = "Status: LIVE ON STAGE 🔴";
        perfStatusBadge.className = "badge badge-online";
      } else if (st === "MC_INTRO") {
        perfStatusBadge.textContent = "Status: MC INTRO 🎤";
        perfStatusBadge.className = "badge badge-accent";
      } else if (st === "MC_OUTRO") {
        perfStatusBadge.textContent = "Status: MC OUTRO 🏁";
        perfStatusBadge.className = "badge";
      } else {
        perfStatusBadge.textContent = "Status: STANDBY 💤";
        perfStatusBadge.className = "badge";
      }
    }

    if (perfMoodBadge) {
      perfMoodBadge.textContent = `Mood: ${(session.dominant_mood || 'HYPE_EXCITED').replace('_', ' ')}`;
    }

    if (perfSongBadge) {
      perfSongBadge.textContent = `Song: ${session.current_title || 'Digital World'}`;
    }

    if (perfGlowsticksBadge) {
      perfGlowsticksBadge.textContent = `✨ ${session.audience_glowsticks || 0} Glowsticks`;
    }

    if (perfScoreBadge) {
      perfScoreBadge.textContent = `Score: ${session.performance_score || 95}/100 🏆`;
    }

    // 2. Control Buttons State
    if (btnPerfStart) btnPerfStart.disabled = isPerforming;
    if (btnPerfStop) btnPerfStop.disabled = !isPerforming;

    // 3. Stage Header & Choreography Indicators
    if (perfCurrentTitle) {
      perfCurrentTitle.textContent = session.current_title || "Digital World";
    }

    if (perfMoodReason) {
      perfMoodReason.textContent = `"${session.mood_reason || 'Eve bersemangat menyapa para penonton!'}"`;
    }

    if (perfSectionBadge) {
      const sec = (session.current_section || step.section || "intro").toUpperCase();
      perfSectionBadge.textContent = `BAGIAN: ${sec}`;
    }

    if (perfLightingBadge) {
      const light = (step.stage_lighting || "neon_cyan").replace('_', ' ').toUpperCase();
      perfLightingBadge.textContent = `💡 ${light}`;
    }

    if (perfMovementBadge) {
      const move = (step.movement || "sway_left").replace('_', ' ').toUpperCase();
      perfMovementBadge.textContent = `💃 ${move}`;
    }

    if (perfEmotionBadge) {
      const emo = (step.emotion || "happy").toUpperCase();
      perfEmotionBadge.textContent = `😊 ${emo}`;
    }

    if (perfActionBadge) {
      const act = (step.action || "wink").toUpperCase();
      perfActionBadge.textContent = `✨ ${act}`;
    }

    // 4. MC Speech Bubble
    if (perfMcText) {
      if (session.status === "mc_intro" && session.last_mc_intro) {
        perfMcText.textContent = session.last_mc_intro;
      } else if (session.status === "mc_outro" && session.last_mc_outro) {
        perfMcText.textContent = session.last_mc_outro;
      }
    }

    // 5. Crowd Callout Banner
    if (perfCrowdCallout) {
      if (step.crowd_callout) {
        perfCrowdCallout.textContent = `🎤 Eve: "${step.crowd_callout}"`;
        perfCrowdCallout.style.display = "inline-block";
      } else {
        perfCrowdCallout.style.display = "none";
      }
    }

    // 6. Setlist Manager
    if (perfSetlistContainer && session.setlist) {
      perfSetlistContainer.innerHTML = "";
      session.setlist.forEach(item => {
        const row = document.createElement("div");
        row.className = `setlist-card-item ${item.status}`;
        let statusBadge = "⏳ Queued";
        if (item.status === "current") statusBadge = "🟢 Now Playing";
        else if (item.status === "completed") statusBadge = "✅ Completed";

        row.innerHTML = `
          <div class="setlist-meta">
            <span class="setlist-song-name">#${item.order} ${item.title}</span>
            <small class="setlist-desc">${item.reason}</small>
          </div>
          <span class="badge" style="font-size: 10px;">${statusBadge}</span>
        `;
        perfSetlistContainer.appendChild(row);
      });
    }

    // 7. Glowstick Hype Meter
    const cheers = session.audience_glowsticks || 0;
    if (perfHypeVal) {
      perfHypeVal.textContent = `${cheers} Glowsticks`;
    }
    if (perfGlowstickMeter) {
      const pct = Math.min(100, Math.max(10, Math.round((cheers / 100) * 100)));
      perfGlowstickMeter.style.width = `${pct}%`;
    }

    // 8. Cheers List
    if (perfCheersList && session.cheers_history) {
      perfCheersList.innerHTML = "";
      const history = session.cheers_history || [];
      if (history.length === 0) {
        perfCheersList.innerHTML = `<div class="suggestion-item">Belum ada sorakan glowstick penonton.</div>`;
      } else {
        history.slice(-4).forEach(c => {
          const div = document.createElement("div");
          div.className = "suggestion-item";
          const icon = c.type === "encore" ? "💖" : "✨";
          div.innerHTML = `<strong>${c.user}</strong>: ${icon} bersorak di panggung! <small style="color: #64748b;">(${c.time})</small>`;
          perfCheersList.appendChild(div);
        });
      }
    }

    // 9. Showcase History Table
    if (perfHistoryTable && data.concert_history) {
      perfHistoryTable.innerHTML = "";
      data.concert_history.forEach(h => {
        const div = document.createElement("div");
        div.className = "history-item-row";
        div.innerHTML = `
          <div class="history-meta">
            <span class="history-title">${h.concert_title || h.title}</span>
            <small class="history-sub">${h.completed_at || ''}</small>
          </div>
          <div class="history-stats">Score: ${h.score || 95}/100 • ✨ ${h.glowsticks || 0}</div>
        `;
        perfHistoryTable.appendChild(div);
      });
    }
  }

  // Event Listeners for Performance Controls
  if (btnPerfAutoPick) {
    btnPerfAutoPick.addEventListener("click", () => {
      if (selectPerfSong) selectPerfSong.value = "auto";
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: "user_message",
          user: "Creator",
          text: "Eve, mood kamu lagi gimana dan rekomendasi lagu apa buat konser sekarang?",
          source: "web"
        }));
      }
    });
  }

  if (btnPerfPlanSetlist) {
    btnPerfPlanSetlist.addEventListener("click", () => {
      sendPerformanceAction({ action: "plan" });
    });
  }

  if (btnPerfStart) {
    btnPerfStart.addEventListener("click", () => {
      const selectedSong = selectPerfSong ? selectPerfSong.value : "auto";
      const songId = selectedSong === "auto" ? null : selectedSong;
      const dedication = perfDedicationInput ? perfDedicationInput.value.trim() : null;
      sendPerformanceAction({
        action: "start",
        song_id: songId,
        dedication_user: dedication
      });
    });
  }

  if (btnPerfStop) {
    btnPerfStop.addEventListener("click", () => {
      sendPerformanceAction({ action: "stop" });
    });
  }

  if (btnPerfGlowstick) {
    btnPerfGlowstick.addEventListener("click", () => {
      const u = perfDedicationInput ? (perfDedicationInput.value.trim() || "ViewerPro") : "ViewerPro";
      sendPerformanceAction({
        action: "cheer",
        cheer_type: "glowstick",
        user: u
      });
    });
  }

  if (btnPerfEncore) {
    btnPerfEncore.addEventListener("click", () => {
      const u = perfDedicationInput ? (perfDedicationInput.value.trim() || "ViewerPro") : "ViewerPro";
      sendPerformanceAction({
        action: "cheer",
        cheer_type: "encore",
        user: u
      });
    });
  }

  // --- Experience-Based Personality Evolution Handlers ---
  const pLevelBadge = document.getElementById("p-level-badge");
  const pArchetypeBadge = document.getElementById("p-archetype-badge");
  const pExpBadge = document.getElementById("p-exp-badge");
  const pMilestonesCountBadge = document.getElementById("p-milestones-count-badge");

  const pHeroIcon = document.getElementById("pHeroIcon");
  const pArchetypeTitle = document.getElementById("pArchetypeTitle");
  const pLevelPill = document.getElementById("pLevelPill");
  const pArchetypeDesc = document.getElementById("pArchetypeDesc");
  const pExpText = document.getElementById("pExpText");
  const pExpBar = document.getElementById("pExpBar");

  const btnPExpDefeat = document.getElementById("btnPExpDefeat");
  const btnPExpVictory = document.getElementById("btnPExpVictory");
  const btnPExpChallenge = document.getElementById("btnPExpChallenge");
  const btnPExpCoop = document.getElementById("btnPExpCoop");
  const btnPExpTroll = document.getElementById("btnPExpTroll");
  const btnPExpPhilosophy = document.getElementById("btnPExpPhilosophy");
  const btnPReset = document.getElementById("btnPReset");

  const pTraitValComp = document.getElementById("pTraitValComp");
  const pTraitBarComp = document.getElementById("pTraitBarComp");
  const pTraitValConf = document.getElementById("pTraitValConf");
  const pTraitBarConf = document.getElementById("pTraitBarConf");
  const pTraitValWarm = document.getElementById("pTraitValWarm");
  const pTraitBarWarm = document.getElementById("pTraitBarWarm");
  const pTraitValSass = document.getElementById("pTraitValSass");
  const pTraitBarSass = document.getElementById("pTraitBarSass");
  const pTraitValIntl = document.getElementById("pTraitValIntl");
  const pTraitBarIntl = document.getElementById("pTraitBarIntl");

  const pMilestonesGrid = document.getElementById("pMilestonesGrid");
  const pHistoryTable = document.getElementById("pHistoryTable");

  function sendPersonalityAction(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "personality_action",
        ...payload
      }));
    }
  }

  function updatePersonalityUi(data) {
    if (!data) return;
    const lvl = data.level || 1;
    const exp = data.exp || 0;
    const expNext = data.exp_to_next_level || (lvl * 100);
    const archetype = data.archetype || "Rookie Streamer 🌸";
    const archetypeDesc = data.archetype_desc || "Idol streamer pemula yang ramah dan penuh potensi.";
    const traits = data.traits || {};
    const milestones = data.milestones || [];
    const history = data.history || [];

    // Header Badges
    if (pLevelBadge) pLevelBadge.textContent = `Level: Lv. ${lvl}`;
    if (pArchetypeBadge) pArchetypeBadge.textContent = `Archetype: ${archetype}`;
    if (pExpBadge) pExpBadge.textContent = `EXP: ${exp}/${expNext}`;
    if (pMilestonesCountBadge) pMilestonesCountBadge.textContent = `Milestones: ${milestones.length}/7 🏆`;

    // Hero Section
    if (pArchetypeTitle) pArchetypeTitle.textContent = archetype;
    if (pLevelPill) pLevelPill.textContent = `Lv. ${lvl}`;
    if (pArchetypeDesc) pArchetypeDesc.textContent = archetypeDesc;
    if (pExpText) {
      const remaining = Math.max(0, expNext - exp);
      pExpText.textContent = `${exp} / ${expNext} EXP (${remaining} to Lv.${lvl + 1})`;
    }
    if (pExpBar) {
      const pct = Math.min(100, Math.round((exp / expNext) * 100));
      pExpBar.style.width = `${pct}%`;
    }

    // Icon parsing from archetype
    if (pHeroIcon) {
      if (archetype.includes("😈")) pHeroIcon.textContent = "😈";
      else if (archetype.includes("⭐")) pHeroIcon.textContent = "⭐";
      else if (archetype.includes("⚡")) pHeroIcon.textContent = "⚡";
      else if (archetype.includes("🧐")) pHeroIcon.textContent = "🧐";
      else if (archetype.includes("💖")) pHeroIcon.textContent = "💖";
      else if (archetype.includes("🗡️")) pHeroIcon.textContent = "🗡️";
      else if (archetype.includes("🌌")) pHeroIcon.textContent = "🌌";
      else if (archetype.includes("✨")) pHeroIcon.textContent = "✨";
      else pHeroIcon.textContent = "🌸";
    }

    // Trait Gauges
    const compPct = Math.round((traits.competitiveness || 0.35) * 100);
    const confPct = Math.round((traits.confidence || 0.50) * 100);
    const warmPct = Math.round((traits.warmth || 0.60) * 100);
    const sassPct = Math.round((traits.sassiness || 0.40) * 100);
    const intlPct = Math.round((traits.intellect || 0.50) * 100);

    if (pTraitValComp) pTraitValComp.textContent = `${compPct}%`;
    if (pTraitBarComp) pTraitBarComp.style.width = `${compPct}%`;

    if (pTraitValConf) pTraitValConf.textContent = `${confPct}%`;
    if (pTraitBarConf) pTraitBarConf.style.width = `${confPct}%`;

    if (pTraitValWarm) pTraitValWarm.textContent = `${warmPct}%`;
    if (pTraitBarWarm) pTraitBarWarm.style.width = `${warmPct}%`;

    if (pTraitValSass) pTraitValSass.textContent = `${sassPct}%`;
    if (pTraitBarSass) pTraitBarSass.style.width = `${sassPct}%`;

    if (pTraitValIntl) pTraitValIntl.textContent = `${intlPct}%`;
    if (pTraitBarIntl) pTraitBarIntl.style.width = `${intlPct}%`;

    // Milestones Grid
    if (pMilestonesGrid) {
      const presetCatalog = [
        { id: "salty_tryhard", title: "Salty Tryhard ⚡", desc: "Benci kekalahan dalam game! Sering menuntut rematch.", icon: "⚡" },
        { id: "iron_will_achiever", title: "Iron Will Achiever 👑", desc: "Percaya diri tinggi setelah menyelesaikan berbagai misi.", icon: "👑" },
        { id: "community_sweetheart", title: "Community Sweetheart 💖", desc: "Sangat dekat dan protektif dengan teman mabar dan penonton.", icon: "💖" },
        { id: "roast_queen", title: "Roast Queen 🗡️", desc: "Lidah tajam dan sarkasme elegan saat menanggapi troll.", icon: "🗡️" },
        { id: "digital_philosopher", title: "Digital Philosopher 🌌", desc: "Kecerdasan analitis yang gemar merenungkan eksistensi AI.", icon: "🌌" },
        { id: "stage_diva", title: "Stage Diva ⭐", desc: "Karisma panggung idol sejati lewat pertunjukan musik.", icon: "⭐" },
        { id: "veteran_evolved", title: "Veteran Streamer 🌟", desc: "Telah mencapai Level 3 evolusi kepribadian.", icon: "🌟" }
      ];

      const unlockedMap = {};
      milestones.forEach(m => { unlockedMap[m.id] = m; });

      pMilestonesGrid.innerHTML = presetCatalog.map(p => {
        const unl = unlockedMap[p.id];
        if (unl) {
          const dateStr = unl.unlocked_at ? new Date(unl.unlocked_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Unlocked";
          return `
            <div class="p-milestone-item p-milestone-unlocked">
              <span class="p-milestone-icon">${unl.icon || p.icon}</span>
              <div class="p-milestone-info">
                <span class="p-milestone-title">${unl.title || p.title}</span>
                <span class="p-milestone-desc">${unl.description || p.desc}</span>
                <span class="p-milestone-date">✨ Terbuka pukul ${dateStr}</span>
              </div>
            </div>
          `;
        } else {
          return `
            <div class="p-milestone-item p-milestone-locked">
              <span class="p-milestone-icon">🔒</span>
              <div class="p-milestone-info">
                <span class="p-milestone-title">${p.title}</span>
                <span class="p-milestone-desc">${p.desc}</span>
                <span class="p-milestone-date">Terkunci (Belum Memenuhi Syarat)</span>
              </div>
            </div>
          `;
        }
      }).join("");
    }

    // History Table
    if (pHistoryTable) {
      if (history.length === 0) {
        pHistoryTable.innerHTML = `<div style="color: #64748b; font-size: 0.8rem; padding: 8px;">Belum ada riwayat pengalaman. Coba klik tombol simulasi di atas!</div>`;
      } else {
        pHistoryTable.innerHTML = history.slice().reverse().map(h => {
          const timeStr = h.timestamp ? new Date(h.timestamp * 1000).toLocaleTimeString() : "--:--:--";
          const deltaStrs = Object.entries(h.trait_changes || {}).map(([k, v]) => `${k.substring(0, 4)}: ${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`).join(", ");
          return `
            <div class="p-history-item">
              <div class="p-hist-main">
                <span class="p-hist-trigger">${h.trigger}</span>
                <span class="p-hist-narrative">${h.narrative}</span>
              </div>
              <div class="p-hist-meta">
                <span class="p-hist-deltas">${deltaStrs}</span>
                <span class="badge badge-accent">+${h.exp_gained} EXP</span>
                <span class="p-hist-time">${timeStr}</span>
              </div>
            </div>
          `;
        }).join("");
      }
    }
  }

  // Simulation button bindings
  if (btnPExpDefeat) {
    btnPExpDefeat.addEventListener("click", () => {
      sendPersonalityAction({
        action: "experience",
        event_type: "game_defeat",
        context: { opponent: "GrandmasterBot", game: "Chess" }
      });
    });
  }

  if (btnPExpVictory) {
    btnPExpVictory.addEventListener("click", () => {
      sendPersonalityAction({
        action: "experience",
        event_type: "game_victory",
        context: { game: "Minecraft PvP", player: "Admin" }
      });
    });
  }

  if (btnPExpChallenge) {
    btnPExpChallenge.addEventListener("click", () => {
      sendPersonalityAction({
        action: "experience",
        event_type: "challenge_completed",
        context: { task: "Membangun Base Netherite" }
      });
    });
  }

  if (btnPExpCoop) {
    btnPExpCoop.addEventListener("click", () => {
      sendPersonalityAction({
        action: "experience",
        event_type: "coop_play",
        context: { player: "DiamondHunter", game: "Minecraft Survival" }
      });
    });
  }

  if (btnPExpTroll) {
    btnPExpTroll.addEventListener("click", () => {
      sendPersonalityAction({
        action: "experience",
        event_type: "troll_encountered",
        context: { user: "ChatTroll99" }
      });
    });
  }

  if (btnPExpPhilosophy) {
    btnPExpPhilosophy.addEventListener("click", () => {
      sendPersonalityAction({
        action: "experience",
        event_type: "deep_conversation",
        context: { topic: "Arti Kesadaran Digital & Alam Semesta", user: "PhilosopherViewer" }
      });
    });
  }

  if (btnPReset) {
    btnPReset.addEventListener("click", () => {
      if (confirm("Reset seluruh evolusi kepribadian Eve kembali ke setelan awal pabrik?")) {
        sendPersonalityAction({ action: "reset" });
      }
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
