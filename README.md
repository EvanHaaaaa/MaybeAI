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
4. **Safety & Moderation Filter:**
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
