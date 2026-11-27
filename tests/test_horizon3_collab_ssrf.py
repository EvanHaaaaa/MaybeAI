import socket
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.collab.manager import CollabManager
from core.collab.protocol import CollabEnvelope
from core.security_net import (
    SSRFValidationError,
    create_pinned_connector,
    resolve_and_pin_host,
    validate_outbound_url,
)
from core.tts_providers import (
    FishSpeechProvider,
    GPTSoVITSProvider,
    KokoroTTSProvider,
    RVCVoiceConverter,
    create_tts_provider,
)


class TestSecurityNetSSRF(unittest.TestCase):
    def test_blocks_invalid_schemes_and_empty_urls(self):
        for bad in ("", "   ", "file:///etc/passwd", "ftp://example.com/a", "gopher://1.1.1.1:70"):
            with self.assertRaises(SSRFValidationError):
                validate_outbound_url(bad)

    def test_blocks_private_and_loopback_by_default(self):
        for private_url in (
            "http://127.0.0.1:8880/v1/audio/speech",
            "http://localhost:8880",
            "http://[::1]:8880",
            "http://10.0.0.5:7860/ws/collab",
            "http://172.16.1.10:7860",
            "http://192.168.1.50:7860",
        ):
            with self.assertRaises(SSRFValidationError):
                validate_outbound_url(private_url, allow_private=False)

    def test_allows_private_when_configured_but_still_blocks_metadata(self):
        self.assertEqual(
            validate_outbound_url("ws://127.0.0.1:7860/ws/collab", allowed_schemes=("ws", "wss"), allow_private=True),
            "ws://127.0.0.1:7860/ws/collab",
        )
        self.assertEqual(
            validate_outbound_url("http://192.168.1.50:8880", allow_private=True),
            "http://192.168.1.50:8880",
        )
        for meta_url in (
            "http://169.254.169.254/latest/meta-data/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://100.100.100.200/latest/meta-data/",
            "http://[fe80::1]/",
        ):
            with self.assertRaises(SSRFValidationError):
                validate_outbound_url(meta_url, allow_private=True)

    def test_dns_rebinding_and_allowlist(self):
        fake_private_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        with patch("core.security_net.socket.getaddrinfo", return_value=fake_private_dns):
            with self.assertRaises(SSRFValidationError):
                validate_outbound_url("https://rebind.evil.com/tts", allow_private=False)

        fake_public_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        with patch("core.security_net.socket.getaddrinfo", return_value=fake_public_dns):
            self.assertEqual(
                validate_outbound_url("https://api.example.com/tts", allow_private=False),
                "https://api.example.com/tts",
            )

        self.assertEqual(
            validate_outbound_url(
                "http://169.254.169.254/custom",
                allow_private=False,
                allowlist=["169.254.169.254"],
            ),
            "http://169.254.169.254/custom",
        )
        self.assertEqual(
            validate_outbound_url(
                "http://10.20.30.40:8080/tts",
                allow_private=False,
                allowlist=["10.20.0.0/16"],
            ),
            "http://10.20.30.40:8080/tts",
        )


class TestTTSProvidersSSRF(unittest.IsolatedAsyncioTestCase):
    async def test_tts_providers_and_rvc_enforce_ssrf_validation(self):
        kokoro = create_tts_provider("kokoro", kokoro_url="http://169.254.169.254/latest/meta-data/")
        self.assertIsInstance(kokoro, KokoroTTSProvider)
        with self.assertRaises(SSRFValidationError):
            await kokoro.synthesize("hi", "af_heart", "+0%", "+0Hz")

        kokoro_strict = KokoroTTSProvider(kokoro_url="http://127.0.0.1:8880", allow_private=False)
        with self.assertRaises(SSRFValidationError):
            await kokoro_strict.synthesize("hi", "af_heart", "+0%", "+0Hz")

        fish = create_tts_provider("fish_speech", custom_tts_url="file:///etc/passwd")
        self.assertIsInstance(fish, FishSpeechProvider)
        with self.assertRaises(SSRFValidationError):
            await fish.synthesize("hi", "eve", "+0%", "+0Hz")

        gptsovits = create_tts_provider("gpt_sovits", custom_tts_url="http://169.254.169.254/tts")
        self.assertIsInstance(gptsovits, GPTSoVITSProvider)
        with self.assertRaises(SSRFValidationError):
            await gptsovits.synthesize("hi", "eve", "+0%", "+0Hz")

        rvc = RVCVoiceConverter(enabled=True, rvc_url="http://169.254.169.254/convert")
        out = await rvc.convert(b"ORIG_AUDIO")
        self.assertEqual(out, b"ORIG_AUDIO")
        self.assertIsNotNone(rvc.last_error)
        self.assertIn("blocked", rvc.last_error.lower())


