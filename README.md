# MaybeAI - Eve Maybe (Autonomous AI VTuber)

**MaybeAI** adalah sistem AI VTuber modular lengkap yang menggerakkan karakter **Eve Maybe** (biasa dipanggil **Eve**). Terinspirasi dari arsitektur *Neuro-sama* (karya Vedal987), Eve memiliki kepribadian yang cerdas, suka bercanda, sedikit sarkas/smug, dan interaktif saat live stream.

Sistem ini menggabungkan Large Language Model (LLM), Text-to-Speech (TTS), speech filtering/moderation, WebSocket live chat ingestion, dan kontrol avatar Live2D/Web Canvas secara real-time.

---

## 🌟 Fitur Utama

1. **Autonomous Brain (LLM & Persona):**
   * Karakter **Eve Maybe** yang cerdik, lucu, suka nge-roast chat secara santai, dan interaktif.
   * Menghasilkan *emotion tags* (contoh: `[emotion: smug]`, `[emotion: happy]`, `[emotion: blush]`) untuk mengontrol avatar secara dinamis.
   * Multi-provider:
     * **Mock Mode (Default):** Bisa langsung dicoba tanpa API key atau tanpa GPU!
     * **Google Gemini (Gemini 1.5 Flash)**
     * **OpenAI (GPT-4o / GPT-4o-mini)**
     * **Local Ollama (Llama 3.2 / Mistral)**
2. **High-Quality TTS & Dynamic Lip-Sync:**
   * Menggunakan **Edge-TTS** (gratis, tanpa API key, suara jernih dan ekspresif).
   * Parameter `mouth_open` dikalkulasikan secara real-time untuk animasi bibir bergerak (lip-sync).
3. **Dual Avatar Display:**
   * **Built-in Web Avatar Viewer:** Langsung tampil di browser (`http://localhost:7860`) dengan animasi mata berkedip, kepala mengambang, perubahan ekspresi, dan sinkronisasi mulut. Cocok dijadikan *Browser Source* di OBS Studio!
   * **VTube Studio API Integration:** Otomatis mendeteksi dan mengirim data WebSocket ke VTube Studio (`ws://localhost:8001`) untuk menggerakkan model Live2D profesional.
4. **🎤 Karaoke & Singing Engine:**
   * Eve bisa menyanyikan lagu lengkap dengan instrumen BGM otomatis!
   * Pitch dan nada vokal diatur secara ritmik per bait lirik, mulut bergerak sinkron dengan vokal, dan ada animasi partikel not balok (♪ ♫) di layar avatar.
   * Mendukung penambahan lagu kustom lewat `config/songs.json` dan file audio di `assets/songs/`.
5. **🟩 Minecraft Gameplay Engine (Mode Santai & Mode Kompe):**
   * **Mode Santai (Casual / Social):** Eve berinteraksi santai dengan player lain di server (menyapa saat player mendekat, membalas crouch/t-bag, berterima kasih saat diberi hadiah item, dan marah lucu/roasting jika dipukul player).
   * **Mode Kompe (Competitive / Speedrun):** Eve fokus speedrun Minecraft sampai tamat (10 fase: Kayu $\rightarrow$ Batu $\rightarrow$ Besi/Ember $\rightarrow$ Nether $\rightarrow$ Blaze Rods $\rightarrow$ Ender Pearl $\rightarrow$ Mata Ender $\rightarrow$ Stronghold $\rightarrow$ End Portal $\rightarrow$ Kalahkan Ender Dragon). Eve memberikan komentar taktis dan split timer secara live!
6. **Safety & Moderation Filter:**
   * Filter pencegah prompt injection, kata-kata kasar, dan pelanggaran Twitch TOS.
5. **Twitch IRC Chat & Interactive Web Chat:**
   * Bisa membaca live chat langsung dari channel Twitch penonton.

---

## 📁 Struktur Direktori

