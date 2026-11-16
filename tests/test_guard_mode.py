import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
from core.minecraft.guard_agent import GuardAgent
from core.minecraft.controller import MinecraftController
from core.orchestrator import Orchestrator

class TestGuardMode(unittest.IsolatedAsyncioTestCase):

    def test_guard_agent_persona(self):
        agent = GuardAgent(bot_name="EveMaybe")
        
        # 1. Activation
        start_line = agent.on_guard_started("PlayerOne")
        self.assertIn("PlayerOne", start_line)
        self.assertIn("[emotion:", start_line)
        self.assertEqual(agent.guarded_player, "PlayerOne")
        self.assertEqual(agent.kills_count, 0)

        # 2. General Threat Detection
        threat_line = agent.on_threat_detected("zombie", "PlayerOne")
        self.assertIn("Zombie", threat_line)
        self.assertIn("PlayerOne", threat_line)

        # 3. Creeper Threat Detection
        creeper_line = agent.on_threat_detected("creeper", "PlayerOne", is_creeper=True)
        self.assertIn("Creeper", creeper_line)
        self.assertIn("PlayerOne", creeper_line)

        # 4. Mob Eliminated
        kill_line = agent.on_mob_eliminated("zombie", "PlayerOne")
        self.assertIn("Zombie", kill_line)
        self.assertEqual(agent.kills_count, 1)

        # 5. Player Hurt
        hurt_line = agent.on_player_hurt("Skeleton", "PlayerOne")
        self.assertIn("Skeleton", hurt_line)
        self.assertIn("PlayerOne", hurt_line)

    async def test_minecraft_controller_guard_mode(self):
        controller = MinecraftController(bot_name="EveMaybe")
        commentary_log = []
        controller.set_callbacks(on_commentary=lambda msg: commentary_log.append(msg))

        # Switch to guard mode
        speech = await controller.guard_player("Alex")
        self.assertEqual(controller.current_mode, "guard")
        self.assertEqual(controller.guard_target, "Alex")
        self.assertIn("Alex", speech)

        # Verify status payload
        status = controller.get_status()
        self.assertEqual(status["mode"], "guard")
        self.assertEqual(status["guard"]["target"], "Alex")
        self.assertEqual(status["guard"]["kills"], 0)

        # Simulate bridge events
        # 1. Threat detected
        threat_msg = controller.guard_agent.on_threat_detected("spider", "Alex")
        await controller.emit_commentary(threat_msg)
        # 2. Mob eliminated
        kill_msg = controller.guard_agent.on_mob_eliminated("spider", "Alex")
        await controller.emit_commentary(kill_msg)

        self.assertEqual(controller.guard_agent.kills_count, 1)
        status_after_kill = controller.get_status()
        self.assertEqual(status_after_kill["guard"]["kills"], 1)

    async def test_orchestrator_guard_command(self):
        orch = Orchestrator()
        orch.tts.speak = AsyncMock() # Mock out TTS speech delay for lightning-fast test
        orch.broadcast = AsyncMock()

        # Test in-game chat requesting guard mode
        from core.conversation.chat_curator import LiveChatMessage, ChatInteraction
        interaction = ChatInteraction(
            interaction_type="single_message",
            primary_message=LiveChatMessage(
                user="DiamondHunter",
                text="!mc guard DiamondHunter",
                source="minecraft"
            )
        )

        await orch._execute_interaction(interaction)
        self.assertEqual(orch.minecraft.current_mode, "guard")
        self.assertEqual(orch.minecraft.guard_target, "DiamondHunter")

if __name__ == "__main__":
    unittest.main()
