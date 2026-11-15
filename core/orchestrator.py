import asyncio
import json
from typing import Dict, Any, Optional, Set, Callable
from core.brain import Brain
from core.tts import TTSEngine
from core.vts_client import VTSClient
from core.chat_receiver import ChatReceiver, ChatMessage
from core.moderator import Moderator
from core.actions import ActionParser

class Orchestrator:
    """
    The Master Conductor coordinating:
    Chat -> Filter -> Brain -> Action/Emotion Parse -> VTS/Avatar -> TTS Voice -> Web Clients
    """

    def __init__(self, config_dir: str = "config"):
        self.moderator = Moderator(f"{config_dir}/filter_words.json")
        self.brain = Brain(f"{config_dir}/settings.json", f"{config_dir}/character.json")
        
        # Load TTS config
        settings = self.brain.settings
        tts_cfg = settings.get("tts", {})
        self.tts = TTSEngine(
            voice=tts_cfg.get("voice", "en-US-AnaNeural"),
            rate=tts_cfg.get("rate", "+5%"),
            pitch=tts_cfg.get("pitch", "+10Hz")
        )

        # Load VTS config
        vts_cfg = settings.get("vts", {})
        self.vts = VTSClient(
            host=vts_cfg.get("host", "localhost"),
            port=vts_cfg.get("port", 8001),
            plugin_name=vts_cfg.get("plugin_name", "MaybeAI-VTuber")
        )

        self.chat = ChatReceiver()
        self.is_running = False
        self.is_busy = False
        self.web_listeners: Set[Callable[[Dict[str, Any]], None]] = set()

    def register_listener(self, callback: Callable[[Dict[str, Any]], None]):
        self.web_listeners.add(callback)

    def unregister_listener(self, callback: Callable[[Dict[str, Any]], None]):
        self.web_listeners.discard(callback)

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        message = {"type": event_type, "data": data}
        for listener in list(self.web_listeners):
            try:
                res = listener(message)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

    async def start(self):
        self.is_running = True
        print("[Orchestrator] Starting MaybeAI Engine...")

        # Connect to VTube Studio in background if enabled
        if self.brain.settings.get("vts", {}).get("enabled", True):
            asyncio.create_task(self.vts.connect())

        # Connect to Twitch if enabled
        twitch_cfg = self.brain.settings.get("twitch", {})
        if twitch_cfg.get("enabled", False) and twitch_cfg.get("channel"):
            asyncio.create_task(
                self.chat.start_twitch_listener(
                    channel=twitch_cfg["channel"],
                    bot_nick=twitch_cfg.get("bot_nick", ""),
                    oauth=twitch_cfg.get("oauth_token", "")
                )
            )

        # Start master processing loop
        asyncio.create_task(self._process_chat_loop())

    async def _process_chat_loop(self):
        """
        Continuously pulls messages from queue and generates live streaming responses.
        """
        while self.is_running:
            try:
                msg: ChatMessage = await self.chat.get_next_message()

                if self.is_busy:
                    # Drop or defer if currently speaking
                    continue

                self.is_busy = True
                await self._handle_message(msg)
                self.is_busy = False

            except Exception as e:
                print(f"[Orchestrator Error] {e}")
                self.is_busy = False
                await asyncio.sleep(1)

    async def _handle_message(self, msg: ChatMessage):
        # 1. Moderation & Safety check
        is_safe, clean_input = self.moderator.clean_text(msg.text)
        if not is_safe:
            print(f"[Moderator] Filtered unsafe input from {msg.user}: {msg.text}")

        await self.broadcast("chat_received", {
            "user": msg.user,
            "text": clean_input,
            "source": msg.source
        })

        # 2. Brain generates response
        raw_response = await self.brain.generate_response(msg.user, clean_input)

        # Filter AI response just in case
        _, clean_response = self.moderator.clean_text(raw_response)

        # 3. Parse Emotions & Actions
        speech_text, emotions, actions = ActionParser.parse(clean_response)
        primary_emotion = emotions[0] if emotions else "neutral"

        await self.broadcast("ai_response", {
            "user": msg.user,
            "raw": clean_response,
            "speech": speech_text,
            "emotions": emotions,
            "actions": actions
        })

        # 4. Trigger Avatar Expression
        if self.vts.connected:
            await self.vts.trigger_expression(primary_emotion)

        # 5. Speak & Live Lip-sync
        async def on_mouth_update(val: float):
            # Update VTube Studio parameter
            if self.vts.connected:
                await self.vts.update_mouth(val)
            # Update Web Canvas Avatar parameter
            await self.broadcast("avatar_state", {
                "mouth_open": val,
                "emotion": primary_emotion
            })

        print(f"[AI Speech] [{primary_emotion}] {speech_text}")
        await self.tts.speak(speech_text, on_mouth_update=lambda val: asyncio.create_task(on_mouth_update(val)))

        # Return to idle
        if self.vts.connected:
            await self.vts.trigger_expression("neutral")
            await self.vts.update_mouth(0.0)

        await self.broadcast("avatar_state", {
            "mouth_open": 0.0,
            "emotion": "neutral"
        })
