import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

try:
    import tests  # noqa: F401
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

from core.chat_receiver import ChatReceiver
from core.collab.manager import CollabManager
from core.collab.protocol import CollabEnvelope
from core.platforms.discord_adapter import DiscordAdapter
from core.platforms.tiktok import TikTokLiveAdapter


class _FakeHTTPResp:
    def __init__(self, status: int, json_data=None, text_data: str = ""):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeWS:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def send_json(self, payload):
        self.sent.append(payload)


class TestPlatformsV2AndCollab(unittest.IsolatedAsyncioTestCase):
    def test_twitch_ircv3_tags_bits_sub_and_raid(self):
        bits_line = "@display-name=RichViewer;bits=500 :richviewer!richviewer@richviewer.tmi.twitch.tv PRIVMSG #evemaybe :Cheer500 nice clutch!"
        parsed_bits = ChatReceiver.parse_twitch_irc_line(bits_line)
        self.assertIsNotNone(parsed_bits)
        self.assertEqual(parsed_bits["user"], "RichViewer")
        self.assertTrue(parsed_bits["is_donation"])
        self.assertEqual(parsed_bits["donation_amount"], "500")
        self.assertEqual(parsed_bits["donation_currency"], "bits")

        sub_line = "@display-name=SubFan;msg-id=sub;system-msg=SubFan\\ssubscribed! :tmi.twitch.tv USERNOTICE #evemaybe :Hello!"
        parsed_sub = ChatReceiver.parse_twitch_irc_line(sub_line)
        self.assertIsNotNone(parsed_sub)
        self.assertEqual(parsed_sub["user"], "SubFan")
        self.assertFalse(parsed_sub["is_donation"])

        subgift_line = "@display-name=Gifter;msg-id=subgift :tmi.twitch.tv USERNOTICE #evemaybe"
        parsed_gift = ChatReceiver.parse_twitch_irc_line(subgift_line)
        self.assertIsNotNone(parsed_gift)
        self.assertTrue(parsed_gift["is_donation"])
        self.assertEqual(parsed_gift["donation_currency"], "subgift")

        raid_line = "@display-name=Raider;msg-id=raid;system-msg=Raider\\sis\\sraiding\\swith\\s20\\sviewers! :tmi.twitch.tv USERNOTICE #evemaybe"
        parsed_raid = ChatReceiver.parse_twitch_irc_line(raid_line)
        self.assertIsNotNone(parsed_raid)
        self.assertEqual(parsed_raid["user"], "Raider")

    async def test_discord_no_backlog_startup_outbound_reply_and_gateway(self):
        receiver = ChatReceiver()
        adapter = DiscordAdapter(
            receiver=receiver,
            bot_token="test-token",
            channel_id="chan-1",
            enabled=True,
            skip_initial_backlog=True,
        )
        adapter.is_running = True

        class _MockSession:
            closed = False

            def __init__(self, responses):
                self._responses = responses
                self.posts = []

            def get(self, url, **kwargs):
                return self._responses.pop(0)

            def post(self, url, **kwargs):
                self.posts.append((url, kwargs))
                return _FakeHTTPResp(200, json_data={"id": "999"})

        backlog_msgs = [
            {"id": "200", "content": "old message 2", "author": {"username": "OldUser"}},
            {"id": "100", "content": "old message 1", "author": {"username": "OldUser"}},
        ]
        new_msgs = [
            {"id": "201", "content": "fresh message!", "author": {"username": "NewUser"}},
        ]
        session = _MockSession([
            _FakeHTTPResp(200, json_data=backlog_msgs),
            _FakeHTTPResp(200, json_data=new_msgs),
        ])

        await adapter.poll_once(session=session)
        self.assertEqual(receiver.queue.qsize(), 0)
        self.assertEqual(adapter._last_message_id, "200")

        await adapter.poll_once(session=session)
        self.assertEqual(receiver.queue.qsize(), 1)
        msg = await receiver.get_next_message()
        self.assertEqual(msg.user, "NewUser")
        self.assertEqual(msg.text, "fresh message!")

        adapter._session = session
        sent_ok = await adapter.send_message("Hello Discord!")
        self.assertTrue(sent_ok)
        self.assertEqual(len(session.posts), 1)
        self.assertIn("chan-1/messages", session.posts[0][0])

        # Gateway frame handling
        ws = _FakeWS()
        keep_hello = await adapter._handle_gateway_payload(ws, {"op": 10, "d": {"heartbeat_interval": 45000}})
        self.assertTrue(keep_hello)
        self.assertEqual(ws.sent[0]["op"], 2)  # IDENTIFY
        if adapter._heartbeat_task:
            adapter._heartbeat_task.cancel()
            try:
                await adapter._heartbeat_task
            except asyncio.CancelledError:
                pass

        keep_msg = await adapter._handle_gateway_payload(
            ws,
            {
                "op": 0,
                "s": 5,
                "t": "MESSAGE_CREATE",
                "d": {
                    "id": "300",
                    "channel_id": "chan-1",
                    "content": "gateway hello",
                    "author": {"username": "GWUser"},
                },
            },
        )
        self.assertTrue(keep_msg)
        gw_msg = await receiver.get_next_message()
        self.assertEqual(gw_msg.text, "gateway hello")

        keep_reconn = await adapter._handle_gateway_payload(ws, {"op": 7})
        self.assertFalse(keep_reconn)

    async def test_tiktok_live_adapter_comments_and_gifts(self):
        receiver = ChatReceiver()
        adapter = TikTokLiveAdapter(receiver=receiver, username="evemaybe", enabled=True)

        await adapter.handle_tiktok_event("comment", {"nickname": "TTUser", "comment": "Keren banget!"})
        await adapter.handle_tiktok_event(
            "gift",
            {"unique_id": "GifterTT", "gift_name": "Rose", "repeat_count": 3, "diamond_count": 30},
        )

        m1 = await receiver.get_next_message()
        self.assertEqual(m1.source, "tiktok")
        self.assertEqual(m1.user, "TTUser")
        self.assertFalse(m1.is_donation)

        m2 = await receiver.get_next_message()
        self.assertEqual(m2.source, "tiktok")
        self.assertTrue(m2.is_donation)
        self.assertEqual(m2.donation_amount, "30")
        self.assertEqual(m2.donation_currency, "diamonds")

    async def test_collab_manager_action_callbacks_and_nonblocking_reply_dispatch(self):
        seen_actions = []
        reply_started = asyncio.Event()
        release_reply = asyncio.Event()

        async def _on_duet(env: CollabEnvelope):
            seen_actions.append(("duet_sync", env.payload))

        async def _on_emote(env: CollabEnvelope):
            seen_actions.append(("emote_sync", env.payload))

        async def _on_game(env: CollabEnvelope):
            seen_actions.append(("game_move", env.payload))

        async def _slow_reply(env: CollabEnvelope):
            reply_started.set()
            await release_reply.wait()

        mgr = CollabManager(settings={"enabled": True, "max_collab_turns": 5, "turn_cooldown_sec": 0.0})
        mgr.set_action_callbacks(on_duet_sync=_on_duet, on_emote_sync=_on_emote, on_game_move=_on_game)
        mgr.set_reply_callback(_slow_reply)

        for evt_type, payload in (
            ("duet_sync", {"song_id": "song1", "action": "start"}),
            ("emote_sync", {"emotion": "happy"}),
            ("game_move", {"move": "e2e4"}),
        ):
            env = CollabEnvelope(event_type=evt_type, sender_id="peer-1", sender_name="Peer", payload=payload)
            res = await mgr.handle_incoming_envelope(env.to_dict(), is_loopback=True)
            self.assertTrue(res["accepted"])

        self.assertEqual([a[0] for a in seen_actions], ["duet_sync", "emote_sync", "game_move"])

        # Non-blocking reply dispatch on turn_utterance
        utt = CollabEnvelope(event_type="turn_utterance", sender_id="peer-1", sender_name="Peer", speech="Your turn!")
        res_utt = await asyncio.wait_for(mgr.handle_incoming_envelope(utt.to_dict(), is_loopback=True), timeout=0.5)
        self.assertTrue(res_utt["reply_triggered"])
        await asyncio.wait_for(reply_started.wait(), timeout=0.5)
        self.assertEqual(len(mgr._reply_tasks), 1)

        await mgr.shutdown()
        self.assertEqual(len(mgr._reply_tasks), 0)


if __name__ == "__main__":
    unittest.main()
