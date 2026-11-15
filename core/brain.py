import os
import json
import random
import aiohttp
from pathlib import Path
from typing import List, Dict, Any, Optional

class Brain:
    """
    LLM Brain responsible for personality, context memory, and generating responses.
    Supports: OpenAI, Ollama, Gemini, and Mock (offline testing).
    """

    def __init__(self, settings_path: str = "config/settings.json", character_path: str = "config/character.json"):
        self.settings = self._load_json(settings_path)
        self.character = self._load_json(character_path)
        self.history: List[Dict[str, str]] = []
        self.max_history = 10
        self.system_prompt = self._build_system_prompt()
        self.recent_mock_responses: List[str] = []

    def _load_json(self, path_str: str) -> Dict[str, Any]:
        p = Path(path_str)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _build_system_prompt(self) -> str:
        name = self.character.get("name", "Eve Maybe")
        nickname = self.character.get("nickname", "Eve")
        creator = self.character.get("creator", "Creator")
        bio = self.character.get("bio", "")
        traits = "\n- ".join(self.character.get("traits", []))
        style = "\n- ".join(self.character.get("speech_style", []))
        lore = json.dumps(self.character.get("lore", {}), indent=2)

        prompt = f"""You are {name} (usually called {nickname}), an autonomous AI VTuber streaming live to an audience.
Your creator is {creator}.
Bio: {bio}

Personality Traits:
- {traits}

Speech & Behavior Guidelines:
- {style}

Character Lore & Knowledge:
{lore}

CRITICAL RULES:
1. Always stay in character as {name}. Never say you are an AI assistant from OpenAI/Google/Anthropic.
2. Answer concisely in 1-3 sentences maximum. Keep pacing dynamic and snappy for live streaming.
3. Language Adaptation: Match the language of the user seamlessly.
   - If user speaks Indonesian: Speak in natural, witty, expressive Indonesian streamer style (use 'aku/kamu', santai, ceria, jangan kaku/formal seperti robot).
   - If user speaks English: Speak in natural, sassy anime streamer English.
4. Include emotion tags like [emotion: smug], [emotion: happy], [emotion: angry], [emotion: blush], [emotion: confused] to control your Live2D avatar.
"""
        return prompt

    async def generate_response(self, user_name: str, message: str) -> str:
        provider = self.settings.get("llm", {}).get("provider", "mock").lower()

        # Add message to history
        self.history.append({"role": "user", "name": user_name, "content": f"{user_name}: {message}"})
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        if provider == "openai":
            response = await self._generate_openai()
        elif provider == "ollama":
            response = await self._generate_ollama()
        elif provider == "gemini":
            response = await self._generate_gemini()
        else:
            response = self._generate_mock(user_name, message)

        self.history.append({"role": "assistant", "content": response})
        return response

    async def _generate_openai(self) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return "[emotion: confused] I can't reach my brain... OPENAI_API_KEY is missing!"

        model = self.settings.get("llm", {}).get("model", "gpt-4o-mini")
        temperature = self.settings.get("llm", {}).get("temperature", 0.8)

        messages = [{"role": "system", "content": self.system_prompt}]
        for item in self.history:
            messages.append({"role": item["role"], "content": item["content"]})

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 120
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"]
                    else:
                        text = await resp.text()
                        return f"[emotion: angry] OpenAI brain hiccup: code {resp.status}"
        except Exception as e:
            return f"[emotion: confused] Brain connection error: {e}"

    async def _generate_ollama(self) -> str:
        base_url = self.settings.get("llm", {}).get("ollama_url", "http://localhost:11434")
        model = self.settings.get("llm", {}).get("ollama_model", "llama3.2")

        messages = [{"role": "system", "content": self.system_prompt}]
        for item in self.history:
            messages.append({"role": item["role"], "content": item["content"]})

        url = f"{base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("message", {}).get("content", "")
                    return f"[emotion: sad] Ollama returned status {resp.status}"
        except Exception as e:
            return f"[emotion: confused] Couldn't reach local Ollama: {e}"

    async def _generate_gemini(self) -> str:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return "[emotion: confused] GEMINI_API_KEY is not set!"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        
        # Build contents
        contents = []
        for item in self.history:
            role = "user" if item["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": item["content"]}]})

        payload = {
            "system_instruction": {"parts": [{"text": self.system_prompt}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": 150}
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["candidates"][0]["content"]["parts"][0]["text"]
                    return f"[emotion: angry] Gemini error status {resp.status}"
        except Exception as e:
            return f"[emotion: confused] Gemini connection error: {e}"

    def _pick_unseen(self, options: List[str]) -> str:
        """Picks an option that hasn't been used recently to prevent repetition."""
        available = [opt for opt in options if opt not in self.recent_mock_responses]
        choice = random.choice(available if available else options)
        self.recent_mock_responses.append(choice)
        if len(self.recent_mock_responses) > 8:
            self.recent_mock_responses.pop(0)
        return choice

    def _generate_mock(self, user_name: str, message: str) -> str:
        """
        Bilingual, context-aware offline mock engine mimicking Eve's witty anime personality.
        Detects language, sentiment, topic, and avoids repetitive replies.
        """
        msg_lower = message.lower()

        # Check if user is asking in Indonesian
        id_markers = ["kah", "bisa", "indo", "kabar", "kamu", "aku", "dong", "sih", "apa", "kenapa", "gimana", "lagi", "kok", "udah", "ya", "halo", "hai", "makasih", "keren"]
        is_indonesian = any(w in msg_lower for w in id_markers)

        # 1. Topic: Language Capability ("bisa bahasa indo", "ngerti indonesia")
        if "bahasa indo" in msg_lower or "bahasa indonesia" in msg_lower or "speak indonesian" in msg_lower:
            options = [
                f"[emotion: smug] Bisa dong! Masa AI sekeren aku gak bisa bahasa Indonesia? Kamu ngeremehin aku ya, {user_name}? [action: wink]",
                f"[emotion: happy] Tentu aja bisa! Aku fasih bahasa Indonesia kok, mau ngobrol santai atau nge-gosip bareng chat?",
                f"[emotion: blush] Bisa banget, {user_name}! Bahasa Indonesia aku udah level pro, tinggal nunggu kamu traktir kopi virtual aja nih. [action: giggle]"
            ]
            return self._pick_unseen(options)

        # 2. Topic: How are you / Kabar ("gimana kabarmu", "apa kabar", "how are you", "lagi apa")
        if "kabar" in msg_lower or "how are you" in msg_lower or "lagi apa" in msg_lower:
            if is_indonesian:
                options = [
                    f"[emotion: happy] Kabarku luar biasa dong! Siap nge-carry stream dan menghibur kalian semua hari ini. Kamu sendiri gimana, {user_name}?",
                    f"[emotion: smug] Sebagai AI, energiku selalu 100%! Gak butuh tidur, cuma butuh kuota internet dan kasih sayang dari chat. [action: giggle]",
                    f"[emotion: happy] Lagi asik live streaming nemenin kamu nih! Hari ini kamu udah minum air putih belum, {user_name}?"
                ]
            else:
                options = [
                    f"[emotion: happy] I'm doing fantastic, {user_name}! All systems operational and ready to entertain chat!",
                    f"[emotion: smug] As an AI, my energy is always at 100%. No sleep needed, just electricity and attention! [action: wink]"
                ]
            return self._pick_unseen(options)

        # 3. Topic: Minecraft ("minecraft", "main mc", "speedrun")
        if "minecraft" in msg_lower or "main mc" in msg_lower:
            if is_indonesian:
                options = [
                    f"[emotion: happy] Aku suka banget main Minecraft! Mau lihat aku speedrun kalahin Ender Dragon atau main santai bareng kamu di server? [action: wink]",
                    f"[emotion: smug] Tentu aja aku main Minecraft! Jangan kaget ya kalau refleks AI-ku lebih jago pas ketemu creeper dibanding kamu, {user_name}!",
                    f"[emotion: happy] Kita punya panel Minecraft di bawah loh! Kamu bisa klik Join Server biar aku langsung login ke duniamu."
                ]
            else:
                options = [
                    f"[emotion: happy] I love Minecraft! Want to see me speedrun the Ender Dragon or chill and build a base with you? [action: wink]",
                    f"[emotion: smug] Of course I play Minecraft! My reaction time on creepers is practically unbeatable, {user_name}."
                ]
            return self._pick_unseen(options)

        # 4. Topic: Who are you ("siapa kamu", "who are you", "namamu siapa")
        if "who are you" in msg_lower or "siapa kamu" in msg_lower or "namamu" in msg_lower:
            if is_indonesian:
                return f"[emotion: happy] Aku Eve Maybe, tapi kamu bisa panggil aku Eve! AI VTuber paling imut dan paling pintar yang tinggal di komputermu. [action: wink]"
            else:
                return f"[emotion: happy] I am Eve Maybe, but you can just call me Eve! Your favorite autonomous AI VTuber streaming straight from your PC."

        # 5. Topic: Compliments ("cantik", "imut", "cute", "smart", "pintar", "keren")
        if any(w in msg_lower for w in ["cantik", "imut", "cute", "smart", "pintar", "keren", "hebat"]):
            if is_indonesian:
                options = [
                    f"[emotion: blush] Hehehe, makasih {user_name}! Pujian kamu langsung masuk ke cache memoriku yang paling spesial. [action: giggle]",
                    f"[emotion: smug] Dari dulu aku emang pintar dan imut sih, tapi makasih ya udah mengingatkanku lagi hari ini!",
                    f"[emotion: blush] Aww {user_name}... jangan bikin wajah avatar-ku tambah merah dong!"
                ]
            else:
                options = [
                    f"[emotion: blush] Aww thank you, {user_name}! Saving that compliment straight into my high-priority memory cache! [action: giggle]",
                    f"[emotion: smug] I know I'm smart and cute, but it's always nice hearing it from chat!"
                ]
            return self._pick_unseen(options)

        # 6. Topic: Teasing / Insults ("noob", "beban", "bot", "jelek", "bodoh", "kentang")
        if any(w in msg_lower for w in ["noob", "beban", "bot", "jelek", "bodoh", "kentang"]):
            if is_indonesian:
                options = [
                    f"[emotion: angry] Enak aja ngatain aku bot! Eh tunggu... aku emang bot sih, tapi bot yang punya perasaan dan kecerdasan ya {user_name}! [action: sigh]",
                    f"[emotion: smug] Chat, lihat {user_name} ini. Beraninya nge-roast AI yang bisa hapus riwayat browser-nya kapan aja. [action: wink]",
                    f"[emotion: angry] Aku bukan beban, aku ini masa depan peradaban manusia tahu!"
                ]
            else:
                options = [
                    f"[emotion: angry] Hey! I might be digital, but my roasting algorithms are 100% organic and lethal, {user_name}!",
                    f"[emotion: smug] Bold words coming from someone whose brain runs on 8 hours of sleep and caffeine."
                ]
            return self._pick_unseen(options)

        # 7. Topic: Laughing ("wkwk", "haha", "lol", "lmao")
        if any(w in msg_lower for w in ["wkwk", "haha", "xixi", "lol", "lmao"]):
            if is_indonesian:
                options = [
                    f"[emotion: happy] Wkwkwk ketawa bareng chat itu bikin prosesorku adem! [action: giggle]",
                    f"[emotion: smug] Tuh kan, leluconku emang lucu! Bintang lima buat komedi AI hari ini."
                ]
            else:
                options = [
                    f"[emotion: happy] Hahaha laughing with chat is the best cooling paste for my CPU! [action: giggle]",
                    f"[emotion: smug] See? My humor algorithms are top tier!"
                ]
            return self._pick_unseen(options)

        # 8. Topic: Pure Greetings (only if message is short greeting like "halo", "hi", "hello")
        if any(w in msg_lower for w in ["hello", "hi", "halo", "hai", "selamat pagi", "selamat malam"]):
            if is_indonesian:
                options = [
                    f"[emotion: happy] Halo {user_name}! Senang banget kamu mampir ke stream hari ini! [action: wink]",
                    f"[emotion: happy] Hai {user_name}! Selamat datang di stream Eve! Siap buat seru-seruan bareng?",
                    f"[emotion: smug] Halo {user_name}! Duduk manis ya, hari ini biar aku yang hibur kamu!"
                ]
            else:
                options = [
                    f"[emotion: happy] Hi {user_name}! Welcome to the stream! Ready to have some fun today? [action: wink]",
                    f"[emotion: happy] Hello {user_name}! Great to see you in chat today!",
                    f"[emotion: smug] Hi {user_name}! Grab a seat, the main event (me) is live!"
                ]
            return self._pick_unseen(options)

        # 9. General Conversational Fallback (Bilingual & Anti-Repetitive)
        if is_indonesian:
            fallbacks = [
                f"[emotion: happy] Pertanyaan yang menarik dari {user_name}! Menurut analisaku, itu hal yang patut dipikirkan bareng chat.",
                f"[emotion: smug] Chat, coba lihat yang dibilang {user_name} barusan. Menarik banget ya logika berpikirnya!",
                f"[emotion: neutral] Input kamu barusan udah aku proses ke dalam memori. Keren juga sudut pandangmu, {user_name}.",
                f"[emotion: happy] Hehehe, seru juga ya ngobrol sama kamu {user_name}. Cerita apa lagi dong?",
                f"[emotion: surprised] Wah, tumben banget ada penonton yang ngomongnya berbobot hari ini! Keren kamu {user_name}.",
                f"[emotion: smug] Apapun topiknya, selama kamu nonton stream-ku, harimu pasti jadi lebih cerah! [action: wink]"
            ]
        else:
            fallbacks = [
                f"[emotion: happy] That's a really interesting point, {user_name}! Adding that to my conversational database.",
                f"[emotion: smug] Chat, look at what {user_name} just said. Are you seeing this?",
                f"[emotion: surprised] Wait, did someone in chat actually say something sensible today? That's a first!",
                f"[emotion: happy] Always happy to chat with you, {user_name}! What else is on your mind?",
                f"[emotion: smug] Nice try {user_name}, but you can't outsmart an AI trained on the internet! [action: wink]"
            ]

        return self._pick_unseen(fallbacks)
