import asyncio
import json
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
import websockets
from core.minecraft.casual_agent import CasualAgent
from core.minecraft.speedrun_agent import SpeedrunAgent, PHASE_NAMES, SpeedrunPhase
from core.minecraft.guard_agent import GuardAgent
from core.minecraft.multiplayer import MultiplayerSocialEngine

class MinecraftController:
    """
    Master Controller for Eve's Minecraft gameplay.
    Coordinates:
    - Mode switching: 'santai' (Casual / Social) vs 'kompe' (Speedrun / Competitive)
    - Multi-server manager (Add, Delete, Select, Connect)
    - State synchronization (Health, Position, Inventory, Current Objective)
    - Mineflayer bot process spawning and live WebSocket bridge communication
    - Real-time commentary triggered via Orchestrator
    """

    def __init__(self, bot_name: str = "EveMaybe", servers_config_path: str = "config/minecraft_servers.json"):
        self.bot_name = bot_name
        self.current_mode = "santai"  # "santai" or "kompe"
        self.is_active = False
        self.servers_config_path = Path(servers_config_path)

        self.casual_agent = CasualAgent(bot_name=bot_name)
        self.speedrun_agent = SpeedrunAgent(bot_name=bot_name)
        self.guard_agent = GuardAgent(bot_name=bot_name)
        self.guard_target: Optional[str] = None
        self.multiplayer = MultiplayerSocialEngine()

        # Multi-Server List
        self.servers: List[Dict[str, Any]] = []
        self.active_server: Optional[Dict[str, Any]] = None
        self.load_servers()

        # Telemetry & Game State
        self.health = 20
        self.food = 20
        self.pos = {"x": 0, "y": 0, "z": 0}
        self.connection_status = "disconnected"  # "disconnected", "connecting", "connected"
        self.viewer_url: Optional[str] = None
        self.nearby_players: List[Dict[str, Any]] = []
        self.latest_telemetry: Dict[str, Any] = {}

        # Bot Process & WebSocket Bridge
        self.bot_process: Optional[subprocess.Popen] = None
        self.bridge_ws: Optional[websockets.WebSocketClientProtocol] = None
        self.bridge_task: Optional[asyncio.Task] = None

        self.on_commentary_callback: Optional[Callable[[str], Any]] = None
        self.on_state_change_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
        self.on_in_game_chat_callback: Optional[Callable[[str, str], Any]] = None
        self.on_telemetry_callback: Optional[Callable[[Dict[str, Any]], Any]] = None

    def set_callbacks(
        self, 
        on_commentary: Callable[[str], Any], 
        on_state_change: Optional[Callable[[Dict[str, Any]], Any]] = None,
        on_in_game_chat: Optional[Callable[[str, str], Any]] = None,
        on_telemetry: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ):
        self.on_commentary_callback = on_commentary
        self.on_state_change_callback = on_state_change
        self.on_in_game_chat_callback = on_in_game_chat
        self.on_telemetry_callback = on_telemetry

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
            "viewer_url": self.viewer_url,
            "speedrun": {
                "phase": phase,
                "phase_name": phase_title,
                "split_time": self.speedrun_agent.get_elapsed_time_str()
            },
            "guard": {
                "target": self.guard_target,
                "kills": self.guard_agent.kills_count
            },
            "nearby_players": self.nearby_players,
            "telemetry": self.get_telemetry(),
            "multiplayer": self.multiplayer.get_state()
        }

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns the latest Mineflayer telemetry snapshot."""
        if self.latest_telemetry:
            return dict(self.latest_telemetry)
        return {
            "health": self.health,
            "food": self.food,
            "pos": self.pos,
            "biome": "unknown",
            "inventory": {},
            "nearby_players": list(self.nearby_players),
            "nearby_hostiles": [],
        }

    def get_inventory_count(self, item_terms: Any) -> int:
        """
        Sums inventory item counts matching any term in `item_terms`
        (case-insensitive substring match against item names).
        """
        if isinstance(item_terms, str):
            raw_terms = [item_terms]
        elif item_terms is None:
            raw_terms = []
        else:
            raw_terms = list(item_terms)

        terms = [str(t).strip().lower() for t in raw_terms if t and str(t).strip()]
        if not terms:
            return 0

        inventory = self.latest_telemetry.get("inventory", {})
        if not isinstance(inventory, dict):
            return 0

        total = 0
        for item_name, count in inventory.items():
            name_lower = str(item_name).lower()
            if any(term in name_lower for term in terms):
                try:
                    total += int(count)
                except (TypeError, ValueError):
                    pass
        return total

    async def _ensure_bridge_running(self):
        """Checks and starts the Mineflayer Node.js bot process and WebSocket bridge."""
        node_exe = Path("minecraft/node/node.exe")
        if not node_exe.exists():
            node_cmd = shutil.which("node") or "node"
        else:
            node_cmd = str(node_exe.resolve())

        if self.bot_process is None or self.bot_process.poll() is not None:
            print(f"[Minecraft] Starting Mineflayer bot process with: {node_cmd}...")
            self.bot_process = subprocess.Popen(
                [node_cmd, "bot.js"],
                cwd="minecraft"
            )
            await asyncio.sleep(1.5)

        if self.bridge_ws is None:
            for attempt in range(4):
                try:
                    self.bridge_ws = await websockets.connect("ws://localhost:25566")
                    print("[Minecraft] Connected to Mineflayer WebSocket bridge!")
                    if self.bridge_task is None or self.bridge_task.done():
                        self.bridge_task = asyncio.create_task(self._listen_bridge())
                    break
                except Exception as e:
                    if attempt < 3:
                        await asyncio.sleep(0.8)
                    else:
                        print(f"[Minecraft] Failed connecting to bridge ws://localhost:25566: {e}")

    async def _listen_bridge(self):
        """Listens for real-time events from the Mineflayer bot."""
        while self.bridge_ws:
            try:
                msg_raw = await self.bridge_ws.recv()
                event = json.loads(msg_raw)
                event_type = event.get("type")
                data = event.get("data", {})

                if event_type == "bot_spawned":
                    self.connection_status = "connected"
                    self.is_active = True
                    self.pos = data.get("pos", self.pos)
                    self.health = data.get("health", 20)
                    self.food = data.get("food", 20)
                    print(f"[Minecraft] Eve spawned in server! Pos: {self.pos}")
                    await self.emit_commentary("[emotion: happy] I'm in! Eve has spawned into the world! Time to explore. [action: wink]")
                    await self.emit_state()

                elif event_type == "player_nearby":
                    await self.player_joined_proximity(data.get("username", ""), data.get("distance", 5.0))

                elif event_type == "player_chat":
                    sender = data.get("username", "")
                    message = data.get("message", "")
                    if self.on_in_game_chat_callback and sender and message:
                        res = self.on_in_game_chat_callback(sender, message)
                        if asyncio.iscoroutine(res):
                            await res
                    else:
                        await self.player_sent_chat(sender, message)

                elif event_type == "casual_action":
                    act = data.get("action", "")
                    if act == "picked_flower":
                        fl = data.get("flower", "bunga")
                        await self.emit_commentary(f"[emotion: happy] Aku nemu bunga {fl}! Cantik banget buat ditaruh di base.")
                    elif act == "observed_animal":
                        an = data.get("animal", "hewan")
                        await self.emit_commentary(f"[emotion: happy] Liat deh chat, ada {an} lucu! Mau aku pelihara nggak ya?")
                    elif act == "picked_item":
                        await self.emit_commentary("[emotion: smug] Ooh, ada item gratis jatuh di tanah! Masuk ke kantongku.")
                    elif act == "gifted_player":
                        target = data.get("player", "Player")
                        item_name = data.get("item", "hadiah")
                        gift_reactions = [
                            f"[emotion: blush] Aku baru aja ngasih {item_name} ke {target}! Chat, manis banget kan aku hari ini? [action: giggle]",
                            f"[emotion: happy] Spesial buat {target}, aku kasih {item_name}! Disimpan baik-baik ya! [action: wink]",
                            f"[emotion: smug] Nih {target}, aku sedekahin {item_name}. Bersyukurlah kepada AI idol-mu!"
                        ]
                        import random
                        await self.emit_commentary(random.choice(gift_reactions))
                    await self.emit_state()

                elif event_type == "bot_hurt":
                    await self.player_attacked_bot(data.get("source", "danger"))

                elif event_type == "speedrun_action":
                    action_type = data.get("action", "")
                    reaction = self.speedrun_agent.on_speedrun_action(action_type, data)
                    if reaction:
                        await self.emit_commentary(reaction)
                    await self.emit_state()

                elif event_type == "speedrun_phase_completed":
                    next_p = data.get("nextPhase")
                    phase, comment = self.speedrun_agent.advance_phase(direct_phase=next_p)
                    await self.emit_commentary(comment)
                    await self.emit_state()

                elif event_type in ["guard_started", "guard_mode_activated"]:
                    tgt = data.get("target") or "Player"
                    self.current_mode = "guard"
                    self.guard_target = tgt
                    comment = self.guard_agent.on_guard_started(tgt)
                    await self.emit_commentary(comment)
                    await self.emit_state()

                elif event_type == "guard_threat_detected":
                    mob = data.get("mob", "monster")
                    tgt = data.get("targetPlayer", self.guard_target)
                    is_creeper = data.get("isCreeper", False)
                    comment = self.guard_agent.on_threat_detected(mob, tgt, is_creeper=is_creeper)
                    await self.emit_commentary(comment)
                    await self.emit_state()

                elif event_type == "guard_mob_eliminated":
                    mob = data.get("mob", "monster")
                    tgt = data.get("targetPlayer", self.guard_target)
                    comment = self.guard_agent.on_mob_eliminated(mob, tgt)
                    await self.emit_commentary(comment)
                    await self.emit_state()

                elif event_type == "guard_player_hurt":
                    attacker = data.get("attacker", "hostile")
                    tgt = data.get("target", self.guard_target)
                    comment = self.guard_agent.on_player_hurt(attacker, tgt)
                    await self.emit_commentary(comment)
                    await self.emit_state()

                elif event_type == "mc_telemetry":
                    self.health = data.get("health", self.health)
                    self.food = data.get("food", self.food)
                    self.pos = data.get("pos", self.pos)
                    if "nearby_players" in data and isinstance(data["nearby_players"], list):
                        self.nearby_players = data["nearby_players"]
                    self.latest_telemetry = dict(data)
                    if self.on_telemetry_callback:
                        res = self.on_telemetry_callback(self.latest_telemetry)
                        if asyncio.iscoroutine(res):
                            await res
                    await self.emit_state()

                elif event_type == "viewer_started":
                    self.viewer_url = data.get("url", "http://localhost:3007")
                    print(f"[Minecraft] Live 3D POV window available at: {self.viewer_url}")
                    await self.emit_state()

                elif event_type in ["bot_kicked", "bot_error", "bot_disconnected"]:
                    self.connection_status = "disconnected"
                    self.is_active = False
                    self.viewer_url = None
                    reason = data.get("reason") or data.get("message") or "Connection dropped"
                    print(f"[Minecraft] Bot disconnected from server: {reason}")
                    await self.emit_commentary(f"[emotion: sad] Disconnected from server: {reason}")
                    await self.emit_state()

            except Exception as e:
                print(f"[Minecraft Bridge Reader] Error or disconnect: {e}")
                break
        self.bridge_ws = None

    async def connect_to_server(self, server_id: Optional[str] = None) -> str:
        """Connect bot to designated server."""
        if server_id:
            match = next((s for s in self.servers if s.get("id") == server_id), None)
            if match:
                self.active_server = match

        if not self.active_server:
            return "No server selected."

        name = self.active_server.get("name", "Minecraft Server")
        host = self.active_server.get("host", "basic.raehost.com")
        port = self.active_server.get("port", 19214)
        version = self.active_server.get("version", "1.21.1")

        self.connection_status = "connecting"
        await self.emit_state()

        speech = f"[emotion: happy] Logging into {name} at {host}:{port}! Wish me luck chat, Eve is entering the server! [action: wink]"
        await self.emit_commentary(speech)

        # Start bridge and send connect command
        await self._ensure_bridge_running()
        if self.bridge_ws:
            cmd = {
                "action": "connect_server",
                "host": host,
                "port": port,
                "username": self.bot_name,
                "version": version,
                "mode": self.current_mode
            }
            await self.bridge_ws.send(json.dumps(cmd))
            print(f"[Minecraft] Sent connect command to bridge for {host}:{port}")

        return speech

    async def disconnect_from_server(self) -> str:
        """Disconnect bot from active server."""
        self.connection_status = "disconnected"
        self.is_active = False

        if self.bridge_ws:
            try:
                await self.bridge_ws.send(json.dumps({"action": "disconnect_server"}))
            except Exception:
                pass

        if self.bot_process and self.bot_process.poll() is None:
            try:
                self.bot_process.terminate()
            except Exception:
                pass
            self.bot_process = None

        speech = "[emotion: smug] Left the server for now! Back to streaming with chat."
        await self.emit_commentary(speech)
        await self.emit_state()
        return speech

    async def send_bridge_cmd(self, action: str, **kwargs):
        """Sends command payload to Mineflayer bot bridge."""
        if self.bridge_ws:
            payload = {"action": action, **kwargs}
            try:
                await self.bridge_ws.send(json.dumps(payload))
            except Exception as e:
                print(f"[Minecraft Command Error] {e}")

    async def send_chat(self, message: str):
        """Send message into Minecraft in-game chat."""
        import re
        clean_msg = re.sub(r'\[(?:emotion|action):[^\]]+\]', '', message).strip()
        clean_msg = clean_msg.replace('\n', ' ')
        if len(clean_msg) > 240:
            clean_msg = clean_msg[:237] + "..."
        if clean_msg:
            await self.send_bridge_cmd("chat", message=clean_msg)

    async def follow_nearest(self):
        await self.send_bridge_cmd("follow_nearest")

    async def stop_moving(self):
        await self.send_bridge_cmd("stop_moving")

    async def jump(self):
        await self.send_bridge_cmd("jump")

    async def crouch(self):
        await self.send_bridge_cmd("crouch")

    async def dance(self):
        await self.send_bridge_cmd("dance")

    async def celebrate(self, user: str = "", amount: str = ""):
        await self.send_bridge_cmd("celebrate", user=user, amount=amount)

    async def gift_nearest(self):
        await self.send_bridge_cmd("gift_nearest")

    async def look_at(self, target: str):
        await self.send_bridge_cmd("look_at", target=target)

    async def toggle_wander(self):
        await self.send_bridge_cmd("toggle_wander")

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

    async def set_mode(self, new_mode: str, target: Optional[str] = None) -> str:
        """Switch between 'santai' (Casual), 'kompe' (Speedrun), and 'guard' (Bodyguard)."""
        new_mode = new_mode.lower()
        if new_mode not in ["santai", "kompe", "guard"]:
            return "Mode must be 'santai', 'kompe', or 'guard'."

        self.current_mode = new_mode
        self.is_active = True
        if target:
            self.guard_target = target

        # Send command to Mineflayer bridge so it starts/stops appropriate behavior
        await self.send_bridge_cmd("set_mode", mode=new_mode, target=self.guard_target)

        if new_mode == "santai":
            speech = "[emotion: happy] Switching to Mode Santai! Time to chill, explore, and hang out with everyone on the server! [action: wink]"
        elif new_mode == "guard":
            speech = self.guard_agent.on_guard_started(self.guard_target)
        else:
            speech = self.speedrun_agent.start_run()

        await self.emit_commentary(speech)
        await self.emit_state()
        return speech

    async def guard_player(self, player_name: Optional[str] = None) -> str:
        """Explicitly switch to Mode Guard for a player."""
        self.current_mode = "guard"
        self.guard_target = player_name
        self.is_active = True

        await self.send_bridge_cmd("guard_player", target=player_name)
        speech = self.guard_agent.on_guard_started(player_name)
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
        # 1. Process in multiplayer social engine
        reaction = self.multiplayer.process_in_game_chat(sender, message)
        if reaction:
            await self.emit_commentary(reaction)
            return

        # 2. Fallback to casual agent
        if self.current_mode == "santai":
            reaction = self.casual_agent.on_player_chat(sender, message)
            if reaction:
                await self.emit_commentary(reaction)

    async def player_attacked_bot(self, attacker: str):
        self.health = max(1, self.health - 2)
        self.multiplayer.ledger.record_pvp(attacker, 2.0)
        self.multiplayer.save()
        if self.current_mode == "santai":
            reaction = self.casual_agent.on_player_attack(attacker)
        elif self.current_mode == "guard":
            reaction = self.guard_agent.on_player_hurt(attacker, self.guard_target or "Eve")
        else:
            reaction = self.speedrun_agent.on_damage_taken(attacker, self.health)
        await self.emit_commentary(reaction)
        await self.emit_state()

    async def player_gave_gift(self, giver: str, item_name: str):
        self.multiplayer.ledger.record_donation(giver, item_name, 1)
        self.multiplayer.save()
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
        # Inform the bridge bot of the phase advancement
        await self.send_bridge_cmd("advance_speedrun", phase=phase)
        await self.emit_commentary(comment)
        await self.emit_state()
        return comment
