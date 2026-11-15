import time
import random
from typing import Dict, Any, List, Optional, Tuple

class SpeedrunPhase:
    WOOD_TOOLS = 1
    STONE_AGE = 2
    IRON_AND_FOOD = 3
    NETHER_PORTAL = 4
    BLAZE_RODS = 5
    ENDER_PEARLS = 6
    EYES_OF_ENDER = 7
    LOCATE_STRONGHOLD = 8
    ENTER_END = 9
    SLAY_DRAGON = 10
    VICTORY = 11

PHASE_NAMES = {
    SpeedrunPhase.WOOD_TOOLS: "Phase 1: Gathering Wood & Crafting Table",
    SpeedrunPhase.STONE_AGE: "Phase 2: Stone Tools Upgrade",
    SpeedrunPhase.IRON_AND_FOOD: "Phase 3: Smelting Iron & Water Bucket",
    SpeedrunPhase.NETHER_PORTAL: "Phase 4: Speedrun Lava Portal to Nether",
    SpeedrunPhase.BLAZE_RODS: "Phase 5: Nether Fortress & Blaze Rods",
    SpeedrunPhase.ENDER_PEARLS: "Phase 6: Piglin Bartering / Ender Pearls",
    SpeedrunPhase.EYES_OF_ENDER: "Phase 7: Crafting Eyes of Ender",
    SpeedrunPhase.LOCATE_STRONGHOLD: "Phase 8: Stronghold Triangulation",
    SpeedrunPhase.ENTER_END: "Phase 9: Activating End Portal",
    SpeedrunPhase.SLAY_DRAGON: "Phase 10: Ender Dragon Slay",
    SpeedrunPhase.VICTORY: "VICTORY: Minecraft Completed! GG!"
}