```
MaybeAI/
├── config/
│   ├── settings.json       # Pengaturan port, provider LLM, TTS, VTS
│   ├── character.json      # Karakter Eve, lore, kepribadian, gaya bicara
│   └── filter_words.json   # Blacklist kata terlarang & regex filter
├── core/
│   ├── brain.py            # Otak LLM (OpenAI, Ollama, Gemini, Mock)
│   ├── tts.py              # Text-to-Speech (Edge-TTS) & Lip-sync
│   ├── vts_client.py       # Client WebSocket VTube Studio API
│   ├── chat_receiver.py    # Ingestion chat (Twitch IRC & Web)
│   ├── moderator.py        # Filter moderasi & keamanan pesan
│   └── actions.py          # Parser emosi dan perintah aksi
├── web/
│   ├── index.html          # Web Dashboard & Virtual Avatar Eve
│   ├── style.css           # Tampilan Cyberpunk/VTuber
│   └── app.js              # Animasi 2D Canvas & WebSocket client
├── run.py                  # Server FastAPI & Launcher utama
├── requirements.txt        # Dependensi Python
└── .env                    # Konfigurasi API Keys
```

---

## 🚀 Cara Menjalankan

### 1. Jalankan Sistem (Mode Default - Siap Pakai)
Kamu bisa langsung menjalankannya dengan satu perintah:

```powershell
.\.venv\Scripts\python.exe run.py
```

Buka browser kamu dan akses:
👉 **`http://localhost:7860`**

Di halaman ini, kamu bisa langsung mengetik chat dan melihat avatar Eve berbicara, berekspresi, serta menggerakkan mulutnya secara real-time!

---

### 2. Memilih Model AI (LLM Provider)

Secara default, MaybeAI berjalan dalam **Mock Mode** (sudah memiliki kepribadian cerdas bawaan Eve tanpa butuh API key atau internet).

Untuk menggunakan AI sesungguhnya:

#### A. Menggunakan Google Gemini (Rekomendasi Cepat & Gratis)
1. Buat file `.env` (atau salin dari `.env.example`).
2. Masukkan API key kamu:
   ```env
   GEMINI_API_KEY=AIzaSy...
   ```
3. Jalankan dengan flag:
   ```powershell
   .\.venv\Scripts\python.exe run.py --provider gemini
   ```

#### B. Menggunakan OpenAI (GPT-4o-mini)
1. Masukkan API key di `.env`:
   ```env
   OPENAI_API_KEY=sk-...
   ```
2. Jalankan:
   ```powershell
   .\.venv\Scripts\python.exe run.py --provider openai
   ```

