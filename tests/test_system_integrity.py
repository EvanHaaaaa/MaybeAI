import asyncio
import unittest
from unittest.mock import AsyncMock
from core.brain import Brain
from core.moderator import Moderator
from core.actions import ActionParser
from core.singer import Singer
from core.conversation.chat_curator import ChatCurator, LiveChatMessage
from core.minecraft.controller import MinecraftController
from core.orchestrator import Orchestrator

class TestSystemIntegrity(unittest.IsolatedAsyncioTestCase):

    def test_action_parser(self):
        raw = "[emotion: smug] You really thought you could win? [action: giggle]"
        clean, emotions, actions = ActionParser.parse(raw)
        self.assertEqual(clean, "You really thought you could win?")
        self.assertEqual(emotions, ["smug"])
        self.assertEqual(actions, ["giggle"])

    def test_moderator(self):
        mod = Moderator()
        is_safe, cleaned = mod.clean_text("Hello Eve, you are cool!")
        self.assertTrue(is_safe)
        self.assertIn("Hello", cleaned)

    def test_chat_curator_priority(self):
        curator = ChatCurator()
        
        # Ingest regular vs joke vs donation
        curator.add_message("User1", "Just watching the stream")
        curator.add_message("User2", "Tahu gak kenapa ayam nyebrang jalan?")
        curator.add_message("Donator", "Keep up the great stream!", is_donation=True, donation_amount="$10")

        interaction = curator.select_next_interaction()
        self.assertIsNotNone(interaction)
        # Donation must be selected first due to high urgency
        self.assertEqual(interaction.interaction_type, "donation")
        self.assertEqual(interaction.primary_message.user, "Donator")

    def test_singer_catalog(self):
        singer = Singer()
        songs = singer.get_available_songs()
        self.assertGreater(len(songs), 0)
        self.assertEqual(songs[0]["id"], "digital_world")

    def test_minecraft_controller_server_management(self):
        mc = MinecraftController(servers_config_path="config/minecraft_servers.json")
        initial_count = len(mc.servers)
        new_srv = mc.add_server(name="Test Server", host="127.0.0.1", port=25565)
        self.assertEqual(len(mc.servers), initial_count + 1)
        
        # Delete test server
        deleted = mc.delete_server(new_srv["id"])
        self.assertTrue(deleted)
        self.assertEqual(len(mc.servers), initial_count)

    async def test_brain_offline_and_intent(self):
        brain = Brain()
        resp = await brain.generate_response(user_name="ViewerX", message="Halo Eve apa kabar?")
        self.assertIn("[emotion:", resp)

    async def test_orchestrator_pipeline(self):
        orch = Orchestrator()
        orch.tts.speak = AsyncMock()
        orch.broadcast = AsyncMock()

        await orch.chat.put_message(user="TestFan", text="Halo Eve apa kabar?")
        msg = await orch.chat.get_next_message()
        await orch._ingest_message(msg)

        interaction = orch.brain.conversation.select_next_interaction()
        self.assertIsNotNone(interaction)
        await orch._execute_interaction(interaction)
        orch.broadcast.assert_called()

    async def test_mic_input_priority_and_orchestration(self):
        orch = Orchestrator()
        orch.tts.speak = AsyncMock()
        orch.broadcast = AsyncMock()

        # Ingest text chat vs mic spoken voice
        await orch.chat.put_message(user="Chatter1", text="Just regular chat", source="web")
        await orch.chat.put_message(user="Creator", text="Halo Eve, kamu dengar suaraku gak?", source="mic")

        # Ingest both
        while not orch.chat.queue.empty():
            m = await orch.chat.get_next_message()
            await orch._ingest_message(m)

        # The mic message MUST be selected first because it has priority 95+ vs 10
        interaction = orch.brain.conversation.select_next_interaction()
        self.assertIsNotNone(interaction)
        self.assertEqual(interaction.primary_message.source, "mic")
        self.assertEqual(interaction.primary_message.user, "Creator")

        # Process the voice interaction
        await orch._execute_interaction(interaction)
        orch.tts.speak.assert_called()

if __name__ == "__main__":
    unittest.main()
