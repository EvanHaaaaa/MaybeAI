import os
import sys
import json
import time
import hmac
import array
import base64
import secrets
import asyncio
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

from contextlib import asynccontextmanager

# Load .env file
load_dotenv()

# Add workspace to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from core.orchestrator import Orchestrator
from core.config_manager import ConfigManager

orchestrator = Orchestrator()
config_mgr = ConfigManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await orchestrator.start()
    yield
    await orchestrator.shutdown()

app = FastAPI(title="MaybeAI - Eve Maybe AI VTuber", lifespan=lifespan)

_LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1")


def _get_security_settings() -> Dict[str, Any]:
    sec = config_mgr.settings.get("security", {})
    return sec if isinstance(sec, dict) else {}


def _is_allowed_origin(origin: str) -> bool:
    if not isinstance(origin, str):
        return False
    raw_origin = origin.strip()
    if not raw_origin or raw_origin.lower() == "null":
        return False

    try:
        parsed = urlparse(raw_origin)
        _ = parsed.port
    except ValueError:
        return False

    if (
        parsed.scheme in ("http", "https")
        and parsed.hostname in ("127.0.0.1", "localhost", "::1")
        and parsed.username is None
        and parsed.password is None
        and parsed.path in ("", "/")
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    ):
        return True

    allowed_origins = _get_security_settings().get("allowed_origins", [])
    if isinstance(allowed_origins, list):
        normalized_origin = raw_origin.rstrip("/").lower()
        for entry in allowed_origins:
            if isinstance(entry, str) and entry.strip():
                if normalized_origin == entry.strip().rstrip("/").lower():
                    return True
    return False


def _get_configured_creator_token() -> str:
    env_token = os.getenv("MAYBEAI_CREATOR_TOKEN")
    if env_token:
        return env_token
    cfg_token = _get_security_settings().get("creator_token")
    if isinstance(cfg_token, str) and cfg_token and cfg_token != "********":
        return cfg_token
    return ""


def _is_http_creator_authorized(request: Request) -> tuple[bool, int, str]:
    configured_token = _get_configured_creator_token()
    if configured_token:
        provided_token = (request.headers.get("x-creator-token") or "").strip()
        if not provided_token:
            auth_header = request.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                provided_token = auth_header[7:].strip()
        if not provided_token or not secrets.compare_digest(
            provided_token.encode("utf-8"),
            configured_token.encode("utf-8"),
        ):
            return False, 401, "Creator authentication required"
        return True, 200, ""

    client_host = request.client.host if request.client else None
    if client_host not in _LOOPBACK_HOSTS:
        return False, 403, "Creator access restricted to loopback"
    return True, 200, ""


def _is_ws_creator_authorized(websocket: WebSocket) -> bool:
    client_host = websocket.client.host if websocket.client else None
    if client_host not in _LOOPBACK_HOSTS:
        return False
    configured_token = _get_configured_creator_token()
    if not configured_token:
        return True
    provided_token = websocket.query_params.get("token", "")
    if not provided_token:
        return False
    return secrets.compare_digest(
        provided_token.encode("utf-8"),
        configured_token.encode("utf-8"),
    )


def _get_collab_secret() -> str:
    env_secret = os.getenv("MAYBEAI_COLLAB_SECRET", "").strip()
    if env_secret:
        return env_secret
    mgr_secret = getattr(orchestrator.collab, "shared_secret", "")
    if isinstance(mgr_secret, str) and mgr_secret.strip():
        return mgr_secret.strip()
    collab_cfg = config_mgr.settings.get("collab", {})
    if isinstance(collab_cfg, dict):
        cfg_secret = str(collab_cfg.get("shared_secret") or "").strip()
        if cfg_secret and cfg_secret != "********":
            return cfg_secret
    return ""


def _decode_pcm_chunk(raw_audio: Any) -> bytes:
    if raw_audio is None:
        return b""
    if isinstance(raw_audio, (bytes, bytearray, memoryview)):
        return bytes(raw_audio)
    if isinstance(raw_audio, str):
        cleaned = raw_audio.strip()
        if not cleaned:
            return b""
        try:
            return base64.b64decode(cleaned)
        except Exception:
            return b""
    if isinstance(raw_audio, list):
        try:
            ints = [max(-32768, min(32767, int(x))) for x in raw_audio]
            return array.array("h", ints).tobytes()
        except Exception:
            return b""
    return b""


def _get_missions_status() -> Dict[str, Any]:
    st = orchestrator.missions.get_status()
    st.setdefault("running", st.get("is_running", False))
    st.setdefault("paused", st.get("is_paused", False))
    st.setdefault("last_step", st.get("last_action"))
    return st


