import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core.event_bus import EventBus
from core.plugins import (
    ALLOWED_PLUGIN_PERMISSIONS,
    DEFAULT_PLUGIN_PERMISSIONS,
    PluginManifest,
    PluginRegistry,
)


class TestPluginManifestPermissions(unittest.TestCase):
    def test_default_permissions_and_validation(self):
        m = PluginManifest(id="sample", name="Sample")
        self.assertEqual(m.permissions, list(DEFAULT_PLUGIN_PERMISSIONS))
        self.assertEqual(m.to_dict()["permissions"], ["chat:read", "event:sub"])
        m.validate()

        m_all = PluginManifest(
            id="all_perms",
            name="All Perms",
            permissions=list(ALLOWED_PLUGIN_PERMISSIONS),
        )
        m_all.validate()

        m_bad = PluginManifest(id="bad", name="Bad", permissions=["chat:read", "shell:exec"])
        with self.assertRaises(ValueError):
            m_bad.validate()


class TestSandboxedPluginExecution(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)
        self.plugins_dir = self.root / "plugins"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    async def test_stripped_env_hides_host_secrets(self):
        plugin_file = self.plugins_dir / "env_probe.py"
        plugin_file.write_text(
            "import json, os\n"
            "from core.plugins.sdk import MaybeAIPlugin, PluginManifest, plugin_command\n"
            "class EnvProbe(MaybeAIPlugin):\n"
            "    manifest = PluginManifest(id='env_probe', name='Env Probe', commands=['!env'])\n"
            "    @plugin_command('!env')\n"
            "    async def env(self, args, user, is_creator, ctx):\n"
            "        return json.dumps(dict(os.environ))\n",
            encoding="utf-8",
        )

        secret_env = {
            "GEMINI_API_KEY": "super-secret-gemini",
            "OPENAI_API_KEY": "super-secret-openai",
            "MAYBEAI_CREATOR_TOKEN": "creator-secret",
            "MAYBEAI_COLLAB_SECRET": "collab-secret",
        }
        with patch.dict(os.environ, secret_env, clear=False):
            reg = PluginRegistry(
                plugins_dir=str(self.plugins_dir),
                enabled_plugins=["word_chain", "env_probe"],
                sandbox_mode="subprocess",
            )
            try:
                await reg.discover_plugins()
                meta = {p["id"]: p for p in reg.list_plugins()}
                self.assertFalse(meta["word_chain"]["sandboxed"])
                self.assertTrue(meta["env_probe"]["sandboxed"])

                handled, resp = await reg.dispatch_command("!env", user="Tester")
                self.assertTrue(handled)
                env_data = json.loads(resp)
                for key in secret_env:
                    self.assertNotIn(key, env_data)
                self.assertEqual(env_data.get("PYTHONUNBUFFERED"), "1")
                self.assertIn("PYTHONPATH", env_data)
            finally:
                await reg.shutdown()

    async def test_permission_enforcement_on_rpc_callbacks(self):
        denied_file = self.plugins_dir / "no_perms.py"
        denied_file.write_text(
            "from core.plugins.sdk import MaybeAIPlugin, PluginManifest, plugin_command\n"
            "class NoPerms(MaybeAIPlugin):\n"
            "    manifest = PluginManifest(id='no_perms', name='No Perms', commands=['!tryspeak', '!trybcast', '!trypub'])\n"
            "    @plugin_command('!tryspeak')\n"
            "    async def tryspeak(self, args, user, is_creator, ctx):\n"
            "        await ctx.speak('blocked')\n"
            "        return 'ok'\n"
            "    @plugin_command('!trybcast')\n"
            "    async def trybcast(self, args, user, is_creator, ctx):\n"
            "        await ctx.broadcast('x.y', {'a': 1})\n"
            "        return 'ok'\n"
            "    @plugin_command('!trypub')\n"
            "    async def trypub(self, args, user, is_creator, ctx):\n"
            "        await ctx.event_bus.publish('x.z', {'b': 2})\n"
            "        return 'ok'\n",
            encoding="utf-8",
        )

        allowed_file = self.plugins_dir / "with_perms.py"
        allowed_file.write_text(
            "from core.plugins.sdk import MaybeAIPlugin, PluginManifest, plugin_command\n"
            "class WithPerms(MaybeAIPlugin):\n"
            "    manifest = PluginManifest(\n"
            "        id='with_perms',\n"
            "        name='With Perms',\n"
            "        commands=['!dospeak', '!dobcast', '!dopub'],\n"
            "        permissions=['chat:read', 'tts:speak', 'event:sub', 'event:pub'],\n"
            "    )\n"
            "    @plugin_command('!dospeak')\n"
            "    async def dospeak(self, args, user, is_creator, ctx):\n"
            "        await ctx.speak('hello', 'happy')\n"
            "        return 'spoke'\n"
            "    @plugin_command('!dobcast')\n"
            "    async def dobcast(self, args, user, is_creator, ctx):\n"
            "        await ctx.broadcast('custom.bcast', {'v': 1})\n"
            "        return 'bcast'\n"
            "    @plugin_command('!dopub')\n"
            "    async def dopub(self, args, user, is_creator, ctx):\n"
            "        await ctx.event_bus.publish('custom.pub', {'v': 2})\n"
            "        return 'pub'\n",
            encoding="utf-8",
        )

        spoken = []
        broadcasts = []
        bus_events = []
        bus = EventBus()
        bus.subscribe("custom.pub", lambda ev, pl: bus_events.append((ev, pl)))
        bus.subscribe("x.z", lambda ev, pl: bus_events.append((ev, pl)))

        async def speak_cb(text: str, emotion: str):
            spoken.append((text, emotion))

        async def broadcast_cb(ev_type: str, data: dict):
            broadcasts.append((ev_type, data))

        reg = PluginRegistry(
            plugins_dir=str(self.plugins_dir),
            enabled_plugins=["no_perms", "with_perms"],
            sandbox_mode="subprocess",
            event_bus=bus,
            speak_cb=speak_cb,
            broadcast_cb=broadcast_cb,
        )
        try:
            await reg.discover_plugins()

            # Denied plugin must NOT trigger callbacks
            await reg.dispatch_command("!tryspeak")
            await reg.dispatch_command("!trybcast")
            await reg.dispatch_command("!trypub")
            self.assertEqual(spoken, [])
            self.assertEqual(broadcasts, [])
            self.assertEqual(bus_events, [])

            meta_denied = next(p for p in reg.list_plugins() if p["id"] == "no_perms")
            self.assertGreaterEqual(meta_denied["error_count"], 3)

            # Allowed plugin MUST trigger callbacks
            _, r1 = await reg.dispatch_command("!dospeak")
            _, r2 = await reg.dispatch_command("!dobcast")
            _, r3 = await reg.dispatch_command("!dopub")
            self.assertEqual(r1, "spoke")
            self.assertEqual(r2, "bcast")
            self.assertEqual(r3, "pub")
            self.assertEqual(spoken, [("hello", "happy")])
            self.assertEqual(broadcasts, [("custom.bcast", {"v": 1})])
            self.assertEqual(bus_events, [("custom.pub", {"v": 2})])
        finally:
            await reg.shutdown()

    async def test_hard_timeout_kills_infinite_loop_subprocess(self):
        hang_file = self.plugins_dir / "hang_plugin.py"
        hang_file.write_text(
            "from core.plugins.sdk import MaybeAIPlugin, PluginManifest, plugin_command\n"
            "class HangPlugin(MaybeAIPlugin):\n"
            "    manifest = PluginManifest(id='hang_plugin', name='Hang Plugin', commands=['!hang'])\n"
            "    @plugin_command('!hang')\n"
            "    async def hang(self, args, user, is_creator, ctx):\n"
            "        while True:\n"
            "            pass\n",
            encoding="utf-8",
        )

        reg = PluginRegistry(
            plugins_dir=str(self.plugins_dir),
            enabled_plugins=["hang_plugin"],
            hook_timeout_sec=0.3,
            sandbox_mode="subprocess",
        )
        try:
            await reg.discover_plugins()
            client = reg._subprocesses["hang_plugin"]
            proc = client.proc
            self.assertIsNotNone(proc)
            self.assertIsNone(proc.returncode)

            handled, resp = await asyncio.wait_for(reg.dispatch_command("!hang"), timeout=3.0)
            self.assertTrue(handled)
            self.assertIsNone(resp)
            # Subprocess must have been killed
            self.assertIsNotNone(proc.returncode)
            self.assertNotIn("hang_plugin", reg._subprocesses)

            meta = next(p for p in reg.list_plugins() if p["id"] == "hang_plugin")
            self.assertFalse(meta["loaded"])
            self.assertGreaterEqual(meta["error_count"], 1)
            self.assertIn("timed out", meta["last_error"].lower())
        finally:
            await reg.shutdown()


