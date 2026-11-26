import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

try:
    import tests  # noqa: F401
except ImportError:
    os.environ.setdefault("MAYBEAI_LLM_PROVIDER", "mock")

from core.planning.engine import GoalEngine
from core.minecraft.controller import MinecraftController
from core.planning.executor import AutonomousMissionExecutor
from core.planning.models import GoalCategory
from core.vision.engine import VisionEngine
from core.vts_client import VTSClient


class TestAvatarVTSAndTelemetry(unittest.IsolatedAsyncioTestCase):
    async def test_vts_client_set_parameters_and_apply_mood_rig(self):
        vts = VTSClient()
        vts.connected = True
        sent_payloads = []

        class _FakeWS:
            async def send(self, msg: str):
                sent_payloads.append(json.loads(msg))

        vts.ws = _FakeWS()
        await vts.set_parameters({"FaceAngleX": 4.0, "MouthForm": 0.8}, weight=0.9)
        self.assertEqual(len(sent_payloads), 1)
        req = sent_payloads[0]
        self.assertEqual(req["messageType"], "InjectParameterDataRequest")
        ids = {p["id"]: p["value"] for p in req["data"]["parameterValues"]}
        self.assertEqual(ids["FaceAngleX"], 4.0)
        self.assertEqual(ids["MouthForm"], 0.8)

        rig = await vts.apply_mood_rig("happy", mood_dims={"energy": 0.9, "joy": 0.8}, singing=True)
        self.assertIn("FaceAngleZ", rig)
        self.assertIn("EyeOpenLeft", rig)
        self.assertIn("BrowLeftY", rig)
        self.assertIn("MouthForm", rig)
        self.assertEqual(vts.get_rig_state()["MouthForm"], rig["MouthForm"])

    def test_minecraft_telemetry_and_inventory_count(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            mc = MinecraftController(servers_config_path=str(Path(tmpdir) / "mc_servers.json"))
            seen = []
            mc.set_callbacks(
                on_commentary=lambda msg: None,
                on_telemetry=lambda t: seen.append(t),
            )
            # Simulate incoming mc_telemetry payload as handled by controller
            telemetry_payload = {
                "health": 18,
                "food": 16,
                "pos": {"x": 10, "y": 64, "z": -5},
                "biome": "forest",
                "inventory": {"oak_log": 4, "birch_log": 2, "cobblestone": 12},
                "nearby_players": [{"name": "Steve", "distance": 5}],
                "nearby_hostiles": [],
            }
            mc.latest_telemetry = telemetry_payload
            if mc.on_telemetry_callback:
                mc.on_telemetry_callback(telemetry_payload)

            self.assertEqual(mc.get_telemetry()["biome"], "forest")
            self.assertEqual(mc.get_inventory_count(["log"]), 6)
            self.assertEqual(mc.get_inventory_count("cobblestone"), 12)
            self.assertEqual(len(seen), 1)

    async def test_autonomous_mission_executor_real_inventory_delta_check(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            ge = GoalEngine(storage_dir=tmpdir)
            mc = MinecraftController(servers_config_path=str(Path(tmpdir) / "mc_servers.json"))
            mc.connection_status = "connected"
            mc.latest_telemetry = {"inventory": {"oak_log": 2}}
            mc.toggle_wander = AsyncMock()

            executor = AutonomousMissionExecutor(goal_engine=ge, minecraft=mc)
            goal = ge.create_goal(
                title="Collect 5 oak logs",
                description="Chop oak logs",
                category=GoalCategory.MINECRAFT.value,
            )
            ge.set_active_goal(goal.id)
            subtask = goal.get_active_subtask() or goal.subtasks[0]
            plan = {"action_name": "minecraft_gather", "params": {"mode": "santai", "item": "logs", "delta": 1.0}}

            # No inventory delta -> must fail instead of crediting fake progress
            res_fail = await executor._execute_minecraft(plan, goal, subtask)
            self.assertFalse(res_fail["success"])
            self.assertEqual(res_fail["observed_delta"], 0)

            # Simulate inventory increasing during execution -> must succeed
            async def _gain_logs():
                mc.latest_telemetry = {"inventory": {"oak_log": 5}}

            mc.toggle_wander = AsyncMock(side_effect=_gain_logs)
            res_ok = await executor._execute_minecraft(plan, goal, subtask)
            self.assertTrue(res_ok["success"])
            self.assertGreater(subtask.progress, 0.0)

    async def test_vision_engine_aperceive_with_vlm(self):
        engine = VisionEngine()
        engine.vlm_enabled = True
        engine.vlm_interval_sec = 0.0
        engine.last_vlm_time = 0.0

        with patch(
            "core.vision.engine.MultimodalVisionModel.analyze_with_vlm_api",
            AsyncMock(return_value="Minecraft forest biome with oak trees ahead."),
        ) as mock_vlm:
            obs = await engine.aperceive_with_vlm(
                simulated_scene="minecraft",
                api_provider="gemini",
                gemini_api_key="test-gemini-key",
            )
            mock_vlm.assert_awaited_once()
            self.assertEqual(obs.summary, "Minecraft forest biome with oak trees ahead.")
            self.assertTrue(obs.details.get("vlm_enriched"))

        # Mock provider must not call external VLM API
        with patch(
            "core.vision.engine.MultimodalVisionModel.analyze_with_vlm_api",
            AsyncMock(return_value="should-not-run"),
        ) as mock_vlm_skipped:
            obs_mock = await engine.aperceive_with_vlm(
                simulated_scene="desktop",
                api_provider="mock",
                gemini_api_key="test-gemini-key",
            )
            mock_vlm_skipped.assert_not_awaited()
            self.assertFalse(obs_mock.details.get("vlm_enriched", False))


if __name__ == "__main__":
    unittest.main()
