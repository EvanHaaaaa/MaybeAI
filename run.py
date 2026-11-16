import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from contextlib import asynccontextmanager

# Load .env file
load_dotenv()

# Add workspace to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from core.orchestrator import Orchestrator

orchestrator = Orchestrator()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await orchestrator.start()
    yield

app = FastAPI(title="MaybeAI - Eve Maybe AI VTuber", lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory="web"), name="static")

@app.get("/")
async def get_index():
    return FileResponse("web/index.html")

@app.get("/api/status")
async def get_status():
    return {
        "status": "online",
        "busy": orchestrator.is_busy,
        "vts_connected": orchestrator.vts.connected,
        "llm_provider": orchestrator.brain.settings.get("llm", {}).get("provider", "gemini")
    }

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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
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

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "user_message":
                user = data.get("user", "User")
                text = data.get("text", "")
                source = data.get("source", "web")
                await orchestrator.chat.put_message(user=user, text=text, source=source)
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
                    donation_currency=currency
                )
            elif data.get("type") == "bulk_chat":
                msgs = data.get("messages", [])
                for m in msgs:
                    await orchestrator.chat.put_message(user=m.get("user", "Chatter"), text=m.get("text", ""), source="web")
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
                    await orchestrator.broadcast("ai_response", {
                        "user": "Eve (Desktop Companion)",
                        "raw": speech,
                        "speech": speech,
                        "emotions": ["happy" if req.status == "executed" else "surprised"],
                        "actions": ["wink"]
                    })
                elif act == "confirm_action":
                    action_id = data.get("action_id", "")
                    approved = bool(data.get("approved", True))
                    req, speech = engine.confirm_action(action_id, approved)
                    await orchestrator.broadcast("desktop_updated", engine.get_state())
                    await orchestrator.broadcast("ai_response", {
                        "user": "Eve (Desktop Companion)",
                        "raw": speech,
                        "speech": speech,
                        "emotions": ["happy" if approved else "neutral"],
                        "actions": ["nod"]
                    })
    except WebSocketDisconnect:
        orchestrator.unregister_listener(listener)
    except Exception as e:
        orchestrator.unregister_listener(listener)



def main():
    parser = argparse.ArgumentParser(description="MaybeAI - Eve Maybe (Autonomous AI VTuber)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface")
    parser.add_argument("--port", type=int, default=7860, help="Web port (default: 7860)")
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
