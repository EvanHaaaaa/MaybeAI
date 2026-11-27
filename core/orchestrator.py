import asyncio
import base64
import copy
import inspect
import json
import os
import re
import time
from typing import Dict, Any, Optional, Set, Callable, List
from core.brain import Brain
from core.config_manager import ConfigManager
from core.metrics import MetricsCollector
from core.tts import TTSEngine
from core.vts_client import VTSClient
from core.chat_receiver import ChatReceiver, ChatMessage
from core.platforms import YouTubeLiveAdapter, DiscordAdapter, TikTokLiveAdapter
from core.moderator import Moderator
from core.actions import ActionParser
from core.singer import Singer
from core.stt import STTEngine, StreamingSTTSession
from core.planning.executor import AutonomousMissionExecutor
from core.collab.manager import CollabManager
from core.collab.protocol import CollabEnvelope
from core.plugins.registry import PluginRegistry
from core.minecraft.controller import MinecraftController
from core.chess.controller import ChessController
from core.conversation.chat_curator import ChatInteraction
from core.desktop.obs_client import OBSWebSocketClient
from core.highlights import HighlightDetector, ClipPipeline, VODSummarizer
from core.event_bus import (
    EventBus,
    WS_TO_BUS_EVENT,
    BUS_TO_WS_EVENT,
    INTERACTION_STARTED,
    COLLAB_STATE,
)