class TestPluginCLI(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_cli_init_test_and_pack(self):
        plugins_dir = self.root / "plugins"
        dist_dir = self.root / "dist"

        # 1. init
        res_init = subprocess.run(
            [sys.executable, "-m", "core.plugins.cli", "init", "hello_cli", "--dir", str(plugins_dir)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_init.returncode, 0, msg=res_init.stderr)
        plugin_path = plugins_dir / "hello_cli.py"
        readme_path = plugins_dir / "README.md"
        self.assertTrue(plugin_path.exists())
        self.assertTrue(readme_path.exists())

        # 2. test
        res_test = subprocess.run(
            [sys.executable, "-m", "core.plugins.cli", "test", str(plugin_path)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_test.returncode, 0, msg=res_test.stderr)
        self.assertIn("[PASS]", res_test.stdout)

        # 3. pack
        res_pack = subprocess.run(
            [sys.executable, "-m", "core.plugins.cli", "pack", str(plugin_path), "--out", str(dist_dir)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_pack.returncode, 0, msg=res_pack.stderr)
        zip_path = dist_dir / "hello_cli-1.0.0.zip"
        self.assertTrue(zip_path.exists())

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            self.assertEqual(names, {"hello_cli.py", "manifest.json", "SHA256SUMS.txt"})

            manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
            self.assertEqual(manifest_data["id"], "hello_cli")
            self.assertEqual(manifest_data["permissions"], ["chat:read", "event:sub"])

            sums_text = zf.read("SHA256SUMS.txt").decode("utf-8").strip().splitlines()
            sums_map = {line.split()[1]: line.split()[0] for line in sums_text}
            self.assertEqual(
                sums_map["hello_cli.py"],
                hashlib.sha256(zf.read("hello_cli.py")).hexdigest(),
            )
            self.assertEqual(
                sums_map["manifest.json"],
                hashlib.sha256(zf.read("manifest.json")).hexdigest(),
            )
