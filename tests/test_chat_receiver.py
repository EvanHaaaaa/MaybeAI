import unittest
from unittest.mock import MagicMock

from core.chat_receiver import ChatMessage, ChatReceiver


class TestChatReceiver(unittest.IsolatedAsyncioTestCase):
    async def test_queue_fifo_and_status(self):
        receiver = ChatReceiver(twitch_channel="eve_channel")
        await receiver.put_message(user="Viewer1", text="First", source="web")
        await receiver.put_message(user="Viewer2", text="Second", source="twitch")

        status = receiver.get_status()
        self.assertEqual(status["channel"], "eve_channel")
        self.assertEqual(status["queue_size"], 2)
        self.assertFalse(status["is_running"])
        self.assertFalse(status["is_connected"])

        m1 = await receiver.get_next_message()
        m2 = await receiver.get_next_message()
        self.assertEqual((m1.user, m1.text, m1.source), ("Viewer1", "First", "web"))
        self.assertEqual((m2.user, m2.text, m2.source), ("Viewer2", "Second", "twitch"))
        self.assertEqual(receiver.get_status()["queue_size"], 0)

    async def test_creator_detected_by_source_not_username(self):
        receiver = ChatReceiver()

        # Spoofed creator-like usernames on non-creator sources must NOT grant creator status
        for spoofed_user in ("creator", "Creator", "admin", "evanh", "EvanH"):
            for source in ("web", "twitch"):
                await receiver.put_message(user=spoofed_user, text="hello", source=source)
                msg = await receiver.get_next_message()
                self.assertFalse(
                    msg.is_creator,
                    f"Username {spoofed_user!r} on source={source!r} must not be creator",
                )

        # Trusted internal sources ("creator", "mic") grant creator status regardless of username
        for source in ("creator", "mic"):
            await receiver.put_message(user="Host", text="hi", source=source)
            msg = await receiver.get_next_message()
            self.assertTrue(msg.is_creator, f"source={source!r} should default is_creator=True")

    async def test_explicit_is_creator_override(self):
        msg_forced_false = ChatMessage(user="Host", text="hi", source="creator", is_creator=False)
        msg_forced_true = ChatMessage(user="Host", text="hi", source="web", is_creator=True)
        self.assertFalse(msg_forced_false.is_creator)
        self.assertTrue(msg_forced_true.is_creator)

    async def test_stop_resets_state_and_closes_writer(self):
        receiver = ChatReceiver()
        receiver.is_running = True
        receiver.is_connected = True
        mock_writer = MagicMock()
        receiver._writer = mock_writer

        receiver.stop()
        self.assertFalse(receiver.is_running)
        self.assertFalse(receiver.is_connected)
        self.assertIsNone(receiver._writer)
        mock_writer.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
