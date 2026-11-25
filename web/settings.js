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

  // Modal Elements
  const confirmModal = document.getElementById("confirmModal");
  const modalTitle = document.getElementById("modalTitle");
  const modalMessage = document.getElementById("modalMessage");
  const btnModalClose = document.getElementById("btnModalClose");
  const btnModalCancel = document.getElementById("btnModalCancel");
  const btnModalConfirm = document.getElementById("btnModalConfirm");
  let onModalConfirmCallback = null;

  // Initialize
  init();

  async function init() {
    try {
      const [cfgRes, schemaRes, diagRes] = await Promise.all([
        fetch("/api/config").then(r => r.json()),
        fetch("/api/config/schema").then(r => r.json()),
        fetch("/api/system/diagnostics").then(r => r.json())
      ]);

      savedConfig = cfgRes;
      draftConfig = JSON.parse(JSON.stringify(cfgRes));
      schema = schemaRes;
      diagnostics = diagRes;

      if (loadingState) loadingState.style.display = "none";
      renderNavigation();
      renderContent();
      setupEventListeners();
    } catch (err) {
      console.error("[Settings] Initialization failed:", err);
      showToast(`Failed to load configuration: ${err.message}`, "danger");
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
    const categoryItems = schema.filter(item => item.category === category);
    const categoryTitles = {
      general: { title: "⚙️ General Settings", desc: "Sistem dasar bot, mode otonom, dan konfigurasi bahasa utama." },
      brain: { title: "🧠 AI & Brain (LLM)", desc: "Penyedia model bahasa (Gemini, OpenAI, Ollama), suhu kreativitas, dan limit token." },
      personality: { title: "🎭 Personality & Persona", desc: "Parameter intensitas humor, kadar sarkasme/tsundere, kehangatan, dan gaya berbicara." },
      memory: { title: "💾 Memory & Second Brain", desc: "Pengaturan memori jangka pendek, penyimpanan episodik, dan sinkronisasi Karpathy BrainMap." },
      mood: { title: "💖 Mood & Emotion", desc: "Kecepatan decay emosi internal dan kepekaan reaksi terhadap event streaming." },
      voice: { title: "🎙️ Voice & TTS (Edge-TTS)", desc: "Aktor suara vokal sintetis, laju bicara, modulasi pitch, dan sensitivitas lip-sync." },
      stt: { title: "🎧 Speech-to-Text (STT)", desc: "Pengaturan pengenalan suara lokal Whisper (enable, ukuran model, dan device komputasi)." },
      avatar: { title: "👤 Avatar & VTube Studio", desc: "Integrasi WebSocket VTube Studio (port 8001), intensitas gerakan, dan ekspresi Live2D." },
      karaoke: { title: "🎤 Karaoke & Performance", desc: "Pengaturan volume vokal/BGM panggung idol, katalog lagu, dan glowstick crowd cheer." },
      twitch: { title: "💬 Twitch & Chat Stream", desc: "Koneksi live chat Twitch IRC, bot nick, dan perlindungan keamanan OAuth token." },
      youtube: { title: "▶️ YouTube Live Chat", desc: "Polling live chat & SuperChat YouTube Data API v3 dengan perlindungan keamanan API key." },
      discord: { title: "👾 Discord Bot Chat", desc: "Koneksi channel Discord menggunakan Bot Token dan Channel ID secara aman." },
      moderator: { title: "🛡️ Moderation & Safety", desc: "Filter kata terlarang, batas panjang pesan penonton, dan pencegahan prompt injection." },
      security: { title: "🔐 Security & Access", desc: "Token otentikasi Creator WebSocket dan daftar origin tambahan yang diizinkan." },
      minecraft: { title: "⛏️ Minecraft Engine", desc: "Mode santai vs kompe, jarak follow bodyguard player, dan batas keselamatan HP." },
      autonomous: { title: "🤖 Autonomous Agent", desc: "Perencanaan target mandiri, jeda obrolan spontan saat chat sepi, dan persetujuan aksi." },
      performance: { title: "⚡ Performance & Network", desc: "Batas antrean tugas simultan, heartbeat ping, dan alokasi buffer audio." }
    };

    const headerInfo = categoryTitles[category] || { title: `${category.toUpperCase()} SETTINGS`, desc: "" };

    let html = `
      <div class="category-header">
        <div class="category-title-row">
          <h2 class="category-title">${headerInfo.title}</h2>
          <button class="btn btn-secondary btn-sm" id="btnResetCategory" data-cat="${category}" title="Reset kategori ini ke nilai bawaan">
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
        <div class="setting-card ${isModified ? 'modified' : ''}" data-path="${item.path}">
          <div class="setting-info">
            <div class="setting-label-row">
              <span class="setting-label">${item.label}</span>
              <span class="badge-tag ${tagClass}">${tagText}</span>
              ${isModified ? '<span class="badge-tag" style="background: rgba(139,92,246,0.25); color: #c4b5fd;">Modified</span>' : ''}
            </div>
            <p class="setting-desc">${item.description}</p>
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
    const p = item.path;

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
          <input type="range" data-path="${p}" min="${item.min}" max="${item.max}" step="${item.step || 1}" value="${val}">
          <span class="slider-value-pill" id="val_${p}">${val}${unit}</span>
        </div>
      `;
    } else if (item.type === "select") {
      const optionsHtml = (item.options || []).map(opt => `
        <option value="${opt.value}" ${opt.value === value ? 'selected' : ''}>${opt.label}</option>
      `).join("");
      return `
        <select class="cyber-select" data-path="${p}">
          ${optionsHtml}
        </select>
      `;
    } else if (item.type === "number") {
      const minAttr = item.min !== undefined ? `min="${item.min}"` : "";
      const maxAttr = item.max !== undefined ? `max="${item.max}"` : "";
      return `
        <input type="number" class="cyber-input" data-path="${p}" value="${value !== undefined ? value : item.default}" ${minAttr} ${maxAttr}>
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
      const rowsHtml = items.map((entry, idx) => `
        <div class="list-item-row" style="display: flex; gap: 8px; align-items: center;">
          <input type="text" class="cyber-input list-item-input" data-list-path="${p}" data-index="${idx}" value="${escapeAttr(entry)}" placeholder="http://localhost:3000">
          <button type="button" class="btn btn-danger-outline list-remove-btn" data-list-path="${p}" data-index="${idx}" title="Remove origin" style="padding: 6px 10px;">✕</button>
        </div>
      `).join("");
      return `
        <div class="list-editor" data-path="${p}" style="display: flex; flex-direction: column; gap: 8px; width: 100%; max-width: 380px;">
          <div class="list-items-container" style="display: flex; flex-direction: column; gap: 6px;">
            ${rowsHtml || '<small style="color: var(--text-dim);">No entries configured (localhost allowed by default).</small>'}
          </div>
          <div class="list-add-row" style="display: flex; gap: 8px; align-items: center;">
            <input type="text" class="cyber-input list-add-input" data-list-path="${p}" placeholder="e.g. http://192.168.1.50:7860">
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
    return String(val)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
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
    const matches = schema.filter(item => {
      return (
        item.label.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q) ||
        item.path.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q)
      );
    });

    let html = `
      <div class="category-header">
        <h2 class="category-title">🔍 Search Results</h2>
        <p class="category-desc">Found ${matches.length} parameter(s) matching "${searchQuery}".</p>
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
          <div class="setting-card ${isModified ? 'modified' : ''}" data-path="${item.path}">
            <div class="setting-info">
              <div class="setting-label-row">
                <span class="setting-label">${item.label}</span>
                <span class="badge-tag" style="background: rgba(255,255,255,0.08); color: var(--text-muted);">${item.category.toUpperCase()}</span>
                <span class="badge-tag ${tagClass}">${tagText}</span>
              </div>
              <p class="setting-desc">${item.description}</p>
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
          <h3 style="font-size: 1.3rem; color: var(--accent-cyan); font-family: var(--font-mono);">${diag.uptime_human || '0s'}</h3>
        </div>
        <div style="background: var(--bg-card); border: 1px solid var(--border-color); padding: 12px 18px; border-radius: 10px; flex: 1; min-width: 160px;">
          <small style="color: var(--text-dim); font-size: 0.75rem;">STATUS MASTER ENGINE</small>
          <h3 style="font-size: 1.3rem; color: #34d399; font-weight: 700;">${diag.engine_running ? 'RUNNING 🟢' : 'STOPPED 🔴'}</h3>
        </div>
        <div style="background: var(--bg-card); border: 1px solid var(--border-color); padding: 12px 18px; border-radius: 10px; flex: 1; min-width: 160px;">
          <small style="color: var(--text-dim); font-size: 0.75rem;">ACTIVE WEBSOCKETS</small>
          <h3 style="font-size: 1.3rem; color: #c4b5fd; font-family: var(--font-mono);">${diag.active_listeners_count || 1} client(s)</h3>
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
            <span class="status-pill status-online">${modules.llm_brain?.status || 'Active'}</span>
          </div>
          <div class="diag-meta-list">
            <div>Provider: <strong>${modules.llm_brain?.provider || 'gemini'}</strong></div>
            <div>Model: <strong>${modules.llm_brain?.model || 'default'}</strong></div>
            <div>Context History: <strong>${modules.llm_brain?.memory_turns || 0} turns</strong></div>
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
            <div>Voice: <strong>${modules.tts?.voice || 'en-US-AnaNeural'}</strong></div>
            <div>Rate / Pitch: <strong>${modules.tts?.rate || '+5%'} / ${modules.tts?.pitch || '+10Hz'}</strong></div>
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
            <div>Target: <strong>${modules.vts?.host || 'localhost'}:${modules.vts?.port || 8001}</strong></div>
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
            <div>Channel: <strong>#${modules.twitch?.channel || 'none'}</strong></div>
            <div>Message Queue: <strong>${modules.twitch?.queue_size || 0} msgs</strong></div>
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
            <div>Rules Active: <strong>${(modules.moderator?.banned_words_count || 0) + (modules.moderator?.banned_patterns_count || 0)} rules</strong></div>
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
            <div>Episodes: <strong>${modules.memory?.stats?.total_episodes || 0} records</strong></div>
            <div>Users Tracked: <strong>${modules.memory?.stats?.unique_users_count || 0} people</strong></div>
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
          diagnostics = await fetch("/api/system/diagnostics").then(r => r.json());
          renderDiagnosticsView();
          showToast("Telemetry refreshed successfully!", "success");
        } catch (err) {
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
          const res = await fetch(`/api/config/test/${testName}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" }
          }).then(r => r.json());

          const timestamp = new Date().toLocaleTimeString();
          if (consoleEl) {
            consoleEl.innerHTML = `[${timestamp}] [TEST: ${testName.toUpperCase()}] SUCCESS: ${res.success ? 'PASSED ✅' : 'FAILED ❌'}\n` +
              JSON.stringify(res, null, 2);
          }
          if (statusEl) statusEl.textContent = `Test ${testName.toUpperCase()} completed.`;
          showToast(`Test ${testName.toUpperCase()} completed successfully!`, "success");
        } catch (err) {
          if (consoleEl) {
            consoleEl.innerHTML = `[ERROR: ${testName.toUpperCase()}] ${err.message}`;
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
      const res = await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draftConfig)
      }).then(r => r.json());

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
      const res = await fetch("/api/config/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category })
      }).then(r => r.json());

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
      const res = await fetch("/api/config/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      }).then(r => r.json());

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
