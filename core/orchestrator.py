import asyncio
import json
import time
from typing import Dict, Any, Optional, Set, Callable
from core.brain import Brain
from core.tts import TTSEngine
from core.vts_client import VTSClient
from core.chat_receiver import ChatReceiver, ChatMessage
from core.moderator import Moderator
from core.actions import ActionParser
from core.singer import Singer
from core.minecraft.controller import MinecraftController
from core.conversation.chat_curator import ChatInteraction

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
        # Start spontaneous banter / idle stream thoughts loop
        asyncio.create_task(self._idle_banter_loop())

    async def _idle_banter_loop(self):
        """
        Periodically checks for stream dead-air (quiet chat) and triggers
        spontaneous streamer thoughts, engagement questions, or banter.
        """
        last_banter_time = time.time()
        while self.is_running:
            await asyncio.sleep(5)
            now = time.time()
            idle_duration = now - self.brain.conversation.last_interaction_time

            # If chat is silent for >= 40 seconds and Eve hasn't made spontaneous banter in 45s
            if idle_duration >= 40.0 and (now - last_banter_time) >= 45.0 and not self.is_busy:
                last_banter_time = now
                print(f"[Orchestrator] Chat idle for {idle_duration:.1f}s. Triggering spontaneous streamer banter!")
                await self.trigger_improv()

    async def trigger_improv(self):
        """Triggers an unprompted spontaneous monologue or engaging streamer thought."""
        if self.is_busy:
            return
        self.is_busy = True
        try:
            game_context = ""
            if self.minecraft.connection_status == "connected":
                srv = self.minecraft.active_server.get("name", "Minecraft") if self.minecraft.active_server else "Minecraft"
                mode_desc = f"mode={self.minecraft.current_mode}"
                if self.minecraft.current_mode == "guard":
                    mode_desc += f", guarding {self.minecraft.guard_target or 'player'}"
                game_context = f"Playing in Minecraft ({srv}, {mode_desc})"

            raw_thought = self.brain.generate_spontaneous_banter(game_context=game_context)
            _, clean_response = self.moderator.clean_text(raw_thought)
            speech_text, emotions, actions = ActionParser.parse(clean_response)
            primary_emotion = emotions[0] if emotions else "happy"

            await self.broadcast("ai_response", {
                "user": "Eve (Spontaneous)",
                "raw": clean_response,
                "speech": speech_text,
                "emotions": emotions,
                "actions": actions,
                "source": "improv"
            })

            if self.vts.connected:
                await self.vts.trigger_expression(primary_emotion)

            async def on_mouth_update(val: float):
                if self.vts.connected:
                    await self.vts.update_mouth(val)
                await self.broadcast("avatar_state", {
                    "mouth_open": val,
                    "emotion": primary_emotion
                })

            print(f"[AI Improv] [{primary_emotion}] {speech_text}")
            await self.tts.speak(speech_text, on_mouth_update=lambda val: asyncio.create_task(on_mouth_update(val)))

            if self.vts.connected:
                await self.vts.trigger_expression("neutral")
                await self.vts.update_mouth(0.0)

            await self.broadcast("avatar_state", {
                "mouth_open": 0.0,
                "emotion": "neutral"
            })
            await self.broadcast("conversation_state", self.brain.get_conversation_state())
        except Exception as e:
            print(f"[Improv Error] {e}")
        finally:
            self.is_busy = False

    async def _ingest_message(self, msg: ChatMessage):
        """Filters, broadcasts, and ingests message into ChatCurator."""
        is_safe, clean_input = self.moderator.clean_text(msg.text)
        if not is_safe:
            print(f"[Moderator] Filtered unsafe input from {msg.user}: {msg.text}")

        await self.broadcast("chat_received", {
            "user": msg.user,
            "text": clean_input,
            "source": msg.source,
            "is_donation": msg.is_donation,
            "donation_amount": msg.donation_amount
        })

        if msg.is_donation:
            print(f"[Donation Alert] 🎁 {msg.user} sent {msg.donation_amount}: '{clean_input}'")
            await self.broadcast("donation_received", {
                "user": msg.user,
                "amount": msg.donation_amount,
                "currency": msg.donation_currency,
                "text": clean_input
            })

        self.brain.conversation.record_incoming_chat(
            user=msg.user,
            text=clean_input,
            source=msg.source,
            is_donation=msg.is_donation,
            donation_amount=msg.donation_amount,
            donation_currency=msg.donation_currency
        )

    async def _process_chat_loop(self):
        """
        Continuously ingests chat into ChatCurator, then selects the highest
        priority message or group debate to respond to using real-time curation.
        """
        while self.is_running:
            try:
                # 1. Drain incoming messages from queue into curator buffer
                while not self.chat.queue.empty():
                    msg = await self.chat.get_next_message()
                    await self._ingest_message(msg)

                # 2. If not busy, select next best interaction from curator
                if not self.is_busy:
                    interaction = self.brain.conversation.select_next_interaction()
                    if interaction:
                        self.is_busy = True
                        await self._execute_interaction(interaction)
                        self.is_busy = False
                        continue

                # 3. If no interaction ready or currently busy, wait for next message
                try:
                    msg = await asyncio.wait_for(self.chat.get_next_message(), timeout=0.8)
                    await self._ingest_message(msg)
                except asyncio.TimeoutError:
                    pass

            except Exception as e:
                print(f"[Orchestrator Error] {e}")
                self.is_busy = False
                await asyncio.sleep(1)

    async def _execute_interaction(self, interaction: ChatInteraction):
        primary = interaction.primary_message
        clean_input = primary.text
        msg_lower = clean_input.lower()

        # Check for spontaneous improv command
        if msg_lower.startswith("!improv"):
            await self.trigger_improv()
            return

        # Check for sing command / request
        if msg_lower.startswith("!sing") or "sing a song" in msg_lower or "nyanyi" in msg_lower or "coba nyanyi" in msg_lower:
            song_id = "digital_world"
            parts = clean_input.split()
            if len(parts) > 1 and parts[1] in self.singer.songs:
                song_id = parts[1]
            await self.perform_song(song_id)
            return

        # Check for Minecraft command / request
        if msg_lower.startswith("!mc") or "main minecraft" in msg_lower or "speedrun minecraft" in msg_lower or "guard me" in msg_lower or "lindungi aku" in msg_lower:
            parts = clean_input.split()
            if "guard" in msg_lower or "lindungi" in msg_lower or "jaga" in msg_lower:
                target = None
                if len(parts) > 2 and parts[1].lower() == "guard":
                    target = parts[2]
                elif len(parts) > 1 and parts[0].lower() == "!mc" and parts[1].lower() == "guard" and len(parts) > 2:
                    target = parts[2]
                elif primary.source == "minecraft":
                    target = primary.user
                await self.minecraft.guard_player(target)
            elif "dance" in msg_lower or "joget" in msg_lower:
                await self.minecraft.dance()
            elif "gift" in msg_lower or "hadiah" in msg_lower:
                await self.minecraft.gift_nearest()
            elif "jump" in msg_lower or "lompat" in msg_lower:
                await self.minecraft.jump()
            elif "crouch" in msg_lower or "jongkok" in msg_lower:
                await self.minecraft.crouch()
            elif "follow" in msg_lower or "ikut" in msg_lower:
                await self.minecraft.follow_nearest()
            elif "stop" in msg_lower or "diam" in msg_lower or "stay" in msg_lower:
                await self.minecraft.stop_moving()
            elif "santai" in msg_lower or ("mode" in msg_lower and "santai" in msg_lower):
                await self.minecraft.set_mode("santai")
            elif "kompe" in msg_lower or "speedrun" in msg_lower:
                await self.minecraft.set_mode("kompe")
            elif len(parts) > 1 and parts[1] == "next":
                await self.minecraft.advance_speedrun()
            elif len(parts) > 2 and parts[1] == "attack":
                await self.minecraft.player_attacked_bot(parts[2])
            elif len(parts) > 2 and parts[1] == "nearby":
                await self.minecraft.player_joined_proximity(parts[2])
            else:
                await self.minecraft.set_mode("santai")
            return

        # Game context
        game_context = ""
        if self.minecraft.connection_status == "connected":
            srv = self.minecraft.active_server.get("name", "Minecraft Server") if self.minecraft.active_server else "Minecraft"
            mode_desc = f"mode={self.minecraft.current_mode}"
            if self.minecraft.current_mode == "guard":
                mode_desc += f", bodyguarding {self.minecraft.guard_target or 'player'}"
            game_context = f"Playing in Minecraft ({srv}, {mode_desc}, health={self.minecraft.health}/20)"

        is_donation = (interaction.interaction_type == "donation")
        is_group_debate = (interaction.interaction_type == "group_debate")
        debate_users = [primary.user] + [m.user for m in interaction.related_messages] if is_group_debate else None

        if primary.source == "minecraft":
            llm_input = f"[Minecraft In-Game Chat from {primary.user}]: {clean_input}\n(You are currently inside Minecraft playing with them! Respond directly to {primary.user} in 1-2 witty sentences)"
        elif is_donation:
            llm_input = f"[DONATION {primary.donation_amount} from {primary.user}]: {clean_input}"
        elif is_group_debate:
            u2_msg = interaction.related_messages[0]
            llm_input = f"[CHAT DEBATE between {primary.user} and {u2_msg.user}]: {primary.user} said '{primary.text}', while {u2_msg.user} said '{u2_msg.text}'. (Commentate on this chat discussion!)"
        else:
            llm_input = clean_input

        raw_response = await self.brain.generate_response(
            user_name=primary.user,
            message=llm_input,
            game_context=game_context,
            is_donation=is_donation,
            donation_amount=primary.donation_amount,
            is_group_debate=is_group_debate,
            debate_users=debate_users
        )

        _, clean_response = self.moderator.clean_text(raw_response)
        speech_text, emotions, actions = ActionParser.parse(clean_response)
        primary_emotion = emotions[0] if emotions else "neutral"

        if is_donation:
            user_label = f"Eve (to {primary.user} 🎁 {primary.donation_amount})"
            # In-game celebration if Eve is connected in Minecraft!
            if self.minecraft.connection_status == "connected":
                asyncio.create_task(self.minecraft.celebrate(user=primary.user, amount=primary.donation_amount))
        elif is_group_debate:
            user_label = f"Eve (Commenting on {primary.user} & {interaction.related_messages[0].user})"
        elif primary.source == "minecraft":
            user_label = f"Eve (to {primary.user})"
        else:
            user_label = "Eve"

        await self.broadcast("ai_response", {
            "user": user_label,
            "raw": clean_response,
            "speech": speech_text,
            "emotions": emotions,
            "actions": actions,
            "source": primary.source,
            "is_donation": is_donation,
            "donation_amount": primary.donation_amount
        })

        if primary.source == "minecraft":
            await self.minecraft.send_chat(speech_text)

        if self.vts.connected:
            await self.vts.trigger_expression(primary_emotion)

        async def on_mouth_update(val: float):
            if self.vts.connected:
                await self.vts.update_mouth(val)
            await self.broadcast("avatar_state", {
                "mouth_open": val,
                "emotion": primary_emotion
            })

        print(f"[AI Speech] [{primary_emotion}] {speech_text}")
        await self.tts.speak(speech_text, on_mouth_update=lambda val: asyncio.create_task(on_mouth_update(val)))

        if self.vts.connected:
            await self.vts.trigger_expression("neutral")
            await self.vts.update_mouth(0.0)

        await self.broadcast("avatar_state", {
            "mouth_open": 0.0,
            "emotion": "neutral"
        })
        await self.broadcast("conversation_state", self.brain.get_conversation_state())

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

        # Also speak into server chat so in-game players see Eve's reaction
        if self.minecraft.connection_status == "connected":
            await self.minecraft.send_chat(speech_text)

        if self.vts.connected:
            await self.vts.trigger_expression("neutral")
            await self.vts.update_mouth(0.0)

        await self.broadcast("avatar_state", {"mouth_open": 0.0, "emotion": "neutral"})

    async def _on_minecraft_state_change(self, state: Dict[str, Any]):
        await self.broadcast("minecraft_state", state)

    async def _on_in_game_chat(self, sender: str, message: str):
        print(f"[Minecraft Chat Ingested] <{sender}>: {message}")
        prof = self.brain.conversation.user_memory.get_or_create(sender)
        prof.tags.add("minecraft_player")
        if "plays on server" not in prof.known_facts:
            prof.known_facts.append("plays on server")
        await self.chat.put_message(user=sender, text=message, source="minecraft")
