import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import tests  # noqa: F401
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

import run
from core.collab import CollabEnvelope, CollabManager
from core.config_manager import ConfigManager
from core.event_bus import EventBus
from core.plugins import MaybeAIPlugin, PluginManifest, PluginRegistry, WordChainPlugin, plugin_command, plugin_event


class TestCollabProtocolAndManager(unittest.IsolatedAsyncioTestCase):
    def test_envelope_hmac_sign_and_verify(self):
        env = CollabEnvelope(
            sender_id="peer-1",
            sender_name="NeuroPeer",
            event_type="turn_utterance",
            speech="Halo Eve!",
            emotion="happy",
            turn_index=1,
        )
        sig = env.sign("super-secret")
        self.assertTrue(sig)
        self.assertTrue(env.verify("super-secret"))
        self.assertFalse(env.verify("wrong-secret"))

        # Tampering invalidates signature
        env.speech = "Tampered!"
        self.assertFalse(env.verify("super-secret"))

        # Unsigned frame policy
        unsigned = CollabEnvelope(sender_id="p", sender_name="P", event_type="ping")
        self.assertFalse(unsigned.verify("", allow_unsigned=False))
        self.assertTrue(unsigned.verify("", allow_unsigned=True))

        with self.assertRaises(ValueError):
            CollabEnvelope(event_type="invalid_event_type")

    async def test_floor_state_machine_and_anti_loop_protection(self):
        bus = EventBus()
        sent_frames = []

        async def fake_peer_send(frame):
            sent_frames.append(frame)

        mgr = CollabManager(
            settings={
                "enabled": True,
                "peer_name": "NeuroPeer",
                "shared_secret": "collab-key",
                "max_collab_turns": 3,
                "turn_cooldown_sec": 5.0,
            },
            event_bus=bus,
        )
        mgr.set_peer_sender(fake_peer_send, peer_name="NeuroPeer")

        # Turn 1: send utterance & yield -> listening
        r1 = await mgr.initiate_prompt("Bahas game indie yuk!")
        self.assertTrue(r1["sent"])
        self.assertEqual(mgr.turn_count, 1)
        self.assertEqual(mgr.floor_state, "listening")
        self.assertEqual([f["event_type"] for f in sent_frames[:2]], ["turn_utterance", "turn_yield"])

        # Peer yields back -> idle
        yield_back = CollabEnvelope(sender_id="peer", sender_name="NeuroPeer", event_type="turn_yield")
        yield_back.sign("collab-key")
        res_yield = await mgr.handle_incoming_envelope(yield_back.to_dict())
        self.assertTrue(res_yield["accepted"])
        self.assertEqual(mgr.floor_state, "idle")

        # Turn 2: inbound utterance triggers reply callback
        replies = []
        peer_utt = CollabEnvelope(
            sender_id="peer",
            sender_name="NeuroPeer",
            event_type="turn_utterance",
            speech="Setuju! Game apa dulu?",
        )
        peer_utt.sign("collab-key")
        res_in2 = await mgr.handle_incoming_envelope(
            peer_utt.to_dict(),
            on_reply_needed=lambda e: replies.append(e.speech),
        )
        self.assertTrue(res_in2["accepted"])
        self.assertTrue(res_in2["reply_triggered"])
        self.assertEqual(replies, ["Setuju! Game apa dulu?"])
        self.assertEqual(mgr.turn_count, 2)

        # Turn 3 hits max_collab_turns=3 -> enters cooldown & blocks further turns
        r3 = await mgr.send_utterance("Kita main Catur dulu!", yield_turn=True)
        self.assertTrue(r3["sent"])
        self.assertEqual(mgr.turn_count, 3)
        self.assertEqual(mgr.floor_state, "cooldown")

        r4 = await mgr.send_utterance("Loop keempat harus ditolak!", yield_turn=True)
        self.assertFalse(r4["sent"])
        self.assertEqual(r4["reason"], "max_collab_turns_reached")

        # Inbound utterance during cooldown does not trigger reply loop
        peer_utt2 = CollabEnvelope(
            sender_id="peer",
            sender_name="NeuroPeer",
            event_type="turn_utterance",
            speech="Ayo terus!",
        )
        peer_utt2.sign("collab-key")
        res_in4 = await mgr.handle_incoming_envelope(
            peer_utt2.to_dict(),
            on_reply_needed=lambda e: replies.append(e.speech),
        )
        self.assertFalse(res_in4["reply_triggered"])
        self.assertEqual(len(replies), 1)

        # Reset turns restores idle
        await mgr.reset_turns()
        self.assertEqual(mgr.turn_count, 0)
        self.assertEqual(mgr.floor_state, "idle")

    async def test_duet_and_emote_sync_and_invalid_signature_rejected(self):
        bus = EventBus()
        sent_frames = []

        async def fake_send(frame):
            sent_frames.append(frame)

        mgr = CollabManager(
            settings={"enabled": True, "shared_secret": "s3cr3t"},
            event_bus=bus,
        )
        mgr.set_peer_sender(fake_send, peer_name="DuetPartner")

        duet = await mgr.send_duet_sync("digital_world", lyric_index=4, timestamp=12.5)
        self.assertTrue(duet["sent"])
        self.assertEqual(sent_frames[-1]["event_type"], "duet_sync")
        self.assertEqual(sent_frames[-1]["payload"]["song_id"], "digital_world")

        emote = await mgr.send_emote_sync("smug", action="wink")
        self.assertTrue(emote["sent"])
        self.assertEqual(sent_frames[-1]["event_type"], "emote_sync")
        self.assertEqual(sent_frames[-1]["payload"]["action"], "wink")

        bad = CollabEnvelope(sender_id="eve2", sender_name="Fake", event_type="turn_utterance", speech="hi")
        bad.sign("wrong-secret")
        res = await mgr.handle_incoming_envelope(bad.to_dict())
        self.assertFalse(res["accepted"])


