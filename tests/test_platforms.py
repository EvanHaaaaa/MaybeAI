import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

try:
    import tests  # noqa: F401  # Ensure tests/__init__.py sets MAYBEAI_LLM_PROVIDER=mock
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

from core.chat_receiver import ChatReceiver
from core.config_manager import ConfigManager
from core.platforms import YouTubeLiveAdapter, DiscordAdapter


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


class TestYouTubeLiveAdapter(unittest.IsolatedAsyncioTestCase):
    async def test_graceful_degradation_when_disabled_or_unconfigured(self):
        receiver = ChatReceiver()
        disabled = YouTubeLiveAdapter(receiver=receiver, api_key="key", live_chat_id="chat1", enabled=False)
        self.assertFalse(await disabled.start())
        self.assertFalse(disabled.is_running)

        missing_creds = YouTubeLiveAdapter(receiver=receiver, api_key="", live_chat_id="", enabled=True)
        self.assertFalse(await missing_creds.start())
        self.assertFalse(missing_creds.is_running)
        self.assertIsNotNone(missing_creds.last_error)

    async def test_poll_once_maps_chat_superchat_supersticker_and_deduplicates(self):
        receiver = ChatReceiver()
        adapter = YouTubeLiveAdapter(
            receiver=receiver,
            api_key="yt-test-key",
            live_chat_id="LCID123",
            poll_interval_sec=4.0,
            enabled=True,
        )

        payload = {
            "nextPageToken": "TOKEN_2",
            "pollingIntervalMillis": 6000,
            "items": [
                {
                    "id": "msg_1",
                    "authorDetails": {"displayName": "YTViewer"},
                    "snippet": {
                        "type": "textMessageEvent",
                        "displayMessage": "Halo Eve dari YouTube!",
                    },
                },
                {
                    "id": "msg_2",
                    "authorDetails": {"displayName": "SuperFan"},
                    "snippet": {
                        "type": "superChatEvent",
                        "superChatDetails": {
                            "amountDisplayString": "$10.00",
                            "currency": "USD",
                            "userComment": "Keep up the stream!",
                        },
                    },
                },
                {
                    "id": "msg_3",
                    "authorDetails": {"displayName": "StickerFan"},
                    "snippet": {
                        "type": "superStickerEvent",
                        "superStickerDetails": {
                            "amountDisplayString": "¥500",
                            "currency": "JPY",
                        },
                    },
                },
            ],
        }

        captured_params = []

        def fake_get(url, params=None):
            captured_params.append(dict(params or {}))
            return _FakeHTTPResp(200, json_data=payload)

        fake_session = MagicMock()
        fake_session.closed = False
        fake_session.get = fake_get

        delay = await adapter.poll_once(session=fake_session)
        self.assertEqual(delay, 6.0)
        self.assertTrue(adapter.is_connected)
        self.assertIsNone(adapter.last_error)
        self.assertEqual(receiver.queue.qsize(), 3)

        m1 = await receiver.get_next_message()
        m2 = await receiver.get_next_message()
        m3 = await receiver.get_next_message()

        self.assertEqual((m1.user, m1.text, m1.source, m1.is_donation), ("YTViewer", "Halo Eve dari YouTube!", "youtube", False))
        self.assertEqual((m2.user, m2.text, m2.source, m2.is_donation, m2.donation_amount, m2.donation_currency),
                         ("SuperFan", "Keep up the stream!", "youtube", True, "$10.00", "USD"))
        self.assertEqual((m3.user, m3.source, m3.is_donation, m3.donation_amount, m3.donation_currency),
                         ("StickerFan", "youtube", True, "¥500", "JPY"))

        # Second poll with same items should deduplicate and pass pageToken=TOKEN_2
        await adapter.poll_once(session=fake_session)
        self.assertEqual(receiver.queue.qsize(), 0)
        self.assertEqual(captured_params[-1].get("pageToken"), "TOKEN_2")

    async def test_poll_once_handles_http_error(self):
        receiver = ChatReceiver()
        adapter = YouTubeLiveAdapter(receiver=receiver, api_key="k", live_chat_id="c", enabled=True)
        fake_session = MagicMock()
        fake_session.closed = False
        fake_session.get = MagicMock(return_value=_FakeHTTPResp(403, text_data="Quota exceeded"))

        delay = await adapter.poll_once(session=fake_session)
        self.assertGreaterEqual(delay, 10.0)
        self.assertFalse(adapter.is_connected)
        self.assertIn("403", adapter.last_error)


