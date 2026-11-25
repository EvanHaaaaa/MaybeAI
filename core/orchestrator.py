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
from core.chess.controller import ChessController
from core.conversation.chat_curator import ChatInteraction

class Orchestrator:
    """
    The Master Conductor coordinating:
    Chat -> Filter -> Brain -> Action/Emotion Parse -> VTS/Avatar -> TTS Voice -> Web Clients
    """

    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.brain = Brain(f"{config_dir}/settings.json", f"{config_dir}/character.json")
        settings = self.brain.settings

        # Load Moderator config
        mod_cfg = settings.get("moderator", {})
        self.moderator = Moderator(
            f"{config_dir}/filter_words.json",
            max_message_length=mod_cfg.get("max_message_length", 250),
            strict_mode=mod_cfg.get("strict_mode", True)
        )
        
        # Load TTS config
        tts_cfg = settings.get("tts", {})
        self.tts = TTSEngine(
            voice=tts_cfg.get("voice", "en-US-AnaNeural"),
            rate=tts_cfg.get("rate", "+5%"),
            pitch=tts_cfg.get("pitch", "+10Hz"),
            enabled=tts_cfg.get("enabled", True)
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

        # Chess Gameplay Controller
        self.chess = ChessController(bot_name="EveMaybe")
        self.chess.set_callbacks(
            on_commentary=self._on_chess_commentary,
            on_state_change=self._on_chess_state_change,
            on_game_event=self._on_chess_game_event
        )

        self.chat = ChatReceiver()
        self.is_running = False
        self._busy_lock = asyncio.Lock()
        self.web_listeners: Set[Callable[[Dict[str, Any]], None]] = set()

    @property
    def is_busy(self) -> bool:
        return self._busy_lock.locked()

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
        # Start visual perception / screen awareness loop
        asyncio.create_task(self._visual_perception_loop())

    async def shutdown(self):
        """Gracefully stops background loops and closes external client sessions."""
        self.is_running = False
        self.chat.stop()
        await self.vts.disconnect()
        await self.brain.close()

    async def close(self):
        await self.shutdown()

    async def apply_configuration_hot_reload(self, new_settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applies runtime configuration updates cleanly without requiring app restart.
        Hot-reloads: LLM settings, TTS voice/speed/pitch/toggle, VTS connection, Twitch listener, Moderator rules.
        """
        self.brain.reload_settings(new_settings)

        # 1. Update TTS
        tts_cfg = new_settings.get("tts", {})
        self.tts.update_config(
            enabled=tts_cfg.get("enabled"),
            voice=tts_cfg.get("voice"),
            rate=tts_cfg.get("rate"),
            pitch=tts_cfg.get("pitch")
        )
        if tts_cfg.get("voice"):
            self.singer.voice = tts_cfg["voice"]

        # 2. Update VTS
        vts_cfg = new_settings.get("vts", {})
        if vts_cfg.get("enabled") is False and self.vts.connected:
            await self.vts.disconnect()
        elif vts_cfg.get("enabled") is True and not self.vts.connected:
            asyncio.create_task(self.vts.connect())
        elif vts_cfg.get("enabled") is True and (vts_cfg.get("host") != self.vts.host or vts_cfg.get("port") != self.vts.port):
            asyncio.create_task(self.vts.reconnect(host=vts_cfg.get("host"), port=vts_cfg.get("port")))

        # 3. Update Twitch
        twitch_cfg = new_settings.get("twitch", {})
        if twitch_cfg.get("enabled") is False and self.chat.is_running:
            self.chat.stop()
        elif twitch_cfg.get("enabled") is True and not self.chat.is_running and twitch_cfg.get("channel"):
            asyncio.create_task(
                self.chat.start_twitch_listener(
                    channel=twitch_cfg["channel"],
                    bot_nick=twitch_cfg.get("bot_nick", ""),
                    oauth=twitch_cfg.get("oauth_token", "")
                )
            )

        # 4. Update Moderator
        mod_cfg = new_settings.get("moderator", {})
        self.moderator.update_config(
            strict_mode=mod_cfg.get("strict_mode"),
            max_message_length=mod_cfg.get("max_message_length")
        )

        # Broadcast live event to all connected WebSocket clients
        await self.broadcast("configuration_updated", {
            "settings": new_settings,
            "status": "applied_live"
        })

        return {"status": "success", "hot_reloaded": True}

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
            if idle_duration >= 40.0 and (now - last_banter_time) >= 45.0 and not self._busy_lock.locked():
                last_banter_time = now
                print(f"[Orchestrator] Chat idle for {idle_duration:.1f}s. Triggering spontaneous streamer banter!")
                active_g = self.brain.goals.get_active_goal()
                if not active_g or active_g.status == "completed":
                    self.brain.goals.autonomous_select_next_activity(self.brain.mood.dimensions)
                    await self.broadcast("goal_updated", self.brain.goals.get_state())

                self.brain.mood.apply_stimulus("chat_idle")
                await self.broadcast("mood_updated", self.brain.mood.get_state())
                await self.trigger_improv()

    async def trigger_improv(self):
        """Triggers an unprompted spontaneous monologue or engaging streamer thought."""
        if self._busy_lock.locked():
            return
        async with self._busy_lock:
            await self._run_improv()

    async def _run_improv(self):
        try:
            game_contexts = []
            if self.minecraft.connection_status == "connected":
                srv = self.minecraft.active_server.get("name", "Minecraft") if self.minecraft.active_server else "Minecraft"
                mode_desc = f"mode={self.minecraft.current_mode}"
                if self.minecraft.current_mode == "guard":
                    mode_desc += f", guarding {self.minecraft.guard_target or 'player'}"
                game_contexts.append(f"Playing in Minecraft ({srv}, {mode_desc})")
            if self.chess.is_active:
                game_contexts.append(f"Playing Chess against {self.chess.player_name} (Eve ELO {self.chess.engine.elo}, turn: {self.chess.engine.turn})")
            game_context = "; ".join(game_contexts)

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
            await self.broadcast("mood_updated", self.brain.mood.get_state())
        except Exception as e:
            print(f"[Improv Error] {e}")

    async def _visual_perception_loop(self):
        """
        Periodically captures screen or observes scene, analyzes visual changes,
        and triggers spontaneous visual commentary when events occur.
        """
        while self.is_running:
            interval = self.brain.vision.config.capture_interval_sec
            await asyncio.sleep(interval)
            if not self.brain.vision.is_auto_active:
                continue

            try:
                dominant_mood, _ = self.brain.mood.get_dominant_mood()
                mood_directive = self.brain.mood.get_behavioral_directive()
                obs = await asyncio.to_thread(
                    self.brain.vision.perceive,
                    mood_directive=mood_directive,
                    dominant_mood=dominant_mood
                )
                await self.broadcast("vision_updated", self.brain.vision.get_state())

                # If an event occurred or commentary produced and not busy, speak commentary
                if obs.eve_commentary and not self._busy_lock.locked():
                    await self._speak_visual_commentary(obs)
            except Exception as e:
                print(f"[Orchestrator] Visual perception loop error: {e}")

    async def _speak_visual_commentary(self, obs: Any):
        if not obs.eve_commentary or self._busy_lock.locked():
            return
        async with self._busy_lock:
            raw_thought = obs.eve_commentary
            _, clean_response = self.moderator.clean_text(raw_thought)
            speech_text, emotions, actions = ActionParser.parse(clean_response)
            primary_emotion = emotions[0] if emotions else "happy"

            # Apply mood stimulus based on visual scene
            if obs.scene_type == "minecraft_defeat":
                self.brain.mood.apply_stimulus("minecraft_threat", 0.8)
                await self.broadcast("mood_updated", self.brain.mood.get_state())
            elif obs.scene_type == "minecraft_diamond":
                self.brain.mood.apply_stimulus("minecraft_gift", 0.9)
                await self.broadcast("mood_updated", self.brain.mood.get_state())
            elif obs.scene_type in ("chess_gameover", "chess_match"):
                self.brain.mood.apply_stimulus("chess_queen_capture", 0.7)
                await self.broadcast("mood_updated", self.brain.mood.get_state())

            await self.broadcast("ai_response", {
                "user": "Eve (Screen Awareness)",
                "raw": clean_response,
                "speech": speech_text,
                "emotions": emotions,
                "actions": actions,
                "source": "vision"
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

            print(f"[Screen Awareness] [{primary_emotion}] {speech_text}")
            await self.tts.speak(speech_text, on_mouth_update=lambda val: asyncio.create_task(on_mouth_update(val)))

            if self.vts.connected:
                await self.vts.trigger_expression("neutral")
                await self.vts.update_mouth(0.0)

            await self.broadcast("avatar_state", {"mouth_open": 0.0, "emotion": "neutral"})

    async def perceive_screen_now(self, simulated_scene: Optional[str] = None):
        """Triggers an immediate on-demand visual perception scan."""
        dominant_mood, _ = self.brain.mood.get_dominant_mood()
        mood_directive = self.brain.mood.get_behavioral_directive()
        obs = await asyncio.to_thread(
            self.brain.vision.perceive,
            simulated_scene=simulated_scene,
            force_commentary=True,
            mood_directive=mood_directive,
            dominant_mood=dominant_mood
        )
        await self.broadcast("vision_updated", self.brain.vision.get_state())
        if obs.eve_commentary and not self._busy_lock.locked():
            asyncio.create_task(self._speak_visual_commentary(obs))
        return obs

    async def _ingest_message(self, msg: ChatMessage):
        """Filters, broadcasts, and ingests message into ChatCurator."""
        is_safe, clean_input = self.moderator.clean_text(msg.text)
        if not is_safe:
            print(f"[Moderator] Filtered unsafe input from {msg.user}: {msg.text}")

        is_creator_flag = bool(getattr(msg, "is_creator", False) or msg.source in ("creator", "mic"))

        await self.broadcast("chat_received", {
            "user": msg.user,
            "text": clean_input,
            "source": msg.source,
            "is_donation": msg.is_donation,
            "donation_amount": msg.donation_amount,
            "is_creator": is_creator_flag,
            "channel": "creator" if is_creator_flag else "audience"
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
            donation_currency=msg.donation_currency,
            is_creator=is_creator_flag
        )
        await self.broadcast("mood_updated", self.brain.mood.get_state())
        await self.broadcast("relationship_updated", self.brain.relationships.get_state())

        # Process active interactive minigame input
        if self.brain.minigames and self.brain.minigames.session.status == "active":
            game_res = self.brain.minigames.process_chat_input(msg.user, clean_input)
            if game_res is not None:
                is_handled, host_speech = game_res
                await self.broadcast("minigame_updated", self.brain.minigames.get_state())
                if is_handled and host_speech:
                    speech_text, emotions, actions = ActionParser.parse(host_speech)
                    await self.broadcast("ai_response", {
                        "user": "Eve (Game Host)",
                        "raw": host_speech,
                        "speech": speech_text,
                        "emotions": emotions,
                        "actions": actions
                    })

        # Process active storytelling / community RPG vote or action
        if self.brain.storytelling and self.brain.storytelling.session.status in ("active", "voting", "dice_roll"):
            story_res = self.brain.storytelling.process_chat_input(msg.user, clean_input)
            if story_res is not None:
                is_handled, narrative_speech = story_res
                await self.broadcast("story_updated", self.brain.storytelling.get_state())
                if is_handled and narrative_speech:
                    speech_text, emotions, actions = ActionParser.parse(narrative_speech)
                    role_title = self.brain.storytelling.session.eve_role.replace('_', ' ').title()
                    await self.broadcast("ai_response", {
                        "user": f"Eve ({role_title})",
                        "raw": narrative_speech,
                        "speech": speech_text,
                        "emotions": emotions,
                        "actions": actions
                    })

        # Process performance audience cheers (glowstick / encore)
        if any(w in clean_input.lower() for w in ["!glowstick", "!cheer", "!clap", "!encore", "glowstick", "encore"]):
            cheer_type = "encore" if "encore" in clean_input.lower() else "glowstick"
            cnt = self.brain.performance.record_audience_cheer(msg.user, cheer_type)
            await self.broadcast("performance_updated", self.brain.performance.get_state())
            await self.broadcast("audience_cheer", {
                "user": msg.user,
                "type": cheer_type,
                "total_glowsticks": cnt
            })

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
                if not self._busy_lock.locked():
                    async with self._busy_lock:
                        interaction = self.brain.conversation.select_next_interaction()
                        if interaction:
                            await self._execute_interaction(interaction)
                            continue

                # 3. If no interaction ready or currently busy, wait for next message
                try:
                    msg = await asyncio.wait_for(self.chat.get_next_message(), timeout=0.8)
                    await self._ingest_message(msg)
                except asyncio.TimeoutError:
                    pass

            except Exception as e:
                print(f"[Orchestrator Error] {e}")
                await asyncio.sleep(1)

    async def _execute_interaction(self, interaction: ChatInteraction):
        primary = interaction.primary_message
        clean_input = primary.text
        msg_lower = clean_input.lower()
        is_creator = bool(getattr(primary, "is_creator", False) or primary.source in ("creator", "mic"))

        # Check for spontaneous improv command
        if msg_lower.startswith("!improv"):
            if self._busy_lock.locked():
                await self._run_improv()
            else:
                await self.trigger_improv()
            return

        # Check for sing command / request
        if msg_lower.startswith("!sing") or "sing a song" in msg_lower or "nyanyi" in msg_lower or "coba nyanyi" in msg_lower:
            parts = clean_input.split()
            requested_song = None
            if len(parts) > 1 and parts[1] in self.singer.songs:
                requested_song = parts[1]
            await self.perform_song(requested_song, dedication_user=primary.user)
            return

        # Check for Minecraft command / request
        if msg_lower.startswith("!mc") or "main minecraft" in msg_lower or "speedrun minecraft" in msg_lower or "guard me" in msg_lower or "lindungi aku" in msg_lower:
            parts = clean_input.split()
            is_crucial_mc = any(k in msg_lower for k in ["mode", "kompe", "speedrun", "advance", "santai", "stop", "join", "connect", "disconnect", "server"]) or (len(parts) > 1 and parts[1] in ("next", "mode", "stop", "connect", "disconnect"))
            if is_crucial_mc and not is_creator:
                refuse_speech = f"[emotion: sassy] Hehe {primary.user}, pengaturan mode dan server Minecraft cuma boleh diubah sama Creator! Chat bolehnya ajak mabar, minta dilindungi ('guard me'), atau kasih gift ya! [action: pout]"
                await self._speak_response(refuse_speech, user_label="Eve (Minecraft Guard)", is_creator=False)
                return

            if "guard" in msg_lower or "lindungi" in msg_lower or "jaga" in msg_lower:
                target = None
                if len(parts) > 2 and parts[1].lower() == "guard":
                    target = parts[2]
                elif len(parts) > 1 and parts[0].lower() == "!mc" and parts[1].lower() == "guard" and len(parts) > 2:
                    target = parts[2]
                elif primary.source == "minecraft":
                    target = primary.user
                await self.minecraft.guard_player(target)
                self.brain.mood.apply_stimulus("minecraft_threat", 0.7)
                self.brain.relationships.record_gaming_event(target or primary.user, "minecraft", "guard_player", {})
                await self.broadcast("mood_updated", self.brain.mood.get_state())
                await self.broadcast("relationship_updated", self.brain.relationships.get_state())
            elif "dance" in msg_lower or "joget" in msg_lower:
                await self.minecraft.dance()
                self.brain.mood.apply_stimulus("joke", 0.8)
                await self.broadcast("mood_updated", self.brain.mood.get_state())
            elif "gift" in msg_lower or "hadiah" in msg_lower:
                await self.minecraft.gift_nearest()
                self.brain.mood.apply_stimulus("minecraft_gift")
                self.brain.relationships.record_gaming_event(primary.user, "minecraft", "gift", {"item": "Diamond"})
                await self.broadcast("mood_updated", self.brain.mood.get_state())
                await self.broadcast("relationship_updated", self.brain.relationships.get_state())
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
                self.brain.mood.apply_stimulus("chess_start", 0.8)
                await self.broadcast("mood_updated", self.brain.mood.get_state())
            elif len(parts) > 1 and parts[1] == "next":
                await self.minecraft.advance_speedrun()
                self.brain.mood.apply_stimulus("minecraft_speedrun_advance")
                await self.broadcast("mood_updated", self.brain.mood.get_state())
            elif len(parts) > 2 and parts[1] == "attack":
                await self.minecraft.player_attacked_bot(parts[2])
                self.brain.mood.apply_stimulus("minecraft_attacked")
                self.brain.relationships.record_gaming_event(parts[2], "minecraft", "attack", {})
                await self.broadcast("mood_updated", self.brain.mood.get_state())
                await self.broadcast("relationship_updated", self.brain.relationships.get_state())
            elif len(parts) > 2 and parts[1] == "nearby":
                await self.minecraft.player_joined_proximity(parts[2])
            else:
                await self.minecraft.set_mode("santai")
            return

        # Check for Chess commands / requests
        if msg_lower.startswith("!chess") or msg_lower.startswith("!catur") or "main catur" in msg_lower or "play chess" in msg_lower:
            parts = clean_input.split()
            is_crucial_chess = any(k in msg_lower for k in ["elo", "new", "mulai", "start", "resign", "menyerah"])
            if is_crucial_chess and not is_creator:
                refuse_speech = f"[emotion: smug] Santai dulu {primary.user}, cuma Creator yang berhak atur level ELO dan reset catur! Tapi kalau kamu mau adu taktik langkah per langkah, ketik '!chess move <langkah>' ya! [action: wink]"
                await self._speak_response(refuse_speech, user_label="Eve (Chess Guard)", is_creator=False)
                return

            # ELO command: !chess elo 1500
            if "elo" in msg_lower:
                for idx, p in enumerate(parts):
                    if p.lower() == "elo" and idx + 1 < len(parts):
                        try:
                            elo_val = int(parts[idx + 1])
                            await self.chess.set_elo(elo_val)
                            return
                        except ValueError:
                            pass
            elif "resign" in msg_lower or "menyerah" in msg_lower:
                await self.chess.resign_game()
                self.brain.mood.apply_stimulus("chess_opponent_resigned")
                await self.broadcast("mood_updated", self.brain.mood.get_state())
                return
            elif "move" in msg_lower or "jalan" in msg_lower:
                for idx, p in enumerate(parts):
                    if p.lower() in ("move", "jalan") and idx + 1 < len(parts):
                        move_str = parts[idx + 1]
                        success, err = await self.chess.make_player_move(move_str)
                        if not success:
                            self.brain.mood.apply_stimulus("roast_request", 0.5)
                            await self.broadcast("mood_updated", self.brain.mood.get_state())
                            await self.chess.emit_commentary(f"[emotion: smug] Langkah '{move_str}' tidak valid, {primary.user}! Mau ngeceat di depan grandmaster ya? [action: pout]")
                        return
            elif "new" in msg_lower or "mulai" in msg_lower or "start" in msg_lower or "main catur" in msg_lower or "play chess" in msg_lower:
                player_color = "black" if "black" in msg_lower or "hitam" in msg_lower else "white"
                self.brain.mood.apply_stimulus("chess_start")
                self.brain.relationships.record_gaming_event(primary.user, "chess", "match_start", {})
                await self.broadcast("mood_updated", self.brain.mood.get_state())
                await self.broadcast("relationship_updated", self.brain.relationships.get_state())
                await self.chess.start_game(player_name=primary.user, player_color=player_color)
                return

        # Check for Desktop Companion commands / queries
        is_desktop_command = (
            msg_lower.startswith("!desktop") or
            any(k in msg_lower for k in [
                "buka notepad", "buka calc", "buka spotify", "buka discord", "buka obs",
                "kecilin volume", "turunin volume", "besarin volume", "naikin volume",
                "mute volume", "bisu", "unmute", "suara kekencengan", "suara kecil",
                "next lagu", "pause lagu", "stop lagu", "play lagu", "putar lagu", "setel musik", "ganti lagu"
            ])
        )
        if is_desktop_command:
            if not is_creator:
                self.brain.mood.apply_stimulus("roast_request", 0.6)
                await self.broadcast("mood_updated", self.brain.mood.get_state())
                refuse_speech = f"[emotion: smug] Eits {primary.user}, fitur desktop dan kontrol sistem cuma boleh diatur sama Creator-ku tersayang! Chat cuma boleh nonton dan nikmati stream ya~ [action: wink]"
                await self._speak_response(refuse_speech, user_label="Eve (Security Guard)", is_creator=False)
                return

            desktop_engine = self.brain.desktop
            parts = clean_input.split()
            speech_resp = None
            handled = False

            # Volume
            if any(k in msg_lower for k in ["kecilin volume", "turunin volume", "suara kekencengan", "!desktop volume down"]):
                _, speech_resp = desktop_engine.request_action("volume_control", "adjust_volume", {"delta": -15})
                handled = True
            elif any(k in msg_lower for k in ["besarin volume", "naikin volume", "suara kecil", "!desktop volume up"]):
                _, speech_resp = desktop_engine.request_action("volume_control", "adjust_volume", {"delta": 15})
                handled = True
            elif "mute" in msg_lower or "bisu" in msg_lower or "!desktop mute" in msg_lower:
                _, speech_resp = desktop_engine.request_action("volume_control", "toggle_mute", {})
                handled = True
            elif "!desktop volume" in msg_lower:
                for idx, p in enumerate(parts):
                    if p.lower() == "volume" and idx + 1 < len(parts):
                        try:
                            target_vol = int(parts[idx + 1])
                            _, speech_resp = desktop_engine.request_action("volume_control", "set_volume", {"volume": target_vol})
                            handled = True
                            break
                        except ValueError:
                            pass

            # Media Player
            elif any(k in msg_lower for k in ["pause", "jeda", "stop lagu", "!desktop pause"]):
                _, speech_resp = desktop_engine.request_action("media_control", "play_pause", {})
                handled = True
            elif any(k in msg_lower for k in ["play lagu", "puter lagu", "putar lagu", "setel musik", "!desktop play"]):
                _, speech_resp = desktop_engine.request_action("media_control", "play_pause", {})
                handled = True
            elif any(k in msg_lower for k in ["next lagu", "ganti lagu", "lagu berikutnya", "!desktop next"]):
                _, speech_resp = desktop_engine.request_action("media_control", "next_track", {})
                handled = True

            # App Launch
            elif any(k in msg_lower for k in ["buka ", "!desktop app"]):
                app_target = "notepad.exe"
                if "calc" in msg_lower:
                    app_target = "calc.exe"
                elif "spotify" in msg_lower:
                    app_target = "spotify.exe"
                elif "discord" in msg_lower:
                    app_target = "discord.exe"
                elif "obs" in msg_lower:
                    app_target = "obs64.exe"
                elif "!desktop app" in msg_lower and len(parts) > 2:
                    app_target = parts[2]
                _, speech_resp = desktop_engine.request_action("app_launch", "launch_app", {"app_name": app_target})
                handled = True

            # Notifications
            elif "notifikasi" in msg_lower or "!desktop notif" in msg_lower:
                _, speech_resp = desktop_engine.request_action("notifications_read", "read_notification", {})
                handled = True

            # General Status
            elif "!desktop" in msg_lower or "desktop companion" in msg_lower:
                st = "AKTIF" if desktop_engine.config.master_enabled else "MATI"
                speech_resp = f"[emotion: happy] Mode Desktop Companion lagi {st}! Eve bisa bantu atur volume ({desktop_engine.config.current_volume}%), kontrol musik, buka aplikasi, dan cek notifikasi sesuai izin kamu! [action: wink]"
                handled = True

            if handled and speech_resp:
                await self.broadcast("desktop_updated", desktop_engine.get_state())
                await self._speak_response(speech_resp, user_label="Eve (Desktop Companion)")
                return

        # Game context
        game_contexts = []
        if self.minecraft.connection_status == "connected":
            srv = self.minecraft.active_server.get("name", "Minecraft Server") if self.minecraft.active_server else "Minecraft"
            mode_desc = f"mode={self.minecraft.current_mode}"
            if self.minecraft.current_mode == "guard":
                mode_desc += f", bodyguarding {self.minecraft.guard_target or 'player'}"
            game_contexts.append(f"Playing in Minecraft ({srv}, {mode_desc}, health={self.minecraft.health}/20)")
        if self.chess.is_active:
            game_contexts.append(f"Playing Chess against {self.chess.player_name} (Eve ELO {self.chess.engine.elo}, turn: {self.chess.engine.turn})")
        game_context = "; ".join(game_contexts)

        is_donation = (interaction.interaction_type == "donation")
        is_group_debate = (interaction.interaction_type == "group_debate")
        debate_users = [primary.user] + [m.user for m in interaction.related_messages] if is_group_debate else None

        if primary.source == "minecraft":
            llm_input = f"[Minecraft In-Game Chat from {primary.user}]: {clean_input}\n(You are currently inside Minecraft playing with them! Respond directly to {primary.user} in 1-2 witty sentences)"
        elif primary.source == "mic":
            llm_input = f"[Spoken Voice from Creator/User via Microphone]: {clean_input}\n(They are speaking directly to you via voice microphone! Answer them directly, naturally, and warmly/playfully in 1-2 sentences with emotion tags)"
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
        elif primary.source == "mic":
            user_label = f"Eve (to {primary.user} 🎙️)"
        else:
            user_label = "Eve"

        channel_name = "creator" if is_creator else "audience"
        await self.broadcast("ai_response", {
            "user": user_label,
            "raw": clean_response,
            "speech": speech_text,
            "emotions": emotions,
            "actions": actions,
            "source": primary.source,
            "is_donation": is_donation,
            "donation_amount": primary.donation_amount,
            "is_creator": is_creator,
            "channel": channel_name
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
        await self.broadcast("mood_updated", self.brain.mood.get_state())

    async def perform_song(self, song_id: Optional[str] = None, dedication_user: Optional[str] = None):
        dominant_mood, _ = self.brain.mood.get_dominant_mood()
        director = self.brain.performance

        # 1. Autonomous Song Selection & Pre-Show MC
        actual_song_id, pre_show_mc = director.start_performance(
            song_id=song_id,
            dominant_mood=dominant_mood,
            dedication_user=dedication_user
        )

        song = self.singer.songs.get(actual_song_id)
        if not song:
            print(f"[Singer] Song '{actual_song_id}' not found.")
            return

        title = song.get("title", actual_song_id)
        await self.broadcast("performance_updated", director.get_state())

        print(f"[Karaoke Director] Eve is starting performance: {title} (Mood: {dominant_mood})")

        # 2. Pre-Show MC Speech
        speech_text, emotions, actions = ActionParser.parse(pre_show_mc)
        primary_emotion = emotions[0] if emotions else "happy"
        await self.broadcast("ai_response", {
            "user": "Eve (AI Idol)",
            "raw": pre_show_mc,
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

        # 3. Synchronized Choreography Performance
        await self.broadcast("song_started", {"song_id": actual_song_id, "title": title})

        line_counter = 0

        async def on_lyric_update(line_text: str, default_emotion: str):
            nonlocal line_counter
            step = director.get_choreography_step_for_line(actual_song_id, line_counter)
            line_counter += 1

            emotion = step.emotion or default_emotion
            print(f"[Stage Choreography] [{step.section.upper()}] [{emotion}] [{step.movement}] ♪ {line_text} ♪")

            if self.vts.connected:
                await self.vts.trigger_expression(emotion)

            await self.broadcast("performance_updated", director.get_state())
            await self.broadcast("lyric_line", {
                "text": line_text,
                "emotion": emotion,
                "section": step.section,
                "movement": step.movement,
                "stage_lighting": step.stage_lighting,
                "crowd_callout": step.crowd_callout,
                "is_singing": True
            })

            # Broadcast avatar dance movement and lighting
            await self.broadcast("avatar_movement", {
                "movement": step.movement,
                "action": step.action,
                "lighting": step.stage_lighting
            })

        async def on_sing_mouth(val: float):
            if self.vts.connected:
                await self.vts.update_mouth(val)
            await self.broadcast("avatar_state", {"mouth_open": val, "is_singing": True})

        await self.singer.sing(
            song_id=actual_song_id,
            on_lyric_update=on_lyric_update,
            on_mouth_update=lambda val: asyncio.create_task(on_sing_mouth(val))
        )

        await self.broadcast("song_ended", {"song_id": actual_song_id, "title": title})

        # 4. Post-Show MC & Self Evaluation
        outro_speech, score = director.finish_performance()
        if hasattr(self.brain, "personality") and self.brain.personality:
            self.brain.personality.record_experience("stage_performance", {"song": actual_song_id, "score": score})
            self.brain.personality.sync_to_mood_baselines(self.brain.mood)
            await self.broadcast("personality_updated", self.brain.personality.get_state())
        await self.broadcast("performance_updated", director.get_state())

        speech_text, emotions, actions = ActionParser.parse(outro_speech)
        primary_emotion = emotions[0] if emotions else "blush"
        await self.broadcast("ai_response", {
            "user": "Eve (AI Idol)",
            "raw": outro_speech,
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
        await self.evaluate_goal_event("player_greeted", {"player": sender})

        # Process in multiplayer social engine and broadcast
        self.brain.multiplayer.process_in_game_chat(sender, message)
        await self.broadcast("multiplayer_updated", self.brain.multiplayer.get_state())

        await self.chat.put_message(user=sender, text=message, source="minecraft")

    async def _speak_response(self, speech_raw: str, user_label: str = "Eve", is_creator: bool = True):
        speech_text, emotions, actions = ActionParser.parse(speech_raw)
        primary_emotion = emotions[0] if emotions else "neutral"

        await self.broadcast("ai_response", {
            "user": user_label,
            "raw": speech_raw,
            "speech": speech_text,
            "emotions": emotions,
            "actions": actions,
            "is_creator": is_creator,
            "channel": "creator" if is_creator else "audience"
        })

        if self.vts.connected:
            await self.vts.trigger_expression(primary_emotion)

        async def on_mouth_update(val: float):
            if self.vts.connected:
                await self.vts.update_mouth(val)
            await self.broadcast("avatar_state", {"mouth_open": val, "emotion": primary_emotion})

        print(f"[{user_label}] [{primary_emotion}] {speech_text}")
        await self.tts.speak(speech_text, on_mouth_update=lambda val: asyncio.create_task(on_mouth_update(val)))

        if self.vts.connected:
            await self.vts.trigger_expression("neutral")
            await self.vts.update_mouth(0.0)

        await self.broadcast("avatar_state", {"mouth_open": 0.0, "emotion": "neutral"})

    async def _on_chess_commentary(self, speech_raw: str):
        await self._speak_response(speech_raw, user_label="Eve (Chess)")

    async def _on_chess_state_change(self, state: Dict[str, Any]):
        await self.broadcast("chess_state", state)

    async def _on_chess_game_event(self, event_type: str, data: Dict[str, Any]):
        if event_type == "queen_captured":
            self.brain.episodic_memory.on_chess_queen_capture(
                player=data.get("player", "Player"),
                eve_captured_player_queen=True,
                san=data.get("san", "")
            )
            self.brain.mood.apply_stimulus("chess_queen_capture")
            self.brain.relationships.record_gaming_event(data.get("player", "Player"), "chess", "queen_captured", data)
        elif event_type == "game_over":
            self.brain.episodic_memory.on_chess_game_ended(
                player=data.get("player", "Player"),
                eve_won=data.get("eve_won", False),
                player_won=data.get("player_won", False),
                result=data.get("result", "finished"),
                moves_count=data.get("moves_count", 0),
                elo=data.get("elo", 1200)
            )
            self.brain.relationships.record_gaming_event(data.get("player", "Player"), "chess", "game_over", data)
            if data.get("eve_won"):
                self.brain.mood.apply_stimulus("chess_victory")
                if hasattr(self.brain, "personality") and self.brain.personality:
                    self.brain.personality.record_experience("game_victory", {"game": "chess", "opponent": data.get("player")})
                    self.brain.personality.sync_to_mood_baselines(self.brain.mood)
                await self.evaluate_goal_event("chess_game_won", data)
            elif data.get("player_won"):
                self.brain.mood.apply_stimulus("chess_defeat")
                if hasattr(self.brain, "personality") and self.brain.personality:
                    self.brain.personality.record_experience("game_defeat", {"game": "chess", "opponent": data.get("player")})
                    self.brain.personality.sync_to_mood_baselines(self.brain.mood)
        await self.broadcast("memory_updated", self.brain.episodic_memory.get_stats())
        await self.broadcast("mood_updated", self.brain.mood.get_state())
        await self.broadcast("relationship_updated", self.brain.relationships.get_state())
        if hasattr(self.brain, "personality") and self.brain.personality:
            await self.broadcast("personality_updated", self.brain.personality.get_state())

    async def evaluate_goal_event(self, event_type: str, data: Dict[str, Any]):
        """Evaluates domain events against autonomous active subtasks."""
        res = self.brain.goals.evaluate_event(event_type, data)
        if res.get("advanced"):
            details = res.get("details", {})
            if details.get("goal_completed"):
                self.brain.mood.apply_stimulus("goal_all_completed")
                g_dict = details.get("goal", {})
                if hasattr(self.brain, "personality") and self.brain.personality:
                    self.brain.personality.record_experience("challenge_completed", {"task": g_dict.get("title")})
                    self.brain.personality.sync_to_mood_baselines(self.brain.mood)
                    await self.broadcast("personality_updated", self.brain.personality.get_state())
                self.brain.episodic_memory.record_episode(
                    title=f"Misi Selesai: {g_dict.get('title')}",
                    content=f"Eve berhasil menyelesaikan seluruh target '{g_dict.get('title')}' secara mandiri!",
                    episode_type="achievement",
                    user="Stream",
                    emotional_tag="happy",
                    importance_score=0.9
                )
                await self.broadcast("goal_completed", details)
                await self.broadcast("memory_updated", self.brain.episodic_memory.get_stats())
            elif details.get("subtask_completed"):
                self.brain.mood.apply_stimulus("goal_milestone_completed")

            await self.broadcast("goal_updated", self.brain.goals.get_state())
            await self.broadcast("mood_updated", self.brain.mood.get_state())
