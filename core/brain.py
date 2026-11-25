import os
import json
import asyncio
import random
import tempfile
import aiohttp
from pathlib import Path
from typing import List, Dict, Any, Optional
from core.conversation.engine import ConversationEngine

class Brain:
    """
    LLM Brain responsible for personality, context memory, and generating responses.
    Powered by the Neuro-sama styled ConversationEngine for natural banter,
    context retention, humor, storytelling, hot takes, roleplay, improvisation,
    and intelligent real-time chat curation.
    Supports: OpenAI, Ollama, Gemini, and rich offline fallback.
    """

    def __init__(self, settings_path: str = "config/settings.json", character_path: str = "config/character.json"):
        self.settings_path = settings_path
        self.character_path = character_path
        self.settings = self._load_json(settings_path)
        self.character = self._load_json(character_path)
        self.conversation = ConversationEngine(self.character)
        self.system_prompt = self.conversation.build_system_prompt("Chat")
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def history(self) -> List[Dict[str, Any]]:
        return self.conversation.context_memory.buffer

    @history.setter
    def history(self, val: List[Dict[str, Any]]):
        self.conversation.context_memory.buffer = val

    @property
    def episodic_memory(self):
        return self.conversation.episodic_memory

    @property
    def mood(self):
        return self.conversation.mood

    @property
    def goals(self):
        return self.conversation.goals

    @property
    def relationships(self):
        return self.conversation.relationships

    @property
    def vision(self):
        return self.conversation.vision

    @property
    def multiplayer(self):
        return self.conversation.multiplayer

    @property
    def desktop(self):
        return self.conversation.desktop

    @property
    def minigames(self):
        return self.conversation.minigames

    @property
    def storytelling(self):
        return self.conversation.storytelling

    @property
    def performance(self):
        return self.conversation.performance

    @property
    def personality(self):
        return self.conversation.personality

    def _load_json(self, path_str: str) -> Dict[str, Any]:
        p = Path(path_str)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazily creates and reuses a shared aiohttp ClientSession on the active event loop."""
        loop = asyncio.get_running_loop()
        if self._session is not None and self._session.closed is not True:
            session_loop = getattr(self._session, "_loop", None)
            if session_loop is not None and (session_loop.is_closed() or session_loop is not loop):
                try:
                    await self._session.close()
                except Exception:
                    pass
                self._session = None
        if self._session is None or self._session.closed is True:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Closes the shared aiohttp ClientSession if it is open."""
        if self._session is not None and self._session.closed is not True:
            await self._session.close()
        self._session = None

    def get_provider(self) -> str:
        """Returns the active LLM provider, respecting the MAYBEAI_LLM_PROVIDER env override."""
        env_provider = os.getenv("MAYBEAI_LLM_PROVIDER", "").strip().lower()
        if env_provider:
            return env_provider
        return self.settings.get("llm", {}).get("provider", "mock").lower()

    def _atomic_write_settings(self):
        """Atomically writes self.settings to self.settings_path using a temp file and os.replace."""
        target = Path(self.settings_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, target)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise

    def reload_settings(self, new_settings: Dict[str, Any]):
        self.settings = new_settings

    def set_provider(self, provider: str) -> str:
        prov = provider.lower().strip()
        if prov in ["mock", "gemini", "openai", "ollama"]:
            self.settings.setdefault("llm", {})["provider"] = prov
            persisted = False
            try:
                settings_file = Path(self.settings_path)
                if settings_file.name == "settings.json":
                    from core.config_manager import ConfigManager
                    cfg_mgr = ConfigManager(config_dir=str(settings_file.parent))
                    success, _, _ = cfg_mgr.save_config({"llm": {"provider": prov}})
                    persisted = bool(success)
            except Exception:
                persisted = False

            if not persisted:
                try:
                    self._atomic_write_settings()
                except Exception:
                    pass
            return prov
        return self.get_provider()

    def set_roleplay(self, role: Optional[str]):
        self.conversation.topic_tracker.set_roleplay(role)

    def get_conversation_state(self) -> Dict[str, Any]:
        return {
            "current_topic": self.conversation.topic_tracker.current_topic,
            "active_roleplay": self.conversation.topic_tracker.active_roleplay,
            "active_chatters": self.conversation.user_memory.get_active_chatters(),
            "total_chatters": len(self.conversation.user_memory.users),
            "memory_turns": len(self.conversation.context_memory.buffer),
            "second_brain": self.conversation.episodic_memory.get_stats(),
            "mood": self.mood.get_state(),
            "goals": self.goals.get_state(),
            "relationships": self.relationships.get_state(),
            "vision": self.vision.get_state(),
            "multiplayer": self.multiplayer.get_state(),
            "desktop": self.desktop.get_state(),
            "minigames": self.minigames.get_state(),
            "storytelling": self.storytelling.get_state(),
            "performance": self.performance.get_state(),
            "personality": self.personality.get_state()
        }

    async def generate_response(
        self,
        user_name: str,
        message: str,
        game_context: str = "",
        is_donation: bool = False,
        donation_amount: str = "",
        is_group_debate: bool = False,
        debate_users: Optional[List[str]] = None,
        image_base64: Optional[str] = None
    ) -> str:
        provider = self.get_provider()

        # If user explicitly asks about screen/visual and no image passed, use latest vision thumbnail
        if image_base64 is None and self.vision and self.vision.current_observation:
            obs = self.vision.current_observation
            if any(w in message.lower() for w in ["layar", "screen", "liat", "lihat", "gambar"]):
                image_base64 = obs.thumbnail_base64

        # Build dynamic contextual system prompt
        system_prompt = self.conversation.build_system_prompt(
            current_user=user_name,
            game_context=game_context,
            is_donation=is_donation,
            donation_amount=donation_amount,
            is_group_debate=is_group_debate,
            debate_users=debate_users,
            current_message=message
        )

        if provider == "openai":
            response = await self._generate_openai(system_prompt, user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, image_base64)
        elif provider == "ollama":
            response = await self._generate_ollama(system_prompt, user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, image_base64)
        elif provider == "gemini":
            response = await self._generate_gemini(system_prompt, user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, image_base64)
        else:
            response = self.conversation.generate_mock_response(
                user_name=user_name,
                message=message,
                game_context=game_context,
                is_donation=is_donation,
                donation_amount=donation_amount,
                is_group_debate=is_group_debate,
                debate_users=debate_users
            )

        # Record full turn in multi-turn memory
        self.conversation.record_turn(user_name, message, response)
        return response

    def generate_spontaneous_banter(self, game_context: str = "") -> str:
        """Generates an unprompted streamer remark, shower thought, or question to chat."""
        return self.conversation.generate_spontaneous_improv_text(game_context)

    async def _generate_openai(
        self, system_prompt: str, user_name: str, message: str, game_context: str,
        is_donation: bool, donation_amount: str, is_group_debate: bool, debate_users: Optional[List[str]],
        image_base64: Optional[str] = None
    ) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)

        model = self.settings.get("llm", {}).get("model", "gpt-4o-mini")
        temperature = float(self.settings.get("llm", {}).get("temperature", 0.85))
        max_tokens = int(self.settings.get("llm", {}).get("max_tokens", 150))

        messages = [{"role": "system", "content": system_prompt}]
        for item in self.conversation.context_memory.get_history_for_llm():
            messages.append({"role": item["role"], "content": item["content"]})
        
        user_prefix = f"[Donation: {donation_amount}] {user_name}" if is_donation else user_name
        prompt_text = f"{user_prefix}: {message}"

        if image_base64:
            raw_b64 = image_base64.split("base64,")[1] if "base64," in image_base64 else image_base64
            user_content = [
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{raw_b64}"}}
            ]
        else:
            user_content = prompt_text

        messages.append({"role": "user", "content": user_content})

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            session = await self._get_session()
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    print(f"[Brain Warning] OpenAI status {resp.status}. Using persona fallback.")
                    return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)
        except Exception as e:
            print(f"[Brain Error] OpenAI connection error: {e}")
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)

    async def _generate_ollama(
        self, system_prompt: str, user_name: str, message: str, game_context: str,
        is_donation: bool, donation_amount: str, is_group_debate: bool, debate_users: Optional[List[str]],
        image_base64: Optional[str] = None
    ) -> str:
        base_url = os.getenv("OLLAMA_BASE_URL") or self.settings.get("llm", {}).get("ollama_url", "http://localhost:11434")
        model = self.settings.get("llm", {}).get("ollama_model", "llama3.2")

        messages = [{"role": "system", "content": system_prompt}]
        for item in self.conversation.context_memory.get_history_for_llm():
            messages.append({"role": item["role"], "content": item["content"]})
        
        user_prefix = f"[Donation: {donation_amount}] {user_name}" if is_donation else user_name
        user_msg = {"role": "user", "content": f"{user_prefix}: {message}"}
        if image_base64:
            raw_b64 = image_base64.split("base64,")[1] if "base64," in image_base64 else image_base64
            user_msg["images"] = [raw_b64]
        messages.append(user_msg)

        url = f"{base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False
        }

        try:
            session = await self._get_session()
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("message", {}).get("content", "").strip()
                return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)
        except Exception as e:
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)

    async def _generate_gemini(
        self, system_prompt: str, user_name: str, message: str, game_context: str,
        is_donation: bool, donation_amount: str, is_group_debate: bool, debate_users: Optional[List[str]],
        image_base64: Optional[str] = None
    ) -> str:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)

        model = self.settings.get("llm", {}).get("gemini_model", "gemini-3-flash-preview")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json"
        }
        
        # Build contents from conversational history
        contents = []
        for item in self.conversation.context_memory.get_history_for_llm():
            role = "user" if item["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": item["content"]}]})
        
        # Append current message with optional vision part
        user_prefix = f"[Donation: {donation_amount}] {user_name}" if is_donation else user_name
        user_parts = [{"text": f"{user_prefix}: {message}"}]
        if image_base64:
            raw_b64 = image_base64.split("base64,")[1] if "base64," in image_base64 else image_base64
            user_parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": raw_b64
                }
            })
        contents.append({"role": "user", "parts": user_parts})

        cfg_temp = float(self.settings.get("llm", {}).get("temperature", 0.85))
        cfg_max_tokens = int(self.settings.get("llm", {}).get("max_tokens", 800))
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": cfg_temp,
                "maxOutputTokens": cfg_max_tokens,
                "thinkingConfig": {"thinkingBudget": 50}
            }
        }

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            session = await self._get_session()
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0] and "parts" in candidates[0]["content"]:
                        parts = candidates[0]["content"]["parts"]
                        text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
                        if text:
                            return text
                    print(f"[Brain Warning] Gemini response missing valid parts. Falling back to persona.")
                    return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)
                else:
                    err_text = await resp.text()
                    print(f"[Brain Warning] Gemini returned status {resp.status}: {err_text[:120]}. Using persona fallback.")
                    return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)
        except Exception as e:
            print(f"[Brain Warning] Gemini request error/timeout ({e}). Using persona fallback.")
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)