class TestPluginSDKRegistryAndWordChain(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.plugins_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    async def test_discovery_enable_disable_reload_and_external_plugin(self):
        ext_file = self.plugins_dir / "greeter_ext.py"
        ext_file.write_text(
            "from core.plugins.sdk import MaybeAIPlugin, PluginManifest, plugin_command\n"
            "class ExtGreeter(MaybeAIPlugin):\n"
            "    manifest = PluginManifest(id='ext_greeter', name='Ext Greeter', commands=['!greet', '!adminping'], creator_only_commands=['!adminping'])\n"
            "    @plugin_command('!greet')\n"
            "    async def greet(self, args, user, is_creator, ctx):\n"
            "        return f'Halo {user}! {args}'.strip()\n"
            "    @plugin_command('!adminping', creator_only=True)\n"
            "    async def adminping(self, args, user, is_creator, ctx):\n"
            "        return 'pong-creator'\n",
            encoding="utf-8",
        )

        bus = EventBus()
        reg = PluginRegistry(
            plugins_dir=str(self.plugins_dir),
            enabled_plugins=["word_chain", "ext_greeter"],
            event_bus=bus,
        )
        discovered = await reg.discover_plugins()
        self.assertIn("word_chain", discovered)
        self.assertIn("ext_greeter", discovered)

        handled, resp = await reg.dispatch_command("!greet Eve", user="Tester", is_creator=False)
        self.assertTrue(handled)
        self.assertEqual(resp, "Halo Tester! Eve")

        # Creator-only enforcement
        handled_c, resp_non = await reg.dispatch_command("!adminping", user="Viewer", is_creator=False)
        self.assertTrue(handled_c)
        self.assertIn("Creator", resp_non)

        _, resp_cr = await reg.dispatch_command("!adminping", user="Creator", is_creator=True)
        self.assertEqual(resp_cr, "pong-creator")

        # Disable stops command routing
        dis = await reg.disable_plugin("ext_greeter")
        self.assertTrue(dis["success"])
        handled_dis, _ = await reg.dispatch_command("!greet Eve", user="Tester", is_creator=False)
        self.assertFalse(handled_dis)

        # Enable & reload restore routing
        en = await reg.enable_plugin("ext_greeter")
        self.assertTrue(en["success"])
        rel = await reg.reload_plugin("ext_greeter")
        self.assertTrue(rel["success"])
        handled_rel, resp_rel = await reg.dispatch_command("!greet Back", user="Tester", is_creator=False)
        self.assertTrue(handled_rel)
        self.assertEqual(resp_rel, "Halo Tester! Back")

        await reg.shutdown()

    async def test_hook_timeout_and_exception_isolation(self):
        class FaultyPlugin(MaybeAIPlugin):
            manifest = PluginManifest(
                id="faulty",
                name="Faulty",
                commands=["!slow", "!boom"],
                events=["chat.received"],
            )

            @plugin_command("!slow")
            async def slow(self, args, user, is_creator, ctx):
                await asyncio.sleep(1.5)
                return "never"

            @plugin_command("!boom")
            async def boom(self, args, user, is_creator, ctx):
                raise RuntimeError("boom command")

            @plugin_event("chat.received")
            async def on_chat(self, event_name, payload, ctx):
                if payload.get("mode") == "slow":
                    await asyncio.sleep(1.5)
                raise ValueError("boom event")

        bus = EventBus()
        reg = PluginRegistry(
            plugins_dir=str(self.plugins_dir),
            enabled_plugins=["faulty"],
            hook_timeout_sec=0.1,
            event_bus=bus,
        )
        reg.register_plugin(FaultyPlugin(), auto_enable=True)
        await reg._load_plugin_instance("faulty")
        reg.attach_to_event_bus(bus)

        handled_slow, resp_slow = await reg.dispatch_command("!slow", user="U", is_creator=True)
        self.assertTrue(handled_slow)
        self.assertIsNone(resp_slow)

        handled_boom, resp_boom = await reg.dispatch_command("!boom", user="U", is_creator=True)
        self.assertTrue(handled_boom)
        self.assertIsNone(resp_boom)

        # EventBus publish must not raise even if plugin hook fails or times out
        await bus.publish("chat.received", {"mode": "boom"})
        await bus.publish("chat.received", {"mode": "slow"})

        meta = next(p for p in reg.list_plugins() if p["id"] == "faulty")
        self.assertGreaterEqual(meta["error_count"], 4)
        self.assertIsNotNone(meta["last_error"])
        await reg.shutdown()

    async def test_word_chain_gameplay(self):
        reg = PluginRegistry(plugins_dir=str(self.plugins_dir), enabled_plugins=["word_chain"])
        await reg.discover_plugins()

        h1, r1 = await reg.dispatch_command("!sambungkata start kopi", user="Alice")
        self.assertTrue(h1)
        self.assertIn("kopi", r1.lower())

        # Valid next word starting with 'i'
        _, r2 = await reg.dispatch_command("!wc ikan", user="Bob")
        self.assertIn("nyambung", r2.lower())

        # Wrong starting letter (needs 'n')
        _, r3 = await reg.dispatch_command("!wc apel", user="Charlie")
        self.assertIn("tetot", r3.lower())

        # Repeated word rejected
        _, r4 = await reg.dispatch_command("!wc nasi", user="Bob")
        self.assertIn("nyambung", r4.lower())
        _, r5 = await reg.dispatch_command("!wc ikan", user="Alice")
        self.assertIn("sudah dipakai", r5.lower())

        # Score & stop
        _, r_score = await reg.dispatch_command("!wc score", user="Alice")
        self.assertIn("Bob: 2 pts", r_score)

        _, r_stop = await reg.dispatch_command("!wc stop", user="Alice")
        self.assertIn("selesai", r_stop.lower())
        await reg.shutdown()


class TestCollabConfigMasking(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.cfg_mgr = ConfigManager(config_dir=self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_collab_shared_secret_masked_and_preserved(self):
        ok, errs, _ = self.cfg_mgr.save_config({"collab": {"shared_secret": "ultra-secret-999"}})
        self.assertTrue(ok, errs)

        pub = self.cfg_mgr.get_public_config()
        self.assertEqual(pub["collab"]["shared_secret"], "********")
        self.assertTrue(pub["collab"]["shared_secret_configured"])

        # Saving masked placeholder preserves real secret on disk
        ok2, errs2, _ = self.cfg_mgr.save_config({"collab": {"shared_secret": "********", "peer_name": "PeerB"}})
        self.assertTrue(ok2, errs2)
        self.assertEqual(self.cfg_mgr.settings["collab"]["shared_secret"], "ultra-secret-999")
        self.assertEqual(self.cfg_mgr.settings["collab"]["peer_name"], "PeerB")


async def _run_http_request(method: str, path: str, payload=None):
    body_bytes = json.dumps(payload).encode("utf-8") if payload is not None else b""
    headers = [(b"content-type", b"application/json")] if payload is not None else []
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 50400),
        "server": ("127.0.0.1", 7860),
    }
    sent = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await run.app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    resp_body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], json.loads(resp_body.decode("utf-8"))


