import os
import re
import json
import asyncio
import random
import tempfile
import aiohttp
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncIterator, Tuple
from core.conversation.engine import ConversationEngine


class ContextBudgetManager:
    """
    Enforces per-provider input token budgets using priority-ordered truncation:
    system core > creator/safety > mood/personality > recent conversation turns > retrieved memories > lore.
    """

    DEFAULT_INPUT_BUDGET = 1800
    DEFAULT_PROVIDER_BUDGETS: Dict[str, int] = {
        "openai": 1800,
        "gemini": 1800,
        "ollama": 1600,
        "mock": 1800,
    }

    _MOOD_PERSONALITY_MARKERS = (
        "[MOOD",
        "CURRENT MOOD",
        "MOOD:",
        "BEHAVIORAL DIRECTIVE",
        "[PERSONALITY",
        "PERSONALITY:",
        "EXPERIENCE-BASED PERSONALITY",
        "CONTROLLED EVOLUTIONARY BEHAVIOR",
        "AUTONOMOUS GOALS",
        "RELATIONSHIP DOSSIER",
        "LIVE VISUAL PERCEPTION",
        "MULTIPLAYER SOCIAL INTELLIGENCE",
        "COMMUNITY BEHAVIORAL RULES",
        "DESKTOP COMPANION",
        "INTERACTIVE MINI-GAME",
        "LIVE INTERACTIVE RPG",
        "DYNAMIC PERFORMANCE DIRECTOR",
        "[GOAL",
        "[RELATIONSHIP",
        "[MULTIPLAYER",
        "[DESKTOP",
        "[MINIGAME",
        "[STORYTELLING",
        "[PERFORMANCE",
    )

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}

    @staticmethod
    def estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return (len(text) + 3) // 4

    def get_budget(self, provider: str) -> int:
        prov = (provider or "mock").strip().lower()
        llm_cfg = self.settings.get("llm", {}) if isinstance(self.settings, dict) else {}
        per_provider = llm_cfg.get("provider_token_budgets", {})
        if isinstance(per_provider, dict) and prov in per_provider:
            return max(128, int(per_provider[prov]))
        if "input_token_budget" in llm_cfg and llm_cfg["input_token_budget"] is not None:
            return max(128, int(llm_cfg["input_token_budget"]))
        return self.DEFAULT_PROVIDER_BUDGETS.get(prov, self.DEFAULT_INPUT_BUDGET)

    @classmethod
    def _classify_block(cls, block: str, current_tier: str) -> Tuple[str, str]:
        upper = block.upper()
        if (
            "10 CONVERSATIONAL PILLARS" in upper
            or "LANGUAGE ADAPTATION:" in upper
            or "OUTPUT FORMATTING RULES:" in upper
            or "CURRENT STREAM SITUATION" in upper
            or "[ACTIVE ROLEPLAY MODE" in upper
            or "[ACTIVE STORYTELLING MODE]" in upper
            or "SPECIAL DONATION" in upper
            or "LIVE CHAT DEBATE COMMENTARY" in upper
        ):
            return "system_core", "system_core"
        if "CORE CHARACTER LORE:" in upper:
            return "lore", "lore"
        if "SECOND BRAIN" in upper or "EPISODIC MEMORY RECALL" in upper:
            return "memories", "memories"
        if "[CREATOR VERIFIED]" in upper:
            return "creator_safety", "system_core"
        if any(marker in upper for marker in cls._MOOD_PERSONALITY_MARKERS):
            return "mood_personality", "mood_personality"
        if current_tier in ("lore", "memories", "mood_personality"):
            return current_tier, current_tier
        return "system_core", "system_core"

    @classmethod
    def _segment_system_prompt(cls, system_prompt: str) -> List[Tuple[str, str]]:
        if not system_prompt:
            return []
        raw_blocks = [b.strip() for b in system_prompt.split("\n\n") if b.strip()]
        segmented: List[Tuple[str, str]] = []
        current_tier = "system_core"
        for block in raw_blocks:
            tier, current_tier = cls._classify_block(block, current_tier)
            segmented.append((tier, block))
        return segmented

    def apply(
        self,
        provider: str,
        system_prompt: str,
        history_items: Optional[List[Dict[str, Any]]] = None,
        current_message_text: str = "",
    ) -> Tuple[str, List[Dict[str, Any]]]:
        budget = self.get_budget(provider)
        blocks = self._segment_system_prompt(system_prompt)
        history = [dict(item) for item in (history_items or [])]
        msg_tokens = self.estimate_tokens(current_message_text)

        def total_tokens() -> int:
            sys_tok = sum(self.estimate_tokens(text) for _, text in blocks)
            hist_tok = sum(self.estimate_tokens(str(item.get("content", ""))) for item in history)
            return sys_tok + hist_tok + msg_tokens

        def drop_tier(target_tier: str) -> bool:
            for idx in range(len(blocks) - 1, -1, -1):
                if blocks[idx][0] == target_tier:
                    blocks.pop(idx)
                    return True
            return False

        # Priority-ordered truncation (drop lowest priority first):
        # lore -> retrieved memories -> oldest conversation turns -> mood/personality -> creator/safety -> system core
        while total_tokens() > budget:
            if drop_tier("lore"):
                continue
            if drop_tier("memories"):
                continue
            if history:
                history.pop(0)
                continue
            if drop_tier("mood_personality"):
                continue
            if drop_tier("creator_safety"):
                continue
            break

        # Final safeguard if system_core + current_message_text still exceeds budget
        if total_tokens() > budget and blocks:
            available_chars = max(0, (budget - msg_tokens) * 4)
            joined = "\n\n".join(text for _, text in blocks)
            if len(joined) > available_chars:
                joined = joined[:available_chars].rstrip()
            return joined, history

        return "\n\n".join(text for _, text in blocks), history


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
        self.budget_manager = ContextBudgetManager(self.settings)
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

    def is_streaming_enabled(self) -> bool:
        """Returns True if streaming LLM responses are enabled in settings."""
        return bool(self.settings.get("llm", {}).get("streaming_enabled", False))

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
        self.budget_manager = ContextBudgetManager(self.settings)

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
        image_base64: Optional[str] = None,
        is_creator: bool = False
    ) -> str:
        provider = self.get_provider()

        # If user explicitly asks about screen/visual and no image passed, use latest vision thumbnail
        if image_base64 is None and self.vision and self.vision.current_observation:
            obs = self.vision.current_observation
            if any(w in message.lower() for w in ["layar", "screen", "liat", "lihat", "gambar"]):
                image_base64 = obs.thumbnail_base64

        # Build dynamic contextual system prompt
        system_prompt = await self.conversation.abuild_system_prompt(
            current_user=user_name,
            game_context=game_context,
            is_donation=is_donation,
            donation_amount=donation_amount,
            is_group_debate=is_group_debate,
            debate_users=debate_users,
            current_message=message,
            is_creator=is_creator
        )

        if provider == "openai":
            response = await self._generate_openai(system_prompt, user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, image_base64, is_creator=is_creator)
        elif provider == "ollama":
            response = await self._generate_ollama(system_prompt, user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, image_base64, is_creator=is_creator)
        elif provider == "gemini":
            response = await self._generate_gemini(system_prompt, user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, image_base64, is_creator=is_creator)
        else:
            response = self.conversation.generate_mock_response(
                user_name=user_name,
                message=message,
                game_context=game_context,
                is_donation=is_donation,
                donation_amount=donation_amount,
                is_group_debate=is_group_debate,
                debate_users=debate_users,
                is_creator=is_creator
            )

        # Record full turn in multi-turn memory
        self.conversation.record_turn(user_name, message, response)
        return response

    async def generate_response_stream(
        self,
        user_name: str,
        message: str,
        game_context: str = "",
        is_donation: bool = False,
        donation_amount: str = "",
        is_group_debate: bool = False,
        debate_users: Optional[List[str]] = None,
        image_base64: Optional[str] = None,
        is_creator: bool = False
    ) -> AsyncIterator[str]:
        """
        Streams incremental LLM text chunks as they are generated, then records
        the complete accumulated response into conversation history/memory.
        Supports Gemini SSE, OpenAI SSE, Ollama NDJSON, and realistic Mock chunking.
        """
        provider = self.get_provider()

        if image_base64 is None and self.vision and self.vision.current_observation:
            obs = self.vision.current_observation
            if any(w in message.lower() for w in ["layar", "screen", "liat", "lihat", "gambar"]):
                image_base64 = obs.thumbnail_base64

        system_prompt = await self.conversation.abuild_system_prompt(
            current_user=user_name,
            game_context=game_context,
            is_donation=is_donation,
            donation_amount=donation_amount,
            is_group_debate=is_group_debate,
            debate_users=debate_users,
            current_message=message,
            is_creator=is_creator
        )

        if provider == "openai":
            stream = self._stream_openai(system_prompt, user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, image_base64, is_creator=is_creator)
        elif provider == "ollama":
            stream = self._stream_ollama(system_prompt, user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, image_base64, is_creator=is_creator)
        elif provider == "gemini":
            stream = self._stream_gemini(system_prompt, user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, image_base64, is_creator=is_creator)
        else:
            stream = self._stream_mock(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator)

        accumulated: List[str] = []
        async for chunk in stream:
            if chunk:
                accumulated.append(chunk)
                yield chunk

        full_response = "".join(accumulated).strip()
        if full_response:
            self.conversation.record_turn(user_name, message, full_response)

    @staticmethod
    async def _iter_lines(stream) -> AsyncIterator[str]:
        """Yields decoded lines from an aiohttp StreamReader or async byte/str iterator."""
        buffer = ""
        async for raw in stream:
            text = raw.decode("utf-8", errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
            buffer += text
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                yield line.rstrip("\r")
        if buffer:
            yield buffer.rstrip("\r")

    @staticmethod
    def _split_mock_chunks(text: str) -> List[str]:
        """
        Splits a mock response into realistic sentence/phrase chunks while keeping
        [emotion: ...] / [action: ...] tags intact and preserving exact concatenation.
        """
        if not text:
            return []

        # First split on sentence boundaries outside [...] tags
        chunks: List[str] = []
        start = 0
        depth = 0
        n = len(text)
        i = 0
        while i < n:
            ch = text[i]
            if ch == "[":
                depth += 1
            elif ch == "]" and depth > 0:
                depth -= 1
            elif depth == 0 and ch in ".!?\n~":
                end = i + 1
                while end < n and text[end] in ".!?~":
                    end += 1
                while end < n and text[end] == " ":
                    end += 1
                if end - start >= 6:
                    chunks.append(text[start:end])
                    start = end
                    i = end
                    continue
            i += 1
        if start < n:
            chunks.append(text[start:])

        # If only a single chunk was produced and it's moderately long, split into 2-3 phrase chunks outside tags
        if len(chunks) == 1 and len(text) > 24:
            split_points: List[int] = []
            depth = 0
            for idx, ch in enumerate(text):
                if ch == "[":
                    depth += 1
                elif ch == "]" and depth > 0:
                    depth -= 1
                elif depth == 0 and ch == " " and idx > 0 and idx < n - 1:
                    split_points.append(idx + 1)
            if len(split_points) >= 2:
                mid = split_points[len(split_points) // 2]
                return [text[:mid], text[mid:]]

        return chunks

    async def _stream_mock(
        self, user_name: str, message: str, game_context: str,
        is_donation: bool, donation_amount: str, is_group_debate: bool, debate_users: Optional[List[str]],
        is_creator: bool = False
    ) -> AsyncIterator[str]:
        response = self.conversation.generate_mock_response(
            user_name=user_name,
            message=message,
            game_context=game_context,
            is_donation=is_donation,
            donation_amount=donation_amount,
            is_group_debate=is_group_debate,
            debate_users=debate_users,
            is_creator=is_creator
        )
        for chunk in self._split_mock_chunks(response):
            await asyncio.sleep(0)
            yield chunk

    def generate_spontaneous_banter(self, game_context: str = "") -> str:
        """Generates an unprompted streamer remark, shower thought, or question to chat."""
        return self.conversation.generate_spontaneous_improv_text(game_context)

    def _build_openai_payload(
        self, system_prompt: str, user_name: str, message: str,
        is_donation: bool, donation_amount: str, image_base64: Optional[str] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        model = self.settings.get("llm", {}).get("model", "gpt-4o-mini")
        temperature = float(self.settings.get("llm", {}).get("temperature", 0.85))
        max_tokens = int(self.settings.get("llm", {}).get("max_tokens", 800))

        user_prefix = f"[Donation: {donation_amount}] {user_name}" if is_donation else user_name
        prompt_text = f"{user_prefix}: {message}"

        history_items = self.conversation.context_memory.get_history_for_llm()
        bounded_prompt, bounded_history = self.budget_manager.apply(
            "openai", system_prompt, history_items, prompt_text
        )

        messages = [{"role": "system", "content": bounded_prompt}]
        for item in bounded_history:
            messages.append({"role": item["role"], "content": item["content"]})

        if image_base64:
            raw_b64 = image_base64.split("base64,")[1] if "base64," in image_base64 else image_base64
            user_content: Any = [
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{raw_b64}"}}
            ]
        else:
            user_content = prompt_text

        messages.append({"role": "user", "content": user_content})

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        if stream:
            payload["stream"] = True
        return payload

    async def _generate_openai(
        self, system_prompt: str, user_name: str, message: str, game_context: str,
        is_donation: bool, donation_amount: str, is_group_debate: bool, debate_users: Optional[List[str]],
        image_base64: Optional[str] = None, is_creator: bool = False
    ) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator)

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = self._build_openai_payload(system_prompt, user_name, message, is_donation, donation_amount, image_base64, stream=False)

        try:
            session = await self._get_session()
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    print(f"[Brain Warning] OpenAI status {resp.status}. Using persona fallback.")
                    return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator)
        except Exception as e:
            print(f"[Brain Error] OpenAI connection error: {e}")
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator)

    async def _stream_openai(
        self, system_prompt: str, user_name: str, message: str, game_context: str,
        is_donation: bool, donation_amount: str, is_group_debate: bool, debate_users: Optional[List[str]],
        image_base64: Optional[str] = None, is_creator: bool = False
    ) -> AsyncIterator[str]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            async for chunk in self._stream_mock(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator):
                yield chunk
            return

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = self._build_openai_payload(system_prompt, user_name, message, is_donation, donation_amount, image_base64, stream=True)

        yielded_any = False
        try:
            session = await self._get_session()
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    print(f"[Brain Warning] OpenAI stream status {resp.status}. Using persona fallback.")
                else:
                    async for line in self._iter_lines(resp.content):
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            if data_str == "[DONE]":
                                break
                            continue
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yielded_any = True
                                yield content
        except Exception as e:
            print(f"[Brain Error] OpenAI stream error: {e}")

        if not yielded_any:
            async for chunk in self._stream_mock(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator):
                yield chunk

    def _build_ollama_payload(
        self, system_prompt: str, user_name: str, message: str,
        is_donation: bool, donation_amount: str, image_base64: Optional[str] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        model = self.settings.get("llm", {}).get("ollama_model", "llama3.2")

        user_prefix = f"[Donation: {donation_amount}] {user_name}" if is_donation else user_name
        prompt_text = f"{user_prefix}: {message}"

        history_items = self.conversation.context_memory.get_history_for_llm()
        bounded_prompt, bounded_history = self.budget_manager.apply(
            "ollama", system_prompt, history_items, prompt_text
        )

        messages = [{"role": "system", "content": bounded_prompt}]
        for item in bounded_history:
            messages.append({"role": item["role"], "content": item["content"]})

        user_msg: Dict[str, Any] = {"role": "user", "content": prompt_text}
        if image_base64:
            raw_b64 = image_base64.split("base64,")[1] if "base64," in image_base64 else image_base64
            user_msg["images"] = [raw_b64]
        messages.append(user_msg)

        return {
            "model": model,
            "messages": messages,
            "stream": stream
        }

    async def _generate_ollama(
        self, system_prompt: str, user_name: str, message: str, game_context: str,
        is_donation: bool, donation_amount: str, is_group_debate: bool, debate_users: Optional[List[str]],
        image_base64: Optional[str] = None, is_creator: bool = False
    ) -> str:
        base_url = os.getenv("OLLAMA_BASE_URL") or self.settings.get("llm", {}).get("ollama_url", "http://localhost:11434")
        url = f"{base_url}/api/chat"
        payload = self._build_ollama_payload(system_prompt, user_name, message, is_donation, donation_amount, image_base64, stream=False)

        try:
            session = await self._get_session()
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("message", {}).get("content", "").strip()
                return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator)
        except Exception:
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator)

    async def _stream_ollama(
        self, system_prompt: str, user_name: str, message: str, game_context: str,
        is_donation: bool, donation_amount: str, is_group_debate: bool, debate_users: Optional[List[str]],
        image_base64: Optional[str] = None, is_creator: bool = False
    ) -> AsyncIterator[str]:
        base_url = os.getenv("OLLAMA_BASE_URL") or self.settings.get("llm", {}).get("ollama_url", "http://localhost:11434")
        url = f"{base_url}/api/chat"
        payload = self._build_ollama_payload(system_prompt, user_name, message, is_donation, donation_amount, image_base64, stream=True)

        yielded_any = False
        try:
            session = await self._get_session()
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    async for line in self._iter_lines(resp.content):
                        stripped = line.strip()
                        if not stripped:
                            continue
                        try:
                            data = json.loads(stripped)
                        except json.JSONDecodeError:
                            continue
                        content = data.get("message", {}).get("content")
                        if content:
                            yielded_any = True
                            yield content
                        if data.get("done"):
                            break
        except Exception as e:
            print(f"[Brain Error] Ollama stream error: {e}")

        if not yielded_any:
            async for chunk in self._stream_mock(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator):
                yield chunk

    def _build_gemini_payload(
        self, system_prompt: str, user_name: str, message: str,
        is_donation: bool, donation_amount: str, image_base64: Optional[str] = None
    ) -> Dict[str, Any]:
        user_prefix = f"[Donation: {donation_amount}] {user_name}" if is_donation else user_name
        prompt_text = f"{user_prefix}: {message}"

        history_items = self.conversation.context_memory.get_history_for_llm()
        bounded_prompt, bounded_history = self.budget_manager.apply(
            "gemini", system_prompt, history_items, prompt_text
        )

        # Build contents from conversational history
        contents = []
        for item in bounded_history:
            role = "user" if item["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": item["content"]}]})

        # Append current message with optional vision part
        user_parts: List[Dict[str, Any]] = [{"text": prompt_text}]
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
        return {
            "systemInstruction": {"parts": [{"text": bounded_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": cfg_temp,
                "maxOutputTokens": cfg_max_tokens,
                "thinkingConfig": {"thinkingBudget": 50}
            }
        }

    async def _generate_gemini(
        self, system_prompt: str, user_name: str, message: str, game_context: str,
        is_donation: bool, donation_amount: str, is_group_debate: bool, debate_users: Optional[List[str]],
        image_base64: Optional[str] = None, is_creator: bool = False
    ) -> str:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator)

        model = self.settings.get("llm", {}).get("gemini_model", "gemini-3-flash-preview")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json"
        }
        payload = self._build_gemini_payload(system_prompt, user_name, message, is_donation, donation_amount, image_base64)

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
                    return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator)
                else:
                    err_text = await resp.text()
                    print(f"[Brain Warning] Gemini returned status {resp.status}: {err_text[:120]}. Using persona fallback.")
                    return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator)
        except Exception as e:
            print(f"[Brain Warning] Gemini request error/timeout ({e}). Using persona fallback.")
            return self.conversation.generate_mock_response(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator)

    async def _stream_gemini(
        self, system_prompt: str, user_name: str, message: str, game_context: str,
        is_donation: bool, donation_amount: str, is_group_debate: bool, debate_users: Optional[List[str]],
        image_base64: Optional[str] = None, is_creator: bool = False
    ) -> AsyncIterator[str]:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            async for chunk in self._stream_mock(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator):
                yield chunk
            return

        model = self.settings.get("llm", {}).get("gemini_model", "gemini-3-flash-preview")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json"
        }
        payload = self._build_gemini_payload(system_prompt, user_name, message, is_donation, donation_amount, image_base64)

        yielded_any = False
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            session = await self._get_session()
            async with session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    print(f"[Brain Warning] Gemini stream returned status {resp.status}: {err_text[:120]}. Using persona fallback.")
                else:
                    async for line in self._iter_lines(resp.content):
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            if data_str == "[DONE]":
                                break
                            continue
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        candidates = data.get("candidates", [])
                        if candidates and "content" in candidates[0] and "parts" in candidates[0]["content"]:
                            parts = candidates[0]["content"]["parts"]
                            text = "".join(p.get("text", "") for p in parts if "text" in p)
                            if text:
                                yielded_any = True
                                yield text
        except Exception as e:
            print(f"[Brain Warning] Gemini stream error/timeout ({e}). Using persona fallback.")

        if not yielded_any:
            async for chunk in self._stream_mock(user_name, message, game_context, is_donation, donation_amount, is_group_debate, debate_users, is_creator=is_creator):
                yield chunk
