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
        "llm_provider": orchestrator.brain.settings.get("llm", {}).get("provider", "mock")
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    async def listener(event: dict):
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    orchestrator.register_listener(listener)

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "user_message":
                user = data.get("user", "User")
                text = data.get("text", "")
                await orchestrator.chat.put_message(user=user, text=text, source="web")
            elif data.get("type") == "minecraft_action":
                act = data.get("action")
                if act == "set_mode":
                    await orchestrator.minecraft.set_mode(data.get("mode", "santai"))
                elif act == "advance_speedrun":
                    await orchestrator.minecraft.advance_speedrun()
                elif act == "simulate_event":
                    event_name = data.get("event")
                    target = data.get("target", "Player1")
                    if event_name == "nearby":
                        await orchestrator.minecraft.player_joined_proximity(target)
                    elif event_name == "attack":
                        await orchestrator.minecraft.player_attacked_bot(target)
                    elif event_name == "gift":
                        await orchestrator.minecraft.player_gave_gift(target, data.get("item", "Diamond"))
                    elif event_name == "crouch":
                        await orchestrator.minecraft.player_crouched(target)
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