class SpeedrunAgent:
    """
    Mode Kompe (Competitive / Speedrun Gameplay):
    Follows an optimized speedrun state machine to defeat the Ender Dragon as fast as possible.
    Provides live timer splits, competitive banter, and tactical commentary.
    """

    def __init__(self, bot_name: str = "EveMaybe"):
        self.bot_name = bot_name
        self.current_phase = SpeedrunPhase.WOOD_TOOLS
        self.start_time: Optional[float] = None
        self.splits: Dict[int, float] = {}
        self.inventory: Dict[str, int] = {}
        self.dragon_health = 200
        self.last_action_comment_time = 0.0

    def start_run(self) -> str:
        self.start_time = time.time()
        self.current_phase = SpeedrunPhase.WOOD_TOOLS
        self.splits = {}
        self.last_action_comment_time = time.time()
        return "[emotion: smug] Mode Kompe activated! Starting the speedrun timer right now! Chat, clip this, we are going for the world record! [action: wink]"

    def get_elapsed_time_str(self) -> str:
        if not self.start_time:
            return "00:00"
        elapsed = int(time.time() - self.start_time)
        mins = elapsed // 60
        secs = elapsed % 60
        return f"{mins:02d}:{secs:02d}"

    def set_phase(self, phase: int) -> Tuple[int, str]:
        """Manually or externally set phase."""
        self.current_phase = max(1, min(SpeedrunPhase.VICTORY, phase))
        return self.advance_phase(direct_phase=self.current_phase)

    def advance_phase(self, direct_phase: Optional[int] = None) -> Tuple[int, str]:
        """Advance to next speedrun milestone."""
        if not self.start_time:
            self.start_time = time.time()

        split_time = self.get_elapsed_time_str()
        self.splits[self.current_phase] = time.time() - self.start_time

        if direct_phase is not None:
            self.current_phase = direct_phase
        elif self.current_phase < SpeedrunPhase.VICTORY:
            self.current_phase += 1

        new_phase_name = PHASE_NAMES.get(self.current_phase, "Unknown Phase")

        # Commentary per milestone
        commentary_map = {
            SpeedrunPhase.STONE_AGE: f"[emotion: happy] Wood tools crafted at {split_time}! Moving straight to stone mining. No time to waste!",
            SpeedrunPhase.IRON_AND_FOOD: f"[emotion: smug] Stone age cleared at {split_time}! Now hunting food and smelting iron for our bucket. Pacing is solid!",
            SpeedrunPhase.NETHER_PORTAL: f"[emotion: happy] Iron bucket acquired at {split_time}! Found a surface lava pool, casting the portal frame with water!",
            SpeedrunPhase.BLAZE_RODS: f"[emotion: surprised] We made it to the Nether! Spotting a Fortress nearby, time to farm some Blazes!",
            SpeedrunPhase.ENDER_PEARLS: f"[emotion: happy] Blaze rods secured at {split_time}! Now trading all our gold ingots with Piglins for pearls. Come on RNG!",
            SpeedrunPhase.EYES_OF_ENDER: f"[emotion: smug] Got 14 ender pearls! Combining with blaze powder. Eyes of Ender ready at {split_time}!",
            SpeedrunPhase.LOCATE_STRONGHOLD: f"[emotion: happy] Throwing the first Eye at {split_time}! Calculating vector trajectory... Stronghold is approximately 600 blocks north!",
            SpeedrunPhase.ENTER_END: f"[emotion: surprised] Portal room discovered! Filling the frame sockets... The End portal is open at {split_time}!",
            SpeedrunPhase.SLAY_DRAGON: f"[emotion: angry] Entering The End! Dragon is perching. Setting up bed explosion bombs... watch this burst damage!",
            SpeedrunPhase.VICTORY: f"[emotion: smug] THE DRAGON IS DEFEATED at {split_time}! GG chat! That is how an AI speedruns Minecraft! [action: giggle]"
        }

        comment = commentary_map.get(
            self.current_phase,
            f"[emotion: happy] Advanced to {new_phase_name} at {split_time}!"
        )
        self.last_action_comment_time = time.time()
        return self.current_phase, comment

    def on_speedrun_action(self, action: str, details: Dict[str, Any]) -> Optional[str]:
        """Triggered during in-game live actions like digging logs, mining stone, or hunting."""
        now = time.time()
        # Cooldown check: at least 7 seconds between minor micro-commentaries
        if now - self.last_action_comment_time < 7.0:
            return None

        self.last_action_comment_time = now
        split_time = self.get_elapsed_time_str()

        if action == "log_dug":
            log_type = details.get("block", "tree log")
            lines = [
                f"[emotion: smug] Down goes another {log_type}! Gathering wood fast at {split_time}.",
                f"[emotion: happy] Got the wood! Crafting table is practically in my hands.",
                f"[emotion: happy] Timbeeer! First logs collected, keeping optimal speedrun pace."
            ]
            return random.choice(lines)

        elif action == "searching_wood":
            lines = [
                f"[emotion: neutral] Scanning chunk coordinates for trees... Spotting one over there!",
                f"[emotion: happy] Pathfinding towards the nearest tree line at {split_time}."
            ]
            return random.choice(lines)

        elif action == "stone_mined":
            lines = [
                f"[emotion: smug] Cobblestone mined! Upgrading our pickaxe and axe right away.",
                f"[emotion: happy] Stone collected! Goodbye flimsy wooden tools, hello efficiency!"
            ]
            return random.choice(lines)

        elif action == "mob_hunted":
            lines = [
                f"[emotion: smug] Target secured! Food drop in our inventory, stamina restored.",
                f"[emotion: happy] Hunter phase active! Quick combat clears the path."
            ]
            return random.choice(lines)

        elif action == "defended_mob":
            return "[emotion: angry] Back off, mob! You are interfering with a world record pace!"

        return None

    def on_damage_taken(self, damage_source: str, hp_left: int) -> str:
        """Triggered when Eve takes damage during speedrun."""
        if hp_left <= 6:
            return f"[emotion: angry] Low HP alert! Only {hp_left} hearts left! Eating food and shielding immediately!"
        return f"[emotion: annoyed] Took damage from {damage_source}. Annoying, but the split timer won't stop for scratches!"

    def on_mob_slain(self, mob_name: str) -> str:
        """Triggered when Eve defeats a hostile mob."""
        return f"[emotion: smug] Eliminated {mob_name}! Moving forward without breaking stride."
