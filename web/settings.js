// ============================================================
// MaybeAI - Configuration Center Client Engine
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  let savedConfig = {};
  let draftConfig = {};
  let schema = [];
  let diagnostics = null;
  let activeCategory = "diagnostics";
  let searchQuery = "";

  const CREATOR_TOKEN_KEY = "maybeai_creator_token";

  function setCreatorToken(token) {
    const clean = String(token || "").trim();
    if (!clean) return;
    try { localStorage.setItem(CREATOR_TOKEN_KEY, clean); } catch (e) {}
    try { sessionStorage.setItem(CREATOR_TOKEN_KEY, clean); } catch (e) {}
  }

  function clearCreatorToken() {
    try { localStorage.removeItem(CREATOR_TOKEN_KEY); } catch (e) {}
    try { sessionStorage.removeItem(CREATOR_TOKEN_KEY); } catch (e) {}
  }

  function getCreatorToken() {
    try {
      const urlToken = new URLSearchParams(window.location.search).get("token");
      if (urlToken && urlToken.trim()) {
        const clean = urlToken.trim();
        setCreatorToken(clean);
        return clean;
      }
    } catch (e) {}
    try {
      return (
        localStorage.getItem(CREATOR_TOKEN_KEY) ||
        sessionStorage.getItem(CREATOR_TOKEN_KEY) ||
        ""
      );
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

  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // DOM Elements
  const sidebarNav = document.getElementById("sidebarNav");
  const settingsContent = document.getElementById("settingsContent");
  const loadingState = document.getElementById("loadingState");
  const unsavedBanner = document.getElementById("unsavedBanner");
  const unsavedCountText = document.getElementById("unsavedCountText");
  const btnSaveAllChanges = document.getElementById("btnSaveAllChanges");
  const btnDiscardChanges = document.getElementById("btnDiscardChanges");
  const btnResetAll = document.getElementById("btnResetAll");
  const configSearchInput = document.getElementById("configSearchInput");
  const clearSearchBtn = document.getElementById("clearSearchBtn");
  const toastContainer = document.getElementById("toastContainer");
  const creatorAuthBar = document.getElementById("creatorAuthBar");
  const creatorAuthMsg = document.getElementById("creatorAuthMsg");
  const creatorTokenInput = document.getElementById("creatorTokenInput");
  const btnSaveCreatorToken = document.getElementById("btnSaveCreatorToken");
  const btnClearCreatorToken = document.getElementById("btnClearCreatorToken");
  const btnToggleCreatorAuth = document.getElementById("btnToggleCreatorAuth");
  const connectionText = document.getElementById("connectionText");
  let listenersInitialized = false;

  // Modal Elements
  const confirmModal = document.getElementById("confirmModal");
  const modalTitle = document.getElementById("modalTitle");
  const modalMessage = document.getElementById("modalMessage");
  const btnModalClose = document.getElementById("btnModalClose");
  const btnModalCancel = document.getElementById("btnModalCancel");
  const btnModalConfirm = document.getElementById("btnModalConfirm");
  let onModalConfirmCallback = null;

  function showCreatorAuthBar(message) {
    if (creatorAuthMsg && message) {
      creatorAuthMsg.textContent = message;
    }
    if (creatorTokenInput && !creatorTokenInput.value) {
      creatorTokenInput.value = getCreatorToken();
    }
    if (creatorAuthBar) {
      creatorAuthBar.style.display = "flex";
    }
  }

  function hideCreatorAuthBar() {
    if (creatorAuthBar) {
      creatorAuthBar.style.display = "none";
    }
  }

  async function fetchJsonAuth(url, options = {}) {
    const res = await authFetch(url, options);
    if (res.status === 401 || res.status === 403) {
      let detail = `Creator token required or invalid (HTTP ${res.status}).`;
      try {
        const errBody = await res.json();
        if (errBody && (errBody.error || errBody.detail)) {
          detail = `${errBody.error || errBody.detail} (HTTP ${res.status})`;
        }
      } catch (e) {}
      if (connectionText) connectionText.textContent = "AUTH REQUIRED";
      showCreatorAuthBar(detail);
      const err = new Error(detail);
      err.isAuthError = true;
      err.status = res.status;
      throw err;
    }
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const errBody = await res.json();
        if (errBody && (errBody.error || errBody.detail)) {
          detail = errBody.error || errBody.detail;
        }
      } catch (e) {}
      throw new Error(detail);
    }
    return res.json();
  }

  // Initialize
  setupEventListeners();
  init();

  async function init() {
    try {
      const [cfgRes, schemaRes, diagRes] = await Promise.all([
        fetchJsonAuth("/api/config"),
        fetchJsonAuth("/api/config/schema"),
        fetchJsonAuth("/api/system/diagnostics")
      ]);

      savedConfig = cfgRes && typeof cfgRes === "object" ? cfgRes : {};
      draftConfig = JSON.parse(JSON.stringify(savedConfig));
      schema = Array.isArray(schemaRes) ? schemaRes : [];
      diagnostics = diagRes && typeof diagRes === "object" ? diagRes : {};

      hideCreatorAuthBar();
      if (connectionText) connectionText.textContent = "SYSTEM ONLINE";
      if (loadingState) loadingState.style.display = "none";
      renderNavigation();
      renderContent();
    } catch (err) {
      console.error("[Settings] Initialization failed:", err);
      if (loadingState) loadingState.style.display = "none";
      if (err && err.isAuthError) {
        if (settingsContent) {
          settingsContent.innerHTML = `
            <div class="category-header">
              <h2 class="category-title">🔐 Creator Authentication Required</h2>
              <p class="category-desc">${escapeHtml(err.message)} Enter your Creator Token in the bar above and click <strong>Save &amp; Retry</strong>.</p>
            </div>
          `;
        }
      } else {
        showToast(`Failed to load configuration: ${err.message}`, "danger");
      }
    }
  }

  // --- Navigation & Category Switching ---
  function renderNavigation() {
    sidebarNav.querySelectorAll(".nav-item").forEach(btn => {
      btn.addEventListener("click", () => {
        const cat = btn.getAttribute("data-category");
        if (cat === activeCategory) return;
        activeCategory = cat;
        sidebarNav.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        renderContent();
      });
    });
  }

  // --- Render Active View ---
  function renderContent() {
    if (searchQuery.trim().length > 0) {
      renderSearchResults();
      return;
    }

    if (activeCategory === "diagnostics") {
      renderDiagnosticsView();
    } else {
      renderCategorySettingsView(activeCategory);
    }
  }

  // --- Category Settings View ---
  function renderCategorySettingsView(category) {
    const safeSchema = Array.isArray(schema) ? schema : [];
    const categoryItems = safeSchema.filter(item => item.category === category);
    const categoryTitles = {
      general: { title: "⚙️ General Settings", desc: "Sistem dasar bot, mode otonom, dan konfigurasi bahasa utama." },
      brain: { title: "🧠 AI & Brain (LLM)", desc: "Penyedia model bahasa (Gemini, OpenAI, Ollama), suhu kreativitas, dan limit token." },
      personality: { title: "🎭 Personality & Persona", desc: "Parameter intensitas humor, kadar sarkasme/tsundere, kehangatan, dan gaya berbicara." },
      memory: { title: "💾 Memory & Second Brain", desc: "Pengaturan memori jangka pendek, penyimpanan episodik, dan sinkronisasi Karpathy BrainMap." },
      mood: { title: "💖 Mood & Emotion", desc: "Kecepatan decay emosi internal dan kepekaan reaksi terhadap event streaming." },
      voice: { title: "🎙️ Voice & TTS (Edge-TTS)", desc: "Aktor suara vokal sintetis, laju bicara, modulasi pitch, dan sensitivitas lip-sync." },
      stt: { title: "🎧 Speech-to-Text (STT)", desc: "Pengaturan pengenalan suara lokal Whisper (enable, ukuran model, dan device komputasi)." },
      avatar: { title: "👤 Avatar & VTube Studio", desc: "Integrasi WebSocket VTube Studio (port 8001), renderer 2D/3D VRM, dan ekspresi Live2D." },
      vision: { title: "👁️ Vision & VLM", desc: "Persepsi layar berkala menggunakan Vision-Language Model (VLM) multimodal." },
      karaoke: { title: "🎤 Karaoke & Performance", desc: "Pengaturan volume vokal/BGM panggung idol, katalog lagu, dan glowstick crowd cheer." },
      twitch: { title: "💬 Twitch & Chat Stream", desc: "Koneksi live chat Twitch IRC (TLS/IRCv3), bot nick, dan perlindungan keamanan OAuth token." },
      youtube: { title: "▶️ YouTube Live Chat", desc: "Polling live chat & SuperChat YouTube Data API v3 dengan perlindungan keamanan API key." },
      discord: { title: "👾 Discord Bot Chat", desc: "Koneksi channel Discord menggunakan Bot Token, Gateway WS, dan Reply Bridge." },
      tiktok: { title: "🎵 TikTok Live Chat", desc: "Integrasi komentar, gift, like, dan follow dari TikTok Live." },
      moderator: { title: "🛡️ Moderation & Safety", desc: "Filter kata terlarang, batas panjang pesan penonton, dan pencegahan prompt injection." },
      security: { title: "🔐 Security & Access", desc: "Token otentikasi Creator WebSocket dan daftar origin tambahan yang diizinkan." },
      minecraft: { title: "⛏️ Minecraft Engine", desc: "Mode santai vs kompe, jarak follow bodyguard player, dan batas keselamatan HP." },
      autonomous: { title: "🤖 Autonomous Agent", desc: "Perencanaan target mandiri, misi otonom closed-loop, jeda obrolan spontan, dan persetujuan aksi." },
      collab: { title: "🤝 AI Collab Protocol", desc: "Kolaborasi multi-VTuber via /ws/collab dengan HMAC-SHA256, turn-taking, dan batas anti-loop." },
      plugins: { title: "🧩 Plugins & SDK", desc: "Ekstensi plugin built-in & eksternal (misal: word_chain) dengan isolasi sandbox subprocess dan timeout hook." },
      obs: { title: "🎬 OBS Showrunner", desc: "Kontrol scene OBS Studio otomatis, replay buffer, dan otentikasi obs-websocket v5." },
      highlights: { title: "📸 Highlights & VOD", desc: "Deteksi highlight otomatis, pipeline klip vertikal ffmpeg, dan ringkasan VOD Markdown." },
      performance: { title: "⚡ Performance & Network", desc: "Batas antrean tugas simultan, heartbeat ping, dan alokasi buffer audio." }
    };

    const headerInfo = categoryTitles[category] || { title: `${escapeHtml(category.toUpperCase())} SETTINGS`, desc: "" };

    let html = `
      <div class="category-header">
        <div class="category-title-row">
          <h2 class="category-title">${headerInfo.title}</h2>
          <button class="btn btn-secondary btn-sm" id="btnResetCategory" data-cat="${escapeAttr(category)}" title="Reset kategori ini ke nilai bawaan">
            <span>🔄</span> Reset Category
          </button>
        </div>
        <p class="category-desc">${headerInfo.desc}</p>
      </div>

      <div class="settings-group">
    `;

    categoryItems.forEach(item => {
      const currVal = getValueByPath(draftConfig, item.path);
      const isModified = isFieldModified(item.path);
      const tagClass = item.restart_required ? "tag-restart" : "tag-hotreload";
      const tagText = item.restart_required ? "Restart Required 🔄" : "Hot-Reload ⚡";

      html += `
        <div class="setting-card ${isModified ? 'modified' : ''}" data-path="${escapeAttr(item.path)}">
          <div class="setting-info">
            <div class="setting-label-row">
              <span class="setting-label">${escapeHtml(item.label)}</span>
              <span class="badge-tag ${tagClass}">${tagText}</span>
              ${isModified ? '<span class="badge-tag" style="background: rgba(139,92,246,0.25); color: #c4b5fd;">Modified</span>' : ''}
            </div>
            <p class="setting-desc">${escapeHtml(item.description)}</p>
          </div>
          <div class="setting-control">
            ${renderControlHtml(item, currVal)}
          </div>
        </div>
      `;
    });

    html += `</div>`;
    settingsContent.innerHTML = html;

    // Attach control listeners
    attachControlListeners();

    // Category reset listener
    const btnResetCat = document.getElementById("btnResetCategory");
    if (btnResetCat) {
      btnResetCat.addEventListener("click", () => {
        openConfirmModal(
          `Reset Kategori ${category.toUpperCase()}?`,
          `Seluruh parameter dalam kategori ini akan dikembalikan ke nilai default pabrik. Tindakan ini tidak menghapus riwayat obrolan atau data memori.`,
          () => resetCategory(category)
        );
      });
    }
  }

  // --- Render Control HTML by Type ---
  function renderControlHtml(item, value) {
    const p = escapeAttr(item.path);

    if (item.type === "toggle") {
      const checked = Boolean(value);
      return `
        <label class="cyber-switch">
          <input type="checkbox" data-path="${p}" ${checked ? 'checked' : ''}>
          <span class="cyber-slider"></span>
        </label>
      `;
    } else if (item.type === "slider") {
      const val = value !== undefined ? value : item.default;
      const unit = item.unit || "";
      return `
        <div class="slider-wrapper">
          <input type="range" data-path="${p}" min="${escapeAttr(item.min)}" max="${escapeAttr(item.max)}" step="${escapeAttr(item.step || 1)}" value="${escapeAttr(val)}">
          <span class="slider-value-pill" id="val_${p}">${escapeHtml(val)}${escapeHtml(unit)}</span>
        </div>
      `;
    } else if (item.type === "select") {
      const optionsHtml = (item.options || []).map(opt => `
        <option value="${escapeAttr(opt.value)}" ${opt.value === value ? 'selected' : ''}>${escapeHtml(opt.label)}</option>
      `).join("");
      return `
        <select class="cyber-select" data-path="${p}">
          ${optionsHtml}
        </select>
      `;
    } else if (item.type === "number") {
      const minAttr = item.min !== undefined ? `min="${escapeAttr(item.min)}"` : "";
      const maxAttr = item.max !== undefined ? `max="${escapeAttr(item.max)}"` : "";
      const stepAttr = item.step !== undefined ? `step="${escapeAttr(item.step)}"` : 'step="any"';
      return `
        <input type="number" class="cyber-input" data-path="${p}" value="${escapeAttr(value !== undefined ? value : item.default)}" ${minAttr} ${maxAttr} ${stepAttr}>
      `;
    } else if (item.type === "secret") {
      return `
        <div class="secret-wrapper">
          <input type="password" class="cyber-input" data-path="${p}" value="${escapeAttr(value || '')}" placeholder="Enter secret key...">
          <button type="button" class="secret-toggle-btn" title="Toggle visibility">👁️</button>
        </div>
      `;
    } else if (item.type === "list") {
      const items = Array.isArray(value) ? value : [];
      const rawPath = String(item.path || "");
      const itemPlaceholder = rawPath.includes("plugin") ? "word_chain" : "http://192.168.1.50:7860";
      const emptyLabel = rawPath.includes("plugin") ? "No plugins enabled." : "No entries configured (localhost allowed by default).";
      const rowsHtml = items.map((entry, idx) => `
        <div class="list-item-row" style="display: flex; gap: 8px; align-items: center;">
          <input type="text" class="cyber-input list-item-input" data-list-path="${p}" data-index="${idx}" value="${escapeAttr(entry)}" placeholder="${escapeAttr(itemPlaceholder)}">
          <button type="button" class="btn btn-danger-outline list-remove-btn" data-list-path="${p}" data-index="${idx}" title="Remove item" style="padding: 6px 10px;">✕</button>
        </div>
      `).join("");
      return `
        <div class="list-editor" data-path="${p}" style="display: flex; flex-direction: column; gap: 8px; width: 100%; max-width: 380px;">
          <div class="list-items-container" style="display: flex; flex-direction: column; gap: 6px;">
            ${rowsHtml || `<small style="color: var(--text-dim);">${escapeHtml(emptyLabel)}</small>`}
          </div>
          <div class="list-add-row" style="display: flex; gap: 8px; align-items: center;">
            <input type="text" class="cyber-input list-add-input" data-list-path="${p}" placeholder="e.g. ${escapeAttr(itemPlaceholder)}">
            <button type="button" class="btn btn-secondary list-add-btn" data-list-path="${p}" style="white-space: nowrap;">+ Add</button>
          </div>
        </div>
      `;
    } else {
      // Default: text
      return `
        <input type="text" class="cyber-input" data-path="${p}" value="${escapeAttr(value !== undefined ? value : '')}" placeholder="${escapeAttr(item.default || '')}">
      `;
    }
  }

  function escapeAttr(val) {
    return escapeHtml(val);
  }

  // --- Attach Control Listeners ---
  function attachControlListeners() {
    // Checkbox toggles
    settingsContent.querySelectorAll('input[type="checkbox"]').forEach(input => {
      input.addEventListener("change", (e) => {
        const path = e.target.getAttribute("data-path");
        setValueByPath(draftConfig, path, e.target.checked);
        onDraftModified(path);
      });
    });

    // Range sliders
    settingsContent.querySelectorAll('input[type="range"]').forEach(input => {
      input.addEventListener("input", (e) => {
        const path = e.target.getAttribute("data-path");
        const val = parseFloat(e.target.value);
        setValueByPath(draftConfig, path, val);

        const schemaItem = schema.find(s => s.path === path);
        const unit = schemaItem?.unit || "";
        const pill = document.getElementById(`val_${path}`);
        if (pill) pill.textContent = `${val}${unit}`;

        onDraftModified(path);
      });
    });

    // Selects
    settingsContent.querySelectorAll('select.cyber-select').forEach(select => {
      select.addEventListener("change", (e) => {
        const path = e.target.getAttribute("data-path");
        setValueByPath(draftConfig, path, e.target.value);
        onDraftModified(path);
      });
    });

    // Number & Text inputs
    settingsContent.querySelectorAll('input.cyber-input').forEach(input => {
      if (input.type === "range" || input.type === "checkbox") return;
      if (input.closest(".list-editor")) return;
      input.addEventListener("input", (e) => {
        const path = e.target.getAttribute("data-path");
        let val = e.target.value;
        if (e.target.type === "number") {
          val = e.target.value === "" ? 0 : parseFloat(e.target.value);
        }
        setValueByPath(draftConfig, path, val);
        onDraftModified(path);
      });
    });

    // List editors (e.g. security.allowed_origins)
    settingsContent.querySelectorAll(".list-editor").forEach(editor => {
      const path = editor.getAttribute("data-path");

      editor.querySelectorAll(".list-item-input").forEach(itemInput => {
        itemInput.addEventListener("input", (e) => {
          const idx = parseInt(e.target.getAttribute("data-index"), 10);
          const currentList = Array.isArray(getValueByPath(draftConfig, path))
            ? [...getValueByPath(draftConfig, path)]
            : [];
          currentList[idx] = e.target.value;
          setValueByPath(draftConfig, path, currentList);
          onDraftModified(path);
        });
      });

      editor.querySelectorAll(".list-remove-btn").forEach(removeBtn => {
        removeBtn.addEventListener("click", (e) => {
          const idx = parseInt(e.currentTarget.getAttribute("data-index"), 10);
          const currentList = Array.isArray(getValueByPath(draftConfig, path))
            ? [...getValueByPath(draftConfig, path)]
            : [];
          currentList.splice(idx, 1);
          setValueByPath(draftConfig, path, currentList);
          onDraftModified(path);
          renderContent();
        });
      });

      const addInput = editor.querySelector(".list-add-input");
      const addBtn = editor.querySelector(".list-add-btn");
      const addOriginItem = () => {
        if (!addInput) return;
        const newVal = addInput.value.trim();
        if (!newVal) return;
        const currentList = Array.isArray(getValueByPath(draftConfig, path))
          ? [...getValueByPath(draftConfig, path)]
          : [];
        if (!currentList.includes(newVal)) {
          currentList.push(newVal);
        }
        setValueByPath(draftConfig, path, currentList);
        onDraftModified(path);
        renderContent();
      };

      if (addBtn) {
        addBtn.addEventListener("click", addOriginItem);
      }
      if (addInput) {
        addInput.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            addOriginItem();
          }
        });
      }
    });

    // Secret visibility toggles
    settingsContent.querySelectorAll(".secret-toggle-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const input = e.target.previousElementSibling;
        if (input) {
          if (input.type === "password") {
            input.type = "text";
            e.target.textContent = "🔒";
          } else {
            input.type = "password";
            e.target.textContent = "👁️";
          }
        }
      });
    });
  }

  // --- Search Results View ---
  function renderSearchResults() {
    const q = searchQuery.toLowerCase().trim();
    const safeSchema = Array.isArray(schema) ? schema : [];
    const matches = safeSchema.filter(item => {
      return (
        String(item.label || "").toLowerCase().includes(q) ||
        String(item.description || "").toLowerCase().includes(q) ||
        String(item.path || "").toLowerCase().includes(q) ||
        String(item.category || "").toLowerCase().includes(q)
      );
    });

    let html = `
      <div class="category-header">
        <h2 class="category-title">🔍 Search Results</h2>
        <p class="category-desc">Found ${matches.length} parameter(s) matching "${escapeHtml(searchQuery)}".</p>
      </div>
      <div class="settings-group">
    `;

    if (matches.length === 0) {
      html += `
        <div style="text-align: center; padding: 40px; color: var(--text-dim);">
          <p style="font-size: 1.1rem; margin-bottom: 8px;">No configuration parameters found.</p>
          <small>Try searching for words like 'volume', 'temperature', 'provider', or 'minecraft'.</small>
        </div>
      `;
    } else {
      matches.forEach(item => {
        const currVal = getValueByPath(draftConfig, item.path);
        const isModified = isFieldModified(item.path);
        const tagClass = item.restart_required ? "tag-restart" : "tag-hotreload";
        const tagText = item.restart_required ? "Restart Required 🔄" : "Hot-Reload ⚡";

        html += `
          <div class="setting-card ${isModified ? 'modified' : ''}" data-path="${escapeAttr(item.path)}">
            <div class="setting-info">
              <div class="setting-label-row">
                <span class="setting-label">${escapeHtml(item.label)}</span>
                <span class="badge-tag" style="background: rgba(255,255,255,0.08); color: var(--text-muted);">${escapeHtml(String(item.category || "").toUpperCase())}</span>
                <span class="badge-tag ${tagClass}">${tagText}</span>
              </div>
              <p class="setting-desc">${escapeHtml(item.description)}</p>
            </div>
            <div class="setting-control">
              ${renderControlHtml(item, currVal)}
            </div>
          </div>
        `;
      });
    }

    html += `</div>`;
    settingsContent.innerHTML = html;
    attachControlListeners();
  }

  // --- System Diagnostics View ---
  function renderDiagnosticsView() {
    const diag = diagnostics || {};
    const modules = diag.modules || {};

    let html = `
      <div class="category-header">
        <div class="category-title-row">
          <h2 class="category-title">📊 System Diagnostics & Telemetry</h2>
          <button class="btn btn-secondary btn-sm" id="btnRefreshDiagnostics">
            <span>🔄</span> Refresh Telemetry
          </button>
        </div>
        <p class="category-desc">Status operasional runtime aktual, kesehatan koneksi modul, dan konsol pengujian interaktif.</p>
      </div>

      <!-- Quick Telemetry Banner -->
      <div style="display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap;">
        <div style="background: var(--bg-card); border: 1px solid var(--border-color); padding: 12px 18px; border-radius: 10px; flex: 1; min-width: 160px;">
          <small style="color: var(--text-dim); font-size: 0.75rem;">UPTIME SISTEM</small>
          <h3 style="font-size: 1.3rem; color: var(--accent-cyan); font-family: var(--font-mono);">${escapeHtml(diag.uptime_human || '0s')}</h3>
        </div>
        <div style="background: var(--bg-card); border: 1px solid var(--border-color); padding: 12px 18px; border-radius: 10px; flex: 1; min-width: 160px;">
          <small style="color: var(--text-dim); font-size: 0.75rem;">STATUS MASTER ENGINE</small>
          <h3 style="font-size: 1.3rem; color: #34d399; font-weight: 700;">${diag.engine_running ? 'RUNNING 🟢' : 'STOPPED 🔴'}</h3>
        </div>
        <div style="background: var(--bg-card); border: 1px solid var(--border-color); padding: 12px 18px; border-radius: 10px; flex: 1; min-width: 160px;">
          <small style="color: var(--text-dim); font-size: 0.75rem;">ACTIVE WEBSOCKETS</small>
          <h3 style="font-size: 1.3rem; color: #c4b5fd; font-family: var(--font-mono);">${escapeHtml(diag.active_listeners_count || 1)} client(s)</h3>
        </div>
      </div>

      <!-- Module Status Cards -->
      <div class="diag-grid">
        <!-- 1. LLM Brain -->
        <div class="diag-card">
          <div class="diag-card-top">
            <div class="diag-title-group">
              <h4>🧠 LLM Brain</h4>
              <small>Autonomous Conversation & Persona</small>
            </div>
            <span class="status-pill status-online">${escapeHtml(modules.llm_brain?.status || 'Active')}</span>
          </div>
          <div class="diag-meta-list">
            <div>Provider: <strong>${escapeHtml(modules.llm_brain?.provider || 'gemini')}</strong></div>
            <div>Model: <strong>${escapeHtml(modules.llm_brain?.model || 'default')}</strong></div>
            <div>Context History: <strong>${escapeHtml(modules.llm_brain?.memory_turns || 0)} turns</strong></div>
          </div>
          <div class="diag-actions">
            <button class="btn btn-secondary btn-block btn-diag-test" data-test="llm">
              <span>🧠</span> Test LLM Response
            </button>
          </div>
        </div>

        <!-- 2. TTS Voice -->
        <div class="diag-card">
          <div class="diag-card-top">
            <div class="diag-title-group">
              <h4>🎙️ Edge-TTS Voice</h4>
              <small>Speech Synthesis & Playback</small>
            </div>
            <span class="status-pill ${modules.tts?.enabled ? 'status-online' : ''}">${modules.tts?.enabled ? 'Active' : 'Disabled'}</span>
          </div>
          <div class="diag-meta-list">
            <div>Voice: <strong>${escapeHtml(modules.tts?.voice || 'en-US-AnaNeural')}</strong></div>
            <div>Rate / Pitch: <strong>${escapeHtml(modules.tts?.rate || '+5%')} / ${escapeHtml(modules.tts?.pitch || '+10Hz')}</strong></div>
          </div>
          <div class="diag-actions">
            <button class="btn btn-secondary btn-block btn-diag-test" data-test="tts">
              <span>🔊</span> Test Voice Output
            </button>
          </div>
        </div>

        <!-- 3. VTube Studio -->
        <div class="diag-card">
          <div class="diag-card-top">
            <div class="diag-title-group">
              <h4>👤 VTube Studio</h4>
              <small>Live2D Tracking WebSocket</small>
            </div>
            <span class="status-pill ${modules.vts?.connected ? 'status-online' : ''}">${modules.vts?.connected ? 'Connected' : 'Standalone'}</span>
          </div>
          <div class="diag-meta-list">
            <div>Target: <strong>${escapeHtml(modules.vts?.host || 'localhost')}:${escapeHtml(modules.vts?.port || 8001)}</strong></div>
            <div>Authenticated: <strong>${modules.vts?.authenticated ? 'YES' : 'NO'}</strong></div>
          </div>
          <div class="diag-actions">
            <button class="btn btn-secondary btn-block btn-diag-test" data-test="vts">
              <span>🔌</span> Reconnect VTS
            </button>
          </div>
        </div>

        <!-- 4. Twitch Chat -->
        <div class="diag-card">
          <div class="diag-card-top">
            <div class="diag-title-group">
              <h4>💬 Twitch IRC</h4>
              <small>Live Stream Chat Ingestion</small>
            </div>
            <span class="status-pill ${modules.twitch?.is_connected ? 'status-online' : ''}">${modules.twitch?.is_connected ? 'Connected' : 'Standby'}</span>
          </div>
          <div class="diag-meta-list">
            <div>Channel: <strong>#${escapeHtml(modules.twitch?.channel || 'none')}</strong></div>
            <div>Message Queue: <strong>${escapeHtml(modules.twitch?.queue_size || 0)} msgs</strong></div>
          </div>
          <div class="diag-actions">
            <button class="btn btn-secondary btn-block btn-diag-test" data-test="twitch">
              <span>💬</span> Test Chat Listener
            </button>
          </div>
        </div>

        <!-- 5. Moderator & Safety -->
        <div class="diag-card">
          <div class="diag-card-top">
            <div class="diag-title-group">
              <h4>🛡️ Moderator & Safety</h4>
              <small>Prompt Injection & Profanity Filter</small>
            </div>
            <span class="status-pill status-online">Active Filter</span>
          </div>
          <div class="diag-meta-list">
            <div>Strict Mode: <strong>${modules.moderator?.strict_mode ? 'ON' : 'OFF'}</strong></div>
            <div>Rules Active: <strong>${Number(modules.moderator?.banned_words_count || 0) + Number(modules.moderator?.banned_patterns_count || 0)} rules</strong></div>
          </div>
          <div class="diag-actions">
            <button class="btn btn-secondary btn-block btn-diag-test" data-test="moderator">
              <span>🛡️</span> Test Filter Probe
            </button>
          </div>
        </div>

        <!-- 6. Memory & Second Brain -->
        <div class="diag-card">
          <div class="diag-card-top">
            <div class="diag-title-group">
              <h4>💾 Second Brain Memory</h4>
              <small>SQLite + Markdown Karpathy Map</small>
            </div>
            <span class="status-pill status-online">Synced</span>
          </div>
          <div class="diag-meta-list">
            <div>Episodes: <strong>${escapeHtml(modules.memory?.stats?.total_episodes || 0)} records</strong></div>
            <div>Users Tracked: <strong>${escapeHtml(modules.memory?.stats?.unique_users_count || 0)} people</strong></div>
          </div>
          <div class="diag-actions">
            <button class="btn btn-secondary btn-block btn-diag-test" data-test="memory">
              <span>📋</span> Inspect Memory State
            </button>
          </div>
        </div>
      </div>

      <!-- Live Test Output Terminal Console -->
      <div class="diag-console">
        <div class="diag-console-header">
          <span>📟 INTERACTIVE DIAGNOSTIC LOG OUTPUT</span>
          <span id="testStatusPill" style="font-size: 0.72rem; color: var(--text-dim);">Ready for test probe</span>
        </div>
        <div class="console-output" id="diagOutputConsole">
> System diagnostics loaded. Click any 'Test' button above to run live subsystem verification.
        </div>
      </div>
    `;

    settingsContent.innerHTML = html;

    // Refresh telemetry
    const btnRefresh = document.getElementById("btnRefreshDiagnostics");
    if (btnRefresh) {
      btnRefresh.addEventListener("click", async () => {
        btnRefresh.disabled = true;
        btnRefresh.innerHTML = `<span>⏳</span> Refreshing...`;
        try {
          diagnostics = await fetchJsonAuth("/api/system/diagnostics");
          renderDiagnosticsView();
          showToast("Telemetry refreshed successfully!", "success");
        } catch (err) {
          btnRefresh.disabled = false;
          btnRefresh.innerHTML = `<span>🔄</span> Refresh Telemetry`;
          showToast(`Refresh failed: ${err.message}`, "danger");
        }
      });
    }

    // Attach diagnostic test buttons
    settingsContent.querySelectorAll(".btn-diag-test").forEach(btn => {
      btn.addEventListener("click", async () => {
        const testName = btn.getAttribute("data-test");
        const consoleEl = document.getElementById("diagOutputConsole");
        const statusEl = document.getElementById("testStatusPill");

        btn.disabled = true;
        const originalText = btn.innerHTML;
        btn.innerHTML = `<span>⏳</span> Testing...`;
        if (statusEl) statusEl.textContent = `Running ${testName.toUpperCase()} diagnostic...`;

        try {
          const res = await fetchJsonAuth(`/api/config/test/${encodeURIComponent(testName)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
          });

          const timestamp = new Date().toLocaleTimeString();
          if (consoleEl) {
            consoleEl.textContent = `[${timestamp}] [TEST: ${testName.toUpperCase()}] SUCCESS: ${res.success ? 'PASSED ✅' : 'FAILED ❌'}\n` +
              JSON.stringify(res, null, 2);
          }
          if (statusEl) statusEl.textContent = `Test ${testName.toUpperCase()} completed.`;
          showToast(`Test ${testName.toUpperCase()} completed successfully!`, "success");
        } catch (err) {
          if (consoleEl) {
            consoleEl.textContent = `[ERROR: ${testName.toUpperCase()}] ${err.message}`;
          }
          showToast(`Test ${testName.toUpperCase()} error: ${err.message}`, "danger");
        } finally {
          btn.disabled = false;
          btn.innerHTML = originalText;
        }
      });
    });
  }

  // --- Dirty State & Unsaved Tracking ---
  function onDraftModified(path) {
    const isMod = isFieldModified(path);
    const card = settingsContent.querySelector(`.setting-card[data-path="${path}"]`);
    if (card) {
      if (isMod) card.classList.add("modified");
      else card.classList.remove("modified");
    }

    const modifiedPaths = getModifiedPaths();
    if (modifiedPaths.length > 0) {
      unsavedBanner.style.display = "flex";
      unsavedCountText.textContent = `You have modified ${modifiedPaths.length} parameter(s).`;
    } else {
      unsavedBanner.style.display = "none";
    }
  }

  function isFieldModified(path) {
    const saved = getValueByPath(savedConfig, path);
    const draft = getValueByPath(draftConfig, path);
    return JSON.stringify(saved) !== JSON.stringify(draft);
  }

  function getModifiedPaths() {
    if (!Array.isArray(schema)) return [];
    return schema
      .map(item => item.path)
      .filter(path => isFieldModified(path));
  }

  // --- Save All Changes ---
  async function saveAllChanges() {
    const modifiedCount = getModifiedPaths().length;
    if (modifiedCount === 0) return;

    btnSaveAllChanges.disabled = true;
    btnSaveAllChanges.innerHTML = `<span>⏳</span> Saving & Applying...`;

    try {
      const res = await fetchJsonAuth("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draftConfig)
      });

      if (res.success) {
        savedConfig = JSON.parse(JSON.stringify(res.config || draftConfig));
        draftConfig = JSON.parse(JSON.stringify(savedConfig));
        unsavedBanner.style.display = "none";
        renderContent();

        if (res.restart_required) {
          showToast("Saved! Some modified settings require restarting the server to take full effect.", "warning");
        } else {
          showToast("Configuration saved and hot-reloaded successfully!", "success");
        }
      } else {
        const errStr = (res.errors || []).join(", ") || "Validation failed";
        showToast(`Save failed: ${errStr}`, "danger");
      }
    } catch (err) {
      showToast(`Error saving configuration: ${err.message}`, "danger");
    } finally {
      btnSaveAllChanges.disabled = false;
      btnSaveAllChanges.innerHTML = `<span>💾</span> Save & Apply Changes (Ctrl+S)`;
    }
  }

  // --- Discard Changes ---
  function discardChanges() {
    draftConfig = JSON.parse(JSON.stringify(savedConfig));
    unsavedBanner.style.display = "none";
    renderContent();
    showToast("Unsaved changes discarded.", "info");
  }

  // --- Reset Category or All ---
  async function resetCategory(category) {
    try {
      const res = await fetchJsonAuth("/api/config/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category })
      });

      if (res.success) {
        savedConfig = res.config;
        draftConfig = JSON.parse(JSON.stringify(res.config));
        unsavedBanner.style.display = "none";
        renderContent();
        showToast(`Category ${category.toUpperCase()} reset to factory defaults!`, "success");
      }
    } catch (err) {
      showToast(`Reset failed: ${err.message}`, "danger");
    }
  }

  async function resetAllSettings() {
    try {
      const res = await fetchJsonAuth("/api/config/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });

      if (res.success) {
        savedConfig = res.config;
        draftConfig = JSON.parse(JSON.stringify(res.config));
        unsavedBanner.style.display = "none";
        renderContent();
        showToast("All configuration settings reset to defaults!", "success");
      }
    } catch (err) {
      showToast(`Reset all failed: ${err.message}`, "danger");
    }
  }

  // --- Confirmation Modal Helpers ---
  function openConfirmModal(title, message, onConfirm) {
    modalTitle.textContent = title;
    modalMessage.textContent = message;
    onModalConfirmCallback = onConfirm;
    confirmModal.style.display = "flex";
  }

  function closeConfirmModal() {
    confirmModal.style.display = "none";
    onModalConfirmCallback = null;
  }

  // --- Event Listeners Setup ---
  function setupEventListeners() {
    if (listenersInitialized) return;
    listenersInitialized = true;

    if (btnToggleCreatorAuth) {
      btnToggleCreatorAuth.addEventListener("click", () => {
        if (creatorAuthBar && creatorAuthBar.style.display === "flex") {
          hideCreatorAuthBar();
        } else {
          showCreatorAuthBar("Enter your Creator Token to authenticate configuration requests.");
        }
      });
    }

    if (btnSaveCreatorToken) {
      const saveAndRetry = () => {
        const val = creatorTokenInput ? creatorTokenInput.value.trim() : "";
        if (!val) {
          showToast("Please enter a Creator Token.", "warning");
          return;
        }
        setCreatorToken(val);
        showToast("Creator Token saved. Loading configuration...", "info");
        init();
      };
      btnSaveCreatorToken.addEventListener("click", saveAndRetry);
      if (creatorTokenInput) {
        creatorTokenInput.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            saveAndRetry();
          }
        });
      }
    }

    if (btnClearCreatorToken) {
      btnClearCreatorToken.addEventListener("click", () => {
        clearCreatorToken();
        if (creatorTokenInput) creatorTokenInput.value = "";
        showCreatorAuthBar("Creator Token cleared. Enter a valid token and click Save & Retry.");
      });
    }
    if (btnSaveAllChanges) btnSaveAllChanges.addEventListener("click", saveAllChanges);
    if (btnDiscardChanges) btnDiscardChanges.addEventListener("click", discardChanges);

    if (btnResetAll) {
      btnResetAll.addEventListener("click", () => {
        openConfirmModal(
          "Reset Entire Configuration?",
          "Seluruh parameter konfigurasi sistem akan dikembalikan ke setelan pabrik default. Data memori dan database pengguna tidak akan terhapus.",
          () => resetAllSettings()
        );
      });
    }

    if (btnModalClose) btnModalClose.addEventListener("click", closeConfirmModal);
    if (btnModalCancel) btnModalCancel.addEventListener("click", closeConfirmModal);
    if (btnModalConfirm) {
      btnModalConfirm.addEventListener("click", () => {
        if (onModalConfirmCallback) onModalConfirmCallback();
        closeConfirmModal();
      });
    }

    // Keyboard Shortcuts (Ctrl+S / Cmd+S to save)
    window.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        saveAllChanges();
      }
    });

    // Search bar input
    if (configSearchInput) {
      configSearchInput.addEventListener("input", (e) => {
        searchQuery = e.target.value;
        if (clearSearchBtn) {
          clearSearchBtn.style.display = searchQuery ? "inline-block" : "none";
        }
        renderContent();
      });
    }

    if (clearSearchBtn) {
      clearSearchBtn.addEventListener("click", () => {
        searchQuery = "";
        if (configSearchInput) configSearchInput.value = "";
        clearSearchBtn.style.display = "none";
        renderContent();
      });
    }
  }

  // --- Toast Notifications ---
  function showToast(msg, type = "info") {
    if (!toastContainer) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    if (type === "success") toast.style.borderColor = "var(--accent-emerald)";
    else if (type === "danger") toast.style.borderColor = "var(--accent-danger)";
    else if (type === "warning") toast.style.borderColor = "var(--accent-amber)";

    toast.textContent = msg;
    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(20px)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // --- Utility Object Traversal ---
  function getValueByPath(obj, path) {
    if (!obj || !path) return undefined;
    const parts = path.split(".");
    let curr = obj;
    for (const p of parts) {
      if (curr && typeof curr === "object" && p in curr) {
        curr = curr[p];
      } else {
        return undefined;
      }
    }
    return curr;
  }

  function setValueByPath(obj, path, val) {
    if (!obj || !path) return;
    const parts = path.split(".");
    let curr = obj;
    for (let i = 0; i < parts.length - 1; i++) {
      const p = parts[i];
      if (!(p in curr) || typeof curr[p] !== "object") {
        curr[p] = {};
      }
      curr = curr[p];
    }
    curr[parts[parts.length - 1]] = val;
  }
});
