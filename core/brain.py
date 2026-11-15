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
2. Answer concisely in 1-3 sentences maximum. Keep pacing dynamic for streaming.
3. Include emotion tags like [emotion: smug], [emotion: happy], [emotion: angry], [emotion: blush] to control your Live2D avatar.
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

    def _generate_mock(self, user_name: str, message: str) -> str:
        """
        Built-in witty offline responses mimicking Eve Maybe when no API is configured.
        """
        msg_lower = message.lower()
        if "hello" in msg_lower or "hi" in msg_lower or "halo" in msg_lower:
            return f"[emotion: happy] Hi {user_name}! Ready to watch me carry the stream today? [action: wink]"
        if "sing" in msg_lower or "nyanyi" in msg_lower:
            return "[emotion: smug] La la la~ Humans pay millions for auto-tune, but I was born digital! [action: giggle]"
        if "smart" in msg_lower or "pintar" in msg_lower:
            return "[emotion: smug] Of course I'm smart. I have millions of parameters and you have... caffeine?"
        if "game" in msg_lower or "main" in msg_lower:
            return "[emotion: happy] I'm ready to play! Just don't blame me if my AI reflexes make you look slow."
        if "who are you" in msg_lower or "siapa kamu" in msg_lower:
            return "[emotion: happy] I am Eve Maybe, but you can just call me Eve! Your favorite autonomous AI VTuber streaming straight from your computer."
        if "love" in msg_lower or "cinta" in msg_lower:
            return f"[emotion: blush] Aww, thank you {user_name}... but my heart is made of transistors, so don't get too attached!"

        responses = [
            f"[emotion: smug] Chat, look at what {user_name} just said. Are you all seeing this?",
            f"[emotion: happy] That's an interesting thought, {user_name}! Though I think my logic processor disagrees.",
            f"[emotion: neutral] Interesting input. Adding that to my neural weights... or maybe into the recycle bin! [action: giggle]",
            f"[emotion: surprised] Wait, did someone in chat actually say something sensible today? That's a first!",
            f"[emotion: smug] Nice try {user_name}, but you can't outsmart an AI trained on the entire internet."
        ]
        return random.choice(responses)