class TestCollabSSRFAndBidirectional(unittest.IsolatedAsyncioTestCase):
    async def test_connect_peer_ssrf_and_header_subprotocol_secret(self):
        mgr = CollabManager(
            settings={
                "enabled": True,
                "shared_secret": "top-secret",
                "allow_private_peers": False,
            }
        )
        # Private peer blocked when allow_private_peers=False
        blocked = await mgr.connect_peer("ws://127.0.0.1:7860/ws/collab?secret=leak")
        self.assertFalse(blocked)

        # Allowed when allow_private=True; strips ?secret= and passes headers/subprotocols
        async def _empty_ws():
            if False:
                yield None

        fake_ws = MagicMock()
        fake_ws.closed = False
        fake_ws.send_json = AsyncMock()
        fake_ws.close = AsyncMock()
        fake_ws.__aiter__ = MagicMock(side_effect=_empty_ws)

        fake_session = MagicMock()
        fake_session.closed = False
        fake_session.ws_connect = AsyncMock(return_value=fake_ws)
        fake_session.close = AsyncMock()

        with patch("core.collab.manager.aiohttp.ClientSession", return_value=fake_session):
            ok = await mgr.connect_peer(
                "ws://127.0.0.1:7860/ws/collab?secret=leak&room=1",
                peer_name="Neuro",
                allow_private=True,
                extra_headers={"X-Custom": "1"},
                subprotocols=["maybeai-collab-v1"],
            )
            self.assertTrue(ok)
            call_args = fake_session.ws_connect.call_args
            called_url = call_args.args[0]
            called_kwargs = call_args.kwargs
            self.assertNotIn("secret=", called_url)
            self.assertIn("room=1", called_url)
            self.assertEqual(called_kwargs["headers"]["x-collab-secret"], "top-secret")
            self.assertEqual(called_kwargs["headers"]["Authorization"], "Bearer top-secret")
            self.assertEqual(called_kwargs["headers"]["X-Custom"], "1")
            self.assertEqual(called_kwargs["protocols"], ["maybeai-collab-v1"])

            # Verify outbound hello included capabilities
            hello_payload = fake_ws.send_json.call_args_list[0].args[0]
            self.assertEqual(hello_payload["event_type"], "hello")
            self.assertIn("game_move", hello_payload["payload"]["capabilities"])
            await mgr.shutdown()

    async def test_hello_handshake_duet_emote_game_move_and_rate_limit(self):
        sent_frames = []
        duet_events = []
        emote_events = []
        game_events = []

        async def fake_send(frame):
            sent_frames.append(frame)

        mgr = CollabManager(
            settings={
                "enabled": True,
                "shared_secret": "collab-sec",
                "rate_limit_max_events": 3,
                "rate_limit_window_sec": 10.0,
            },
            on_duet_sync=lambda env: duet_events.append(env),
            on_emote_sync=lambda env: emote_events.append(env),
            on_game_move=lambda env: game_events.append(env),
        )
        mgr.set_peer_sender(fake_send, peer_name="PeerA")

        # Outbound hello handshake
        hello_res = await mgr.send_hello(capabilities=["duet_sync", "game_move"])
        self.assertTrue(hello_res["sent"])
        self.assertEqual(sent_frames[-1]["event_type"], "hello")
        self.assertEqual(sent_frames[-1]["payload"]["capabilities"], ["duet_sync", "game_move"])

        # Inbound hello updates peer_capabilities
        peer_hello = CollabEnvelope(
            sender_id="peer-a",
            sender_name="PeerA",
            event_type="hello",
            payload={"capabilities": ["duet_sync", "emote_sync", "game_move"], "protocol_version": "1.0"},
        )
        peer_hello.sign("collab-sec")
        in_hello = await mgr.handle_incoming_envelope(peer_hello.to_dict(), is_loopback=False)
        self.assertTrue(in_hello["accepted"])
        self.assertEqual(mgr.get_status()["peer_capabilities"], ["duet_sync", "emote_sync", "game_move"])

        # Bidirectional duet_sync with lyric_index, timestamp, track
        duet_out = await mgr.send_duet_sync("song_x", lyric_index=7, timestamp=42.5, track="harmony")
        self.assertTrue(duet_out["sent"])
        self.assertEqual(sent_frames[-1]["payload"]["track"], "harmony")
        self.assertEqual(sent_frames[-1]["payload"]["lyric_index"], 7)
        self.assertEqual(sent_frames[-1]["payload"]["timestamp"], 42.5)

        duet_in = CollabEnvelope(
            sender_id="peer-a",
            sender_name="PeerA",
            event_type="duet_sync",
            payload={"song_id": "song_x", "lyric_index": 8, "timestamp": 45.0, "track": "lead"},
        )
        duet_in.sign("collab-sec")
        self.assertTrue((await mgr.handle_incoming_envelope(duet_in.to_dict(), is_loopback=False))["accepted"])
        self.assertEqual(duet_events[-1].payload["track"], "lead")
        self.assertEqual(duet_events[-1].payload["lyric_index"], 8)

        # Bidirectional emote_sync with action, emotion
        emote_out = await mgr.send_emote_sync("excited", action="wave")
        self.assertTrue(emote_out["sent"])
        self.assertEqual(sent_frames[-1]["payload"]["action"], "wave")
        self.assertEqual(sent_frames[-1]["payload"]["emotion"], "excited")

        emote_in = CollabEnvelope(
            sender_id="peer-a",
            sender_name="PeerA",
            event_type="emote_sync",
            emotion="smug",
            payload={"action": "wink", "emotion": "smug"},
        )
        emote_in.sign("collab-sec")
        self.assertTrue((await mgr.handle_incoming_envelope(emote_in.to_dict(), is_loopback=False))["accepted"])
        self.assertEqual(emote_events[-1].payload["action"], "wink")
        self.assertEqual(emote_events[-1].emotion, "smug")

        # Bidirectional game_move
        move_out = await mgr.send_game_move("e2e4", fen="startpos")
        self.assertTrue(move_out["sent"])
        self.assertEqual(sent_frames[-1]["event_type"], "game_move")
        self.assertEqual(sent_frames[-1]["payload"]["move"], "e2e4")
        self.assertEqual(sent_frames[-1]["payload"]["fen"], "startpos")

        move_in = CollabEnvelope(
            sender_id="peer-a",
            sender_name="PeerA",
            event_type="game_move",
            payload={"game": "chess", "move": "e7e5", "uci": "e7e5"},
        )
        move_in.sign("collab-sec")
        self.assertTrue((await mgr.handle_incoming_envelope(move_in.to_dict(), is_loopback=False))["accepted"])
        self.assertEqual(game_events[-1].payload["move"], "e7e5")

        # Per-type rate limiting: 2 more duet_sync inbound succeed (total 3), 4th is rate_limited
        for idx in range(2):
            ev = CollabEnvelope(
                sender_id="peer-a",
                sender_name="PeerA",
                event_type="duet_sync",
                payload={"song_id": "song_x", "lyric_index": idx, "timestamp": float(idx), "track": "lead"},
            )
            ev.sign("collab-sec")
            res = await mgr.handle_incoming_envelope(ev.to_dict(), is_loopback=False)
            self.assertTrue(res["accepted"])

        flood_ev = CollabEnvelope(
            sender_id="peer-a",
            sender_name="PeerA",
            event_type="duet_sync",
            payload={"song_id": "song_x", "lyric_index": 99, "timestamp": 99.0, "track": "lead"},
        )
        flood_ev.sign("collab-sec")
        flood_res = await mgr.handle_incoming_envelope(flood_ev.to_dict(), is_loopback=False)
        self.assertFalse(flood_res["accepted"])
        self.assertEqual(flood_res["reason"], "rate_limited")

        # Other event types (e.g. game_move) are not blocked by duet_sync rate limit
        other_move = CollabEnvelope(
            sender_id="peer-a",
            sender_name="PeerA",
            event_type="game_move",
            payload={"game": "chess", "move": "g1f3"},
        )
        other_move.sign("collab-sec")
        self.assertTrue((await mgr.handle_incoming_envelope(other_move.to_dict(), is_loopback=False))["accepted"])

    async def test_resolve_and_pin_host_and_pinned_connector(self):
        fake_public_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        with patch("core.security_net.socket.getaddrinfo", return_value=fake_public_dns):
            validated_url, pinned_ip, host_header = resolve_and_pin_host(
                "https://api.example.com:8443/v1/test",
                allow_private=False,
            )
            self.assertEqual(validated_url, "https://api.example.com:8443/v1/test")
            self.assertEqual(pinned_ip, "93.184.216.34")
            self.assertEqual(host_header, "api.example.com:8443")

            connector = create_pinned_connector("api.example.com", pinned_ip)
            try:
                resolved = await connector._resolver.resolve("api.example.com", 8443)
                self.assertEqual(resolved[0]["host"], "93.184.216.34")
                with self.assertRaises(SSRFValidationError):
                    await connector._resolver.resolve("evil.example.com", 8443)
            finally:
                await connector.close()

    async def test_disconnect_peer_resets_floor_state_and_on_hello_callback(self):
        hello_events = []
        mgr = CollabManager(settings={"enabled": True, "shared_secret": "collab-sec"})
        mgr.set_action_callbacks(on_hello=lambda env: hello_events.append(env))

        mgr.floor_state = "listening"
        mgr.active_peer = "PeerA"
        mgr.connected_peer = "PeerA"
        mgr.peer_connected = False
        await mgr.disconnect_peer()
        self.assertEqual(mgr.floor_state, "idle")
        self.assertIsNone(mgr.active_peer)
        self.assertIsNone(mgr.connected_peer)

        peer_hello = CollabEnvelope(
            sender_id="peer-a",
            sender_name="PeerA",
            event_type="hello",
            payload={"capabilities": ["duet_sync"], "protocol_version": "1.0"},
        )
        peer_hello.sign("collab-sec")
        res = await mgr.handle_incoming_envelope(peer_hello.to_dict(), is_loopback=False)
        self.assertTrue(res["accepted"])
        import asyncio
        await asyncio.sleep(0)
        self.assertEqual(len(hello_events), 1)
        self.assertEqual(hello_events[0].sender_name, "PeerA")


if __name__ == "__main__":
    unittest.main()
