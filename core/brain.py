import os
import json
import random
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
        self.settings = self._load_json(settings_path)
        self.character = self._load_json(character_path)
        self.conversation = ConversationEngine(self.character)
        self.system_prompt = self.conversation.build_system_prompt("Chat")

    @property
    def history(self) -> List[Dict[str, Any]]:
        return self.conversation.context_memory.buffer

    @history.setter
    def history(self, val: List[Dict[str, Any]]):
        self.conversation.context_memory.buffer = val

    def _load_json(self, path_str: str) -> Dict[str, Any]:
        p = Path(path_str)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def set_provider(self, provider: str) -> str:
        prov = provider.lower().strip()
        if prov in ["mock", "gemini", "openai", "ollama"]:
            self.settings.setdefault("llm", {})["provider"] = prov
            try:
                with open("config/settings.json", "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, indent=2)
            except Exception:
                pass
            return prov
        return self.settings.get("llm", {}).get("provider", "mock")

    def set_roleplay(self, role: Optional[str]):
        self.conversation.topic_tracker.set_roleplay(role)

    def get_conversation_state(self) -> Dict[str, Any]:
        return {
            "current_topic": self.conversation.topic_tracker.current_topic,
            "active_roleplay": self.conversation.topic_tracker.active_roleplay,
            "active_chatters": self.conversation.user_memory.get_active_chatters(),
            "total_chatters": len(self.conversation.user_memory.users),
            "memory_turns": len(self.conversation.context_memory.buffer)
        }

    async def generate_response(
        self,
        user_name: str,
        message: str,
        game_context: str = "",
        is_donation: bool = False,
        donation_amount: str = "",
        is_group_debate: bool = False,
        debate_users: Optional[List[str]] = None
    ) -> str:
        provider = self.settings.get("llm", {}).get("provider", "mock").lower()

        # Build dynamic contextual system prompt
        system_prompt = self.conversation.build_system_prompt(
            current_user=user_name,
            game_context=game_context,
            is_donation=is_donation,
            donation_amount=donation_amount,
            is_group_debate=is_group_debate,
            debate_users=debate_users
        )

        if provider == "openai":
            response = await self._generate_openai(system_prompt, user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)
        elif provider == "ollama":
            response = await self._generate_ollama(system_prompt, user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)
        elif provider == "gemini":
            response = await self._generate_gemini(system_prompt, user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)
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
        is_donation: bool, donation_amount: str, is_group_debate: bool, debate_users: Optional[List[str]]
    ) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)

        model = self.settings.get("llm", {}).get("model", "gpt-4o-mini")
        temperature = self.settings.get("llm", {}).get("temperature", 0.85)

        messages = [{"role": "system", "content": system_prompt}]
        for item in self.conversation.context_memory.get_history_for_llm():
            messages.append({"role": item["role"], "content": item["content"]})
        
        user_prefix = f"[Donation: {donation_amount}] {user_name}" if is_donation else user_name
        messages.append({"role": "user", "content": f"{user_prefix}: {message}"})

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 150
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=12) as resp:
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
        is_donation: bool, donation_amount: str, is_group_debate: bool, debate_users: Optional[List[str]]
    ) -> str:
        base_url = self.settings.get("llm", {}).get("ollama_url", "http://localhost:11434")
        model = self.settings.get("llm", {}).get("ollama_model", "llama3.2")

        messages = [{"role": "system", "content": system_prompt}]
        for item in self.conversation.context_memory.get_history_for_llm():
            messages.append({"role": item["role"], "content": item["content"]})
        
        user_prefix = f"[Donation: {donation_amount}] {user_name}" if is_donation else user_name
        messages.append({"role": "user", "content": f"{user_prefix}: {message}"})

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
                        return data.get("message", {}).get("content", "").strip()
                    return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)
        except Exception as e:
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)

    async def _generate_gemini(
        self, system_prompt: str, user_name: str, message: str, game_context: str,
        is_donation: bool, donation_amount: str, is_group_debate: bool, debate_users: Optional[List[str]]
    ) -> str:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)

        model = self.settings.get("llm", {}).get("gemini_model", "gemini-3.8-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        
        # Build contents from conversational history
        contents = []
        for item in self.conversation.context_memory.get_history_for_llm():
            role = "user" if item["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": item["content"]}]})
        
        # Append current message
        user_prefix = f"[Donation: {donation_amount}] {user_name}" if is_donation else user_name
        contents.append({"role": "user", "parts": [{"text": f"{user_prefix}: {message}"}]})

        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.85, "maxOutputTokens": 160}
        }

        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    else:
                        err_text = await resp.text()
                        print(f"[Brain Warning] Gemini returned status {resp.status}: {err_text[:120]}. Using persona fallback.")
                        return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)
        except Exception as e:
            print(f"[Brain Warning] Gemini request error/timeout ({e}). Using persona fallback.")
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users)