class TestDiscordAdapter(unittest.IsolatedAsyncioTestCase):
    async def test_graceful_degradation_when_disabled_or_unconfigured(self):
        receiver = ChatReceiver()
        disabled = DiscordAdapter(receiver=receiver, bot_token="tok", channel_id="123", enabled=False)
        self.assertFalse(await disabled.start())
        self.assertFalse(disabled.is_running)

        missing = DiscordAdapter(receiver=receiver, bot_token="", channel_id="123", enabled=True)
        self.assertFalse(await missing.start())
        self.assertIsNotNone(missing.last_error)

    async def test_poll_once_chronological_order_bot_filter_and_cursor(self):
        receiver = ChatReceiver()
        adapter = DiscordAdapter(
            receiver=receiver,
            bot_token="Bot secret-discord-token",
            channel_id="999888777",
            poll_interval_sec=3.0,
            enabled=True,
        )
        self.assertEqual(adapter.bot_token, "secret-discord-token")

        # Discord returns newest first
        messages = [
            {"id": "103", "content": "Second message!", "author": {"username": "user2", "global_name": "UserTwo", "bot": False}},
            {"id": "102", "content": "Bot spam", "author": {"username": "helperbot", "bot": True}},
            {"id": "101", "content": "First message!", "author": {"username": "user1", "bot": False}},
        ]

        captured = {}

        def fake_get(url, headers=None, params=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["params"] = dict(params or {})
            return _FakeHTTPResp(200, json_data=messages)

        fake_session = MagicMock()
        fake_session.closed = False
        fake_session.get = fake_get

        delay = await adapter.poll_once(session=fake_session)
        self.assertEqual(delay, 3.0)
        self.assertTrue(adapter.is_connected)
        self.assertEqual(captured["headers"].get("Authorization"), "Bot secret-discord-token")
        self.assertEqual(receiver.queue.qsize(), 2)

        m1 = await receiver.get_next_message()
        m2 = await receiver.get_next_message()
        self.assertEqual((m1.user, m1.text, m1.source), ("user1", "First message!", "discord"))
        self.assertEqual((m2.user, m2.text, m2.source), ("UserTwo", "Second message!", "discord"))

        # Next poll passes after=103
        await adapter.poll_once(session=fake_session)
        self.assertEqual(captured["params"].get("after"), "103")
        self.assertEqual(receiver.queue.qsize(), 0)

    async def test_poll_once_handles_rate_limit_429(self):
        receiver = ChatReceiver()
        adapter = DiscordAdapter(receiver=receiver, bot_token="tok", channel_id="123", enabled=True)
        fake_session = MagicMock()
        fake_session.closed = False
        fake_session.get = MagicMock(return_value=_FakeHTTPResp(429, json_data={"retry_after": 7.5}))

        delay = await adapter.poll_once(session=fake_session)
        self.assertEqual(delay, 7.5)
        self.assertIn("429", adapter.last_error)


class TestChatReceiverMultiAdapter(unittest.IsolatedAsyncioTestCase):
    async def test_register_start_stop_and_platforms_status(self):
        receiver = ChatReceiver(twitch_channel="eve_tv")
        yt = YouTubeLiveAdapter(api_key="", live_chat_id="", enabled=False)
        dc = DiscordAdapter(bot_token="", channel_id="", enabled=False)

        receiver.register_adapter(yt)
        receiver.register_adapter(dc)
        self.assertIn("youtube", receiver.adapters)
        self.assertIn("discord", receiver.adapters)

        start_results = await receiver.start_adapters()
        self.assertEqual(start_results, {"youtube": False, "discord": False})

        status = receiver.get_platforms_status()
        self.assertIn("twitch", status)
        self.assertIn("youtube", status)
        self.assertIn("discord", status)

        await receiver.stop_adapters()
        removed = receiver.unregister_adapter("discord")
        self.assertIs(removed, dc)
        self.assertNotIn("discord", receiver.adapters)


class TestConfigManagerPlatformMasking(unittest.TestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_dir = Path(self._temp_dir_obj.name)
        self.cfg = ConfigManager(config_dir=str(self.temp_dir))

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    def test_youtube_and_discord_secrets_masked_and_preserved_on_save(self):
        ok, errors, _ = self.cfg.save_config({
            "youtube": {
                "enabled": True,
                "api_key": "AIza-youtube-secret",
                "live_chat_id": "CHAT_ABC",
                "poll_interval_sec": 5.0,
            },
            "discord": {
                "enabled": True,
                "bot_token": "MTIz.discord.secret",
                "channel_id": "987654321",
                "poll_interval_sec": 3.0,
            },
        })
        self.assertTrue(ok, f"Unexpected errors: {errors}")

        pub = self.cfg.get_public_config()
        self.assertEqual(pub["youtube"]["api_key"], "********")
        self.assertTrue(pub["youtube"]["api_key_configured"])
        self.assertEqual(pub["discord"]["bot_token"], "********")
        self.assertTrue(pub["discord"]["bot_token_configured"])

        # Re-saving with masked "********" must preserve the real secrets on disk
        ok2, errors2, _ = self.cfg.save_config({
            "youtube": {"api_key": "********", "live_chat_id": "CHAT_XYZ"},
            "discord": {"bot_token": "********", "channel_id": "111222333"},
        })
        self.assertTrue(ok2, f"Unexpected errors: {errors2}")
        self.assertEqual(self.cfg.settings["youtube"]["api_key"], "AIza-youtube-secret")
        self.assertEqual(self.cfg.settings["youtube"]["live_chat_id"], "CHAT_XYZ")
        self.assertEqual(self.cfg.settings["discord"]["bot_token"], "MTIz.discord.secret")
        self.assertEqual(self.cfg.settings["discord"]["channel_id"], "111222333")

    def test_validation_rejects_invalid_embedding_provider_and_poll_intervals(self):
        valid, errors = self.cfg.validate_config({
            "memory": {"embedding_provider": "invalid_provider"},
            "youtube": {"poll_interval_sec": 0.1},
            "discord": {"poll_interval_sec": 999.0},
        })
        self.assertFalse(valid)
        self.assertGreaterEqual(len(errors), 3)


if __name__ == "__main__":
    unittest.main()