async def _run_collab_ws(client_host: str = "127.0.0.1", query_string: str = "", headers=None, incoming_json=None):
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()]
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/ws/collab",
        "raw_path": b"/ws/collab",
        "query_string": query_string.encode("latin-1"),
        "headers": raw_headers,
        "client": (client_host, 50401),
        "server": ("127.0.0.1", 7860),
        "subprotocols": [],
    }
    queue = [{"type": "websocket.connect"}]
    for item in incoming_json or []:
        queue.append({"type": "websocket.receive", "text": json.dumps(item)})
    queue.append({"type": "websocket.disconnect", "code": 1000})

    sent = []

    async def receive():
        if queue:
            return queue.pop(0)
        await asyncio.sleep(0)
        return {"type": "websocket.disconnect", "code": 1000}

    async def send(message):
        sent.append(message)

    await run.app(scope, receive, send)
    return sent


class TestCollabAndPluginASGI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._orig_collab = run.orchestrator.collab
        self._orig_plugins = run.orchestrator.plugins
        self._orig_plugins_loaded = run.orchestrator._plugins_discovered
        self._orig_collab_cfg = dict(run.config_mgr.settings.get("collab", {}))
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)

        run.orchestrator.collab = CollabManager(
            settings={"enabled": True, "peer_name": "PeerTest", "shared_secret": ""},
            event_bus=run.orchestrator.event_bus,
        )
        run.orchestrator.plugins = PluginRegistry(
            plugins_dir=self._tmp.name,
            enabled_plugins=["word_chain"],
            event_bus=run.orchestrator.event_bus,
        )
        run.orchestrator._plugins_discovered = False

    async def asyncTearDown(self):
        await run.orchestrator.collab.shutdown()
        await run.orchestrator.plugins.shutdown()
        run.orchestrator.collab = self._orig_collab
        run.orchestrator.plugins = self._orig_plugins
        run.orchestrator._plugins_discovered = self._orig_plugins_loaded
        run.config_mgr.settings["collab"] = self._orig_collab_cfg
        self._tmp.cleanup()

    async def test_ws_collab_secret_and_loopback_auth(self):
        # 1. Unconfigured secret -> non-loopback rejected with 1008
        with patch.dict(os.environ, {"MAYBEAI_COLLAB_SECRET": ""}, clear=False):
            run.config_mgr.settings["collab"] = {"shared_secret": ""}
            run.orchestrator.collab.shared_secret = ""
            sent_remote = await _run_collab_ws(client_host="198.51.100.77")
            self.assertNotIn("websocket.accept", [m["type"] for m in sent_remote])
            self.assertEqual([m["code"] for m in sent_remote if m["type"] == "websocket.close"], [1008])

            # 2. Configured secret -> wrong secret rejected with 1008
            run.orchestrator.collab.shared_secret = "shared-hmac-secret"
            sent_bad = await _run_collab_ws(client_host="127.0.0.1", query_string="secret=wrong")
            self.assertNotIn("websocket.accept", [m["type"] for m in sent_bad])
            self.assertEqual([m["code"] for m in sent_bad if m["type"] == "websocket.close"], [1008])

            # 3. Valid secret + signed CollabEnvelope accepted
            env = CollabEnvelope(
                sender_id="neuro-peer",
                sender_name="NeuroPeer",
                event_type="hello",
                speech="Halo Eve!",
                emotion="happy",
            )
            env.sign("shared-hmac-secret")
            sent_ok = await _run_collab_ws(
                client_host="127.0.0.1",
                query_string="secret=shared-hmac-secret",
                incoming_json=[env.to_dict()],
            )
            self.assertIn("websocket.accept", [m["type"] for m in sent_ok])
            self.assertGreaterEqual(len(run.orchestrator.collab.history), 1)
            self.assertEqual(run.orchestrator.collab.history[-1]["sender_name"], "NeuroPeer")

    async def test_collab_and_plugins_http_endpoints(self):
        c_st_code, c_st = await _run_http_request("GET", "/api/collab/status")
        self.assertEqual(c_st_code, 200)
        self.assertIn("floor_state", c_st)

        c_act_code, c_act = await _run_http_request(
            "POST",
            "/api/collab/action",
            {"action": "initiate", "topic": "Main game bareng"},
        )
        self.assertEqual(c_act_code, 200)
        self.assertTrue(c_act["sent"])

        p_list_code, p_list = await _run_http_request("GET", "/api/plugins")
        self.assertEqual(p_list_code, 200)
        self.assertTrue(p_list["enabled"])
        self.assertTrue(any(p["id"] == "word_chain" for p in p_list["plugins"]))

        p_dis_code, p_dis = await _run_http_request(
            "POST",
            "/api/plugins/action",
            {"action": "disable", "plugin_id": "word_chain"},
        )
        self.assertEqual(p_dis_code, 200)
        self.assertTrue(p_dis["success"])

        p_en_code, p_en = await _run_http_request(
            "POST",
            "/api/plugins/action",
            {"action": "enable", "plugin_id": "word_chain"},
        )
        self.assertEqual(p_en_code, 200)
        self.assertTrue(p_en["success"])


if __name__ == "__main__":
    unittest.main()
