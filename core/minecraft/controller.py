import asyncio
import json
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from core.minecraft.casual_agent import CasualAgent
from core.minecraft.speedrun_agent import SpeedrunAgent, PHASE_NAMES, SpeedrunPhase

class MinecraftController:
    """
    Master Controller for Eve's Minecraft gameplay.
    Coordinates:
    - Mode switching: 'santai' (Casual / Social) vs 'kompe' (Speedrun / Competitive)
    - Multi-server manager (Add, Delete, Select, Connect)
    - State synchronization (Health, Position, Inventory, Current Objective)
    - In-game Player Interactions & Chat
    - Real-time commentary triggered via Orchestrator
    """

    def __init__(self, bot_name: str = "EveMaybe", servers_config_path: str = "config/minecraft_servers.json"):
        self.bot_name = bot_name
        self.current_mode = "santai"  # "santai" or "kompe"
        self.is_active = False
        self.servers_config_path = Path(servers_config_path)

        self.casual_agent = CasualAgent(bot_name=bot_name)
        self.speedrun_agent = SpeedrunAgent(bot_name=bot_name)

        # Multi-Server List
        self.servers: List[Dict[str, Any]] = []
        self.active_server: Optional[Dict[str, Any]] = None
        self.load_servers()

        # Telemetry & Game State
        self.health = 20
        self.food = 20
        self.pos = {"x": 120, "y": 64, "z": -250}
        self.connection_status = "disconnected"  # "disconnected", "connecting", "connected"
        self.nearby_players: List[Dict[str, Any]] = []

        self.on_commentary_callback: Optional[Callable[[str], Any]] = None
        self.on_state_change_callback: Optional[Callable[[Dict[str, Any]], Any]] = None

    def set_callbacks(self, on_commentary: Callable[[str], Any], on_state_change: Optional[Callable[[Dict[str, Any]], Any]] = None):
        self.on_commentary_callback = on_commentary
        self.on_state_change_callback = on_state_change

    def load_servers(self):
        if self.servers_config_path.exists():
            try:
                with open(self.servers_config_path, "r", encoding="utf-8") as f:
                    self.servers = json.load(f)
                    if self.servers:
                        self.active_server = self.servers[0]
            except Exception as e:
                print(f"[Minecraft] Error loading servers: {e}")

    def save_servers(self):
        try:
            with open(self.servers_config_path, "w", encoding="utf-8") as f:
                json.dump(self.servers, f, indent=2)
        except Exception as e:
            print(f"[Minecraft] Error saving servers: {e}")

    def add_server(self, name: str, host: str, port: int = 25565, version: str = "1.20.1", notes: str = "") -> Dict[str, Any]:
        server_id = f"srv_{uuid.uuid4().hex[:6]}"
        new_srv = {
            "id": server_id,
            "name": name.strip() or f"Server {host}",
            "host": host.strip(),
            "port": int(port),
            "version": version.strip() or "1.20.1",
            "notes": notes.strip()
        }
        self.servers.append(new_srv)
        self.save_servers()
        return new_srv

    def delete_server(self, server_id: str) -> bool:
        self.servers = [s for s in self.servers if s.get("id") != server_id]
        if self.active_server and self.active_server.get("id") == server_id:
            self.active_server = self.servers[0] if self.servers else None
        self.save_servers()
        return True

    def get_status(self) -> Dict[str, Any]:
        phase = self.speedrun_agent.current_phase
        phase_title = PHASE_NAMES.get(phase, f"Phase {phase}")
        return {
            "is_active": self.is_active,
            "mode": self.current_mode,
            "bot_name": self.bot_name,
            "health": self.health,
            "food": self.food,
            "pos": self.pos,
            "servers": self.servers,
            "active_server": self.active_server,
            "connection_status": self.connection_status,
            "speedrun": {
                "phase": phase,
                "phase_name": phase_title,
                "split_time": self.speedrun_agent.get_elapsed_time_str()
            },
            "nearby_players": self.nearby_players
        }

    async def connect_to_server(self, server_id: Optional[str] = None) -> str:
        """Connect bot to designated server."""
        if server_id:
            match = next((s for s in self.servers if s.get("id") == server_id), None)
            if match:
                self.active_server = match

        if not self.active_server:
            return "No server selected."

        name = self.active_server.get("name", "Minecraft Server")
        host = self.active_server.get("host", "localhost")
        port = self.active_server.get("port", 25565)

        self.connection_status = "connected"
        self.is_active = True

        speech = f"[emotion: happy] Logging into {name} at {host}:{port}! Wish me luck chat, Eve is entering the server! [action: wink]"
        await self.emit_commentary(speech)
        await self.emit_state()
        return speech

    async def disconnect_from_server(self) -> str:
        """Disconnect bot from active server."""
        self.connection_status = "disconnected"
        self.is_active = False

        speech = "[emotion: smug] Left the server for now! Back to streaming with chat."
        await self.emit_commentary(speech)
        await self.emit_state()
        return speech

    async def emit_commentary(self, speech: str):
        if self.on_commentary_callback and speech:
            res = self.on_commentary_callback(speech)
            if asyncio.iscoroutine(res):
                await res

    async def emit_state(self):
        if self.on_state_change_callback:
            res = self.on_state_change_callback(self.get_status())
            if asyncio.iscoroutine(res):
                await res

    async def set_mode(self, new_mode: str) -> str:
        """Switch between 'santai' (Casual) and 'kompe' (Speedrun)."""
        new_mode = new_mode.lower()
        if new_mode not in ["santai", "kompe"]:
            return "Mode must be 'santai' or 'kompe'."

        self.current_mode = new_mode
        self.is_active = True

        if new_mode == "santai":
            speech = "[emotion: happy] Switching to Mode Santai! Time to chill, explore, and hang out with everyone on the server! [action: wink]"
        else:
            speech = self.speedrun_agent.start_run()

        await self.emit_commentary(speech)
        await self.emit_state()
        return speech

    # --- Mode Santai (Casual) Handlers ---
    async def player_joined_proximity(self, player_name: str, distance: float = 5.0):
        if self.current_mode == "santai":
            reaction = self.casual_agent.on_player_nearby(player_name, distance)
            if reaction:
                await self.emit_commentary(reaction)

    async def player_sent_chat(self, sender: str, message: str):
        if self.current_mode == "santai":
            reaction = self.casual_agent.on_player_chat(sender, message)
            if reaction:
                await self.emit_commentary(reaction)

    async def player_attacked_bot(self, attacker: str):
        self.health = max(1, self.health - 2)
        if self.current_mode == "santai":
            reaction = self.casual_agent.on_player_attack(attacker)
        else:
            reaction = self.speedrun_agent.on_damage_taken(attacker, self.health)
        await self.emit_commentary(reaction)
        await self.emit_state()

    async def player_gave_gift(self, giver: str, item_name: str):
        if self.current_mode == "santai":
            reaction = self.casual_agent.on_player_gift(giver, item_name)
            await self.emit_commentary(reaction)

    async def player_crouched(self, player_name: str):
        if self.current_mode == "santai":
            reaction = self.casual_agent.on_player_crouch(player_name)
            await self.emit_commentary(reaction)

    # --- Mode Kompe (Speedrun) Handlers ---
    async def advance_speedrun(self) -> str:
        """Trigger next speedrun milestone."""
        if self.current_mode != "kompe":
            await self.set_mode("kompe")

        phase, comment = self.speedrun_agent.advance_phase()
        await self.emit_commentary(comment)
        await self.emit_state()
        return comment
