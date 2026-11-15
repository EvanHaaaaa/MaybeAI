import asyncio
import json
from typing import Dict, Any, Optional, Callable, List
from core.minecraft.casual_agent import CasualAgent
from core.minecraft.speedrun_agent import SpeedrunAgent, PHASE_NAMES, SpeedrunPhase

class MinecraftController:
    """
    Master Controller for Eve's Minecraft gameplay.
    Coordinates:
    - Mode switching: 'santai' (Casual / Social) vs 'kompe' (Speedrun / Competitive)
    - State synchronization (Health, Position, Inventory, Current Objective)
    - In-game Player Interactions & Chat
    - Real-time commentary triggered via Orchestrator
    """

    def __init__(self, bot_name: str = "EveMaybe"):
        self.bot_name = bot_name
        self.current_mode = "santai"  # "santai" or "kompe"
        self.is_active = False

        self.casual_agent = CasualAgent(bot_name=bot_name)
        self.speedrun_agent = SpeedrunAgent(bot_name=bot_name)

        # Telemetry & Game State
        self.health = 20
        self.food = 20
        self.pos = {"x": 120, "y": 64, "z": -250}
        self.server_info = {"host": "localhost", "port": 25565, "connected": False}
        self.nearby_players: List[Dict[str, Any]] = []

        self.on_commentary_callback: Optional[Callable[[str], Any]] = None
        self.on_state_change_callback: Optional[Callable[[Dict[str, Any]], Any]] = None

    def set_callbacks(self, on_commentary: Callable[[str], Any], on_state_change: Optional[Callable[[Dict[str, Any]], Any]] = None):
        self.on_commentary_callback = on_commentary
        self.on_state_change_callback = on_state_change

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
            "server": self.server_info,
            "speedrun": {
                "phase": phase,
                "phase_name": phase_title,
                "split_time": self.speedrun_agent.get_elapsed_time_str()
            },
            "nearby_players": self.nearby_players
        }

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