async def _handle_collab_action(payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    action = str(payload.get("action") or "").strip().lower()
    if action == "connect":
        ws_url = payload.get("peer_ws_url") or payload.get("ws_url")
        peer_name = payload.get("peer_name")
        ok = await orchestrator.collab.connect_peer(ws_url=ws_url, peer_name=peer_name)
        return 200, {"success": ok, "status": orchestrator.collab.get_status()}
    if action == "disconnect":
        await orchestrator.collab.disconnect_peer()
        return 200, {"success": True, "status": orchestrator.collab.get_status()}
    if action in ("initiate", "prompt"):
        topic = str(payload.get("topic") or payload.get("prompt") or payload.get("speech") or "")
        res = await orchestrator.collab.initiate_prompt(topic)
        return 200, {**res, "status": orchestrator.collab.get_status()}
    if action in ("send_utterance", "utterance"):
        res = await orchestrator.collab.send_utterance(
            speech=str(payload.get("speech") or ""),
            emotion=str(payload.get("emotion") or "neutral"),
            yield_turn=bool(payload.get("yield_turn", True)),
            topic=str(payload.get("topic") or ""),
        )
        return 200, {**res, "status": orchestrator.collab.get_status()}
    if action == "duet_sync":
        res = await orchestrator.collab.send_duet_sync(
            song_id=str(payload.get("song_id") or "digital_world"),
            lyric_index=int(payload.get("lyric_index", 0) or 0),
            timestamp=float(payload.get("timestamp", time.time()) or time.time()),
        )
        return 200, {**res, "status": orchestrator.collab.get_status()}
    if action == "emote_sync":
        res = await orchestrator.collab.send_emote_sync(
            emotion=str(payload.get("emotion") or "happy"),
            action=str(payload.get("emote_action") or payload.get("action_name") or ""),
        )
        return 200, {**res, "status": orchestrator.collab.get_status()}
    if action == "reset_turns":
        st = await orchestrator.collab.reset_turns()
        return 200, {"success": True, "status": st}
    if action == "status":
        return 200, {"success": True, "status": orchestrator.collab.get_status()}
    return 400, {"success": False, "error": f"Unknown collab action: '{action}'"}


async def _handle_plugin_action(payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
    await orchestrator.ensure_plugins_loaded()
    action = str(payload.get("action") or "").strip().lower()
    plugin_id = str(payload.get("plugin_id") or "").strip()
    if action == "enable":
        res = await orchestrator.plugins.enable_plugin(plugin_id)
        return 200, {**res, "plugins": orchestrator.plugins.list_plugins()}
    if action == "disable":
        res = await orchestrator.plugins.disable_plugin(plugin_id)
        return 200, {**res, "plugins": orchestrator.plugins.list_plugins()}
    if action == "reload":
        res = await orchestrator.plugins.reload_plugin(plugin_id)
        return 200, {**res, "plugins": orchestrator.plugins.list_plugins()}
    if action in ("list", "refresh"):
        return 200, {"success": True, "plugins": orchestrator.plugins.list_plugins()}
    return 400, {"success": False, "error": f"Unknown plugin action: '{action}'"}


@app.middleware("http")
async def verify_api_origin_middleware(request: Request, call_next):
    is_mutating_api = request.url.path.startswith("/api/") and request.method in ("PUT", "POST", "PATCH", "DELETE")
    is_sensitive_get = request.url.path == "/api/config" and request.method == "GET"
    if is_mutating_api or is_sensitive_get:
        origin = request.headers.get("origin")
        if origin is not None and not _is_allowed_origin(origin):
            return JSONResponse(status_code=403, content={"detail": "Forbidden origin"})
        authorized, status_code, detail = _is_http_creator_authorized(request)
        if not authorized:
            return JSONResponse(status_code=status_code, content={"detail": detail})
    return await call_next(request)

# Mount static files
app.mount("/static", StaticFiles(directory="web"), name="static")

@app.get("/")
async def get_index():
    return FileResponse("web/index.html")

@app.get("/settings")
async def get_settings_page():
    return FileResponse("web/settings.html")

@app.get("/overlay")
async def get_overlay_page():
    return FileResponse("web/overlay.html")

@app.get("/api/eventbus/stats")
async def get_eventbus_stats():
    return orchestrator.event_bus.get_stats()

# --- Centralized Configuration Center Endpoints ---
@app.get("/api/config")
async def get_configuration():
    return config_mgr.get_public_config()

@app.get("/api/config/schema")
async def get_configuration_schema():
    return config_mgr.get_schema()

@app.put("/api/config")
async def update_configuration(payload: Dict[str, Any]):
    success, errors, restart_required = config_mgr.save_config(payload)
    if not success:
        return {"success": False, "errors": errors}
    await orchestrator.apply_configuration_hot_reload(config_mgr.settings)
    return {
        "success": True,
        "errors": errors,
        "restart_required": restart_required,
        "config": config_mgr.get_public_config()
    }

@app.post("/api/config/validate")
async def validate_configuration(payload: Dict[str, Any]):
    valid, errors = config_mgr.validate_config(payload)
    return {"valid": valid, "errors": errors}

@app.post("/api/config/reset")
async def reset_configuration(req: Optional[Dict[str, Any]] = None):
    category = req.get("category") if req else None
    cfg = config_mgr.reset_to_defaults(category)
    await orchestrator.apply_configuration_hot_reload(config_mgr.settings)
    return {"success": True, "config": cfg}

@app.post("/api/config/test/{feature}")
async def test_feature_diagnostic(feature: str, req: Optional[Dict[str, Any]] = None):
    payload = req or {}
    return await config_mgr.test_feature(feature, orchestrator, payload)

@app.get("/api/system/diagnostics")
async def get_system_diagnostics_report():
    return config_mgr.get_system_diagnostics(orchestrator)

@app.get("/api/status")
async def get_status():
    return {
        "status": "online",
        "busy": orchestrator.is_busy,
        "vts_connected": orchestrator.vts.connected,
        "llm_provider": orchestrator.brain.settings.get("llm", {}).get("provider", "gemini"),
        "streaming_enabled": orchestrator.brain.is_streaming_enabled(),
        "platforms": orchestrator.chat.get_platforms_status(),
    }

@app.get("/api/platforms/status")
async def get_platforms_status():
    return orchestrator.chat.get_platforms_status()

@app.get("/api/memory/stats")
async def get_memory_stats():
    return orchestrator.brain.episodic_memory.get_stats()

@app.get("/api/memory/search")
async def search_memory(q: str = "", user: str = None, limit: int = 10):
    return orchestrator.brain.episodic_memory.search_memories(query=q, top_k=limit, user=user)

@app.get("/api/memory/journal")
async def get_memory_journal():
    return {
        "journal_markdown": orchestrator.brain.episodic_memory.get_latest_journal()
    }

@app.get("/api/memory/recent")
async def get_recent_memories(limit: int = 15):
    return orchestrator.brain.episodic_memory.db.get_recent_memories(limit=limit)

@app.get("/api/mood")
async def get_mood_state():
    return orchestrator.brain.mood.get_state()

@app.get("/api/goals")
async def get_goals_state():
    return orchestrator.brain.goals.get_state()

@app.get("/api/goals/agenda")
async def get_goals_agenda_markdown():
    p = Path("data/goals/agenda.md")
    if p.exists():
        return {"markdown": p.read_text(encoding="utf-8")}
    return {"markdown": "# No agenda yet."}

@app.get("/api/relationships")
async def get_relationships_state():
    return orchestrator.brain.relationships.get_state()

@app.get("/api/relationships/{username}")
async def get_user_relationship(username: str):
    return orchestrator.brain.relationships.get_relationship(username).to_dict()

@app.get("/api/vision/state")
async def get_vision_state():
    return orchestrator.brain.vision.get_state()

@app.post("/api/vision/perceive")
async def trigger_vision_perceive(simulated_scene: Optional[str] = None):
    obs = await orchestrator.perceive_screen_now(simulated_scene=simulated_scene)
    return obs.to_dict()

@app.get("/api/minecraft/multiplayer")
async def get_multiplayer_social_state():
    return orchestrator.brain.multiplayer.get_state()

@app.get("/api/desktop/state")
async def get_desktop_state():
    return orchestrator.brain.desktop.get_state()

@app.get("/api/minigames/state")
async def get_minigames_state():
    return orchestrator.brain.minigames.get_state()

@app.post("/api/minigames/start")
async def start_minigame(game_type: str = "trivia", total_rounds: int = 3):
    sess, speech = orchestrator.brain.minigames.start_game(game_type, total_rounds)
    await orchestrator.broadcast("minigame_updated", orchestrator.brain.minigames.get_state())
    await orchestrator.broadcast("ai_response", {
        "user": "Eve (Game Host)",
        "raw": speech,
        "speech": speech,
        "emotions": ["excited"],
        "actions": ["wink"]
    })
    return sess.to_dict()

@app.post("/api/minigames/stop")
async def stop_minigame():
    sess, speech = orchestrator.brain.minigames.stop_game()
    await orchestrator.broadcast("minigame_updated", orchestrator.brain.minigames.get_state())
    await orchestrator.broadcast("ai_response", {
        "user": "Eve (Game Host)",
        "raw": speech,
        "speech": speech,
        "emotions": ["happy"],
        "actions": ["wink"]
    })
    return sess.to_dict()

# --- Dynamic Storytelling & Community Roleplay Endpoints ---
@app.get("/api/storytelling/state")
async def get_storytelling_state():
    return orchestrator.brain.storytelling.get_state()

@app.post("/api/storytelling/start")
async def start_storytelling(
    preset: str = "petualangan_netherite",
    genre: Optional[str] = None,
    eve_role: Optional[str] = None,
    custom_title: Optional[str] = None,
    custom_premise: Optional[str] = None
):
    engine = orchestrator.brain.storytelling
    sess, speech = engine.start_campaign(
        campaign_preset=preset,
        genre=genre,
        eve_role=eve_role,
        custom_title=custom_title,
        custom_premise=custom_premise
    )
    await orchestrator.broadcast("story_updated", engine.get_state())
    role_title = sess.eve_role.replace('_', ' ').title()
    await orchestrator.broadcast("ai_response", {
        "user": f"Eve ({role_title})",
        "raw": speech,
        "speech": speech,
        "emotions": ["excited"],
        "actions": ["wink"]
    })
    return sess.to_dict()

@app.post("/api/storytelling/advance")
async def advance_storytelling(choice_id: Optional[str] = None, custom_narrative: Optional[str] = None):
    engine = orchestrator.brain.storytelling
    sc, speech = engine.advance_scene(chosen_choice_id=choice_id, custom_narrative=custom_narrative)
    await orchestrator.broadcast("story_updated", engine.get_state())
    role_title = engine.session.eve_role.replace('_', ' ').title()
    await orchestrator.broadcast("ai_response", {
        "user": f"Eve ({role_title})",
        "raw": speech,
        "speech": speech,
        "emotions": ["happy"],
        "actions": ["wink"]
    })
    return sc.to_dict() if sc else {}

@app.post("/api/storytelling/roll")
async def roll_storytelling_dice(roller: str = "Chat"):
    engine = orchestrator.brain.storytelling
    res, speech = engine.roll_dice(roller=roller)
    await orchestrator.broadcast("story_updated", engine.get_state())
    role_title = engine.session.eve_role.replace('_', ' ').title()
    await orchestrator.broadcast("ai_response", {
        "user": f"Eve ({role_title})",
        "raw": speech,
        "speech": speech,
        "emotions": ["excited" if res.is_success else "smug"],
        "actions": ["wink"]
    })
    return res.to_dict()

# --- Dynamic Performance Director Endpoints ---
@app.get("/api/performance/state")
async def get_performance_state():
    return orchestrator.brain.performance.get_state()

@app.post("/api/performance/plan")
async def plan_performance_setlist(title: Optional[str] = None):
    director = orchestrator.brain.performance
    setlist = director.plan_concert_setlist(title)
    await orchestrator.broadcast("performance_updated", director.get_state())
    return [it.to_dict() for it in setlist]

@app.post("/api/performance/start")
async def start_performance_show(song_id: Optional[str] = None, dedication_user: Optional[str] = None):
    asyncio.create_task(orchestrator.perform_song(song_id, dedication_user))
    return {"status": "started", "song_id": song_id}

@app.post("/api/performance/cheer")
async def cheer_performance(user: str = "Chatter", cheer_type: str = "glowstick"):
    director = orchestrator.brain.performance
    cnt = director.record_audience_cheer(user, cheer_type)
    await orchestrator.broadcast("performance_updated", director.get_state())
    await orchestrator.broadcast("audience_cheer", {
        "user": user,
        "type": cheer_type,
        "total_glowsticks": cnt
    })
    return {"total_glowsticks": cnt}

# --- Experience-Based Personality Evolution Endpoints ---
@app.get("/api/personality/state")
async def get_personality_state():
    return orchestrator.brain.personality.get_state()

@app.post("/api/personality/experience")
async def record_personality_experience(req: Dict[str, Any]):
    event_type = req.get("event_type", "friendly_interaction")
    context = req.get("context", {})
    res = orchestrator.brain.personality.record_experience(event_type, context)
    orchestrator.brain.personality.sync_to_mood_baselines(orchestrator.brain.mood)
    await orchestrator.broadcast("personality_updated", orchestrator.brain.personality.get_state())
    await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
    return res

@app.post("/api/personality/reset")
async def reset_personality():
    orchestrator.brain.personality.reset_to_factory_defaults()
    orchestrator.brain.personality.sync_to_mood_baselines(orchestrator.brain.mood)
    await orchestrator.broadcast("personality_updated", orchestrator.brain.personality.get_state())
    await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
    return {"status": "reset", "state": orchestrator.brain.personality.get_state()}

# --- Full-Duplex Voice, Autonomous Missions, AI Collab & Plugin SDK Endpoints ---
@app.get("/api/voice/status")
async def get_voice_status():
    return {
        "stt": orchestrator.stt.get_status(),
        "voice_session": orchestrator.voice_session.get_status(),
        "tts": orchestrator.tts.get_status(),
        "barge_in_count": orchestrator.barge_in_count,
        "busy": orchestrator.is_busy,
    }


@app.get("/api/missions/status")
async def get_missions_status():
    return _get_missions_status()


@app.post("/api/missions/step")
async def step_missions(req: Optional[Dict[str, Any]] = None):
    payload = req or {}
    action = str(payload.get("action") or "step").strip().lower()
    if action == "approve":
        res = await orchestrator.missions.approve_pending()
    elif action == "reject":
        res = await orchestrator.missions.reject_pending(
            reason=str(payload.get("reason") or "Rejected by creator")
        )
    else:
        res = await orchestrator.missions.step_once(force=bool(payload.get("force", False)))
    return {**res, "status": _get_missions_status()}


@app.post("/api/missions/toggle")
async def toggle_missions(req: Optional[Dict[str, Any]] = None):
    payload = req or {}
    if "enabled" in payload:
        target_active = bool(payload["enabled"])
    elif "running" in payload:
        target_active = bool(payload["running"])
    elif "paused" in payload:
        target_active = not bool(payload["paused"])
    else:
        target_active = not (orchestrator.missions.is_running and not orchestrator.missions.is_paused)

    if target_active:
        orchestrator.missions.update_config(enabled=True)
        orchestrator.missions.resume()
        await orchestrator.missions.start_loop()
    else:
        orchestrator.missions.pause()

    st = _get_missions_status()
    return {"success": True, **st, "status": st}


@app.get("/api/collab/status")
async def get_collab_status():
    return orchestrator.collab.get_status()


@app.post("/api/collab/action")
async def post_collab_action(req: Dict[str, Any]):
    status_code, body = await _handle_collab_action(req or {})
    if status_code != 200:
        return JSONResponse(status_code=status_code, content=body)
    return body


@app.get("/api/plugins")
async def get_plugins_list():
    await orchestrator.ensure_plugins_loaded()
    return {
        "enabled": orchestrator.plugins.enabled,
        "plugins": orchestrator.plugins.list_plugins(),
    }


@app.post("/api/plugins/action")
async def post_plugins_action(req: Dict[str, Any]):
    status_code, body = await _handle_plugin_action(req or {})
    if status_code != 200:
        return JSONResponse(status_code=status_code, content=body)
    return body


_CREATOR_ONLY_WS_ACTIONS = frozenset({
    "config_action",
    "desktop_action",
    "minecraft_action",
    "chess_action",
    "set_llm_provider",
    "personality_action",
    "performance_action",
    "vision_action",
    "goal_action",
})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin is not None and not _is_allowed_origin(origin):
        await websocket.close(code=1008)
        return

    ws_creator_authorized = _is_ws_creator_authorized(websocket)

    await websocket.accept()

    async def listener(event: dict):
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    orchestrator.register_listener(listener)

    # Send initial minecraft state immediately upon connection
    await websocket.send_json({
        "type": "minecraft_state",
        "data": orchestrator.minecraft.get_status()
    })

    # Send current LLM provider
    await websocket.send_json({
        "type": "llm_provider_changed",
        "data": {
            "provider": orchestrator.brain.settings.get("llm", {}).get("provider", "gemini")
        }
    })

    # Send initial conversation state
    await websocket.send_json({
        "type": "conversation_state",
        "data": orchestrator.brain.get_conversation_state()
    })

    # Send initial chess state immediately upon connection
    await websocket.send_json({
        "type": "chess_state",
        "data": orchestrator.chess.get_status()
    })

    # Send initial episodic memory stats & recent memories
    await websocket.send_json({
        "type": "memory_updated",
        "data": orchestrator.brain.episodic_memory.get_stats()
    })

    # Send initial mood state
    await websocket.send_json({
        "type": "mood_updated",
        "data": orchestrator.brain.mood.get_state()
    })

    # Send initial goal planning state
    await websocket.send_json({
        "type": "goal_updated",
        "data": orchestrator.brain.goals.get_state()
    })

    # Send initial relationship states
    await websocket.send_json({
        "type": "relationship_updated",
        "data": orchestrator.brain.relationships.get_state()
    })

    # Send initial visual perception / screen awareness state
    await websocket.send_json({
        "type": "vision_updated",
        "data": orchestrator.brain.vision.get_state()
    })

    # Send initial multiplayer social intelligence state
    await websocket.send_json({
        "type": "multiplayer_updated",
        "data": orchestrator.brain.multiplayer.get_state()
    })

    # Send initial desktop companion state
    await websocket.send_json({
        "type": "desktop_updated",
        "data": orchestrator.brain.desktop.get_state()
    })

    # Send initial interactive mini-game state
    await websocket.send_json({
        "type": "minigame_updated",
        "data": orchestrator.brain.minigames.get_state()
    })

    # Send initial dynamic storytelling state
    await websocket.send_json({
        "type": "story_updated",
        "data": orchestrator.brain.storytelling.get_state()
    })

    # Send initial dynamic performance director state
    await websocket.send_json({
        "type": "performance_updated",
        "data": orchestrator.brain.performance.get_state()
    })

    # Send initial experience-based personality evolution state
    await websocket.send_json({
        "type": "personality_updated",
        "data": orchestrator.brain.personality.get_state()
    })

    # Send initial system diagnostics report
    await websocket.send_json({
        "type": "system_diagnostics",
        "data": config_mgr.get_system_diagnostics(orchestrator)
    })

    # Send initial autonomous mission and collab states
    await websocket.send_json({
        "type": "mission_status",
        "data": _get_missions_status()
    })
    await websocket.send_json({
        "type": "collab_state",
        "data": orchestrator.collab.get_status()
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type in _CREATOR_ONLY_WS_ACTIONS and not ws_creator_authorized:
                await websocket.send_json({
                    "type": "error",
                    "data": {"error": f"Creator authorization required for {msg_type}", "code": "forbidden"}
                })
                continue
            if data.get("type") == "user_message":
                user = data.get("user", "User")
                text = data.get("text", "")
                raw_source = str(data.get("source") or "web")
                if ws_creator_authorized:
                    source = raw_source
                    is_creator = data.get("is_creator", None)
                else:
                    source = "web" if raw_source.lower() in ("creator", "mic") else raw_source
                    is_creator = False
                await orchestrator.chat.put_message(user=user, text=text, source=source, is_creator=is_creator)
            elif data.get("type") == "donation":
                user = data.get("user", "Supporter")
                text = data.get("text", "Love your stream!")
                amount = data.get("amount", "$5.00")
                currency = data.get("currency", "USD")
                await orchestrator.chat.put_message(
                    user=user,
                    text=text,
                    source="web",
                    is_donation=True,
                    donation_amount=amount,
                    donation_currency=currency,
                    is_creator=False
                )
            elif data.get("type") == "bulk_chat":
                msgs = data.get("messages", [])
                for m in msgs:
                    await orchestrator.chat.put_message(
                        user=m.get("user", "Chatter"),
                        text=m.get("text", ""),
                        source="web",
                        is_creator=False
                    )
            elif data.get("type") == "set_llm_provider":
                prov = data.get("provider", "mock")
                active_prov = orchestrator.brain.set_provider(prov)
                print(f"[Orchestrator] LLM provider switched to: {active_prov}")
                await orchestrator.broadcast("llm_provider_changed", {"provider": active_prov})
            elif data.get("type") == "trigger_improv":
                await orchestrator.trigger_improv()
            elif data.get("type") == "minecraft_action":
                act = data.get("action")
                if act == "set_mode":
                    await orchestrator.minecraft.set_mode(data.get("mode", "santai"), target=data.get("target"))
                elif act == "guard_player":
                    await orchestrator.minecraft.guard_player(data.get("target"))
                elif act == "advance_speedrun":
                    await orchestrator.minecraft.advance_speedrun()
                elif act == "connect_server":
                    await orchestrator.minecraft.connect_to_server(data.get("server_id"))
                elif act == "disconnect_server":
                    await orchestrator.minecraft.disconnect_from_server()
                elif act == "add_server":
                    orchestrator.minecraft.add_server(
                        name=data.get("name", ""),
                        host=data.get("host", ""),
                        port=data.get("port", 25565),
                        version=data.get("version", "1.20.1"),
                        notes=data.get("notes", "")
                    )
                    await orchestrator.minecraft.emit_state()
                elif act == "delete_server":
                    orchestrator.minecraft.delete_server(data.get("server_id"))
                    await orchestrator.minecraft.emit_state()
                elif act == "follow_nearest":
                    await orchestrator.minecraft.follow_nearest()
                elif act == "stop_moving":
                    await orchestrator.minecraft.stop_moving()
                elif act == "jump":
                    await orchestrator.minecraft.jump()
                elif act == "crouch":
                    await orchestrator.minecraft.crouch()
                elif act == "toggle_wander":
                    await orchestrator.minecraft.toggle_wander()
                elif act == "simulate_event":
                    event_name = data.get("event")
                    target = data.get("target", "Player1")
                    if event_name == "nearby":
                        await orchestrator.minecraft.player_joined_proximity(target)
                        await orchestrator.evaluate_goal_event("player_greeted", {"player": target})
                    elif event_name == "attack":
                        await orchestrator.minecraft.player_attacked_bot(target)
                        orchestrator.brain.episodic_memory.on_minecraft_attack(target)
                        orchestrator.brain.mood.apply_stimulus("minecraft_attacked")
                        orchestrator.brain.relationships.record_gaming_event(target, "minecraft", "attack", {})
                        await orchestrator.broadcast("memory_updated", orchestrator.brain.episodic_memory.get_stats())
                        await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
                        await orchestrator.broadcast("relationship_updated", orchestrator.brain.relationships.get_state())
                    elif event_name == "gift":
                        item_name = data.get("item", "Diamond")
                        await orchestrator.minecraft.player_gave_gift(target, item_name)
                        orchestrator.brain.episodic_memory.on_minecraft_gift(target, item_name)
                        orchestrator.brain.mood.apply_stimulus("minecraft_gift")
                        orchestrator.brain.relationships.record_gaming_event(target, "minecraft", "gift", {"item": item_name})
                        await orchestrator.evaluate_goal_event("minecraft_item_collected", {"item": item_name, "count": 1})
                        await orchestrator.broadcast("memory_updated", orchestrator.brain.episodic_memory.get_stats())
                        await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
                        await orchestrator.broadcast("relationship_updated", orchestrator.brain.relationships.get_state())
                    elif event_name == "crouch":
                        await orchestrator.minecraft.player_crouched(target)
                    elif event_name == "guard_threat":
                        mob = data.get("mob", "Zombie")
                        comment = orchestrator.minecraft.guard_agent.on_threat_detected(mob, target, is_creeper=(mob.lower() == "creeper"))
                        orchestrator.brain.mood.apply_stimulus("minecraft_threat", 0.7)
                        await orchestrator.minecraft.emit_commentary(comment)
                        await orchestrator.minecraft.emit_state()
                        await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
                    elif event_name == "guard_kill":
                        mob = data.get("mob", "Zombie")
                        comment = orchestrator.minecraft.guard_agent.on_mob_eliminated(mob, target)
                        orchestrator.brain.mood.apply_stimulus("minecraft_guard_victory")
                        await orchestrator.minecraft.emit_commentary(comment)
                        await orchestrator.minecraft.emit_state()
                        orchestrator.brain.episodic_memory.on_minecraft_guard_incident(target, mob)
                        orchestrator.brain.relationships.record_gaming_event(target, "minecraft", "guard_kill", {"mob": mob})
                        await orchestrator.evaluate_goal_event("minecraft_guard_victory", {"mob": mob, "target": target})
                        await orchestrator.broadcast("memory_updated", orchestrator.brain.episodic_memory.get_stats())
                        await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
                        await orchestrator.broadcast("relationship_updated", orchestrator.brain.relationships.get_state())
            elif data.get("type") == "chess_action":
                act = data.get("action")
                if act == "start_game":
                    await orchestrator.chess.start_game(
                        player_name=data.get("player_name", "Creator"),
                        player_color=data.get("player_color", "white"),
                        elo=data.get("elo")
                    )
                elif act == "make_move":
                    await orchestrator.chess.make_player_move(data.get("move", ""))
                elif act == "set_elo":
                    await orchestrator.chess.set_elo(int(data.get("elo", 1200)))
                elif act == "resign":
                    await orchestrator.chess.resign_game()
            elif data.get("type") == "memory_action":
                act = data.get("action")
                if act == "search":
                    results = orchestrator.brain.episodic_memory.search_memories(data.get("query", ""), top_k=10)
                    await websocket.send_json({"type": "memory_search_results", "data": results})
                elif act == "get_journal":
                    journal_text = orchestrator.brain.episodic_memory.get_latest_journal()
                    await websocket.send_json({"type": "memory_journal_data", "data": {"markdown": journal_text}})
                elif act == "get_recent":
                    recent = orchestrator.brain.episodic_memory.db.get_recent_memories(limit=15)
                    await websocket.send_json({"type": "memory_recent_data", "data": recent})
                elif act == "get_user_profile":
                    uname = data.get("username", "Creator")
                    profile = orchestrator.brain.episodic_memory.db.get_or_create_user(uname)
                    await websocket.send_json({"type": "memory_user_profile_data", "data": profile})
                elif act == "add_memory":
                    orchestrator.brain.episodic_memory.record_episode(
                        title=data.get("title", "Catatan Memori"),
                        content=data.get("content", ""),
                        episode_type=data.get("episode_type", "general"),
                        user=data.get("user", "Creator"),
                        emotional_tag=data.get("emotional_tag", "neutral"),
                        importance_score=float(data.get("importance_score", 0.7)),
                        game_context=data.get("game_context", "")
                    )
                    await orchestrator.broadcast("memory_updated", orchestrator.brain.episodic_memory.get_stats())
            elif data.get("type") == "mood_action":
                act = data.get("action")
                if act == "apply_stimulus":
                    stim = data.get("stimulus", "")
                    intensity = float(data.get("intensity", 1.0))
                    orchestrator.brain.mood.apply_stimulus(stim, intensity)
                    await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
                elif act == "set_dimension":
                    dim = data.get("dimension", "")
                    val = float(data.get("value", 0.5))
                    orchestrator.brain.mood.set_dimension(dim, val)
                    await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
                elif act == "reset":
                    orchestrator.brain.mood.reset_to_baseline()
                    await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
            elif data.get("type") == "goal_action":
                act = data.get("action")
                if act == "add_goal":
                    orchestrator.brain.goals.create_goal(
                        title=data.get("title", ""),
                        description=data.get("description", ""),
                        tier=data.get("tier", "daily"),
                        category=data.get("category", "general"),
                        priority=int(data.get("priority", 5)),
                        autonomous=False
                    )
                    await orchestrator.broadcast("goal_updated", orchestrator.brain.goals.get_state())
                elif act == "set_active":
                    orchestrator.brain.goals.set_active_goal(data.get("goal_id"))
                    await orchestrator.broadcast("goal_updated", orchestrator.brain.goals.get_state())
                elif act == "advance_subtask":
                    sub_id = data.get("subtask_id")
                    delta = float(data.get("delta", 1.0))
                    res = orchestrator.brain.goals.advance_subtask_progress(sub_id, delta)
                    if res.get("subtask_completed"):
                        orchestrator.brain.mood.apply_stimulus("goal_milestone_completed")
                        await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
                    if res.get("goal_completed"):
                        orchestrator.brain.mood.apply_stimulus("goal_all_completed")
                        g_dict = res.get("goal", {})
                        orchestrator.brain.episodic_memory.record_episode(
                            title=f"Misi Selesai: {g_dict.get('title')}",
                            content=f"Eve berhasil menyelesaikan target '{g_dict.get('title')}' secara mandiri!",
                            episode_type="achievement",
                            user="Stream",
                            emotional_tag="happy",
                            importance_score=0.9
                        )
                        await orchestrator.broadcast("goal_completed", res)
                        await orchestrator.broadcast("memory_updated", orchestrator.brain.episodic_memory.get_stats())
                        await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
                    await orchestrator.broadcast("goal_updated", orchestrator.brain.goals.get_state())
                elif act == "complete_subtask":
                    res = orchestrator.brain.goals.complete_current_subtask()
                    if res.get("subtask_completed"):
                        orchestrator.brain.mood.apply_stimulus("goal_milestone_completed")
                        await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
                    if res.get("goal_completed"):
                        orchestrator.brain.mood.apply_stimulus("goal_all_completed")
                        g_dict = res.get("goal", {})
                        orchestrator.brain.episodic_memory.record_episode(
                            title=f"Misi Selesai: {g_dict.get('title')}",
                            content=f"Eve berhasil menyelesaikan target '{g_dict.get('title')}' secara mandiri!",
                            episode_type="achievement",
                            user="Stream",
                            emotional_tag="happy",
                            importance_score=0.9
                        )
                        await orchestrator.broadcast("goal_completed", res)
                        await orchestrator.broadcast("memory_updated", orchestrator.brain.episodic_memory.get_stats())
                        await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
                    await orchestrator.broadcast("goal_updated", orchestrator.brain.goals.get_state())
                elif act == "replan_subtask":
                    reason = data.get("reason", "Kendala tak terduga dalam eksekusi.")
                    new_sub, speech = orchestrator.brain.goals.fail_and_replan_active_subtask(reason)
                    orchestrator.brain.mood.apply_stimulus("goal_strategy_failed")
                    await orchestrator.broadcast("strategy_adapted", {
                        "new_subtask": new_sub.to_dict() if new_sub else None,
                        "speech": speech,
                        "reason": reason
                    })
                    await orchestrator.broadcast("goal_updated", orchestrator.brain.goals.get_state())
                    await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
                elif act == "autonomous_select":
                    chosen, speech = orchestrator.brain.goals.autonomous_select_next_activity(orchestrator.brain.mood.dimensions)
                    await orchestrator.broadcast("goal_updated", orchestrator.brain.goals.get_state())
                elif act == "get_agenda":
                    p = Path("data/goals/agenda.md")
                    agenda_text = p.read_text(encoding="utf-8") if p.exists() else ""
                    await websocket.send_json({"type": "goal_agenda_data", "data": {"markdown": agenda_text}})
            elif data.get("type") == "relationship_action":
                act = data.get("action")
                if act == "add_inside_joke":
                    uname = data.get("username", "Chatter")
                    topic = data.get("topic", "Inside Joke")
                    punchline = data.get("punchline", "")
                    ctx_str = data.get("context", "web")
                    orchestrator.brain.relationships.add_inside_joke_to_user(uname, topic, punchline, ctx_str)
                    await orchestrator.broadcast("relationship_updated", orchestrator.brain.relationships.get_state())
                elif act == "set_tier":
                    uname = data.get("username", "Chatter")
                    tier = data.get("tier", "new_friend")
                    p = orchestrator.brain.relationships.get_relationship(uname)
                    p.tier = tier
                    orchestrator.brain.relationships.save()
                    orchestrator.brain.relationships.sync_to_markdown(uname)
                    await orchestrator.broadcast("relationship_updated", orchestrator.brain.relationships.get_state())
                elif act == "simulate_event":
                    uname = data.get("username", "Chatter")
                    game = data.get("game", "minecraft")
                    ev = data.get("event", "gift")
                    det = data.get("details", {})
                    orchestrator.brain.relationships.record_gaming_event(uname, game, ev, det)
                    await orchestrator.broadcast("relationship_updated", orchestrator.brain.relationships.get_state())
            elif data.get("type") == "vision_action":
                act = data.get("action")
                if act == "perceive_now":
                    scene = data.get("simulated_scene")
                    await orchestrator.perceive_screen_now(simulated_scene=scene)
                elif act == "toggle_auto":
                    enabled = data.get("enabled", True)
                    orchestrator.brain.vision.set_auto_perception(enabled)
                    await orchestrator.broadcast("vision_updated", orchestrator.brain.vision.get_state())
                elif act == "set_interval":
                    sec = float(data.get("interval_sec", 5.0))
                    orchestrator.brain.vision.config.capture_interval_sec = max(1.0, min(60.0, sec))
                    await orchestrator.broadcast("vision_updated", orchestrator.brain.vision.get_state())
            elif data.get("type") == "multiplayer_action":
                act = data.get("action")
                if act == "choose_partner":
                    m_type = data.get("mission_type", "mining")
                    res = orchestrator.brain.multiplayer.choose_partner(m_type)
                    await orchestrator.broadcast("multiplayer_updated", orchestrator.brain.multiplayer.get_state())
                    await orchestrator.broadcast("ai_response", {
                        "user": "Eve (Squad Commander)",
                        "raw": res["speech"],
                        "speech": res["speech"],
                        "emotions": ["happy"],
                        "actions": ["wink"]
                    })
                elif act == "record_donation":
                    p_name = data.get("player_name", "Steve")
                    item = data.get("item", "diamond")
                    cnt = int(data.get("count", 1))
                    orchestrator.brain.multiplayer.ledger.record_donation(p_name, item, cnt)
                    orchestrator.brain.multiplayer.save()
                    orchestrator.brain.multiplayer.sync_to_second_brain()
                    await orchestrator.broadcast("multiplayer_updated", orchestrator.brain.multiplayer.get_state())
                elif act == "record_combat":
                    p_name = data.get("player_name", "Alex")
                    mob = data.get("mob", "Creeper")
                    orchestrator.brain.multiplayer.ledger.record_combat_aid(p_name, mob)
                    orchestrator.brain.multiplayer.save()
                    orchestrator.brain.multiplayer.sync_to_second_brain()
                    await orchestrator.broadcast("multiplayer_updated", orchestrator.brain.multiplayer.get_state())
                elif act == "record_build":
                    p_name = data.get("player_name", "Steve")
                    task = data.get("task", "Konstruksi Dinding Base")
                    orchestrator.brain.multiplayer.ledger.record_building_help(p_name, task)
                    orchestrator.brain.multiplayer.save()
                    orchestrator.brain.multiplayer.sync_to_second_brain()
                    await orchestrator.broadcast("multiplayer_updated", orchestrator.brain.multiplayer.get_state())
                elif act == "in_game_chat":
                    sender = data.get("sender", "Alex")
                    msg = data.get("message", "Ayo siap-siap ke Nether!")
                    resp = orchestrator.brain.multiplayer.process_in_game_chat(sender, msg)
                    await orchestrator.broadcast("multiplayer_updated", orchestrator.brain.multiplayer.get_state())
                    if resp:
                        await orchestrator.broadcast("ai_response", {
                            "user": "Eve (Squad)",
                            "raw": resp,
                            "speech": resp,
                            "emotions": ["excited"],
                            "actions": ["nod"]
                        })
                elif act == "propose_trade":
                    p_name = data.get("player_name", "Steve")
                    offering = data.get("offering", {"iron_ingot": 8})
                    requesting = data.get("requesting", {"diamond": 1})
                    _, verdict, _ = orchestrator.brain.multiplayer.negotiation.evaluate_incoming_trade(p_name, offering, requesting)
                    orchestrator.brain.multiplayer.save()
                    await orchestrator.broadcast("multiplayer_updated", orchestrator.brain.multiplayer.get_state())
                    await orchestrator.broadcast("ai_response", {
                        "user": "Eve (Barter Desk)",
                        "raw": verdict,
                        "speech": verdict,
                        "emotions": ["smug"],
                        "actions": ["giggle"]
                    })
            elif data.get("type") == "desktop_action":
                act = data.get("action")
                engine = orchestrator.brain.desktop
                if act == "toggle_master":
                    en = bool(data.get("enabled", True))
                    engine.toggle_master(en)
                    await orchestrator.broadcast("desktop_updated", engine.get_state())
                elif act == "toggle_category":
                    cat = data.get("category", "")
                    en = bool(data.get("enabled", True))
                    engine.toggle_category(cat, en)
                    await orchestrator.broadcast("desktop_updated", engine.get_state())
                elif act == "set_policy":
                    req_high = bool(data.get("require_high", True))
                    req_med = bool(data.get("require_medium", False))
                    engine.set_confirmation_policy(req_high, req_med)
                    await orchestrator.broadcast("desktop_updated", engine.get_state())
                elif act == "add_app":
                    app_name = data.get("app_name", "")
                    engine.add_allowed_app(app_name)
                    await orchestrator.broadcast("desktop_updated", engine.get_state())
                elif act == "remove_app":
                    app_name = data.get("app_name", "")
                    engine.remove_allowed_app(app_name)
                    await orchestrator.broadcast("desktop_updated", engine.get_state())
                elif act == "request_action":
                    cat = data.get("category", "volume_control")
                    a_type = data.get("action_type", "adjust_volume")
                    params = data.get("params", {})
                    req, speech = engine.request_action(cat, a_type, params)
                    await orchestrator.broadcast("desktop_updated", engine.get_state())
                    await orchestrator._speak_response(speech, user_label="Eve (Desktop Companion)")
                elif act == "confirm_action":
                    action_id = data.get("action_id", "")
                    approved = bool(data.get("approved", True))
                    req, speech = engine.confirm_action(action_id, approved)
                    await orchestrator.broadcast("desktop_updated", engine.get_state())
                    await orchestrator._speak_response(speech, user_label="Eve (Desktop Companion)")
            elif data.get("type") == "minigame_action":
                act = data.get("action")
                engine = orchestrator.brain.minigames
                if act == "start":
                    g_type = data.get("game_type", "trivia")
                    rounds = int(data.get("total_rounds", 3))
                    sess, speech = engine.start_game(g_type, rounds)
                    await orchestrator.broadcast("minigame_updated", engine.get_state())
                    await orchestrator.broadcast("ai_response", {
                        "user": "Eve (Game Host)",
                        "raw": speech,
                        "speech": speech,
                        "emotions": ["excited"],
                        "actions": ["wink"]
                    })
                elif act == "stop":
                    sess, speech = engine.stop_game()
                    await orchestrator.broadcast("minigame_updated", engine.get_state())
                    await orchestrator.broadcast("ai_response", {
                        "user": "Eve (Game Host)",
                        "raw": speech,
                        "speech": speech,
                        "emotions": ["happy"],
                        "actions": ["wink"]
                    })
                elif act == "next_round":
                    sess, speech = engine.next_round()
                    await orchestrator.broadcast("minigame_updated", engine.get_state())
                    await orchestrator.broadcast("ai_response", {
                        "user": "Eve (Game Host)",
                        "raw": speech,
                        "speech": speech,
                        "emotions": ["excited"],
                        "actions": ["wink"]
                    })
                elif act == "hint":
                    hint_text = engine.request_hint()
                    await orchestrator.broadcast("minigame_updated", engine.get_state())
                    speech = f"[emotion: smug] Nih hint dari Eve buat kalian: '{hint_text}'! Ayo tebak lagi! [action: wink]"
                    await orchestrator.broadcast("ai_response", {
                        "user": "Eve (Game Host)",
                        "raw": speech,
                        "speech": speech,
                        "emotions": ["smug"],
                        "actions": ["wink"]
                    })
                elif act == "chat_input":
                    user = data.get("user", "Chatter")
                    text = data.get("message", "")
                    await orchestrator.chat.put_message(user=user, text=text, source="web", is_creator=False)
            elif data.get("type") == "story_action":
                act = data.get("action")
                engine = orchestrator.brain.storytelling
                if act == "start":
                    preset = data.get("preset", "petualangan_netherite")
                    genre = data.get("genre")
                    role = data.get("eve_role")
                    c_title = data.get("custom_title")
                    c_premise = data.get("custom_premise")
                    sess, speech = engine.start_campaign(
                        campaign_preset=preset,
                        genre=genre,
                        eve_role=role,
                        custom_title=c_title,
                        custom_premise=c_premise
                    )
                    await orchestrator.broadcast("story_updated", engine.get_state())
                    role_title = sess.eve_role.replace('_', ' ').title()
                    await orchestrator.broadcast("ai_response", {
                        "user": f"Eve ({role_title})",
                        "raw": speech,
                        "speech": speech,
                        "emotions": ["excited"],
                        "actions": ["wink"]
                    })
                elif act == "vote":
                    user = data.get("user", "Chatter")
                    choice_id = data.get("choice_id", "opt_1")
                    ok, speech = engine.vote_choice(user, choice_id)
                    await orchestrator.broadcast("story_updated", engine.get_state())
                    if speech:
                        role_title = engine.session.eve_role.replace('_', ' ').title()
                        await orchestrator.broadcast("ai_response", {
                            "user": f"Eve ({role_title})",
                            "raw": speech,
                            "speech": speech,
                            "emotions": ["happy"],
                            "actions": ["nod"]
                        })
                elif act == "action":
                    user = data.get("user", "Chatter")
                    act_text = data.get("action_text", "")
                    ok, speech = engine.submit_freeform_action(user, act_text)
                    await orchestrator.broadcast("story_updated", engine.get_state())
                    if speech:
                        role_title = engine.session.eve_role.replace('_', ' ').title()
                        await orchestrator.broadcast("ai_response", {
                            "user": f"Eve ({role_title})",
                            "raw": speech,
                            "speech": speech,
                            "emotions": ["excited"],
                            "actions": ["wink"]
                        })
                elif act == "roll":
                    roller = data.get("roller", "Chat")
                    dc_target = data.get("dc_target")
                    stat_type = data.get("stat_type")
                    res, speech = engine.roll_dice(roller=roller, dc_target=dc_target, stat_type=stat_type)
                    await orchestrator.broadcast("story_updated", engine.get_state())
                    role_title = engine.session.eve_role.replace('_', ' ').title()
                    await orchestrator.broadcast("ai_response", {
                        "user": f"Eve ({role_title})",
                        "raw": speech,
                        "speech": speech,
                        "emotions": ["excited" if res.is_success else "smug"],
                        "actions": ["wink"]
                    })
                elif act == "advance":
                    choice_id = data.get("choice_id")
                    c_narrative = data.get("custom_narrative")
                    sc, speech = engine.advance_scene(chosen_choice_id=choice_id, custom_narrative=c_narrative)
                    await orchestrator.broadcast("story_updated", engine.get_state())
                    role_title = engine.session.eve_role.replace('_', ' ').title()
                    await orchestrator.broadcast("ai_response", {
                        "user": f"Eve ({role_title})",
                        "raw": speech,
                        "speech": speech,
                        "emotions": ["excited"],
                        "actions": ["wink"]
                    })
                elif act == "end":
                    summary = data.get("summary")
                    sess, speech = engine.end_campaign(outcome_summary=summary)
                    await orchestrator.broadcast("story_updated", engine.get_state())
                    role_title = sess.eve_role.replace('_', ' ').title()
                    await orchestrator.broadcast("ai_response", {
                        "user": f"Eve ({role_title})",
                        "raw": speech,
                        "speech": speech,
                        "emotions": ["happy"],
                        "actions": ["wink"]
                    })
            elif data.get("type") == "performance_action":
                act = data.get("action")
                director = orchestrator.brain.performance
                if act == "start":
                    song_id = data.get("song_id")
                    dedication = data.get("dedication_user")
                    asyncio.create_task(orchestrator.perform_song(song_id, dedication_user=dedication))
                elif act == "stop":
                    orchestrator.singer.stop()
                    director.session.status = "idle"
                    await orchestrator.broadcast("performance_updated", director.get_state())
                elif act == "plan":
                    title = data.get("title")
                    director.plan_concert_setlist(title)
                    await orchestrator.broadcast("performance_updated", director.get_state())
                elif act == "cheer":
                    u = data.get("user", "Chatter")
                    c_type = data.get("cheer_type", "glowstick")
                    cnt = director.record_audience_cheer(u, c_type)
                    await orchestrator.broadcast("performance_updated", director.get_state())
                    await orchestrator.broadcast("audience_cheer", {
                        "user": u,
                        "type": c_type,
                        "total_glowsticks": cnt
                    })
            elif data.get("type") == "personality_action":
                act = data.get("action")
                p_engine = orchestrator.brain.personality
                if act == "experience":
                    ev = data.get("event_type", "friendly_interaction")
                    ctx = data.get("context", {})
                    p_engine.record_experience(ev, ctx)
                    p_engine.sync_to_mood_baselines(orchestrator.brain.mood)
                    await orchestrator.broadcast("personality_updated", p_engine.get_state())
                    await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
                elif act == "reset":
                    p_engine.reset_to_factory_defaults()
                    p_engine.sync_to_mood_baselines(orchestrator.brain.mood)
                    await orchestrator.broadcast("personality_updated", p_engine.get_state())
                    await orchestrator.broadcast("mood_updated", orchestrator.brain.mood.get_state())
            elif data.get("type") == "config_action":
                act = data.get("action")
                if act == "save":
                    payload = data.get("config", {})
                    success, errors, restart = config_mgr.save_config(payload)
                    if success:
                        await orchestrator.apply_configuration_hot_reload(config_mgr.settings)
                    await websocket.send_json({
                        "type": "config_saved",
                        "data": {"success": success, "errors": errors, "restart_required": restart}
                    })
                elif act == "test":
                    feat = data.get("feature", "llm")
                    res = await config_mgr.test_feature(feat, orchestrator, data.get("payload", {}))
                    await websocket.send_json({
                        "type": "feature_test_result",
                        "data": res
                    })
                elif act == "get_diagnostics":
                    await websocket.send_json({
                        "type": "system_diagnostics",
                        "data": config_mgr.get_system_diagnostics(orchestrator)
                    })
            elif data.get("type") == "barge_in":
                if not ws_creator_authorized:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"error": "Creator authorization required for barge_in", "code": "forbidden"}
                    })
                    continue
                reason = str(data.get("reason") or "creator_vad")
                await orchestrator.barge_in(source="creator", reason=reason)
            elif data.get("type") == "voice_audio_chunk":
                if not ws_creator_authorized:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"error": "Creator authorization required for voice_audio_chunk", "code": "forbidden"}
                    })
                    continue
                raw_audio = data.get("audio_b64") or data.get("pcm_b64") or data.get("chunk") or data.get("pcm")
                pcm_bytes = _decode_pcm_chunk(raw_audio)
                if pcm_bytes:
                    res = await orchestrator.process_voice_chunk(
                        pcm_bytes,
                        user=str(data.get("user") or "Creator"),
                        language=data.get("language"),
                    )
                    await websocket.send_json({"type": "voice_chunk_ack", "data": res})
            elif data.get("type") == "mission_action":
                if not ws_creator_authorized:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"error": "Creator authorization required for mission_action", "code": "forbidden"}
                    })
                    continue
                act = str(data.get("action") or "step").strip().lower()
                if act == "step":
                    res = await orchestrator.missions.step_once(force=bool(data.get("force", False)))
                    await websocket.send_json({"type": "mission_step", "data": {**res, "status": _get_missions_status()}})
                elif act == "approve":
                    res = await orchestrator.missions.approve_pending()
                    await websocket.send_json({"type": "mission_step", "data": {**res, "status": _get_missions_status()}})
                elif act == "reject":
                    res = await orchestrator.missions.reject_pending(reason=str(data.get("reason") or "Rejected by creator"))
                    await websocket.send_json({"type": "mission_status", "data": _get_missions_status()})
                elif act in ("toggle", "start", "resume", "pause", "stop"):
                    if act in ("start", "resume"):
                        orchestrator.missions.update_config(enabled=True)
                        orchestrator.missions.resume()
                        await orchestrator.missions.start_loop()
                    elif act in ("pause", "stop"):
                        orchestrator.missions.pause()
                    else:
                        currently_active = orchestrator.missions.is_running and not orchestrator.missions.is_paused
                        if currently_active:
                            orchestrator.missions.pause()
                        else:
                            orchestrator.missions.update_config(enabled=True)
                            orchestrator.missions.resume()
                            await orchestrator.missions.start_loop()
                    await websocket.send_json({"type": "mission_status", "data": _get_missions_status()})
                elif act == "status":
                    await websocket.send_json({"type": "mission_status", "data": _get_missions_status()})
            elif data.get("type") == "collab_action":
                act = str(data.get("action") or "").strip().lower()
                if act != "status" and not ws_creator_authorized:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"error": "Creator authorization required for collab_action", "code": "forbidden"}
                    })
                    continue
                _, body = await _handle_collab_action(data)
                await websocket.send_json({"type": "collab_state", "data": body.get("status", orchestrator.collab.get_status())})
            elif data.get("type") == "plugin_action":
                act = str(data.get("action") or "").strip().lower()
                if act not in ("list", "refresh") and not ws_creator_authorized:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"error": "Creator authorization required for plugin_action", "code": "forbidden"}
                    })
                    continue
                _, body = await _handle_plugin_action(data)
                await websocket.send_json({"type": "plugin_event", "data": body})
    except WebSocketDisconnect:
        orchestrator.unregister_listener(listener)
    except Exception as e:
        orchestrator.unregister_listener(listener)


