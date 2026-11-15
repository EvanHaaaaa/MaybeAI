import asyncio
import json
from typing import Dict, Any, Optional, Set, Callable
from core.brain import Brain
from core.tts import TTSEngine
from core.vts_client import VTSClient
from core.chat_receiver import ChatReceiver, ChatMessage
from core.moderator import Moderator
from core.actions import ActionParser
from core.singer import Singer
from core.minecraft.controller import MinecraftController

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

        # Singer (Karaoke Engine)
        self.singer = Singer(
            songs_config_path=f"{config_dir}/songs.json",
            voice=tts_cfg.get("voice", "en-US-AnaNeural")
        )

        # Minecraft Gameplay Controller
        self.minecraft = MinecraftController(bot_name="EveMaybe")
        self.minecraft.set_callbacks(
            on_commentary=self._on_minecraft_commentary,
            on_state_change=self._on_minecraft_state_change,
            on_in_game_chat=self._on_in_game_chat
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

        # Check for sing command / request
        msg_lower = clean_input.lower()
        if msg_lower.startswith("!sing") or "sing a song" in msg_lower or "nyanyi" in msg_lower or "coba nyanyi" in msg_lower:
            song_id = "digital_world"
            parts = clean_input.split()
            if len(parts) > 1 and parts[1] in self.singer.songs:
                song_id = parts[1]
            await self.perform_song(song_id)
            return

        # Check for Minecraft command / request
        if msg_lower.startswith("!mc") or "main minecraft" in msg_lower or "speedrun minecraft" in msg_lower:
            parts = clean_input.split()
            if "santai" in msg_lower or ("mode" in msg_lower and "santai" in msg_lower):
                await self.minecraft.set_mode("santai")
            elif "kompe" in msg_lower or "speedrun" in msg_lower:
                await self.minecraft.set_mode("kompe")
            elif len(parts) > 1 and parts[1] == "next":
                await self.minecraft.advance_speedrun()
            elif len(parts) > 2 and parts[1] == "attack":
                await self.minecraft.player_attacked_bot(parts[2])
            elif len(parts) > 2 and parts[1] == "nearby":
                await self.minecraft.player_joined_proximity(parts[2])
            elif len(parts) > 1 and parts[1] == "crouch":
                await self.minecraft.player_crouched("Player1")
            elif len(parts) > 3 and parts[1] == "gift":
                await self.minecraft.player_gave_gift(parts[2], parts[3])
            else:
                # Default start santai if general request
                await self.minecraft.set_mode("santai")
            return

        # 2. Brain generates response
        if msg.source == "minecraft":
            llm_input = f"[Minecraft In-Game Chat from {msg.user}]: {clean_input}\n(You are currently inside Minecraft playing with them! Respond directly to {msg.user} in 1-2 witty sentences)"
        else:
            llm_input = clean_input

        raw_response = await self.brain.generate_response(msg.user, llm_input)

        # Filter AI response just in case
        _, clean_response = self.moderator.clean_text(raw_response)

        # 3. Parse Emotions & Actions
        speech_text, emotions, actions = ActionParser.parse(clean_response)
        primary_emotion = emotions[0] if emotions else "neutral"

        await self.broadcast("ai_response", {
            "user": f"Eve (to {msg.user})" if msg.source == "minecraft" else "Eve",
            "raw": clean_response,
            "speech": speech_text,
            "emotions": emotions,
            "actions": actions,
            "source": msg.source
        })

        # If from in-game Minecraft chat, send reply back into Minecraft server chat!
        if msg.source == "minecraft":
            await self.minecraft.send_chat(speech_text)

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

    async def perform_song(self, song_id: str):
        song = self.singer.songs.get(song_id)
        if not song:
            print(f"[Singer] Song '{song_id}' not found.")
            return

        title = song.get("title", song_id)
        intro = song.get("intro_dialogue", f"Alright chat! Let me sing {title} for you! [action: wink]")
        outro = song.get("outro_dialogue", "Thank you everyone for listening! [action: giggle]")

        print(f"[Karaoke] Eve is starting song: {title}")

        # 1. Intro Speech
        speech_text, emotions, actions = ActionParser.parse(intro)
        primary_emotion = emotions[0] if emotions else "happy"
        await self.broadcast("ai_response", {
            "user": "System",
            "raw": intro,
            "speech": speech_text,
            "emotions": emotions,
            "actions": actions
        })
        if self.vts.connected:
            await self.vts.trigger_expression(primary_emotion)

        async def on_mouth_update(val: float):
            if self.vts.connected:
                await self.vts.update_mouth(val)
            await self.broadcast("avatar_state", {"mouth_open": val, "emotion": primary_emotion})

        await self.tts.speak(speech_text, on_mouth_update=lambda val: asyncio.create_task(on_mouth_update(val)))

        # 2. Singing Performance
        await self.broadcast("song_started", {"song_id": song_id, "title": title})

        async def on_lyric_update(line_text: str, emotion: str):
            print(f"[Singing] [{emotion}] ♪ {line_text} ♪")
            if self.vts.connected:
                await self.vts.trigger_expression(emotion)
            await self.broadcast("lyric_line", {
                "text": line_text,
                "emotion": emotion,
                "is_singing": True
            })

        async def on_sing_mouth(val: float):
            if self.vts.connected:
                await self.vts.update_mouth(val)
            await self.broadcast("avatar_state", {"mouth_open": val, "is_singing": True})

        await self.singer.sing(
            song_id=song_id,
            on_lyric_update=on_lyric_update,
            on_mouth_update=lambda val: asyncio.create_task(on_sing_mouth(val))
        )

        await self.broadcast("song_ended", {"song_id": song_id, "title": title})

        # 3. Outro Speech
        speech_text, emotions, actions = ActionParser.parse(outro)
        primary_emotion = emotions[0] if emotions else "blush"
        await self.broadcast("ai_response", {
            "user": "System",
            "raw": outro,
            "speech": speech_text,
            "emotions": emotions,
            "actions": actions
        })
        if self.vts.connected:
            await self.vts.trigger_expression(primary_emotion)
        await self.tts.speak(speech_text, on_mouth_update=lambda val: asyncio.create_task(on_mouth_update(val)))

        # Return to idle
        if self.vts.connected:
            await self.vts.trigger_expression("neutral")
            await self.vts.update_mouth(0.0)

        await self.broadcast("avatar_state", {
            "mouth_open": 0.0,
            "emotion": "neutral",
            "is_singing": False
        })

    async def _on_minecraft_commentary(self, speech_raw: str):
        speech_text, emotions, actions = ActionParser.parse(speech_raw)
        primary_emotion = emotions[0] if emotions else "neutral"

        await self.broadcast("ai_response", {
            "user": "Minecraft",
            "raw": speech_raw,
            "speech": speech_text,
            "emotions": emotions,
            "actions": actions
        })

        if self.vts.connected:
            await self.vts.trigger_expression(primary_emotion)

        async def on_mouth_update(val: float):
            if self.vts.connected:
                await self.vts.update_mouth(val)
            await self.broadcast("avatar_state", {"mouth_open": val, "emotion": primary_emotion})

        print(f"[Minecraft Commentary] [{primary_emotion}] {speech_text}")
        await self.tts.speak(speech_text, on_mouth_update=lambda val: asyncio.create_task(on_mouth_update(val)))

        if self.vts.connected:
            await self.vts.trigger_expression("neutral")
            await self.vts.update_mouth(0.0)

        await self.broadcast("avatar_state", {"mouth_open": 0.0, "emotion": "neutral"})

    async def _on_minecraft_state_change(self, state: Dict[str, Any]):
        await self.broadcast("minecraft_state", state)

    async def _on_in_game_chat(self, sender: str, message: str):
        print(f"[Minecraft Chat Ingested] <{sender}>: {message}")
        await self.chat.put_message(user=sender, text=message, source="minecraft")