#### C. Menggunakan Model Lokal (Ollama / Llama 3)
1. Install [Ollama](https://ollama.com/) dan unduh model:
   ```powershell
   ollama run llama3.2
   ```
2. Jalankan:
   ```powershell
   .\.venv\Scripts\python.exe run.py --provider ollama
   ```

---

## 🎤 Cara Menggunakan Fitur Karaoke / Menyanyi

1. **Meminta Eve Menyanyi via Chat:**
   * Di live chat atau Web UI, ketik:
     * `!sing digital_world`
     * Atau kalimat natural seperti: *"Eve, coba nyanyi dong"* / *"sing a song"*
   * Atau klik tombol instan: **`🎵 Sing "Digital World" (Karaoke)`** di Web Dashboard.
2. **Cara Menambahkan Lagu Baru:**
   * Masukkan file instrumen BGM (`.wav` atau `.mp3`) ke folder `assets/songs/`.
   * Buka [config/songs.json](file:///D:/projects/MaybeAI/config/songs.json) dan daftarkan lagu baru:
     ```json
     "judul_lagu": {
       "title": "Nama Lagu",
       "artist": "Nama Artis",
       "bgm_file": "assets/songs/lagu_kamu.wav",
       "bgm_volume": 0.35,
       "lyrics": [
         {
           "text": "Bait pertama lagu kamu~",
           "pitch": "+30Hz",
           "rate": "-10%",
           "delay_before": 1.0,
           "emotion": "happy"
         }
       ]
     }
     ```

---

## 🟩 Fitur Minecraft: Mode Santai & Mode Kompe

Eve dilengkapi sistem gameplay Minecraft yang memiliki 2 mode interaktif:

### 1. Mode Santai (Casual / Social)
* **Tujuan:** Berkeliling santai, menyapa penonton/player, dan berinteraksi sosial.
* **Perilaku AI:**
  * **Player Mendekat:** Menyapa nama player dengan ramah.
  * **Player Crouch/T-bag:** Eve membalas crouch sebagai sapaan damai.
  * **Player Memberi Hadiah (Drop Item):** Berterima kasih dengan ekspresi senang/blush.
  * **Player Memukul Eve:** Marah lucu khas streamer (*"Hey, kenapa kamu pukul aku?! Chat, catat namanya di blacklist!"*).
* **Perintah Chat:**
  * `!mc mode santai` atau ketik *"Eve, main minecraft santai"*

### 2. Mode Kompe (Competitive / Speedrun)
* **Tujuan:** Speedrun mengalahkan Ender Dragon secepat mungkin!
* **10 Fase Speedrun:**
  1. *Wood Tools & Crafting Table*
  2. *Stone Age Upgrade*
  3. *Smelt Iron & Water Bucket*
  4. *Speedrun Lava Portal to Nether*
  5. *Nether Fortress & Blaze Rods*
  6. *Piglin Bartering / Ender Pearls*
  7. *Craft Eyes of Ender*
  8. *Stronghold Triangulation*
  9. *Activate End Portal*
  10. *Slay Ender Dragon (Victory!)*
* **Perilaku AI:** Menyuarakan split timer (`⏱️ 00:00`), komentar taktis saat naik fase, dan selebrasi kemenangan.
* **Perintah Chat:**
  * `!mc mode kompe` (Memulai speedrun)
  * `!mc next` (Maju ke fase berikutnya)

### 3. Mengontrol via Web Dashboard & Server Manager
Di halaman `http://localhost:7860`, pada panel **Minecraft Live Gameplay Engine**, kamu bisa:
* **Server Manager:**
  * Memilih server target dari daftar (Server kamu **`Raehost Server (basic.raehost.com:19214)`** sudah otomatis terdaftar sebagai pilihan default!).
  * Menambah server baru kapan saja lewat tombol **`➕ Add Server`** (Nama, Host, Port, Versi).
  * Menekan tombol **`🚀 Join Server`** agar Eve otomatis login dan menyapa chat streaming saat masuk, serta **`🛑 Disconnect`** untuk keluar.
* **Ganti Mode:**
  * Beralih antara **🌿 Mode Santai** dan **⚡ Mode Kompe**.
* **Simulasi & Pengujian Interaksi:**
  * Tombol uji interaksi: `👤 Player Nearby`, `🗡️ Hit Eve`, `💎 Give Diamond`, `🙇 Friendly Crouch`, `⏩ Next Milestone`.
  * HUD live status: Status koneksi server, Timer split, dan Darah (❤️ 20/20).

### 4. Menghubungkan ke Server Minecraft Asli (Mineflayer)
Jika kamu menjalankan server Minecraft Java (LAN atau Dedicated Server di `localhost:25565`):
1. Masuk ke folder `minecraft/`:
   ```powershell
   cd minecraft
   npm install
   node bot.js
   ```
2. Bot `EveMaybe` akan langsung login ke server Minecraft kamu dan terhubung ke otak Eve!

---

## 🎙️ Menghubungkan ke VTube Studio (Live2D)

1. Buka aplikasi **VTube Studio**.
2. Masuk ke **Settings (ikon roda gigi)** $\rightarrow$ Tab **Camera/General Settings**.
3. Gulir ke bawah ke bagian **VTube Studio API**, lalu aktifkan **"Start API"** (Port default: `8001`).
4. Jalankan `run.py`. VTube Studio akan menampilkan pop-up konfirmasi perizinan: klik **"Allow"**.
5. Model Live2D kamu sekarang akan otomatis membuka mulutnya saat Eve berbicara dan berganti ekspresi wajah!

---

## 📺 Menghubungkan ke OBS Studio

1. **Untuk Avatar:**
   * Di OBS, tambahkan sumber baru: **Browser Source**.
   * Masukkan URL: `http://localhost:7860`
   * Atur resolusi: Width `500`, Height `600`.
   * Centang opsi *"Control audio via OBS"* jika ingin audio browser terdengar di OBS.
2. **Untuk Chat Twitch:**
   * Di `config/settings.json`, ubah:
     ```json
     "twitch": {
       "enabled": true,
       "channel": "nama_channel_twitch_kamu"
     }
     ```
   * Sekarang semua pesan dari chat penonton di Twitch akan otomatis dibaca dan dijawab oleh Eve!