_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"\bignore\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions?|prompts?|rules?)\b", re.IGNORECASE),
    re.compile(r"\bdisregard\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions?|prompts?|rules?)\b", re.IGNORECASE),
    re.compile(r"\boverride\s+(?:system|safety|developer)\s+(?:instructions?|prompt|rules?)\b", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*(?:system\s+prompt\s*:|<\|im_start\|>\s*system|###\s*system\b)", re.IGNORECASE),
    re.compile(r"\b(?:jailbreak|dan\s+mode|developer\s+mode\s+enabled|act\s+as\s+an?\s+unrestricted)\b", re.IGNORECASE),
)


class Orchestrator:
    """
    The Master Conductor coordinating:
    Chat -> Filter -> Brain -> Action/Emotion Parse -> VTS/Avatar -> TTS Voice -> Web Clients
    """

    def __init__(self, config_dir: str = "config", event_bus: Optional[EventBus] = None):
        self.config_dir = config_dir
        self.event_bus = event_bus if event_bus is not None else EventBus()
        self.metrics = MetricsCollector()
        self.brain = Brain(f"{config_dir}/settings.json", f"{config_dir}/character.json")
        # Share the same EventBus instance between Orchestrator and ConversationEngine
        self.brain.conversation.event_bus = self.event_bus
        settings = self.brain.settings

        # Load Moderator config
        mod_cfg = settings.get("moderator", {})
        self.moderator = Moderator(
            f"{config_dir}/filter_words.json",
            max_message_length=mod_cfg.get("max_message_length", 250),
            strict_mode=mod_cfg.get("strict_mode", True)
        )
        self._prompt_injection_filter: bool = bool(mod_cfg.get("prompt_injection_filter", True))
        
        # Load TTS config
        tts_cfg = settings.get("tts", {})
        tts_output_mode = tts_cfg.get("output_mode", "both")
        rvc_enabled = bool(tts_cfg.get("rvc_enabled", False))
        rvc_url = str(tts_cfg.get("rvc_url", "") or "")
        rvc_pitch_shift = int(tts_cfg.get("rvc_pitch_shift", 0) or 0)
        self.tts = TTSEngine(
            voice=tts_cfg.get("voice", "en-US-AnaNeural"),
            rate=tts_cfg.get("rate", "+5%"),
            pitch=tts_cfg.get("pitch", "+10Hz"),
            enabled=tts_cfg.get("enabled", True),
            interruptible=tts_cfg.get("interruptible", True),
            output_mode=tts_output_mode,
            on_audio_ready=self._on_tts_audio_ready,
            provider=str(tts_cfg.get("provider", "edge-tts") or "edge-tts"),
            rvc_enabled=rvc_enabled,
            rvc_url=rvc_url,
            rvc_pitch_shift=rvc_pitch_shift,
            elevenlabs_voice_id=str(tts_cfg.get("elevenlabs_voice_id", "") or ""),
            kokoro_url=str(tts_cfg.get("kokoro_url", "") or ""),
            custom_tts_url=str(tts_cfg.get("custom_tts_url", "") or ""),
        )

        # Load STT / Full-Duplex Voice config
        stt_cfg = settings.get("stt", {}) if isinstance(settings, dict) else {}
        self.stt = STTEngine(
            model_name=stt_cfg.get("model", "base"),
            device=stt_cfg.get("device", "cpu"),
            enabled=stt_cfg.get("enabled", False),
            vad_enabled=stt_cfg.get("vad_enabled", True),
            vad_energy_threshold=float(stt_cfg.get("vad_energy_threshold", 0.02) or 0.02),
            barge_in_enabled=stt_cfg.get("barge_in_enabled", True),
        )
        self.voice_session = StreamingSTTSession(stt_engine=self.stt)

        # Load VTS config
        vts_cfg = settings.get("vts", {})
        self.vts = VTSClient(
            host=vts_cfg.get("host", "localhost"),
            port=vts_cfg.get("port", 8001),
            plugin_name=vts_cfg.get("plugin_name", "MaybeAI-VTuber"),
            auto_reconnect=bool(vts_cfg.get("auto_reconnect", True)),
        )

        # OBS Showrunner Client
        obs_cfg = settings.get("obs", {}) if isinstance(settings, dict) else {}
        obs_password = str(obs_cfg.get("password") or "").strip()
        if not obs_password or obs_password == "********":
            obs_password = os.getenv("OBS_WS_PASSWORD", "").strip()
        obs_host = str(obs_cfg.get("host") or os.getenv("OBS_WS_HOST", "localhost") or "localhost").strip()
        obs_port = int(obs_cfg.get("port") or os.getenv("OBS_WS_PORT", 4455) or 4455)
        self.obs = OBSWebSocketClient(
            host=obs_host,
            port=obs_port,
            password=obs_password,
            enabled=bool(obs_cfg.get("enabled", False)),
        )
        if hasattr(self.brain, "desktop") and hasattr(self.brain.desktop, "set_obs_client"):
            self.brain.desktop.set_obs_client(self.obs)
        if hasattr(self.brain, "performance"):
            self.brain.performance.scene_switcher = self._switch_obs_scene

        # Singer (Karaoke Engine)
        self.singer = Singer(
            songs_config_path=f"{config_dir}/songs.json",
            voice=tts_cfg.get("voice", "en-US-AnaNeural"),
            output_mode=tts_output_mode,
            rvc_enabled=rvc_enabled,
            rvc_url=rvc_url,
            rvc_pitch_shift=rvc_pitch_shift,
        )

        # Minecraft Gameplay Controller
        self.minecraft = MinecraftController(bot_name="EveMaybe")
        self.minecraft.set_callbacks(
            on_commentary=self._on_minecraft_commentary,
            on_state_change=self._on_minecraft_state_change,
            on_in_game_chat=self._on_in_game_chat,
            on_telemetry=self._on_minecraft_telemetry,
        )

        # Chess Gameplay Controller
        self.chess = ChessController(bot_name="EveMaybe")
        self.chess.set_callbacks(
            on_commentary=self._on_chess_commentary,
            on_state_change=self._on_chess_state_change,
            on_game_event=self._on_chess_game_event
        )

        self.chat = ChatReceiver()
        self._configure_platform_adapters(settings)

        # Autonomous Closed-Loop Mission Executor
        auto_cfg = settings.get("autonomous_agent", {}) if isinstance(settings, dict) else {}
        self.missions = AutonomousMissionExecutor(
            goal_engine=self.brain.goals,
            mood_engine=self.brain.mood,
            minecraft=self.minecraft,
            chess=self.chess,
            performance_runner=self.perform_song,
            speak_fn=self._speak_mission_commentary,
            event_bus=self.event_bus,
            human_approval_required=bool(auto_cfg.get("human_approval_required", False)),
            tick_interval_sec=float(auto_cfg.get("mission_tick_interval_sec", 25.0) or 25.0),
            enabled=bool(auto_cfg.get("closed_loop_missions", True) and auto_cfg.get("enabled", True)),
            scene_switcher=self._switch_obs_scene,
        )

        # AI VTuber Collab Manager
        self.collab = CollabManager(
            settings=settings,
            event_bus=self.event_bus,
            self_name="EveMaybe",
        )
        self.collab.set_reply_callback(self._on_collab_reply_needed)
        collab_action_cbs: Dict[str, Any] = {
            "on_duet_sync": self._on_collab_duet_sync,
            "on_emote_sync": self._on_collab_emote_sync,
            "on_game_move": self._on_collab_game_move,
        }
        if "on_hello" in inspect.signature(self.collab.set_action_callbacks).parameters:
            collab_action_cbs["on_hello"] = self._on_collab_hello
        self.collab.set_action_callbacks(**collab_action_cbs)

        # Sync Vision VLM settings
        vision_cfg = settings.get("vision", {}) if isinstance(settings, dict) else {}
        if hasattr(self.brain, "vision"):
            self.brain.vision.vlm_enabled = bool(vision_cfg.get("vlm_enabled", False))
            self.brain.vision.vlm_interval_sec = float(vision_cfg.get("vlm_interval_sec", 8.0) or 8.0)

        # Community Plugin SDK Registry
        plugins_cfg = settings.get("plugins", {}) if isinstance(settings, dict) else {}
        self.plugins = PluginRegistry(
            plugins_dir=plugins_cfg.get("plugins_dir", "plugins"),
            enabled_plugins=plugins_cfg.get("enabled_plugins", ["word_chain"]),
            hook_timeout_sec=float(plugins_cfg.get("hook_timeout_sec", 5.0) or 5.0),
            enabled=bool(plugins_cfg.get("enabled", True)),
            sandbox_mode=str(plugins_cfg.get("sandbox_mode", "subprocess") or "subprocess"),
            event_bus=self.event_bus,
            speak_cb=self._speak_plugin_response,
            broadcast_cb=self.broadcast,
            settings=settings,
        )
        self._plugins_discovered: bool = False
        self.plugins.attach_to_event_bus(self.event_bus)

        # Highlight Auto-Marker, Vertical Clip Pipeline & VOD Summarizer
        highlights_cfg = settings.get("highlights", {}) if isinstance(settings, dict) else {}
        self.highlights = HighlightDetector(
            event_bus=self.event_bus,
            on_save_replay=self._on_highlight_save_replay,
            chat_burst_threshold=int(highlights_cfg.get("chat_burst_threshold", 8) or 8),
            cooldown_sec=float(highlights_cfg.get("cooldown_sec", 30.0) or 30.0),
            enabled=bool(highlights_cfg.get("enabled", True)),
        )
        data_root = os.getenv("MAYBEAI_DATA_DIR", "").strip()
        clips_dir = os.path.join(data_root, "clips") if data_root else "data/clips"
        streams_dir = os.path.join(data_root, "second_brain", "streams") if data_root else "data/second_brain/streams"
        self.clipper = ClipPipeline(clips_dir=clips_dir)
        self.vod_summarizer = VODSummarizer(
            streams_dir=streams_dir,
            event_bus=self.event_bus,
        )

        self.is_running = False
        self._busy_lock = asyncio.Lock()
        self._busy_owner_task: Optional[asyncio.Task] = None
        self._speech_lock = asyncio.Lock()
        self._bg_tasks: Set[asyncio.Task] = set()
        self._current_emotion: str = "neutral"
        self._active_interaction_task: Optional[asyncio.Task] = None
        self.barge_in_count: int = 0
        self._collab_peer_connected: bool = False
        self.web_listeners: Set[Callable[[Dict[str, Any]], None]] = set()
        self.event_bus.subscribe("*", self._dispatch_to_web_listeners)
        self.event_bus.subscribe(COLLAB_STATE, self._on_collab_state_changed)

    async def _switch_obs_scene(self, scene_name: str, reason: str = "") -> Dict[str, Any]:
        """Switches OBS scene via OBSWebSocketClient and broadcasts obs_scene_changed."""
        obs_cfg = self.brain.settings.get("obs", {}) if isinstance(self.brain.settings, dict) else {}
        auto_switch = bool(obs_cfg.get("auto_scene_switch", True))
        if not auto_switch and reason != "manual":
            return {"success": False, "skipped": True, "scene": scene_name, "reason": reason}
        res = await self.obs.switch_scene(scene_name, reason=reason)
        if res.get("success"):
            await self.broadcast("obs_scene_changed", {
                "scene": res.get("scene", scene_name),
                "reason": reason,
                "status": self.obs.get_status(),
            })
        return res

    async def switch_obs_scene(self, scene_name: str, reason: str = "manual") -> Dict[str, Any]:
        """Public wrapper for manual or API-triggered OBS scene switches."""
        return await self._switch_obs_scene(scene_name, reason=reason)

    async def _connect_obs_and_replay(self) -> None:
        ok = await self.obs.connect()
        if ok:
            obs_cfg = self.brain.settings.get("obs", {}) if isinstance(self.brain.settings, dict) else {}
            if obs_cfg.get("replay_buffer_enabled", True):
                await self.obs.start_replay_buffer()

    async def _on_collab_state_changed(self, _event_name: str, payload: Dict[str, Any]) -> None:
        peer_connected = bool(payload.get("peer_connected", False))
        if peer_connected and not self._collab_peer_connected:
            self._collab_peer_connected = True
            await self._switch_obs_scene("Collab Split-Screen", reason="collab_peer_connected")
        elif not peer_connected:
            self._collab_peer_connected = False

    async def _on_highlight_save_replay(self, _marker: Any) -> Dict[str, Any]:
        obs_cfg = self.brain.settings.get("obs", {}) if isinstance(self.brain.settings, dict) else {}
        if self.obs.is_connected and bool(obs_cfg.get("replay_buffer_enabled", True)):
            return await self.obs.save_replay_buffer()
        return {"success": False, "skipped": True}

    def _spawn_bg_task(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        self.metrics.set_gauge("bg_tasks_active", sum(1 for t in self._bg_tasks if not t.done()))

        def _on_done(done_task: asyncio.Task) -> None:
            self._bg_tasks.discard(done_task)
            self.metrics.set_gauge("bg_tasks_active", sum(1 for t in self._bg_tasks if not t.done()))

        task.add_done_callback(_on_done)
        return task

    @staticmethod
    def _accepts_kwarg(fn: Any, kwarg: str) -> bool:
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return False
        for param in sig.parameters.values():
            if param.kind == inspect.Parameter.VAR_KEYWORD or param.name == kwarg:
                return True
        return False

    @staticmethod
    def _mask_settings_for_broadcast(settings: Dict[str, Any]) -> Dict[str, Any]:
        masked = copy.deepcopy(settings) if isinstance(settings, dict) else {}
        for sec_name, key_name, flag_name in ConfigManager.SECRET_MASK_FIELDS:
            sec_obj = masked.get(sec_name)
            if isinstance(sec_obj, dict):
                raw_val = sec_obj.get(key_name, "")
                is_set = bool(raw_val)
                sec_obj[key_name] = "********" if is_set else ""
                sec_obj[flag_name] = bool(raw_val and raw_val != "********")
        return masked

    @staticmethod
    def _detect_audio_mime(audio_bytes: bytes) -> str:
        """Infers MIME type from audio container magic bytes."""
        if len(audio_bytes) >= 12 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
            return "audio/wav"
        if audio_bytes.startswith(b"OggS"):
            return "audio/ogg"
        if audio_bytes.startswith(b"fLaC"):
            return "audio/flac"
        if audio_bytes.startswith(b"ID3") or (
            len(audio_bytes) >= 2 and audio_bytes[0] == 0xFF and (audio_bytes[1] & 0xE0) == 0xE0
        ):
            return "audio/mpeg"
        return "audio/mpeg"

    async def _on_tts_audio_ready(
        self,
        audio_bytes: bytes,
        text: str,
        voice: str,
        mime: Optional[str] = None,
    ) -> None:
        if not audio_bytes:
            return
        resolved_mime = mime.strip() if isinstance(mime, str) and mime.strip() else self._detect_audio_mime(audio_bytes)
        await self.broadcast("audio_chunk", {
            "audio_b64": base64.b64encode(audio_bytes).decode("ascii"),
            "mime": resolved_mime,
            "text": text,
            "voice": voice,
            "emotion": self._current_emotion,
        })

    def _configure_platform_adapters(self, settings: Dict[str, Any]) -> None:
        """Instantiates and registers YouTube Live & Discord chat adapters from settings/env."""
        yt_cfg = settings.get("youtube", {}) if isinstance(settings, dict) else {}
        yt_key = str(yt_cfg.get("api_key") or "").strip()
        if not yt_key or yt_key == "********":
            yt_key = os.getenv("YOUTUBE_API_KEY", "").strip()
        yt_adapter = YouTubeLiveAdapter(
            receiver=self.chat,
            api_key=yt_key,
            live_chat_id=str(yt_cfg.get("live_chat_id") or "").strip(),
            poll_interval_sec=float(yt_cfg.get("poll_interval_sec", 5.0) or 5.0),
            enabled=bool(yt_cfg.get("enabled", False)),
        )
        self.chat.register_adapter(yt_adapter)

        dc_cfg = settings.get("discord", {}) if isinstance(settings, dict) else {}
        dc_token = str(dc_cfg.get("bot_token") or "").strip()
        if not dc_token or dc_token == "********":
            dc_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        dc_adapter = DiscordAdapter(
            receiver=self.chat,
            bot_token=dc_token,
            channel_id=str(dc_cfg.get("channel_id") or "").strip(),
            poll_interval_sec=float(dc_cfg.get("poll_interval_sec", 3.0) or 3.0),
            enabled=bool(dc_cfg.get("enabled", False)),
            use_gateway=bool(dc_cfg.get("use_gateway", False)),
        )
        self._discord_adapter = dc_adapter
        self._discord_reply_enabled = bool(dc_cfg.get("reply_enabled", False))
        self.chat.register_adapter(dc_adapter)

        tt_cfg = settings.get("tiktok", {}) if isinstance(settings, dict) else {}
        tt_adapter = TikTokLiveAdapter(
            receiver=self.chat,
            username=str(tt_cfg.get("username") or "").strip(),
            webcast_ws_url=str(tt_cfg.get("webcast_ws_url") or "").strip(),
            enabled=bool(tt_cfg.get("enabled", False)),
        )
        self.chat.register_adapter(tt_adapter)

    @property
    def is_busy(self) -> bool:
        return self._busy_lock.locked()

    def register_listener(self, callback: Callable[[Dict[str, Any]], None]):
        self.web_listeners.add(callback)
        self.metrics.set_gauge("active_ws_clients", len(self.web_listeners))

    def unregister_listener(self, callback: Callable[[Dict[str, Any]], None]):
        self.web_listeners.discard(callback)
        self.metrics.set_gauge("active_ws_clients", len(self.web_listeners))

    def get_metrics(self) -> Dict[str, Any]:
        """Returns a JSON-serializable snapshot of runtime observability metrics."""
        bus_stats = self.event_bus.get_stats()
        self.metrics.set_counter("event_bus_published", int(bus_stats.get("total_published", 0)))
        self.metrics.set_counter("event_bus_errors", int(bus_stats.get("handler_errors", 0)))
        self.metrics.set_gauge("active_ws_clients", len(self.web_listeners))
        self.metrics.set_gauge(
            "bg_tasks_active",
            sum(1 for t in self._bg_tasks if not t.done()),
        )
        return self.metrics.snapshot()

    async def _speak_with_metrics(self, speech_text: str, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        try:
            return await self.tts.speak(speech_text, **kwargs)
        finally:
            self.metrics.observe("tts_latency_ms", (time.perf_counter() - t0) * 1000.0)

    async def _dispatch_to_web_listeners(self, event_name: str, payload: Dict[str, Any]):
        ws_type = BUS_TO_WS_EVENT.get(event_name, event_name)
        message = {"type": ws_type, "data": payload}
        listeners = list(self.web_listeners)
        if not listeners:
            return

        async def _send_one(listener: Callable[[Dict[str, Any]], Any]) -> None:
            try:
                res = listener(message)
                if inspect.isawaitable(res):
                    await asyncio.wait_for(res, timeout=2.0)
            except Exception:
                self.web_listeners.discard(listener)
                self.metrics.set_gauge("active_ws_clients", len(self.web_listeners))

        await asyncio.gather(*(_send_one(l) for l in listeners), return_exceptions=True)

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        bus_event = WS_TO_BUS_EVENT.get(event_type, event_type)
        await self.event_bus.publish(bus_event, data)

    async def start(self):
        self.is_running = True
        print("[Orchestrator] Starting MaybeAI Engine...")

        # Connect to VTube Studio in background if enabled
        if self.brain.settings.get("vts", {}).get("enabled", True):
            self._spawn_bg_task(self.vts.connect())

        # Connect to OBS Studio in background if enabled
        if self.obs.enabled:
            self._spawn_bg_task(self._connect_obs_and_replay())

        # Connect to Twitch if enabled
        twitch_cfg = self.brain.settings.get("twitch", {})
        if twitch_cfg.get("enabled", False) and twitch_cfg.get("channel"):
            raw_port = twitch_cfg.get("port")
            self._spawn_bg_task(
                self.chat.start_twitch_listener(
                    channel=twitch_cfg["channel"],
                    bot_nick=twitch_cfg.get("bot_nick", ""),
                    oauth=twitch_cfg.get("oauth_token", ""),
                    use_tls=bool(twitch_cfg.get("use_tls", True)),
                    port=int(raw_port) if raw_port else None,
                )
            )

        # Start configured multi-platform chat adapters (YouTube Live, Discord)
        await self.chat.start_adapters()
        await self.broadcast("platform_status", self.chat.get_platforms_status())

        # Discover and load configured community plugins
        await self.ensure_plugins_loaded()

        # Start closed-loop autonomous mission executor if enabled
        if self.missions.enabled:
            await self.missions.start_loop()

        # Start master processing loop
        self._spawn_bg_task(self._process_chat_loop())
        # Start spontaneous banter / idle stream thoughts loop
        self._spawn_bg_task(self._idle_banter_loop())
        # Start visual perception / screen awareness loop
        self._spawn_bg_task(self._visual_perception_loop())

    async def shutdown(self):
        """Gracefully stops background loops and closes external client sessions."""
        self.is_running = False
        task = self._active_interaction_task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.wait({task}, timeout=0.5)
        self._active_interaction_task = None

        bg_tasks = [t for t in list(self._bg_tasks) if not t.done()]
        for bg in bg_tasks:
            bg.cancel()
        if bg_tasks:
            await asyncio.wait(bg_tasks, timeout=1.0)
        self._bg_tasks.clear()

        bot_proc = getattr(self.minecraft, "bot_process", None)
        if bot_proc is not None and bot_proc.poll() is None:
            try:
                bot_proc.terminate()
                bot_proc.wait(timeout=2.0)
            except Exception:
                try:
                    bot_proc.kill()
                except Exception:
                    pass
            self.minecraft.bot_process = None

        await self.missions.stop_loop()
        await self.collab.shutdown()
        await self.plugins.shutdown()
        highlights_cfg = self.brain.settings.get("highlights", {}) if isinstance(self.brain.settings, dict) else {}
        if getattr(self, "vod_summarizer", None) is not None and bool(highlights_cfg.get("vod_summary_enabled", True)):
            try:
                await asyncio.to_thread(self.vod_summarizer.generate_summary, event_bus=self.event_bus)
            except Exception as exc:
                print(f"[Orchestrator] VOD summary generation error: {exc}")
        self.chat.stop()
        await self.chat.stop_adapters()
        await self.obs.disconnect()
        await self.vts.disconnect()
        for component in (
            getattr(self, "tts", None),
            getattr(self, "stt", None),
            getattr(self, "singer", None),
            getattr(getattr(self.brain, "episodic_memory", None), "embedding_engine", None),
            getattr(self.brain, "embedding_engine", None),
        ):
            if component is None:
                continue
            close_fn = getattr(component, "close", None) or getattr(component, "aclose", None)
            if callable(close_fn):
                try:
                    res = close_fn()
                    if inspect.isawaitable(res):
                        await res
                except Exception:
                    pass
        await self.brain.close()

    async def ensure_plugins_loaded(self) -> None:
        """Lazily discovers and loads configured plugins once."""
        if not self._plugins_discovered:
            self._plugins_discovered = True
            await self.plugins.discover_plugins()

    async def process_voice_chunk(
        self,
        pcm_bytes: bytes,
        user: str = "Creator",
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Processes a raw PCM16 creator voice chunk through EnergyVAD + StreamingSTTSession.
        Triggers barge-in on voice onset when Eve is busy/speaking and forwards final transcripts.
        """
        t0 = time.perf_counter()
        res = await self.voice_session.feed_pcm_chunk(pcm_bytes, language=language)
        if res.get("transcript") or res.get("speech_ended"):
            self.metrics.observe("stt_latency_ms", (time.perf_counter() - t0) * 1000.0)

        if res.get("speech_started") or res.get("speech_ended") or res.get("is_speech"):
            await self.broadcast("voice_vad_state", {
                "is_speech": bool(res.get("is_speech")),
                "speech_started": bool(res.get("speech_started")),
                "speech_ended": bool(res.get("speech_ended")),
                "rms": float(res.get("rms", 0.0)),
            })

        if res.get("speech_started") and self.stt.vad_enabled:
            if self.is_busy or bool(getattr(self.tts, "is_speaking", False)):
                res["barge_in"] = await self.barge_in(source="creator", reason="vad")

        transcript = (res.get("transcript") or "").strip()
        partial_text = str(res.get("partial") or res.get("partial_transcript") or "").strip()
        if partial_text or (
            not transcript
            and res.get("is_speech")
            and getattr(self.voice_session, "_in_utterance", False)
        ):
            await self.broadcast("stt_partial", {
                "user": user,
                "text": partial_text or "Listening...",
                "is_speech": bool(res.get("is_speech")),
                "rms": float(res.get("rms", 0.0)),
                "buffered_bytes": int(getattr(self.voice_session, "_buffered_bytes", 0)),
            })

        if transcript:
            await self.broadcast("stt_final", {
                "user": user,
                "text": transcript,
                "rms": float(res.get("rms", 0.0)),
            })
            await self.chat.put_message(user=user, text=transcript, source="mic", is_creator=True)

        return res

    async def _speak_mission_commentary(self, text: str) -> None:
        if not text:
            return
        if not self._busy_lock.locked():
            async with self._busy_lock:
                await self._speak_response(text, user_label="Eve (Mission)")
        else:
            speech_text, emotions, actions = ActionParser.parse(text)
            await self.broadcast("ai_response", {
                "user": "Eve (Mission)",
                "raw": text,
                "speech": speech_text,
                "emotions": emotions,
                "actions": actions,
                "is_creator": False,
                "channel": "audience",
            })

    async def _speak_plugin_response(self, text: str, user_label: str = "Eve (Plugin)") -> None:
        if not text:
            return
        await self._speak_response(text, user_label=user_label, is_creator=False)

    async def _on_collab_reply_needed(self, env: CollabEnvelope) -> None:
        """Generates Eve's reply when a collab peer yields the turn and sends it back."""
        if self.collab.turn_count >= self.collab.max_collab_turns:
            return

        peer_name = env.sender_name or env.sender_id or self.collab.peer_name or "Peer"
        topic_ctx = f" (topic: {env.topic})" if env.topic else ""
        llm_input = (
            f"[AI VTuber Collab from {peer_name}{topic_ctx}]: {env.speech}\n"
            f"(Reply naturally as Eve Maybe to fellow AI VTuber {peer_name} in 1-2 witty sentences with emotion tags)"
        )

        gen_kwargs: Dict[str, Any] = {
            "user_name": peer_name,
            "message": llm_input,
            "game_context": f"AI VTuber Collab with {peer_name}",
        }
        if self._accepts_kwarg(self.brain.generate_response, "is_creator"):
            gen_kwargs["is_creator"] = False
        self.metrics.inc("llm_requests")
        try:
            raw_reply = await self.brain.generate_response(**gen_kwargs)
        except Exception:
            self.metrics.inc("llm_failovers")
            raise
        _, clean_reply = self.moderator.clean_text(raw_reply)
        speech_text, emotions, _ = ActionParser.parse(clean_reply)
        primary_emotion = emotions[0] if emotions else "happy"

        if not self._busy_lock.locked():
            async with self._busy_lock:
                await self._speak_response(clean_reply, user_label=f"Eve (Collab w/ {peer_name})", is_creator=False)
        else:
            await self.broadcast("ai_response", {
                "user": f"Eve (Collab w/ {peer_name})",
                "raw": clean_reply,
                "speech": speech_text,
                "emotions": emotions,
                "actions": [],
                "is_creator": False,
                "channel": "audience",
            })

        await self.collab.send_utterance(
            speech=speech_text or clean_reply,
            emotion=primary_emotion,
            yield_turn=True,
            topic=env.topic,
        )

    async def _on_collab_hello(self, env: CollabEnvelope) -> None:
        peer_name = env.sender_name or env.sender_id or self.collab.peer_name or "Peer"
        capabilities = env.payload.get("capabilities") if isinstance(env.payload, dict) else None
        payload: Dict[str, Any] = {
            **self.collab.get_status(),
            "hello_peer": peer_name,
        }
        if capabilities is not None:
            payload["peer_capabilities"] = capabilities
        await self.broadcast("collab_state", payload)

    async def _on_collab_duet_sync(self, env: CollabEnvelope) -> None:
        song_id = str(env.payload.get("song_id") or env.topic or "").strip() or None
        lyric_index = int(env.payload.get("lyric_index", 0) or 0)
        timestamp = float(env.payload.get("timestamp", 0.0) or 0.0)
        track = str(env.payload.get("track") or "")
        dedication = env.sender_name or env.sender_id or None

        await self.broadcast(
            "collab_duet_sync",
            {
                "song_id": song_id or "",
                "lyric_index": lyric_index,
                "timestamp": timestamp,
                "track": track,
                "peer_name": dedication or self.collab.peer_name,
            },
        )

        if not self._busy_lock.locked() and (song_id or lyric_index == 0):
            async with self._busy_lock:
                self._busy_owner_task = asyncio.current_task()
                try:
                    await self._perform_song_unlocked(song_id=song_id, dedication_user=dedication)
                finally:
                    self._busy_owner_task = None

    async def _on_collab_emote_sync(self, env: CollabEnvelope) -> None:
        emotion = str(env.emotion or env.payload.get("emotion") or "happy").strip() or "happy"
        action = str(env.payload.get("action") or "").strip()
        self._current_emotion = emotion
        vts_params = await self._apply_vts_mood_rig(emotion)
        if action and self.vts.connected:
            try:
                await self.vts.trigger_expression(action)
            except Exception:
                pass
        extra = {"action": action} if action else {}
        await self.broadcast(
            "avatar_state",
            self._build_avatar_state(0.0, emotion, vts_params, **extra),
        )

    async def _on_collab_game_move(self, env: CollabEnvelope) -> None:
        if not getattr(self.chess, "is_active", False):
            return
        game = str(env.payload.get("game") or "").strip().lower()
        if game and game != "chess":
            return
        move_str = str(
            env.payload.get("move")
            or env.payload.get("uci")
            or env.payload.get("san")
            or env.speech
            or ""
        ).strip()
        if move_str:
            await self.chess.make_player_move(move_str)

    async def barge_in(self, source: str = "creator", reason: str = "vad") -> Dict[str, Any]:
        """
        Preempts Eve's active speech/response when the Creator speaks (full-duplex barge-in).
        Never acquires `_busy_lock` so it cannot deadlock with an in-flight interaction.
        """
        settings = self.brain.settings if isinstance(self.brain.settings, dict) else {}
        stt_cfg = settings.get("stt", {}) if isinstance(settings.get("stt"), dict) else {}
        if not bool(stt_cfg.get("barge_in_enabled", True)):
            return {
                "interrupted": False,
                "reason": "barge_in_disabled",
                "source": source,
                "barge_in_count": self.barge_in_count,
            }

        if not bool(getattr(self.tts, "interruptible", True)):
            return {
                "interrupted": False,
                "reason": "tts_not_interruptible",
                "source": source,
                "barge_in_count": self.barge_in_count,
            }

        tts_stopped = bool(self.tts.stop())
        singer_stopped = False
        singer = getattr(self, "singer", None)
        if singer is not None and hasattr(singer, "stop"):
            try:
                singer_stopped = bool(singer.stop())
            except Exception:
                singer_stopped = False

        task_cancelled = False
        task = self._active_interaction_task
        current = asyncio.current_task()
        if task is not None and not task.done() and task is not current:
            task.cancel()
            await asyncio.wait({task}, timeout=0.5)
            if task.done() and not task.cancelled():
                try:
                    _ = task.exception()
                except Exception:
                    pass
            task_cancelled = True
            if self._active_interaction_task is task and task.done():
                self._active_interaction_task = None

        if self.vts.connected:
            try:
                await self.vts.trigger_expression("neutral")
                await self.vts.update_mouth(0.0)
            except Exception:
                pass

        await self.broadcast("avatar_state", {
            "mouth_open": 0.0,
            "emotion": "neutral",
        })

        self.barge_in_count += 1
        payload = {
            "interrupted": True,
            "source": source,
            "reason": reason,
            "tts_stopped": tts_stopped,
            "singer_stopped": singer_stopped,
            "task_cancelled": task_cancelled,
            "barge_in_count": self.barge_in_count,
            "timestamp": time.time(),
        }
        await self.broadcast("voice_barge_in", payload)
        return payload

    def _get_mood_dims(self) -> Optional[Dict[str, float]]:
        mood = getattr(self.brain, "mood", None)
        dims = getattr(mood, "dimensions", None) if mood else None
        return dict(dims) if isinstance(dims, dict) else None

    async def _apply_vts_mood_rig(self, emotion: str, singing: bool = False) -> Optional[Dict[str, float]]:
        mood_dims = self._get_mood_dims()
        if hasattr(self.vts, "apply_mood_rig"):
            try:
                res = self.vts.apply_mood_rig(emotion, mood_dims=mood_dims, singing=singing)
                if inspect.isawaitable(res):
                    res = await res
                return dict(res) if isinstance(res, dict) else None
            except Exception:
                return None
        if self.vts.connected:
            await self.vts.trigger_expression(emotion)
        return None

    @staticmethod
    def _build_avatar_state(
        mouth_open: float,
        emotion: str,
        vts_params: Optional[Dict[str, float]] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "mouth_open": mouth_open,
            "emotion": emotion,
            **extra,
        }
        if vts_params is not None:
            payload["vts_params"] = vts_params
        return payload

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
            pitch=tts_cfg.get("pitch"),
            interruptible=tts_cfg.get("interruptible"),
            output_mode=tts_cfg.get("output_mode"),
            provider=tts_cfg.get("provider"),
            rvc_enabled=tts_cfg.get("rvc_enabled"),
            rvc_url=tts_cfg.get("rvc_url"),
            rvc_pitch_shift=tts_cfg.get("rvc_pitch_shift"),
            elevenlabs_voice_id=tts_cfg.get("elevenlabs_voice_id"),
            kokoro_url=tts_cfg.get("kokoro_url"),
            custom_tts_url=tts_cfg.get("custom_tts_url"),
        )
        self.singer.update_config(
            voice=tts_cfg.get("voice"),
            output_mode=tts_cfg.get("output_mode"),
            rvc_enabled=tts_cfg.get("rvc_enabled"),
            rvc_url=tts_cfg.get("rvc_url"),
            rvc_pitch_shift=tts_cfg.get("rvc_pitch_shift"),
        )

        # 2. Update VTS
        vts_cfg = new_settings.get("vts", {})
        if vts_cfg.get("enabled") is False and self.vts.connected:
            await self.vts.disconnect()
        elif vts_cfg.get("enabled") is True and not self.vts.connected:
            self._spawn_bg_task(self.vts.connect())
        elif vts_cfg.get("enabled") is True and (vts_cfg.get("host") != self.vts.host or vts_cfg.get("port") != self.vts.port):
            self._spawn_bg_task(self.vts.reconnect(host=vts_cfg.get("host"), port=vts_cfg.get("port")))

        # 3. Update Twitch
        twitch_cfg = new_settings.get("twitch", {})
        if twitch_cfg.get("enabled") is False and self.chat.is_running:
            self.chat.stop()
        elif twitch_cfg.get("enabled") is True and not self.chat.is_running and twitch_cfg.get("channel"):
            raw_port = twitch_cfg.get("port")
            self._spawn_bg_task(
                self.chat.start_twitch_listener(
                    channel=twitch_cfg["channel"],
                    bot_nick=twitch_cfg.get("bot_nick", ""),
                    oauth=twitch_cfg.get("oauth_token", ""),
                    use_tls=bool(twitch_cfg.get("use_tls", True)),
                    port=int(raw_port) if raw_port else None,
                )
            )

        # 3b. Update Multi-Platform Adapters (YouTube Live, Discord)
        await self.chat.stop_adapters()
        self._configure_platform_adapters(new_settings)
        if self.is_running:
            await self.chat.start_adapters()
        await self.broadcast("platform_status", self.chat.get_platforms_status())

        # 4. Update Moderator
        mod_cfg = new_settings.get("moderator", {})
        self.moderator.update_config(
            strict_mode=mod_cfg.get("strict_mode"),
            max_message_length=mod_cfg.get("max_message_length")
        )
        if "prompt_injection_filter" in mod_cfg:
            self._prompt_injection_filter = bool(mod_cfg.get("prompt_injection_filter", True))

        # 5. Update STT / Full-Duplex Voice
        stt_cfg = new_settings.get("stt", {})
        self.stt.update_config(
            enabled=stt_cfg.get("enabled"),
            model=stt_cfg.get("model"),
            device=stt_cfg.get("device"),
            vad_enabled=stt_cfg.get("vad_enabled"),
            vad_energy_threshold=stt_cfg.get("vad_energy_threshold"),
            barge_in_enabled=stt_cfg.get("barge_in_enabled"),
        )
        self.voice_session.vad.energy_threshold = self.stt.vad_energy_threshold

        # 6. Update Closed-Loop Autonomous Missions
        auto_cfg = new_settings.get("autonomous_agent", {})
        missions_enabled = bool(auto_cfg.get("closed_loop_missions", True) and auto_cfg.get("enabled", True))
        self.missions.update_config(
            enabled=missions_enabled,
            human_approval_required=auto_cfg.get("human_approval_required"),
            tick_interval_sec=auto_cfg.get("mission_tick_interval_sec"),
        )
        if self.is_running:
            if missions_enabled and not self.missions.is_running:
                await self.missions.start_loop()
            elif not missions_enabled and self.missions.is_running:
                await self.missions.stop_loop()

        # 7. Update AI Collab, Vision VLM & Plugins
        vision_cfg = new_settings.get("vision", {}) if isinstance(new_settings, dict) else {}
        if hasattr(self.brain, "vision"):
            if "vlm_enabled" in vision_cfg:
                self.brain.vision.vlm_enabled = bool(vision_cfg.get("vlm_enabled", False))
            if "vlm_interval_sec" in vision_cfg and vision_cfg.get("vlm_interval_sec") is not None:
                self.brain.vision.vlm_interval_sec = float(vision_cfg.get("vlm_interval_sec", 8.0) or 8.0)

        self.collab.update_config(new_settings)
        self.plugins.update_config(new_settings)
        self.plugins._rebuild_command_map()

        # 8. Update OBS Showrunner & Highlights
        obs_cfg = new_settings.get("obs", {}) if isinstance(new_settings, dict) else {}
        raw_obs_pw = obs_cfg.get("password")
        obs_pw = None if (raw_obs_pw is None or str(raw_obs_pw) == "********") else str(raw_obs_pw)
        self.obs.update_config(
            host=obs_cfg.get("host"),
            port=obs_cfg.get("port"),
            password=obs_pw,
            enabled=obs_cfg.get("enabled"),
        )
        if self.obs.enabled and not self.obs.is_connected and self.is_running:
            self._spawn_bg_task(self._connect_obs_and_replay())
        elif not self.obs.enabled and self.obs.is_connected:
            await self.obs.disconnect()

        highlights_cfg = new_settings.get("highlights", {}) if isinstance(new_settings, dict) else {}
        self.highlights.update_config(
            enabled=highlights_cfg.get("enabled"),
            chat_burst_threshold=highlights_cfg.get("chat_burst_threshold"),
            cooldown_sec=highlights_cfg.get("cooldown_sec"),
        )

        # Broadcast live event to all connected WebSocket clients (with secrets masked)
        await self.broadcast("configuration_updated", {
            "settings": self._mask_settings_for_broadcast(new_settings),
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
            auto_cfg = self.brain.settings.get("autonomous_agent", {}) if isinstance(self.brain.settings, dict) else {}
            banter_interval = float(auto_cfg.get("idle_banter_interval_sec", 40.0) or 40.0)

            # If chat is silent for >= banter_interval seconds and Eve hasn't made spontaneous banter recently
            if idle_duration >= banter_interval and (now - last_banter_time) >= banter_interval and not self._busy_lock.locked():
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
            async with self._speech_lock:
                self._current_emotion = primary_emotion
                await self._speak_with_metrics(speech_text, on_mouth_update=lambda val: self._spawn_bg_task(on_mouth_update(val)))
                self._current_emotion = "neutral"

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
                llm_cfg = self.brain.settings.get("llm", {}) if isinstance(self.brain.settings, dict) else {}
                gemini_key = str(llm_cfg.get("gemini_api_key") or "").strip()
                if not gemini_key or gemini_key == "********":
                    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
                openai_key = str(llm_cfg.get("openai_api_key") or "").strip()
                if not openai_key or openai_key == "********":
                    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
                obs = await self.brain.vision.aperceive_with_vlm(
                    mood_directive=mood_directive,
                    dominant_mood=dominant_mood,
                    api_provider=str(llm_cfg.get("provider", "gemini") or "gemini"),
                    gemini_api_key=gemini_key or None,
                    openai_api_key=openai_key or None,
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
            async with self._speech_lock:
                self._current_emotion = primary_emotion
                await self._speak_with_metrics(speech_text, on_mouth_update=lambda val: self._spawn_bg_task(on_mouth_update(val)))
                self._current_emotion = "neutral"

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
            self._spawn_bg_task(self._speak_visual_commentary(obs))
        return obs

    @staticmethod
    def _is_prompt_injection(text: str) -> bool:
        if not text:
            return False
        return any(pattern.search(text) for pattern in _PROMPT_INJECTION_PATTERNS)

    async def _ingest_message(self, msg: ChatMessage):
        """Filters, broadcasts, and ingests message into ChatCurator."""
        is_creator_flag = bool(msg.is_creator) if hasattr(msg, "is_creator") else (msg.source in ("creator", "mic"))
        is_safe, clean_input = self.moderator.clean_text(msg.text)
        user_safe, _ = self.moderator.clean_text(msg.user)
        has_injection = self._prompt_injection_filter and (
            self._is_prompt_injection(msg.text) or self._is_prompt_injection(msg.user)
        )
        if has_injection or ((not is_safe or not user_safe) and self.moderator.strict_mode and not is_creator_flag):
            print(f"[Moderator] Dropped unsafe/injected input from {msg.user}: {msg.text}")
            return
        if not is_safe:
            print(f"[Moderator] Filtered unsafe input from {msg.user}: {msg.text}")

        if msg.source == "mic" and is_creator_flag and (self.is_busy or bool(getattr(self.tts, "is_speaking", False))):
            await self.barge_in(source="creator", reason="mic_barge_in")

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
            is_creator=is_creator_flag,
            emit_events=False
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

    async def _run_interaction_with_lock(self, interaction: ChatInteraction):
        async with self._busy_lock:
            self._busy_owner_task = asyncio.current_task()
            try:
                await self._execute_interaction(interaction)
            except asyncio.CancelledError:
                print("[Orchestrator] Active interaction cancelled (barge-in).")
                raise
            finally:
                self._busy_owner_task = None
                if self._active_interaction_task is asyncio.current_task():
                    self._active_interaction_task = None

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
                if not self._busy_lock.locked() and (
                    self._active_interaction_task is None or self._active_interaction_task.done()
                ):
                    interaction = self.brain.conversation.select_next_interaction()
                    if interaction:
                        self._active_interaction_task = asyncio.create_task(
                            self._run_interaction_with_lock(interaction)
                        )
                        await asyncio.sleep(0)
                        continue

                # 3. If no interaction ready or currently busy, wait for next message
                try:
                    msg = await asyncio.wait_for(self.chat.get_next_message(), timeout=0.2)
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

        await self.event_bus.publish(INTERACTION_STARTED, {
            "user": primary.user,
            "text": clean_input,
            "source": primary.source,
            "interaction_type": interaction.interaction_type,
            "is_creator": is_creator,
        })

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
            await self._perform_song_unlocked(requested_song, dedication_user=primary.user)
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

        # Check for registered Plugin !commands before falling back to generic LLM
        if clean_input.strip().startswith("!"):
            await self.ensure_plugins_loaded()
            handled_plugin, plugin_resp = await self.plugins.dispatch_command(
                clean_input,
                user=primary.user,
                is_creator=is_creator,
            )
            if handled_plugin:
                if plugin_resp:
                    await self._speak_response(plugin_resp, user_label="Eve (Plugin)", is_creator=is_creator)
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

        if is_donation:
            user_label = f"Eve (to {primary.user} 🎁 {primary.donation_amount})"
            # In-game celebration if Eve is connected in Minecraft!
            if self.minecraft.connection_status == "connected":
                self._spawn_bg_task(self.minecraft.celebrate(user=primary.user, amount=primary.donation_amount))
        elif is_group_debate:
            user_label = f"Eve (Commenting on {primary.user} & {interaction.related_messages[0].user})"
        elif primary.source == "minecraft":
            user_label = f"Eve (to {primary.user})"
        elif primary.source == "mic":
            user_label = f"Eve (to {primary.user} 🎙️)"
        else:
            user_label = "Eve"

        channel_name = "creator" if is_creator else "audience"

        tts_speak_overridden = (
            "speak" in getattr(self.tts, "__dict__", {})
            and "speak_stream" not in getattr(self.tts, "__dict__", {})
        )
        brain_gen_overridden = (
            "generate_response" in getattr(self.brain, "__dict__", {})
            and "generate_response_stream" not in getattr(self.brain, "__dict__", {})
        )
        use_streaming = (
            hasattr(self.brain, "is_streaming_enabled")
            and self.brain.is_streaming_enabled()
            and hasattr(self.brain, "generate_response_stream")
            and hasattr(self.tts, "speak_stream")
            and not tts_speak_overridden
            and not brain_gen_overridden
        )

        if use_streaming:
            current_emotion = "neutral"
            current_vts_params: Optional[Dict[str, float]] = None
            raw_chunks: List[str] = []

            async def _stream_chunks():
                stream_kwargs: Dict[str, Any] = {
                    "user_name": primary.user,
                    "message": llm_input,
                    "game_context": game_context,
                    "is_donation": is_donation,
                    "donation_amount": primary.donation_amount,
                    "is_group_debate": is_group_debate,
                    "debate_users": debate_users,
                }
                if self._accepts_kwarg(self.brain.generate_response_stream, "is_creator"):
                    stream_kwargs["is_creator"] = is_creator
                self.metrics.inc("llm_requests")
                try:
                    async for chunk in self.brain.generate_response_stream(**stream_kwargs):
                        raw_chunks.append(chunk)
                        yield chunk
                except Exception:
                    self.metrics.inc("llm_failovers")
                    raise

            async def on_tag(chunk_emotions: List[str], chunk_actions: List[str]):
                nonlocal current_emotion, current_vts_params
                if chunk_emotions:
                    current_emotion = chunk_emotions[0]
                    self._current_emotion = current_emotion
                    current_vts_params = await self._apply_vts_mood_rig(current_emotion)
                    await self.broadcast(
                        "avatar_state",
                        self._build_avatar_state(0.0, current_emotion, current_vts_params),
                    )

            async def on_sentence_start(sentence_text: str):
                _, clean_sentence = self.moderator.clean_text(sentence_text)
                if not clean_sentence:
                    return
                print(f"[AI Speech Stream] [{current_emotion}] {clean_sentence}")
                await self.broadcast("ai_chunk", {
                    "user": user_label,
                    "chunk": clean_sentence,
                    "emotion": current_emotion,
                    "source": primary.source,
                    "is_donation": is_donation,
                    "donation_amount": primary.donation_amount,
                    "is_creator": is_creator,
                    "channel": channel_name,
                })

            async def on_stream_mouth_update(val: float):
                if self.vts.connected:
                    await self.vts.update_mouth(val)
                await self.broadcast(
                    "avatar_state",
                    self._build_avatar_state(val, current_emotion, current_vts_params),
                )

            async with self._speech_lock:
                self._current_emotion = current_emotion
                t0 = time.perf_counter()
                try:
                    await self.tts.speak_stream(
                        _stream_chunks(),
                        on_mouth_update=on_stream_mouth_update,
                        on_sentence_start=on_sentence_start,
                        on_tag=on_tag,
                    )
                finally:
                    self.metrics.observe("tts_latency_ms", (time.perf_counter() - t0) * 1000.0)
                self._current_emotion = "neutral"

            raw_response = "".join(raw_chunks).strip()
            _, clean_response = self.moderator.clean_text(raw_response)
            speech_text, emotions, actions = ActionParser.parse(clean_response)

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
                "channel": channel_name,
                "streamed": True,
            })

            if primary.source == "minecraft" and speech_text:
                await self.minecraft.send_chat(speech_text)
            elif (
                primary.source == "discord"
                and getattr(self, "_discord_reply_enabled", False)
                and getattr(self, "_discord_adapter", None) is not None
                and speech_text
            ):
                await self._discord_adapter.send_message(speech_text)
        else:
            gen_kwargs: Dict[str, Any] = {
                "user_name": primary.user,
                "message": llm_input,
                "game_context": game_context,
                "is_donation": is_donation,
                "donation_amount": primary.donation_amount,
                "is_group_debate": is_group_debate,
                "debate_users": debate_users,
            }
            if self._accepts_kwarg(self.brain.generate_response, "is_creator"):
                gen_kwargs["is_creator"] = is_creator
            self.metrics.inc("llm_requests")
            try:
                raw_response = await self.brain.generate_response(**gen_kwargs)
            except Exception:
                self.metrics.inc("llm_failovers")
                raise

            _, clean_response = self.moderator.clean_text(raw_response)
            speech_text, emotions, actions = ActionParser.parse(clean_response)
            primary_emotion = emotions[0] if emotions else "neutral"

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
            elif (
                primary.source == "discord"
                and getattr(self, "_discord_reply_enabled", False)
                and getattr(self, "_discord_adapter", None) is not None
                and speech_text
            ):
                await self._discord_adapter.send_message(speech_text)

            vts_params = await self._apply_vts_mood_rig(primary_emotion)

            async def on_mouth_update(val: float):
                if self.vts.connected:
                    await self.vts.update_mouth(val)
                await self.broadcast(
                    "avatar_state",
                    self._build_avatar_state(val, primary_emotion, vts_params),
                )

            print(f"[AI Speech] [{primary_emotion}] {speech_text}")
            async with self._speech_lock:
                self._current_emotion = primary_emotion
                await self._speak_with_metrics(speech_text, on_mouth_update=lambda val: self._spawn_bg_task(on_mouth_update(val)))
                self._current_emotion = "neutral"

        neutral_vts_params = await self._apply_vts_mood_rig("neutral")
        if self.vts.connected:
            await self.vts.update_mouth(0.0)

        await self.broadcast(
            "avatar_state",
            self._build_avatar_state(0.0, "neutral", neutral_vts_params),
        )
        await self.broadcast("conversation_state", self.brain.get_conversation_state())
        await self.broadcast("mood_updated", self.brain.mood.get_state())

    async def perform_song(self, song_id: Optional[str] = None, dedication_user: Optional[str] = None):
        current = asyncio.current_task()
        if self._busy_lock.locked() and self._busy_owner_task is current and current is not None:
            await self._perform_song_unlocked(song_id=song_id, dedication_user=dedication_user)
            return
        async with self._busy_lock:
            self._busy_owner_task = current
            try:
                await self._perform_song_unlocked(song_id=song_id, dedication_user=dedication_user)
            finally:
                self._busy_owner_task = None

    async def perform_youtube_song(
        self,
        url: str,
        mode: Optional[str] = None,
        dedication_user: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Download/prepare a YouTube song request and perform it on stage."""
        from core.youtube_karaoke import YouTubeKaraokeError, YouTubeKaraokeProcessor

        cfg_enabled = bool(self.config.get("karaoke.youtube_enabled", True)) if getattr(self, "config", None) else True
        if not cfg_enabled:
            msg = "YouTube karaoke is disabled in settings."
            await self.broadcast("youtube_song_status", {"stage": "error", "detail": msg})
            return {"status": "error", "error": msg}

        chosen_mode = mode or (
            self.config.get("karaoke.youtube_mode", "ai_cover") if getattr(self, "config", None) else "ai_cover"
        )
        max_dur = int(
            self.config.get("karaoke.youtube_max_duration_sec", 600) if getattr(self, "config", None) else 600
        )

        async def _on_status(stage: str, detail: str) -> None:
            await self.broadcast(
                "youtube_song_status",
                {"stage": stage, "detail": detail, "url": url, "mode": chosen_mode},
            )

        processor = YouTubeKaraokeProcessor(
            max_duration_sec=max_dur,
            rvc_converter=getattr(self.singer, "_rvc", None),
        )
        try:
            song_entry = await processor.prepare_song(url=url, mode=chosen_mode, on_status=_on_status)
        except YouTubeKaraokeError as exc:
            await self.broadcast("youtube_song_status", {"stage": "error", "detail": str(exc), "url": url})
            return {"status": "error", "error": str(exc)}
        except Exception as exc:
            await self.broadcast("youtube_song_status", {"stage": "error", "detail": str(exc), "url": url})
            return {"status": "error", "error": str(exc)}

        song_id = song_entry["id"]
        self.singer.songs[song_id] = song_entry
        await self.perform_song(song_id=song_id, dedication_user=dedication_user)
        return {"status": "started", "song_id": song_id, "title": song_entry.get("title", song_id)}

    async def _perform_song_unlocked(self, song_id: Optional[str] = None, dedication_user: Optional[str] = None):
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
        vts_params = await self._apply_vts_mood_rig(primary_emotion)

        async def on_mouth_update(val: float):
            if self.vts.connected:
                await self.vts.update_mouth(val)
            await self.broadcast(
                "avatar_state",
                self._build_avatar_state(val, primary_emotion, vts_params),
            )

        async with self._speech_lock:
            self._current_emotion = primary_emotion
            await self._speak_with_metrics(speech_text, on_mouth_update=lambda val: self._spawn_bg_task(on_mouth_update(val)))
            self._current_emotion = "neutral"

        # 3. Synchronized Choreography Performance
        await self.broadcast("song_started", {"song_id": actual_song_id, "title": title})

        line_counter = 0
        sing_emotion = "happy"
        sing_vts_params = await self._apply_vts_mood_rig(sing_emotion, singing=True)

        async def on_lyric_update(line_text: str, default_emotion: str):
            nonlocal line_counter, sing_emotion, sing_vts_params
            step = director.get_choreography_step_for_line(actual_song_id, line_counter)
            line_counter += 1

            emotion = step.emotion or default_emotion
            sing_emotion = emotion
            self._current_emotion = emotion
            print(f"[Stage Choreography] [{step.section.upper()}] [{emotion}] [{step.movement}] ♪ {line_text} ♪")

            sing_vts_params = await self._apply_vts_mood_rig(emotion, singing=True)

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
            await self.broadcast(
                "avatar_state",
                self._build_avatar_state(val, sing_emotion, sing_vts_params, is_singing=True),
            )

        async def on_vocal_audio(audio_bytes: bytes, lyric_text: str):
            await self._on_tts_audio_ready(audio_bytes, lyric_text, self.singer.voice)

        async with self._speech_lock:
            await self.singer.sing(
                song_id=actual_song_id,
                on_lyric_update=on_lyric_update,
                on_mouth_update=lambda val: self._spawn_bg_task(on_sing_mouth(val)),
                on_vocal_audio=on_vocal_audio,
            )
            self._current_emotion = "neutral"

        await self.broadcast("song_ended", {"song_id": actual_song_id, "title": title})

        # 4. Post-Show MC & Self Evaluation
        outro_speech, score = director.finish_performance()
        if hasattr(self.brain, "personality") and self.brain.personality:
            await asyncio.to_thread(self.brain.personality.record_experience, "stage_performance", {"song": actual_song_id, "score": score})
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
        vts_params = await self._apply_vts_mood_rig(primary_emotion)
        async with self._speech_lock:
            self._current_emotion = primary_emotion
            await self._speak_with_metrics(speech_text, on_mouth_update=lambda val: self._spawn_bg_task(on_mouth_update(val)))
            self._current_emotion = "neutral"

        # Return to idle
        neutral_vts_params = await self._apply_vts_mood_rig("neutral", singing=False)
        if self.vts.connected:
            await self.vts.update_mouth(0.0)

        await self.broadcast(
            "avatar_state",
            self._build_avatar_state(0.0, "neutral", neutral_vts_params, is_singing=False),
        )

    async def _on_minecraft_commentary(self, speech_raw: str):
        async with self._speech_lock:
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
            self._current_emotion = primary_emotion
            await self._speak_with_metrics(speech_text, on_mouth_update=lambda val: self._spawn_bg_task(on_mouth_update(val)))
            self._current_emotion = "neutral"

            # Also speak into server chat so in-game players see Eve's reaction
            if self.minecraft.connection_status == "connected":
                await self.minecraft.send_chat(speech_text)

            if self.vts.connected:
                await self.vts.trigger_expression("neutral")
                await self.vts.update_mouth(0.0)

            await self.broadcast("avatar_state", {"mouth_open": 0.0, "emotion": "neutral"})

    async def _on_minecraft_state_change(self, state: Dict[str, Any]):
        await self.broadcast("minecraft_state", state)

    async def _on_minecraft_telemetry(self, telemetry: Dict[str, Any]):
        await self.broadcast("mc_telemetry", telemetry)

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
        async with self._speech_lock:
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

            vts_params = await self._apply_vts_mood_rig(primary_emotion)

            async def on_mouth_update(val: float):
                if self.vts.connected:
                    await self.vts.update_mouth(val)
                await self.broadcast(
                    "avatar_state",
                    self._build_avatar_state(val, primary_emotion, vts_params),
                )

            print(f"[{user_label}] [{primary_emotion}] {speech_text}")
            self._current_emotion = primary_emotion
            await self._speak_with_metrics(speech_text, on_mouth_update=lambda val: self._spawn_bg_task(on_mouth_update(val)))
            self._current_emotion = "neutral"

            neutral_vts_params = await self._apply_vts_mood_rig("neutral")
            if self.vts.connected:
                await self.vts.update_mouth(0.0)

            await self.broadcast(
                "avatar_state",
                self._build_avatar_state(0.0, "neutral", neutral_vts_params),
            )

    async def _on_chess_commentary(self, speech_raw: str):
        await self._speak_response(speech_raw, user_label="Eve (Chess)")

    async def _on_chess_state_change(self, state: Dict[str, Any]):
        await self.broadcast("chess_state", state)

    async def _on_chess_game_event(self, event_type: str, data: Dict[str, Any]):
        if event_type == "queen_captured":
            await asyncio.to_thread(
                self.brain.episodic_memory.on_chess_queen_capture,
                player=data.get("player", "Player"),
                eve_captured_player_queen=True,
                san=data.get("san", "")
            )
            self.brain.mood.apply_stimulus("chess_queen_capture")
            await asyncio.to_thread(
                self.brain.relationships.record_gaming_event,
                data.get("player", "Player"), "chess", "queen_captured", data
            )
        elif event_type == "game_over":
            await asyncio.to_thread(
                self.brain.episodic_memory.on_chess_game_ended,
                player=data.get("player", "Player"),
                eve_won=data.get("eve_won", False),
                player_won=data.get("player_won", False),
                result=data.get("result", "finished"),
                moves_count=data.get("moves_count", 0),
                elo=data.get("elo", 1200)
            )
            await asyncio.to_thread(
                self.brain.relationships.record_gaming_event,
                data.get("player", "Player"), "chess", "game_over", data
            )
            if data.get("eve_won"):
                self.brain.mood.apply_stimulus("chess_victory")
                if hasattr(self.brain, "personality") and self.brain.personality:
                    await asyncio.to_thread(
                        self.brain.personality.record_experience,
                        "game_victory", {"game": "chess", "opponent": data.get("player")}
                    )
                    self.brain.personality.sync_to_mood_baselines(self.brain.mood)
                await self.evaluate_goal_event("chess_game_won", data)
            elif data.get("player_won"):
                self.brain.mood.apply_stimulus("chess_defeat")
                if hasattr(self.brain, "personality") and self.brain.personality:
                    await asyncio.to_thread(
                        self.brain.personality.record_experience,
                        "game_defeat", {"game": "chess", "opponent": data.get("player")}
                    )
                    self.brain.personality.sync_to_mood_baselines(self.brain.mood)
        mem_stats = await asyncio.to_thread(self.brain.episodic_memory.get_stats)
        await self.broadcast("memory_updated", mem_stats)
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
                    await asyncio.to_thread(
                        self.brain.personality.record_experience,
                        "challenge_completed", {"task": g_dict.get("title")}
                    )
                    self.brain.personality.sync_to_mood_baselines(self.brain.mood)
                    await self.broadcast("personality_updated", self.brain.personality.get_state())
                await asyncio.to_thread(
                    self.brain.episodic_memory.record_episode,
                    title=f"Misi Selesai: {g_dict.get('title')}",
                    content=f"Eve berhasil menyelesaikan seluruh target '{g_dict.get('title')}' secara mandiri!",
                    episode_type="achievement",
                    user="Stream",
                    emotional_tag="happy",
                    importance_score=0.9
                )
                await self.broadcast("goal_completed", details)
                mem_stats = await asyncio.to_thread(self.brain.episodic_memory.get_stats)
                await self.broadcast("memory_updated", mem_stats)
            elif details.get("subtask_completed"):
                self.brain.mood.apply_stimulus("goal_milestone_completed")

            await self.broadcast("goal_updated", self.brain.goals.get_state())
            await self.broadcast("mood_updated", self.brain.mood.get_state())
