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
                    elif event_name == "attack":
                        await orchestrator.minecraft.player_attacked_bot(target)
                        orchestrator.brain.episodic_memory.on_minecraft_attack(target)
                        await orchestrator.broadcast("memory_updated", orchestrator.brain.episodic_memory.get_stats())
                    elif event_name == "gift":
                        item_name = data.get("item", "Diamond")
                        await orchestrator.minecraft.player_gave_gift(target, item_name)
                        orchestrator.brain.episodic_memory.on_minecraft_gift(target, item_name)
                        await orchestrator.broadcast("memory_updated", orchestrator.brain.episodic_memory.get_stats())
                    elif event_name == "crouch":
                        await orchestrator.minecraft.player_crouched(target)
                    elif event_name == "guard_threat":
                        mob = data.get("mob", "Zombie")
                        comment = orchestrator.minecraft.guard_agent.on_threat_detected(mob, target, is_creeper=(mob.lower() == "creeper"))
                        await orchestrator.minecraft.emit_commentary(comment)
                        await orchestrator.minecraft.emit_state()
                    elif event_name == "guard_kill":
                        mob = data.get("mob", "Zombie")
                        comment = orchestrator.minecraft.guard_agent.on_mob_eliminated(mob, target)
                        await orchestrator.minecraft.emit_commentary(comment)
                        await orchestrator.minecraft.emit_state()
                        orchestrator.brain.episodic_memory.on_minecraft_guard_incident(target, mob)
                        await orchestrator.broadcast("memory_updated", orchestrator.brain.episodic_memory.get_stats())
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
