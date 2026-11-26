# MaybeAI — Eve Maybe (Autonomous AI VTuber)

<p align="center">
  <img src="https://images.openai.com/static-rsc-4/1KsCRH1rsrU5cosnAbmM5qel7f0Fp9nHz-Q4vpr1ikF_uB62cMBWAsLcmjrs_2oCsXRk-VMTk_eYgp6ODaC_ekQ_zq4ISntJu7PgfrvQ2QB0ByQWlWFx5GYtxVvHZ6Kb8bQ-s2Ph5diQu5UQwmVvAwqhjc8NpNU2py4HjZszqAM?purpose=inline" alt="Eve Maybe Banner" width="700" style="border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.5);" />
</p>

<p align="center">
  <strong>Autonomous AI VTuber Streamer System inspired by Neuro-sama</strong><br>
  <em>Featuring Full-Duplex Voice &amp; Barge-In, Closed-Loop Autonomous Missions, AI-to-AI Collab Protocol, Community Plugin SDK, Streaming Multi-Provider LLMs, Pipelined Sentence-Chunked Edge-TTS Lip-Sync, Dedicated Transparent OBS Overlay &amp; Tabbed Studio UI, Typed Async EventBus, Semantic Memory Embeddings, Multi-Platform Live Chat (Twitch / YouTube Live / Discord), Live2D/Canvas Rendering, Minecraft Autonomy, Screen Vision, Desktop Companion, Mini-Games, Storytelling RPG, Dynamic Karaoke Performance, and Centralized Cyberpunk Configuration Center.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue.svg" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688.svg" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Tests-283%20Passed%20(100%25)-success.svg" alt="Tests" />
  <img src="https://img.shields.io/badge/UI-Cyberpunk%20Futuristic-8b5cf6.svg" alt="UI" />
  <img src="https://img.shields.io/badge/Live2D-VTube%20Studio%20API-ff69b4.svg" alt="VTS" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License" />
</p>

---