@app.websocket("/ws/collab")
async def collab_websocket_endpoint(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin is not None and not _is_allowed_origin(origin):
        await websocket.close(code=1008)
        return

    client_host = websocket.client.host if websocket.client else None
    is_loopback = client_host in _LOOPBACK_HOSTS
    secret = _get_collab_secret()

    if secret:
        provided_secret = (
            websocket.query_params.get("secret")
            or websocket.query_params.get("token")
            or websocket.headers.get("x-collab-secret")
            or ""
        ).strip()
        if not provided_secret:
            auth_header = websocket.headers.get("authorization", "")
            if auth_header.lower().startswith("bearer "):
                provided_secret = auth_header[7:].strip()
        if not provided_secret or not hmac.compare_digest(
            provided_secret.encode("utf-8"),
            secret.encode("utf-8"),
        ):
            await websocket.close(code=1008)
            return
    elif not is_loopback:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    async def send_to_peer(envelope_dict: Dict[str, Any]):
        await websocket.send_json(envelope_dict)

    prev_collab_secret = orchestrator.collab.shared_secret
    secret_overridden = bool(secret and prev_collab_secret != secret)
    if secret_overridden:
        orchestrator.collab.shared_secret = secret

    sender_id = orchestrator.collab.register_peer_sender(send_to_peer)
    try:
        while True:
            raw = await websocket.receive_json()
            res = await orchestrator.collab.handle_incoming_envelope(
                raw,
                is_loopback=is_loopback,
            )
            if not res.get("accepted"):
                await websocket.send_json(res)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        orchestrator.collab.unregister_peer_sender(sender_id)
        if secret_overridden and orchestrator.collab.shared_secret == secret:
            orchestrator.collab.shared_secret = prev_collab_secret



def main():
    sys_cfg = config_mgr.settings.get("system", {})
    default_host = sys_cfg.get("host", "127.0.0.1") if isinstance(sys_cfg, dict) else "127.0.0.1"
    default_port = int(sys_cfg.get("port", 7860)) if isinstance(sys_cfg, dict) else 7860
    parser = argparse.ArgumentParser(description="MaybeAI - Eve Maybe (Autonomous AI VTuber)")
    parser.add_argument("--host", type=str, default=default_host, help=f"Host interface (default: {default_host})")
    parser.add_argument("--port", type=int, default=default_port, help=f"Web port (default: {default_port})")
    parser.add_argument("--provider", type=str, choices=["mock", "openai", "gemini", "ollama"], help="Override LLM provider")
    args = parser.parse_args()

    if args.provider:
        orchestrator.brain.settings.setdefault("llm", {})["provider"] = args.provider
        print(f"[Launcher] LLM provider overridden to: {args.provider}")

    print("=" * 60)
    print("  ✨ MaybeAI - Eve Maybe (Autonomous AI VTuber System)")
    print(f"  🌐 Web Dashboard: http://{args.host}:{args.port}")
    print(f"  🎭 Mode: {orchestrator.brain.settings.get('llm', {}).get('provider', 'mock').upper()}")
    print("=" * 60)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")

if __name__ == "__main__":
    main()