## 📖 Daftar Isi (Table of Contents)
- [Tentang MaybeAI & Eve Maybe](#-tentang-maybeai--eve-maybe)
- [Arsitektur Sistem (System Architecture)](#-arsitektur-sistem)
- [Katalog Fitur Komprehensif](#-katalog-fitur-komprehensif)
  - [1. Autonomous Brain & Multi-Provider LLM](#1-autonomous-brain--multi-provider-llm)
  - [2. Edge-TTS & Dynamic Lip-Sync](#2-edge-tts--dynamic-lip-sync)
  - [3. Dual Avatar Rendering (Canvas 2D + VTS)](#3-dual-avatar-rendering)
  - [4. Centralized Cyberpunk Configuration Center](#4-centralized-cyberpunk-configuration-center)
  - [5. Dynamic Performance Director & Karaoke Engine](#5-dynamic-performance-director--karaoke-engine)
  - [6. Minecraft Dual-Mode Engine & Portable Bridge](#6-minecraft-dual-mode-engine--portable-bridge)
  - [7. Multiplayer Social Intelligence](#7-multiplayer-social-intelligence)
  - [8. Experience-Based Personality Evolution](#8-experience-based-personality-evolution)
  - [9. Visual Perception & Screen Awareness](#9-visual-perception--screen-awareness)
  - [10. Desktop Companion & Permission Gateway](#10-desktop-companion--permission-gateway)
  - [11. Interactive Mini-Game Engine](#11-interactive-mini-game-engine)
  - [12. Dynamic Storytelling & Community RPG](#12-dynamic-storytelling--community-rpg)
  - [13. Chess Engine & Streamer Commentary](#13-chess-engine--streamer-commentary)
  - [14. Goal Planning & Autonomous Agenda](#14-goal-planning--autonomous-agenda)
  - [15. User Relationships & Second Brain Memory](#15-user-relationships--second-brain-memory)
  - [16. Dynamic Mood & Emotion System](#16-dynamic-mood--emotion-system)
  - [17. Safety & Moderation Shield](#17-safety--moderation-shield)
  - [18. Full-Duplex Voice, Energy VAD & Barge-In](#18-full-duplex-voice-energy-vad--barge-in)
  - [19. Multi-Platform Live Chat & EventBus](#19-multi-platform-live-chat-twitch-youtube-live-discord-web--event-driven-core-eventbus)
  - [20. AI-to-AI Collab Protocol (/ws/collab)](#20-ai-to-ai-collab-protocol-wscollab)
  - [21. Community Plugin SDK & Sambung Kata](#21-community-plugin-sdk--sambung-kata)
- [Struktur Direktori Proyek](#-struktur-direktori-proyek)
- [Panduan Instalasi & Menjalankan](#-panduan-instalasi--menjalankan)
- [Panduan Configuration Center (/settings)](#-panduan-configuration-center-settings)
- [Keamanan & Konfigurasi (Security & Config)](#-keamanan--konfigurasi-security--config)
- [Daftar Perintah Chat & Streamer (Commands)](#-daftar-perintah-chat--streamer-commands)
- [REST API & WebSocket Protocol](#-rest-api--websocket-protocol)
- [Panduan Integrasi OBS Studio](#-panduan-integrasi-obs-studio)
- [Pengujian & Jaminan Kualitas (QA Testing)](#-pengujian--jaminan-kualitas-qa-testing)

---

## 🌟 Tentang MaybeAI & Eve Maybe

**MaybeAI** adalah platform kecerdasan buatan modular yang dirancang untuk menggerakkan **Eve Maybe**, seorang AI VTuber otonom. Terinspirasi dari konsep legendaris *Neuro-sama* (karya Vedal987), Eve bukan sekadar chatbot yang berbicara teks, melainkan entitas virtual yang memiliki kepribadian kaya (cerdas, humoris, sedikit sarkas, dan kompetitif), mampu mengamati layar, memainkan game secara mandiri, berinteraksi sosial dengan audiens, menyanyi karaoke, hingga berevolusi karakternya berdasarkan pengalaman nyata selama livestreaming.

Eve terintegrasi secara *full-duplex* dengan browser Web Canvas, VTube Studio (Live2D), Twitch IRC, server Minecraft, dan sistem operasi desktop.

---

## 🏗️ Arsitektur Sistem

```mermaid
flowchart TD
    subgraph Inputs ["Input Layer"]
        Twitch["Twitch IRC / YouTube Live / Discord"]
        WebChat["Web Dashboard Chat (Creator &amp; Audience)"]
        Microphone["Full-Duplex Mic / EnergyVAD &amp; Streaming STT"]
        CollabPeer["AI VTuber Peer (/ws/collab HMAC)"]
        Vision["Screen Capture &amp; Vision OCR"]
        MC_Bridge["Minecraft Server Events"]
    end

    subgraph Core ["MaybeAI Autonomous Orchestrator &amp; EventBus"]
        EventBus["Typed Async EventBus (Pub/Sub &amp; History)"]
        Mod["Safety &amp; Moderation Filter"]
        ConfigMgr["Configuration Manager (Atomic &amp; Hot-Reload)"]
        Brain["Streaming LLM Brain (Gemini / OpenAI / Ollama / Mock)"]
        MoodSys["Dynamic Mood &amp; Emotion System"]
        PersEvo["Personality Evolution (EXP &amp; Leveling)"]
        RelDossier["Semantic Memory Embeddings &amp; Second Brain"]
        GoalPlan["Closed-Loop Autonomous Missions (Executor &amp; Agenda)"]
        CollabMgr["AI Collab Manager (Floor State &amp; Anti-Loop)"]
        PluginSDK["Plugin Registry &amp; Sandboxed SDK (!wc)"]
        Minigames["Interactive Mini-Games Engine"]
        StoryRPG["Dynamic Storytelling &amp; RPG"]
        PerfDir["Karaoke &amp; Performance Director"]
        DesktopComp["Desktop Companion &amp; Permission Gate"]
        MCEngine["Minecraft Dual-Engine &amp; Social AI"]
        ChessEng["Chess Engine &amp; FICS Bridge"]
    end

    subgraph Outputs ["Output &amp; Presentation Layer"]
        TTS["Interruptible Streaming Edge-TTS &amp; Barge-In"]
        OBSOverlay["Dedicated Transparent OBS Overlay (/overlay)"]
        VTS["VTube Studio API (Live2D Model)"]
        WebHUD["Tabbed Web Studio Dashboard (/ &amp; /settings)"]
        DesktopAct["Desktop OS Actions (Media/Apps)"]
        MC_Act["Minecraft Bot Actions (Mineflayer)"]
    end

    Inputs --> Mod
    Mod --> Core
    ConfigMgr <--> Core
    Core --> Outputs
```

---

## 🚀 Katalog Fitur Komprehensif

### 1. Autonomous Brain & Multi-Provider LLM (with Streaming)
- **Multi-Provider Architecture:** Mendukung **Google Gemini** (default: `gemini-3-flash-preview` via `config/settings.json`, otomatis *fallback* ke Mock Mode jika `GEMINI_API_KEY` belum diisi), **OpenAI** (GPT-4o / GPT-4o-mini), **Local Ollama** (Llama 3.2 / Mistral / DeepSeek), serta **Mock Mode** bawaan (bisa langsung dijalankan tanpa internet dan tanpa API key). Provider dapat di-override via `MAYBEAI_LLM_PROVIDER` atau flag `--provider`.
- **Streaming Brain-to-TTS (`llm.streaming_enabled: true`):** `Brain.generate_response_stream()` mengalirkan token secara real-time melalui Gemini SSE (`streamGenerateContent?alt=sse`), OpenAI SSE (`stream: true`), Ollama NDJSON, maupun Mock chunking sehingga Eve mulai berbicara segera setelah kalimat pertama selesai dibentuk.
- **Fallback Otomatis:** Jika API provider utama tidak memiliki API key, kehabisan kuota, atau mengalami timeout, sistem otomatis beralih ke respons persona cadangan (`mock`) tanpa memutus siaran.
- **Dynamic Emotion & Action Tags:** Brain secara cerdas membubuhkan tag ekspresi (seperti `[emotion: neutral]`, `[emotion: happy]`, `[emotion: smug]`, `[emotion: angry]`, `[emotion: blush]`, `[emotion: surprised]`, `[emotion: confused]`) dan tag aksi (`[action: giggle]`, `[action: sigh]`, `[action: wink]`) yang diparsing oleh `ActionParser` (`core/actions.py`) untuk menggerakkan ekspresi avatar secara presisi.
- **Token & Temperature Hot-Reload:** Parameter kreativitas (*temperature*) dan panjang respons (*max_tokens*) dapat diubah langsung dari Configuration Center tanpa me-restart aplikasi.

### 2. Pipelined Streaming Edge-TTS & Dynamic Lip-Sync
- **Pipelined Sentence-Chunked Streaming (`SentenceChunker` + `TTSEngine.speak_stream()`):** Memecah aliran teks LLM per kalimat (`.`, `!`, `?`, `\n`, `~`) sambil menjaga tag `[emotion:]`/`[action:]`, singkatan, dan angka desimal tetap utuh. Kalimat $N+1$ disintesis secara konkuren saat kalimat $N$ sedang diputar, dengan pembersihan file sementara `speech_*.mp3` yang terjamin.
- **Sintesis Suara Natural:** Memanfaatkan teknologi Edge-TTS berkecepatan tinggi dengan berbagai pilihan suara jernih (`en-US-AnaNeural`, `id-ID-GadisNeural`, `ja-JP-NanamiNeural`, dll).
- **Real-Time Lip-Sync Calculation:** Menghitung amplitudo vokal dan pergerakan fonem mulut secara proporsional (`mouth_open` 0.0 – 1.0) untuk menganimasikan bibir avatar sinkron dengan audio.
- **Graceful Mouth Flapping Fallback:** Apabila TTS dinonaktifkan oleh pengguna, avatar tetap menggerakkan bibirnya secara halus saat membalas teks, mencegah avatar terlihat kaku atau *freeze*.
- **Live Voice Modulation:** Pengaturan kecepatan bicara (*rate*), tinggi nada (*pitch*), dan volume suara dapat disesuaikan per milidetik.

### 3. Dual Avatar Rendering, Dedicated OBS Overlay & Tabbed Studio UI
- **Dedicated Transparent OBS Overlay (`/overlay`):** Halaman khusus tanpa kontrol studio di `http://localhost:7860/overlay` (`web/overlay.html`, `overlay.css`, `overlay.js`) dengan latar belakang transparan, Virtual Avatar Canvas (`#avatarCanvas`), subtitle melayang (*glassmorphic*), dan banner notifikasi Donasi/SuperChat real-time—siap pakai sebagai *Browser Source* OBS Studio.
- **Modular 4-Tab Studio Workspace (`/`):** Dashboard utama (`http://localhost:7860`) tertata dalam 4 tab workspace (*sticky nav* dengan persistensi `localStorage`): **🎤 Live Stage**, **🎮 Gaming**, **🎲 RPG & Mini-Games**, dan **🧠 Brain & Memory**, dilengkapi tombol pintas **📺 OBS Overlay**.
- **VTube Studio (VTS) WebSocket API Integration:** Menghubungkan Eve ke model Live2D profesional di VTube Studio (`ws://localhost:8001`). Jika VTS belum berjalan, sistem otomatis masuk ke mode *Standby/Virtual* tanpa menyebabkan error, dan menyediakan tombol *probe reconnect* sekali klik.

### 4. Centralized Cyberpunk Configuration Center
- **Dedicated GUI URL:** Halaman khusus di `http://localhost:7860/settings` dengan tema estetika Cyberpunk / Futuristic AI (aksen neon, glow cards, toggle switch, slider nilai interaktif).
- **19 Kategori Pengaturan Lengkap:** Meliputi General, Brain (`streaming_enabled`), Personality, Memory (`embedding_provider`), Mood, Voice/TTS (`interruptible`), Speech-to-Text (`stt` + `vad_enabled`, `vad_energy_threshold`, `barge_in_enabled`), Avatar/VTS, Karaoke, Twitch, YouTube Live (`youtube`), Discord (`discord`), Moderation, Security (`security`), Minecraft, Autonomous Agent (`closed_loop_missions`, `mission_tick_interval_sec`), **AI Collab Protocol (`collab`)**, **Plugins & SDK (`plugins`)**, dan Performance.
- **Secret Protection:** Token OAuth Twitch (`twitch.oauth_token`), YouTube API Key (`youtube.api_key`), Discord Bot Token (`discord.bot_token`), Creator Access Token (`security.creator_token`), dan Collab HMAC Shared Secret (`collab.shared_secret`) **tidak pernah diekspos dalam bentuk plaintext** via HTTP GET (`"********"` masking) dan tidak akan terhapus jika form disimpan tanpa mengubah token.
- **Atomic Persistence:** Menggunakan mekanisme *temp-write* (`.settings.json.tmp`) dan atomic `os.replace()` untuk mencegah korupsi file saat listrik mati atau crash.
- **Live Hot-Reload:** Perubahan diterapkan seketika ke seluruh modul aktif di runtime tanpa perlu restart server.
- **Interactive Diagnostic Test Runners:** Tombol uji live probe untuk LLM, TTS, VTS, Twitch, Moderator, dan Memory langsung dari browser.

### 5. Dynamic Performance Director & Karaoke Engine
- **Otonomi Konser Musik:** Eve dapat bertindak sebagai penampil profesional yang mengatur penampilannya sendiri: memilih lagu berdasarkan mood, membawakan monolog intro (*MC speech*), mengatur ekspresi per bait lirik, dan memberikan epilog selebrasi setelah bernyanyi.
- **Playback Multi-Track:** Memutar file instrumen BGM otomatis bersamaan dengan vokal ritmik terstruktur, sinkronisasi lirik per baris (*lyric delay*), dan semburan animasi glowstick penonton di layar avatar.
- **Katalog Lagu Kustom:** Mudah menambahkan lagu baru melalui `config/songs.json` dan folder `assets/songs/`.

### 6. Minecraft Dual-Mode Engine & Portable Bridge
- **Zero-Setup Node.js Portable:** MaybeAI menyertakan runtime Node.js portabel internal di Windows; Anda tidak perlu menginstal Node.js secara manual di komputer!
- **Mode Santai (Casual & Social):**
  - Menyapa player saat mendekat.
  - Membalas gerakan *friendly crouch / t-bag* sebagai tanda damai.
  - Berterima kasih saat diberikan hadiah item (seperti Diamond).
  - Melakukan *head-tracking* sosial menatap wajah player terdekat dan mengikutinya (*follow player*).
- **Mode Kompe (Competitive & Speedrun):**
  - Mesin *state machine* speedrun 10 fase (Wood $\rightarrow$ Stone $\rightarrow$ Iron/Bucket $\rightarrow$ Nether Lava Portal $\rightarrow$ Blaze Rods $\rightarrow$ Piglin Trade $\rightarrow$ Eye of Ender $\rightarrow$ Stronghold $\rightarrow$ End Portal $\rightarrow$ Slay Ender Dragon).
  - Dilengkapi split timer live (`⏱️ 00:00`), komentar taktis, dan selebrasi kemenangan.
- **Guard & Combat Mode:** Radius pengawalan base otomatis (`guard_radius: 15.0`) dan mundur darurat saat darah sekarat (`health_retreat_threshold: 6`).

### 7. Multiplayer Social Intelligence
- **Multi-Player Social Cognition:** Eve mampu membedakan siapa yang sedang berbicara di server multiplayer, mengenali peran masing-masing pemain, dan mengingat kontribusi mereka di *Contribution Ledger*.
- **Team & Partnership Formation:** Memilih partner bermain berdasarkan skor reputasi dan kepercayaan (*trust score*), serta bernegosiasi saat terjadi perebutan sumber daya tambang.

### 8. Experience-Based Personality Evolution
- **Sistem Level & EXP Karakter:** Kepribadian Eve berkembang secara organik berdasarkan pengalaman yang dialaminya (EXP didapat dari memenangkan game, dipuji penonton, atau membalas roasting).
- **Evolusi Terkontrol:** Sifat kepribadian (seperti *Competitiveness*, *Friendliness*, *Humor*, dan *Confidence*) beradaptasi secara matematis dan logis tanpa merusak integritas system prompt inti.
- **Second Brain Evolution Sync:** Catatan sejarah perkembangan karakter dicatat secara rapi ke file Markdown `data/second_brain/personality/evolution.md`.

### 9. Visual Perception & Screen Awareness
- **Mata Visual untuk Eve:** Eve dapat "melihat" apa yang sedang terjadi di layar monitor menggunakan integrasi screenshot capture, OCR, computer vision, dan Vision-Language Model (VLM).
- **Komentar Spontan Layar:** Mengenali game yang sedang dimainkan, membaca status HUD game (darah, amunisi, skor), mengetahui saat pemain mengalami kekalahan (*Game Over*), dan mengomentari video YouTube yang sedang ditonton.

### 10. Desktop Companion & Permission Gateway
- **Sistem Izin Berlapis (3-Tier Risk Permission Gate):** Tindakan berisiko tinggi (membuka aplikasi atau mengeksekusi perintah shell) memerlukan izin eksplisit pengguna (*Pending Approval*), sedangkan aksi aman (mengatur volume suara atau media player) dapat langsung dieksekusi.
- **Desktop Companion Capabilities:** Mengontrol lagu (Play/Pause/Next/Volume), meluncurkan aplikasi yang diizinkan (Notepad, Calculator, Browser), membaca notifikasi, dan mengganti scene streaming.

### 11. Interactive Mini-Game Engine
- **Koleksi Game Interaktif bersama Penonton:**
  - 🧠 **Trivia Quiz:** Pertanyaan pengetahuan umum dengan sistem poin.
  - 🔢 **Guess the Number:** Tebak angka rahasia dengan petunjuk lebih tinggi/lebih rendah.
  - 🔤 **Word Association:** Permainan sambung asosiasi kata kreatif.
  - 🧩 **Riddle Challenge:** Teka-teki asah otak.
  - 🤔 **Would You Rather:** Pilihan dilema seru antara dua opsi.
  - 🎵 **Guess the Song:** Tebak lirik atau judul lagu.
- **Twitch Chat Integration:** Penonton di Twitch chat atau Web chat dapat menjawab langsung, mencetak rekor *streak*, dan masuk ke papan peringkat (*Leaderboard*).

### 12. Dynamic Storytelling & Community RPG
- **Petualangan Interaktif Berkelanjutan:** Eve bertindak sebagai Game Master (DM) atau teman petualangan RPG bersama penonton.
- **Community Chat Voting:** Kelanjutan jalan cerita ditentukan oleh voting terbanyak dari pilihan interaktif penonton di live chat.
- **D20 Dice Roll Mechanics:** Sistem lempar dadu keberuntungan untuk menentukan keberhasilan aksi karakter (Critical Success, Normal, Fail, Fumble).
- **Inventory & Story Chronicles:** Inventaris party disimpan dan kronik cerita dicatat ke `data/second_brain/storytelling/campaigns.md`.

### 13. Chess Engine & Streamer Commentary
- **Integrasi Papan Catur FICS/Stockfish:** Eve dapat bermain catur dengan validasi langkah legal, pembacaan notasi FEN/PGN, dan level kesulitan ELO yang dapat diatur dari 800 (pemula) hingga 2000 (ahli).
- **Komentar Catur Cerdas:** Eve mengomentari blunder pemain lawan, memamerkan taktik cerdiknya (*smug banter*), dan memberikan evaluasi posisi pasca-permainan.

### 14. Goal Planning & Closed-Loop Autonomous Missions
- **Closed-Loop Mission Executor (`core/planning/executor.py`):** `AutonomousMissionExecutor` menjalankan siklus otonom berkala (*select goal $\rightarrow$ plan domain action $\rightarrow$ execute $\rightarrow$ evaluate & sync `agenda.md`*) secara langsung untuk 4 domain: **Minecraft** (`santai` / `kompe` / `guard`), **Chess** (`start_game` / `make_bot_move`), **Performance Director** (`perform_song`), dan **Social Outreach**.
- **Failure Replanning (`StrategyReplanner`):** Jika aksi misi gagal atau melempar error, executor otomatis beralih ke `StrategyReplanner` untuk membuat subtugas *Plan B*, menyuarakan adaptasi strategi, dan memperbarui `data/goals/agenda.md`.
- **Human-in-the-Loop Approval Gate:** Bila `autonomous_agent.human_approval_required` diaktifkan, langkah misi akan menunggu persetujuan Creator (`approve` / `reject`) melalui tab **🧠 Brain & Memory** atau REST API `/api/missions/step`.
- **Idle Banter Scheduler:** Jika chat sepi dalam interval tertentu, Eve secara proaktif membuka topik pembicaraan baru atau menceritakan pengalamannya agar stream tetap hidup.

### 15. User Relationships, Semantic Embeddings & Second Brain Memory
- **Multi-Backend Semantic Embeddings (`core/memory/embedding.py`):** Mendukung provider `auto | local | gemini | openai | hash` (otomatis memilih `sentence-transformers`/`fastembed` lokal, Gemini `text-embedding-004`, OpenAI `text-embedding-3-small`, atau *sublinear-TF hash* offline dengan LRU cache dan keamanan *dimension-mismatch* pada `MemoryDatabase` & `MemoryRetriever`).
- **Profil Hubungan Per Penonton (Viewer Dossier):** Eve mengingat siapa saja penontonnya, melacak frekuensi obrolan, skor keakraban (*Familiarity*), tingkat kepercayaan (*Trust*), hubungan rivalitas (*Rivalry*), dan kasih sayang (*Affection*).
- **Shared Inside Jokes:** Mencatat lelucon lokal dan kenangan khusus bersama penonton tertentu ke dalam file Markdown tersinkronisasi di folder `data/second_brain/relationships/`.

### 16. Dynamic Mood & Emotion System
- **5-Dimensi Emosi Real-Time:** *Happiness*, *Annoyance*, *Curiosity*, *Excitement*, dan *Competitiveness*.
- **Decay & Sensitivity Dynamics:** Emosi Eve berubah sesuai situasi (dipuji penonton meningkatkan *Happiness*, di-troll atau kalah game meningkatkan *Annoyance/Competitiveness*) dan secara bertahap mereda kembali ke *baseline* alaminya.

### 17. Safety & Moderation Shield
- **Perlindungan Terhadap Pelanggaran:** Filter kata-kata terlarang (*banned words regex*), pembatasan panjang pesan, deteksi spam beruntun, serta deteksi heuristik untuk mencegah serangan *prompt injection* / *jailbreak*.

### 18. Full-Duplex Voice, Energy VAD & Barge-In
- **Energy VAD & Streaming STT (`core/stt.py`):** Dilengkapi `EnergyVAD` (deteksi RMS PCM16/float32 dengan *onset hysteresis* dan *hangover smoothing*) serta `StreamingSTTSession` yang menyangga fragmen audio mikrofon secara real-time, memicu event `voice_vad_state`, dan mentranskripsi via `faster-whisper`, `openai-whisper`, OpenAI Whisper API, atau fallback offline `mock`.
- **Instant Creator Barge-In (`core/tts.py`, `core/orchestrator.py`):** Saat suara Creator terdeteksi ketika Eve sedang berbicara, `Orchestrator.barge_in()` langsung menghentikan `TTSEngine.speak()` maupun `speak_stream()` via `TTSEngine.stop()`, membatalkan task interaksi aktif tanpa *deadlock* pada `_busy_lock`, membersihkan file `speech_*.mp3`, mereset mulut avatar ke `0.0`, dan memancarkan `voice_barge_in`.
- **Live Web Audio VAD Dock (`web/app.js`):** Panel Creator Voice Dock menampilkan meter energi mikrofon real-time (`#vad-energy-fill`), toggle **Barge-In** (`#chk-barge-in`), serta lencana interupsi (`#barge-in-badge`).

### 19. Multi-Platform Live Chat (Twitch, YouTube Live, Discord, Web) & Event-Driven Core (`EventBus`)
- **Multi-Platform Adapter Registry (`core/platforms/`, `core/chat_receiver.py`):**
  - **Twitch IRC:** Terhubung ke server Twitch IRC port 6667 dengan dukungan token OAuth, anti-spam cooldown, dan mention filter.
  - **YouTube Live (`YouTubeLiveAdapter`):** Polling YouTube Data API v3 (`liveChatMessages`) via `aiohttp`, otomatis memetakan **SuperChat** dan **SuperSticker** menjadi event donasi (`is_donation=True`, `source="youtube"`).
  - **Discord (`DiscordAdapter`):** Polling Discord REST API v10 menggunakan Bot Token & Channel ID (`source="discord"`), memfilter pesan bot, dan terdegradasi aman saat tidak dikonfigurasi.
- **Typed Async EventBus (`core/event_bus.py`):** Menghubungkan `Orchestrator`, `ConversationEngine`, dan WebSocket broadcast melalui pub/sub asinkron dengan dukungan wildcard `*`, isolasi exception per handler, *ring buffer* riwayat event, dan endpoint diagnostik `GET /api/eventbus/stats`.
- **Pemisahan Jalur Komunikasi (Dual Channel Tabs):**
  - **👑 Tab Chat Saya (Creator VIP):** Jalur eksklusif streamer dengan prioritas antrian absolut (`priority_score = 350.0`, melompati antrian penonton umum dan saweran). Dilengkapi dock mikrofon bawaan (Web Speech STT / Whisper) untuk berbicara langsung secara verbal ke Eve.
  - **👥 Tab Stream Chat (Penonton Publik):** Jalur pesan publik (Twitch, YouTube, Discord, & penonton web). Pesan masuk ke antrian kurasi reguler dan dievaluasi berdasarkan relevansi, saweran, atau topik perdebatan.
- **Strict Permission Guardrails:** Perintah krusial sistem (peluncuran aplikasi Desktop Companion `!desktop`, pergantian mode gameplay/server Minecraft `!mc mode/server`, dan reset/pengaturan ELO catur `!chess elo/new`) diproteksi penuh dan hanya dapat dijalankan oleh Creator. Jika penonton mencoba mengeksekusinya, Eve akan menolak dengan nada sarkas khasnya tanpa mengeksekusi aksi fisik pada sistem.

### 20. AI-to-AI Collab Protocol (`/ws/collab`)
- **Signed Wire Envelope (`core/collab/protocol.py`):** `CollabEnvelope` (`protocol_version: "1.0"`) mendukung event `hello`, `turn_utterance`, `turn_yield`, `duet_sync`, `game_move`, `emote_sync`, `ping`, dan `bye` dengan penandatanganan HMAC-SHA256 serta verifikasi constant-time (`hmac.compare_digest`).
- **Turn-Taking Floor & Anti-Loop (`core/collab/manager.py`):** `CollabManager` mengelola *floor state machine* (`idle`, `speaking`, `yielding`, `listening`, `cooldown`), membatasi percakapan beruntun via `max_collab_turns` (default `6`) dan `turn_cooldown_sec` (default `2.5s`) untuk mencegah infinite loop antar-AI, serta menyediakan sinkronisasi duet karaoke (`send_duet_sync`) dan ekspresi (`send_emote_sync`).
- **Studio Controls & Peer WebSocket (`run.py`, `web/index.html`):** Mendukung koneksi outbound ke peer maupun inbound pada `/ws/collab` dengan panel **AI Collab** (`#collabCard`) di tab **🎤 Live Stage**.

### 21. Community Plugin SDK & Sambung Kata
- **Sandboxed Plugin SDK (`core/plugins/sdk.py`, `core/plugins/registry.py`):** Menyediakan `PluginManifest`, `PluginContext` (akses aman ke `EventBus`, `speak`, `broadcast`, dan state per-plugin tanpa membocorkan internal `Orchestrator`/`ConfigManager`), kelas dasar `MaybeAIPlugin`, serta dekorator `@plugin_command` dan `@plugin_event`.
- **Lifecycle, Timeout & Isolasi Error:** `PluginRegistry` menemukan plugin bawaan (`core/plugins/`) dan eksternal (`plugins/*.py`), mendukung `enable` / `disable` / `reload` runtime tanpa restart, menegakkan `creator_only_commands`, dan membungkus setiap eksekusi hook dengan `asyncio.wait_for(..., timeout=hook_timeout_sec)` serta isolasi exception.
- **Built-in Word Chain (`!sambungkata` / `!wc`):** Plugin komunitas interaktif (`core/plugins/word_chain.py`) di mana penonton dan creator bermain sambung huruf terakhir (`!wc start`, `!wc <kata>`, `!wc score`, `!wc stop`) lengkap dengan papan skor dan pencegahan pengulangan kata.

---

## 📁 Struktur Direktori Proyek

```
MaybeAI/
├── assets/
│   └── songs/
│       └── digital_world_bgm.wav  # Instrumen BGM karaoke
├── config/
│   ├── settings.json              # Konfigurasi master (General, LLM, TTS, STT, Security, dll)
│   ├── character.json             # Persona, latar belakang, lore, & gaya bicara Eve
│   ├── filter_words.json          # Blacklist kata & aturan moderasi regex
│   ├── songs.json                 # Katalog lagu karaoke, lirik, & delay timing
│   └── minecraft_servers.json     # Daftar server Minecraft tersimpan
├── core/
│   ├── actions.py                 # Parser tag [emotion: x] dan [action: x]
│   ├── brain.py                   # Otak LLM Streaming (Gemini, OpenAI, Ollama, Mock)
│   ├── event_bus.py               # Typed Async Pub/Sub EventBus & Event History
│   ├── tts.py                     # Pipelined Streaming Edge-TTS (SentenceChunker) & Lip-Sync
│   ├── vts_client.py              # Client WebSocket VTube Studio API
│   ├── chat_receiver.py           # Ingestion Twitch IRC, Web Chat, & Multi-Platform Registry
│   ├── collab/                    # AI-to-AI Collab Protocol (CollabEnvelope HMAC & CollabManager)
│   ├── platforms/                 # Adapter Live Chat (YouTube Live + SuperChat, Discord)
│   ├── plugins/                   # Community Plugin SDK, PluginRegistry, & WordChainPlugin (!wc)
│   ├── moderator.py               # Filter keamanan, spam, & prompt injection
│   ├── singer.py                  # Player BGM Karaoke & sinkronisasi lirik
│   ├── stt.py                     # Full-Duplex EnergyVAD, StreamingSTTSession, & Whisper STT
│   ├── orchestrator.py            # Event loop pusat, barge-in, missions, collab, plugins, & EventBus
│   ├── config_manager.py          # Centralized Config Engine, Atomic Save, & Diagnostics
│   ├── chess/                     # Modul logika catur, ELO scaling, & komentar
│   ├── conversation/              # Manajemen konteks percakapan & memory window
│   ├── desktop/                   # Desktop Companion, App launcher, & Permission gate
│   ├── memory/                    # Semantic Embeddings, Episodic memory, & Second Brain sync
│   ├── minecraft/                 # Minecraft engine, Casual & Speedrun agents, Controller
│   │   └── multiplayer/           # Multiplayer Social Intelligence & Contribution ledger
│   ├── minigames/                 # Interactive Mini-Games Engine (Trivia, Riddle, dll)
│   ├── mood/                      # Dynamic Mood Engine & Emotional Axes
│   ├── performance/               # Dynamic Performance Director & Setlist manager
│   ├── personality/               # Experience-Based Personality Evolution Engine
│   ├── planning/                  # Goal Planning, StrategyReplanner, & AutonomousMissionExecutor
│   ├── relationship/              # User Dossiers & Social Affinity Matrix
│   ├── storytelling/              # Dynamic Storytelling & Community RPG Engine
│   └── vision/                    # Screen Capture, Vision OCR, & VLM Engine
├── data/
│   ├── memory.db                  # Database SQLite memori percakapan
│   ├── desktop/permissions.json   # Log izin dan riwayat aksi sistem desktop
│   ├── goals/agenda.md            # Markdown agenda misi streaming otonom
│   ├── minigames/leaderboard.json # Papan skor mini-game
│   ├── personality/evolution.json # Data level, EXP, & sifat kepribadian
│   ├── relationships/             # JSON data relasi user
│   └── second_brain/              # Direktori catatan Markdown otomatis (Dossier, Setlist, dll)
├── minecraft/
│   ├── bot.js                     # Entrypoint bot Mineflayer
│   ├── casual.js                  # Modul perilaku casual & sosial Minecraft
│   ├── guard.js                   # Modul bodyguard & proteksi player
│   ├── speedrun.js                # State machine speedrun 10 fase
│   ├── config.json                # Konfigurasi koneksi bot Mineflayer
│   ├── package.json               # Dependensi Node.js Mineflayer
│   ├── node/                      # Runtime Node.js portabel (Windows)
│   └── node_modules/              # Paket Node.js terbundel
├── web/
│   ├── index.html                 # Tabbed Web Studio Dashboard & 2D Canvas Avatar
│   ├── style.css                  # Styling Cyberpunk dashboard, workspace tabs, & HUD
│   ├── app.js                     # Logika Web client, workspace tabs, rendering avatar, & WebSocket
│   ├── overlay.html               # Dedicated Transparent OBS Browser Source Overlay (/overlay)
│   ├── overlay.css                # Styling transparan OBS, floating subtitles, & donation alert
│   ├── overlay.js                 # Renderer avatar & subtitle real-time untuk OBS Overlay
│   ├── settings.html              # Antarmuka Cyberpunk Configuration Center
│   ├── settings.css               # Styling khusus Configuration Center
│   └── settings.js                # Form engine, secret protection, & test runner
├── tests/
│   ├── __init__.py                # Menetapkan MAYBEAI_LLM_PROVIDER=mock saat test berjalan
│   ├── test_guard_runner.js       # Uji unit guard mode Minecraft (Node.js)
│   └── test_*.py                  # 29 modul pengujian unit & integrasi Python (283 tests)
├── pyproject.toml                 # Metadata proyek & extras opsional ([stt-local], [embeddings-local], [dev])
├── run.py                         # FastAPI Web Server & Application Launcher
├── requirements.txt               # Daftar dependensi Python
├── start.bat                      # One-click Windows launcher (.venv, pip install, .env, run.py)
├── LICENSE                        # Lisensi MIT (EvanH 2026)
├── push.bat                       # Skrip utilitas push Git (Windows)
├── .env.example                   # Template variabel lingkungan (.env)
└── .env                           # Konfigurasi kunci rahasia lokal (tidak di-commit)
```

---

## 💻 Panduan Instalasi & Menjalankan

### 1. Prasyarat Sistem
- **Sistem Operasi:** Windows 10 / 11 (64-bit).
- **Python:** Python versi **3.11** atau **3.12**.
- **Koneksi Internet:** Diperlukan untuk mendownload library dan menggunakan provider online (Gemini/OpenAI/Edge-TTS).

### 2. Setup Virtual Environment & Dependensi
Buka terminal PowerShell pada direktori proyek:

```powershell
# Buat virtual environment jika belum ada
python -m venv .venv

# Aktifkan virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip dan install dependensi
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Konfigurasi File Lingkungan (`.env`)
Salin `.env.example` menjadi `.env` di folder root lalu isi sesuai kebutuhan:

```env
# Override provider LLM (opsional: gemini | openai | ollama | mock)
MAYBEAI_LLM_PROVIDER=

# Google Gemini (Default provider di settings.json: gemini-3-flash-preview)
GEMINI_API_KEY=AIzaSy...

# OpenAI (Opsional)
OPENAI_API_KEY=sk-...

# Security & Creator Access (Opsional)
MAYBEAI_CREATOR_TOKEN=

# Twitch IRC (Opsional jika ingin membaca chat Twitch)
TWITCH_OAUTH_TOKEN=oauth:...
TWITCH_CHANNEL=nama_channel_kamu
TWITCH_BOT_NICK=EveMaybe

# YouTube Live Chat & Discord (Opsional)
YOUTUBE_API_KEY=
DISCORD_BOT_TOKEN=
MAYBEAI_EMBEDDING_PROVIDER=

# AI Collab Protocol (/ws/collab, Opsional)
MAYBEAI_COLLAB_SECRET=
```

### 4. Menjalankan Aplikasi

#### A. Mode Bawaan (Default `gemini` dengan Fallback Otomatis ke Mock Mode)
Secara default, `config/settings.json` menggunakan provider `gemini` (`gemini-3-flash-preview`). Jika `GEMINI_API_KEY` belum diatur, sistem otomatis *fallback* ke Mock Mode tanpa API key:
```powershell
.\.venv\Scripts\python.exe run.py
```
Untuk memaksa mode Mock murni secara eksplisit:
```powershell
.\.venv\Scripts\python.exe run.py --provider mock
```
Akses di browser Anda: 👉 **`http://localhost:7860`**

#### B. Menggunakan Google Gemini
```powershell
.\.venv\Scripts\python.exe run.py --provider gemini
```

#### C. Menggunakan OpenAI GPT-4o
```powershell
.\.venv\Scripts\python.exe run.py --provider openai
```

#### D. Menggunakan Local Ollama
Pastikan aplikasi [Ollama](https://ollama.com/) sudah aktif di komputer Anda:
```powershell
ollama run llama3.2
.\.venv\Scripts\python.exe run.py --provider ollama
```

---

## ⚙️ Panduan Configuration Center (`/settings`)

Akses halaman kontrol konfigurasi di: 👉 **`http://localhost:7860/settings`**  
*(Atau klik tombol **⚙️ Configuration Center** di bagian atas Web Dashboard utama).*

### Fitur Utama Configuration Center:
1. **Navigasi Sidebar Responsif:** 19 kategori pengaturan (termasuk `stt`, `security`, `youtube`, `discord`, `collab`, dan `plugins`) plus tampilan *System Diagnostics* dengan ikon khas cyberpunk.
2. **Pencarian Real-Time (*Search Box*):** Menemukan pengaturan apapun hanya dengan mengetikkan kata kunci (contoh: *temperature*, *streaming*, *embedding*, *youtube*, *discord*, *token*, *stt*, *vad*, *barge*, *collab*, *plugins*).
3. **Perlindungan Token & Masking:** Secret sensitif seperti `twitch.oauth_token`, `youtube.api_key`, `discord.bot_token`, `security.creator_token`, dan `collab.shared_secret` disamarkan menjadi `********` dan dipertahankan saat penyimpanan atomik bila tidak diubah.
4. **Live Slider & Toggle:** Setiap slider menampilkan nilai numerik secara *real-time*, ditambah editor list interaktif untuk `security.allowed_origins` dan `plugins.enabled_plugins`.
5. **Indikator Unsaved Changes:** Memunculkan banner konfirmasi di bawah layar saat terdapat perubahan yang belum disimpan.
6. **Shortcut Keyboard:** Tekan **`Ctrl + S`** di halaman settings untuk menyimpan secara instan.
7. **Penyimpanan Atomik & Hot-Reload:** Perubahan pada LLM, TTS, VTS, Moderator, Karaoke, STT/VAD, Security, Autonomous Missions, Collab, dan Plugins langsung diterapkan seketika tanpa perlu restart proses.
8. **Interactive Feature Test Runner:** Tekan tombol **Run Test / Probe** di tiap kategori untuk menguji fungsionalitas modul secara langsung.

---

## 🔐 Keamanan & Konfigurasi (Security & Config)

MaybeAI menerapkan kontrol akses ketat untuk melindungi endpoint kontrol dan eksekusi lokal:

- **Validasi Origin (`Origin` Check):**
  - Seluruh endpoint mutasi `/api/*` (`PUT`, `POST`, `PATCH`, `DELETE`) dan koneksi WebSocket `/ws` memeriksa header `Origin` jika disertakan oleh browser/klien.
  - Secara default hanya origin localhost (`http://127.0.0.1:<port>`, `http://localhost:<port>`, `http://[::1]:<port>`, atau `https://`) serta entri yang didaftarkan di `security.allowed_origins` (`config/settings.json` / `/settings`) yang diizinkan.
  - Origin asing ditolak dengan **HTTP `403`** pada `/api/*` dan penutupan WebSocket kode **`1008`** pada `/ws`.
- **Otentikasi Creator Token (`?token=` & `MAYBEAI_CREATOR_TOKEN`):**
  - Klien WebSocket tidak lagi dipercaya berdasarkan `is_creator` dari payload JSON atau nama user.
  - Hak Creator hanya diberikan jika koneksi berasal dari alamat loopback (`127.0.0.1`, `::1`, `localhost`, `::ffff:127.0.0.1`).
  - Jika token dikonfigurasi melalui environment variable `MAYBEAI_CREATOR_TOKEN` (prioritas utama) atau `security.creator_token` di `config/settings.json`, klien wajib menyertakan `?token=<token>` saat membuka `/ws` (diverifikasi menggunakan `secrets.compare_digest`). Tanpa token yang valid, `is_creator` dipaksa `False` dan source `"creator"`/`"mic"` diturunkan menjadi `"web"`.
  - Di Web Dashboard (`web/app.js`), token dibaca otomatis dari parameter URL `?token=` atau `localStorage.maybeai_creator_token` lalu dilampirkan ke URL WebSocket `/ws`.
  - Jika tidak ada token yang dikonfigurasi, klien loopback tetap mendapatkan akses Creator secara default agar dashboard lokal langsung berfungsi.
- **Override Provider LLM (`MAYBEAI_LLM_PROVIDER`):**
  - Menetapkan `MAYBEAI_LLM_PROVIDER` (misal `mock`, `gemini`, `openai`, `ollama`) akan menimpa `llm.provider` dari `config/settings.json` secara langsung (sangat berguna untuk pengujian otomatis maupun isolasi offline).
- **Kategori Baru di `/settings` (`stt`, `security`, `collab`, `plugins`):**
  - **`stt` (Speech-to-Text):** Mengatur `stt.enabled`, `stt.model`, `stt.device`, `stt.vad_enabled`, `stt.vad_energy_threshold`, dan `stt.barge_in_enabled`.
  - **`security` (Security & Access):** Mengatur `security.creator_token` (disamarkan sebagai `********`) dan daftar `security.allowed_origins`.
  - **`collab` (AI Collab Protocol):** Mengatur `collab.enabled`, `collab.peer_name`, `collab.peer_ws_url`, `collab.shared_secret` (disamarkan sebagai `********`, override env `MAYBEAI_COLLAB_SECRET`), `collab.max_collab_turns`, dan `collab.turn_cooldown_sec`.
  - **`plugins` (Plugins & SDK):** Mengatur `plugins.enabled`, `plugins.plugins_dir`, `plugins.enabled_plugins`, dan `plugins.hook_timeout_sec`.
- **Otentikasi `/ws/collab` & Aksi Creator-Only `/ws`:**
  - Endpoint peer `/ws/collab` memverifikasi `MAYBEAI_COLLAB_SECRET` / `collab.shared_secret` menggunakan `hmac.compare_digest` (atau mewajibkan alamat loopback bila secret belum diset), serta memvalidasi tanda tangan HMAC-SHA256 pada `CollabEnvelope`.
  - Event `/ws` sensitif (`barge_in`, `voice_audio_chunk`, `mission_action`, serta mutasi `collab_action` & `plugin_action`) ditolak dengan `{"type": "error", "data": {"code": "forbidden"}}` jika pengirim bukan Creator terotorisasi.
- **Eksekusi Desktop Companion Aman:** `DesktopController` meluncurkan aplikasi hanya dari *allow-list* terverifikasi tanpa `shell=True` dan menolak input yang mengandung metakarakter shell.

---

## 🎮 Daftar Perintah Chat & Streamer (Commands)

Anda dapat mengetik perintah ini di **Interactive Web Chat** atau di **Twitch Live Chat** (aksi UI lanjutan untuk Mini-Games, Story RPG, dan Performance Director juga tersedia langsung melalui panel dashboard / REST API / WebSocket):

| Kategori | Perintah / Contoh Chat | Deskripsi Aksi |
|---|---|---|
| **Karaoke & Panggung** | `!sing` / `!sing digital_world` | Meminta Eve menyanyikan lagu (opsional dengan `song_id`, misal `digital_world`) lengkap dengan BGM. |
| | *"Eve coba nyanyi dong"* | Perintah natural untuk memicu penampilan karaoke. |
| | `!glowstick`, `!cheer`, `!clap`, `!encore` | Memberikan sorakan audiens / glowstick / permintaan encore selama penampilan berlangsung. |
| **Improv & Interaksi** | `!improv` | Memicu monolog spontan atau komentar *shower thought* Eve ke chat. |
| | `!roleplay <peran>` / `!roleplay stop` | Mengaktifkan atau menghentikan mode roleplay karakter tertentu. |
| | `!opinion` / `!hottake <topik>` | Meminta opini tegas atau *hot take* khas Eve. |
| | `!roast` | Meminta Eve me-roast pengirim pesan secara bercanda. |
| | `!story [tema]` | Memicu respons cerita/dongeng personal dan menyimpan catatan cerita ke memori episodik. |
| **Minecraft** | `!mc mode santai` *(Creator-only)* | Mengubah mode Minecraft ke mode sosial interaktif. |
| | `!mc mode kompe` *(Creator-only)* | Memulai speedrun Minecraft dari fase 1. |
| | `!mc next` *(Creator-only)* | Memajukan fase speedrun ke milestone berikutnya. |
| | `!mc guard <player>` | Meminta Eve menjaga/mengawal pemain tertentu. |
| | `!mc follow` / `!mc stop` / `!mc jump` / `!mc crouch` / `!mc dance` / `!mc gift` | Mengontrol aksi bot Minecraft di server. |
| **Catur** | `!chess new [white\|black]` / `!catur new` *(Creator-only)* | Memulai permainan catur baru melawan Eve. |
| | `!chess elo <800-2000>` / `!catur elo <angka>` *(Creator-only)* | Mengatur level ELO engine catur Eve. |
| | `!chess move <langkah>` / `!catur move <langkah>` | Mengirim langkah catur dalam format UCI/SAN (contoh: `e2e4`). |
| | `!chess resign` / `!catur resign` *(Creator-only)* | Mengakhiri/menyerah pada permainan catur aktif. |
| **Mini-Games** | `!A` / `!B` | Memilih opsi saat ronde *Would You Rather* aktif (untuk game lain seperti Trivia, Riddle, Tebak Angka, Asosiasi Kata, dan Tebak Lagu, cukup ketik jawaban langsung di chat; start/stop via UI atau REST API). |
| **Story RPG** | `!1`, `!2`, `!3` | Melakukan voting pilihan jalur cerita saat kampanye RPG aktif (dimulai via UI atau REST API). |
| | `!action <tindakan>` / `!aksi <tindakan>` | Mengajukan aksi *freeform* komunitas dalam cerita RPG aktif. |
| | `!roll` / `!d20` / `!dadu` | Melakukan lempar dadu D20 saat sesi RPG aktif. |
| **Desktop** *(Creator-only)* | `!desktop` | Menampilkan status Desktop Companion dan volume saat ini. |
| | `!desktop volume <0-100>` / `up` / `down` / `mute` | Mengatur volume audio atau mute sistem. |
| | `!desktop play` / `!desktop pause` / `!desktop next` | Mengontrol media player komputer. |
| | `!desktop app <nama>` | Meminta izin meluncurkan aplikasi yang ada di allow-list (misal `notepad.exe`). |
| | `!desktop notif` | Membaca ringkasan notifikasi desktop sesuai kebijakan izin. |
| **Plugin Sambung Kata** | `!sambungkata start [kata]` / `!wc start` | Memulai ronde baru game komunitas Sambung Kata (Indonesia & English). |
| | `!sambungkata <kata>` / `!wc <kata>` | Menyambung kata berikutnya sesuai huruf terakhir kata aktif. |
| | `!wc join` / `!wc score` / `!wc stop` | Bergabung ke ronde, melihat papan skor, atau mengakhiri ronde Sambung Kata. |

---

## 🌐 REST API & WebSocket Protocol

Aplikasi menyediakan REST API dan WebSocket server terpadu pada `run.py`:

### REST Endpoints
- **Web UI:**
  - `GET /`: Halaman utama Tabbed Web Studio Dashboard & Virtual Avatar.
  - `GET /overlay`: Halaman Dedicated Transparent OBS Browser Source Overlay (Avatar, Subtitles, Donation Alerts).
  - `GET /settings`: Halaman Cyberpunk Configuration Center.
- **Configuration, EventBus, Platforms & Diagnostics:**
  - `GET /api/eventbus/stats`: Statistik subscriber, total event terpublikasi, error handler, dan riwayat EventBus.
  - `GET /api/platforms/status`: Status koneksi live seluruh platform chat (Twitch IRC, YouTube Live, Discord).
  - `GET /api/config`: Mengambil data konfigurasi publik (secret dimasking sebagai `********`).
  - `GET /api/config/schema`: Metadata skema konfigurasi (tipe, range, label).
  - `PUT /api/config`: Menyimpan konfigurasi secara atomik dan mengeksekusi hot-reload.
  - `POST /api/config/validate`: Memvalidasi payload konfigurasi.
  - `POST /api/config/reset`: Mereset pengaturan ke default.
  - `POST /api/config/test/{feature}`: Menjalankan probe diagnostik fitur (`llm`, `tts`, `vts`, `twitch`, `moderator`, `memory`).
  - `GET /api/system/diagnostics`: Mengambil laporan diagnostik kesehatan seluruh subsistem.
  - `GET /api/status`: Informasi status umum orchestrator.
- **Memory, Mood, Goals, & Relationships:**
  - `GET /api/memory/stats`: Statistik memori episodik & Second Brain.
  - `GET /api/memory/search`: Pencarian memori episodik (`q`, `user`, `limit`).
  - `GET /api/memory/journal`: Mengambil konten jurnal Markdown terbaru.
  - `GET /api/memory/recent`: Mengambil daftar memori episodik terbaru (`limit`).
  - `GET /api/mood`: Status dimensi mood Eve saat ini.
  - `GET /api/goals`: Status misi & subtask autonomous goal planning.
  - `GET /api/goals/agenda`: Konten Markdown `data/goals/agenda.md`.
  - `GET /api/relationships`: Status seluruh relasi penonton.
  - `GET /api/relationships/{username}`: Profil relasi untuk penonton tertentu.
- **Vision, Minecraft, & Desktop:**
  - `GET /api/vision/state`: Status modul visual perception.
  - `POST /api/vision/perceive`: Memicu pemindaian layar on-demand (`simulated_scene` opsional).
  - `GET /api/minecraft/multiplayer`: Status social intelligence multiplayer Minecraft.
  - `GET /api/desktop/state`: Status Desktop Companion & antrean izin.
- **Mini-Games, Storytelling RPG, Performance, & Personality:**
  - `GET /api/minigames/state`: Status mini-game aktif & leaderboard.
  - `POST /api/minigames/start`: Memulai sesi mini-game (`game_type`, `total_rounds`).
  - `POST /api/minigames/stop`: Menghentikan sesi mini-game aktif.
  - `GET /api/storytelling/state`: Status kampanye Storytelling RPG.
  - `POST /api/storytelling/start`: Memulai kampanye cerita RPG (`preset`, `genre`, `eve_role`, dll).
  - `POST /api/storytelling/advance`: Melanjutkan adegan cerita berdasarkan pilihan/narasi.
  - `POST /api/storytelling/roll`: Melempar dadu D20 pada sesi RPG aktif.
  - `GET /api/performance/state`: Status Performance Director & setlist.
  - `POST /api/performance/plan`: Menyusun setlist konser.
  - `POST /api/performance/start`: Memulai penampilan lagu (`song_id`, `dedication_user`).
  - `POST /api/performance/cheer`: Mencatat sorakan/glowstick audiens.
  - `GET /api/personality/state`: Status evolusi kepribadian, level, & EXP Eve.
  - `POST /api/personality/experience`: Mencatat event pengalaman kepribadian.
  - `POST /api/personality/reset`: Mereset profil evolusi kepribadian ke default.
- **Full-Duplex Voice, Autonomous Missions, AI Collab & Plugins:**
  - `GET /api/voice/status`: Status `stt`, `voice_session` (EnergyVAD & streaming buffer), `tts` (`is_speaking`, `interruptible`), `barge_in_count`, dan `busy`.
  - `GET /api/missions/status`: Status `AutonomousMissionExecutor` (`running`, `paused`, `human_approval_required`, `pending_approval`, `active_goal_title`, `history`).
  - `POST /api/missions/step`: Menjalankan satu langkah misi tertutup (`step`), atau menyetujui/menolak antrean approval (`approve` / `reject`).
  - `POST /api/missions/toggle`: Menyalakan, menjeda, atau melanjutkan background loop misi otonom.
  - `GET /api/collab/status`: Status sesi AI-to-AI Collab (`floor_state`, `turn_count`, `max_collab_turns`, `turns_exhausted`, `secret_configured`, `recent_messages`).
  - `POST /api/collab/action`: Aksi kolaborasi (`connect`, `disconnect`, `initiate`, `send_utterance`, `duet_sync`, `emote_sync`, `reset_turns`, `status`).
  - `GET /api/plugins`: Daftar plugin terdaftar, manifest command/event, status `enabled`/`loaded`, dan statistik error.
  - `POST /api/plugins/action`: Aksi lifecycle plugin (`enable`, `disable`, `reload`, `list`).

### WebSocket Events (`/ws` & `/ws/collab`)
- **Client $\rightarrow$ Server (`/ws`):**
  - `user_message`: `{"type": "user_message", "user": "Admin", "text": "Halo Eve!", "source": "web"}`
  - `donation`: `{"type": "donation", "user": "Supporter", "text": "...", "amount": "$5.00", "currency": "USD"}`
  - `bulk_chat`: `{"type": "bulk_chat", "messages": [{"user": "...", "text": "..."}]}`
  - `set_llm_provider` / `trigger_improv`: Pengaturan cepat LLM provider atau pemicu improv spontan.
  - `barge_in` / `voice_audio_chunk` *(Creator-only)*: Menginterupsi ucapan aktif Eve atau mengirim potongan audio PCM16 (`audio_b64`) ke `EnergyVAD` & `StreamingSTTSession`.
  - `mission_action` *(Creator-only)*: Mengontrol loop misi (`step`, `approve`, `reject`, `toggle`, `start`, `pause`, `status`).
  - `collab_action` & `plugin_action` *(mutasi Creator-only)*: Mengontrol sesi kolaborasi AI dan lifecycle plugin.
  - `*_action`: Event aksi subsistem (`minecraft_action`, `chess_action`, `memory_action`, `mood_action`, `goal_action`, `relationship_action`, `vision_action`, `multiplayer_action`, `desktop_action`, `minigame_action`, `story_action`, `performance_action`, `personality_action`, `config_action`).
- **Server $\rightarrow$ Client (`/ws`):**
  - `ai_chunk`: `{"type": "ai_chunk", "data": {"user": "Eve", "chunk": "...", "emotion": "happy"}}` (potongan kalimat streaming real-time).
  - `ai_response`: `{"type": "ai_response", "data": {"user": "Eve", "raw": "...", "speech": "...", "emotions": ["happy"], "actions": ["wink"], "streamed": true}}`
  - `avatar_state` & `avatar_movement`: `{"type": "avatar_state", "data": {"mouth_open": 0.85, "emotion": "smug"}}` serta gerakan panggung (`movement`, `action`, `lighting`).
  - `voice_barge_in`, `voice_vad_state`, `voice_chunk_ack`, `stt_final`: Telemetri VAD, penghentian barge-in, ack chunk audio, dan transkripsi STT final.
  - `mission_status`, `mission_step`, `collab_state`, `collab_message`, `plugin_event`: Pembaruan real-time misi otonom, floor kolaborasi AI, dan event plugin.
  - `chat_received`, `donation_received`, & `platform_status`: Broadcast pesan chat masuk, notifikasi donasi/SuperChat, dan status adapter multi-platform.
  - `song_started`, `lyric_line`, `song_ended`, `audience_cheer`: Event sinkronisasi karaoke & sorakan penonton.
  - `*_state` / `*_updated` & hasil query: `minecraft_state`, `chess_state`, `conversation_state`, `llm_provider_changed`, `memory_updated`, `memory_search_results`, `memory_journal_data`, `memory_recent_data`, `memory_user_profile_data`, `mood_updated`, `goal_updated`, `goal_completed`, `strategy_adapted`, `relationship_updated`, `vision_updated`, `multiplayer_updated`, `desktop_updated`, `minigame_updated`, `story_updated`, `performance_updated`, `personality_updated`, `system_diagnostics`, `config_saved`, `configuration_updated`, `feature_test_result`.
- **Peer-to-Peer AI Collab WebSocket (`/ws/collab`):**
  - Pertukaran frame `CollabEnvelope` JSON bertanda tangan HMAC-SHA256 (`hello`, `turn_utterance`, `turn_yield`, `duet_sync`, `game_move`, `emote_sync`, `ping`, `bye`), diamankan via `?secret=` / `x-collab-secret` / `Authorization: Bearer` (atau loopback bila secret kosong).

---

## 🎥 Panduan Integrasi OBS Studio

1. **Menampilkan Avatar Transparan di Layar Live Stream (`/overlay`):**
   - Di OBS Studio, klik tombol `+` pada panel **Sources**, pilih **Browser**.
   - Beri nama (misal: *Eve OBS Overlay*), klik **OK**.
   - Masukkan URL: `http://localhost:7860/overlay` *(halaman khusus berlatar transparan tanpa kontrol studio, lengkap dengan Canvas Avatar, floating subtitles, dan banner Donasi/SuperChat)*.
   - Atur resolusi: **Width:** `520`, **Height:** `620` (atau ukuran kanvas OBS pilihan Anda).
   - Centang opsi **"Shutdown source when not visible"** dan **"Control audio via OBS"** (jika ingin output audio browser masuk ke audio mixer OBS).
2. **Koneksi Multi-Platform Live Chat (Twitch, YouTube Live, Discord):**
   - Buka `/settings` di browser, masuk ke kategori **Twitch**, **YouTube Live**, atau **Discord**.
   - Aktifkan toggle, masukkan kredensial/ID channel Anda (disimpan terenkripsi/dimasking sebagai `********`), lalu klik **Save Changes**. Eve akan langsung mendengarkan dan merespons obrolan penonton dari seluruh platform aktif!

---

## 🧪 Pengujian & Jaminan Kualitas (QA Testing)

MaybeAI memiliki rangkaian unit dan integration test yang ketat (secara otomatis menjalankan LLM dalam mode `mock` melalui `tests/__init__.py`) untuk memastikan stabilitas produksi tanpa regresi:

```powershell
# Jalankan seluruh test suite Python otomatis
.\.venv\Scripts\python.exe -m unittest discover tests

# Jalankan uji unit Guard Mode Mineflayer (Node.js)
node tests/test_guard_runner.js
```

### Hasil Verifikasi:
```text
Ran 283 tests
OK
```
- **Total Test Cases:** 283 Python unit/integration tests + `test_guard_runner.js` (Node.js)
- **Success Rate:** **100% PASS (0 Failures, 0 Errors)**
- **Modul Teruji:** `test_autonomous_missions`, `test_brain`, `test_chat_receiver`, `test_chess`, `test_collab_and_plugins`, `test_configuration`, `test_desktop_companion`, `test_event_bus`, `test_fase1_hardening`, `test_goals`, `test_guard_mode`, `test_memory`, `test_minigames`, `test_mood`, `test_multiplayer_social`, `test_overlay_route`, `test_performance`, `test_personality`, `test_platforms`, `test_relationships`, `test_semantic_memory`, `test_storytelling`, `test_streaming_tts`, `test_system_integrity`, `test_tts`, `test_vision`, `test_voice_duplex`, `test_vts_client`, `test_websocket_security`, dan `test_guard_runner.js`.

---

## 📄 Lisensi & Kontribusi

Proyek ini dirilis di bawah lisensi **MIT License**.  
Dibuat dengan ❤️ untuk komunitas AI, VTuber Enthusiasts, dan Kreator Konten Virtual.
