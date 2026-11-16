import unittest
import os
import shutil
from pathlib import Path
from core.planning.models import Goal, Subtask, GoalTier, GoalStatus, GoalCategory
from core.planning.decomposer import GoalDecomposer
from core.planning.replanner import StrategyReplanner
from core.planning.engine import GoalEngine
from core.conversation.engine import ConversationEngine
from core.brain import Brain


class TestGoalDecomposer(unittest.TestCase):
    def test_minecraft_house_decomposition(self):
        subs = GoalDecomposer.decompose("Membangun rumah di Minecraft", tier=GoalTier.DAILY.value)
        self.assertGreaterEqual(len(subs), 4)
        titles = [s.title.lower() for s in subs]
        self.assertTrue(any("kayu" in t or "log" in t for t in titles))
        self.assertTrue(any("fondasi" in t or "crafting" in t for t in titles))
        self.assertEqual(subs[0].status, GoalStatus.IN_PROGRESS.value)

    def test_minecraft_iron_decomposition(self):
        subs = GoalDecomposer.decompose("Mengumpulkan 64 iron", tier=GoalTier.SHORT_TERM.value)
        self.assertGreaterEqual(len(subs), 3)
        self.assertTrue(any(s.target_count == 64.0 for s in subs))

    def test_speedrun_decomposition(self):
        subs = GoalDecomposer.decompose("Menyelesaikan tantangan speedrun", tier=GoalTier.WEEKLY.value)
        self.assertGreaterEqual(len(subs), 4)
        titles = [s.title.lower() for s in subs]
        self.assertTrue(any("nether" in t or "portal" in t for t in titles))
        self.assertTrue(any("dragon" in t or "end" in t for t in titles))

    def test_social_decomposition(self):
        subs = GoalDecomposer.decompose("Berinteraksi dengan player yang belum dikenal", tier=GoalTier.SOCIAL.value)
        self.assertGreaterEqual(len(subs), 3)
        titles = [s.title.lower() for s in subs]
        self.assertTrue(any("sapa" in t or "pantau" in t or "tanya" in t for t in titles))


class TestStrategyReplanner(unittest.TestCase):
    def test_replan_on_creeper_attack(self):
        goal = Goal(
            id="g_test",
            title="Mining Iron",
            subtasks=[
                Subtask(id="s1", title="Cari Iron di Ravine Terbuka", target_count=32.0, unit="iron_ore")
            ]
        )
        failed_sub = goal.subtasks[0]
        new_sub, speech = StrategyReplanner.replan_subtask(
            goal=goal,
            failed_subtask=failed_sub,
            failure_reason="Diserang creeper dan mati di gua terbuka"
        )
        self.assertEqual(failed_sub.status, GoalStatus.REPLANNED.value)
        self.assertIn("Plan B", new_sub.title)
        self.assertIn("perisai", speech.lower())
        self.assertEqual(len(goal.subtasks), 2)
        self.assertEqual(goal.subtasks[1].status, GoalStatus.IN_PROGRESS.value)

    def test_replan_on_player_ignored(self):
        goal = Goal(
            id="g_test2",
            title="Interaksi Sosial",
            subtasks=[
                Subtask(id="s1", title="Sapa Player Baru Steve", target_count=1.0)
            ]
        )
        failed_sub = goal.subtasks[0]
        new_sub, speech = StrategyReplanner.replan_subtask(
            goal=goal,
            failed_subtask=failed_sub,
            failure_reason="Player menolak dan offline"
        )
        self.assertEqual(failed_sub.status, GoalStatus.REPLANNED.value)
        self.assertIn("Chatter Aktif", new_sub.title)
        self.assertIn("Plan B", new_sub.title)


class TestGoalEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = "data/test_goals"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        self.engine = GoalEngine(storage_dir=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_seeded_canonical_goals(self):
        goals = self.engine.get_all_goals()
        titles = [g.title for g in goals]
        self.assertIn("Membangun rumah di Minecraft", titles)
        self.assertIn("Mengumpulkan 64 iron", titles)
        self.assertIn("Menyelesaikan tantangan speedrun", titles)
        self.assertIn("Berinteraksi dengan player yang belum dikenal", titles)
        self.assertIsNotNone(self.engine.get_active_goal())

    def test_advance_progress_and_completion(self):
        active_g = self.engine.get_active_goal()
        active_sub = active_g.get_active_subtask()
        self.assertIsNotNone(active_sub)

        # Advance subtask
        res = self.engine.advance_subtask_progress(active_sub.id, delta=active_sub.target_count)
        self.assertTrue(res["subtask_completed"])
        self.assertGreater(active_g.progress, 0.0)

    def test_complete_current_subtask(self):
        res = self.engine.complete_current_subtask()
        self.assertTrue(res["success"])
        self.assertTrue(res["subtask_completed"])

    def test_fail_and_replan_active(self):
        new_sub, speech = self.engine.fail_and_replan_active_subtask("Creeper meledak saat mengumpulkan kayu")
        self.assertIsNotNone(new_sub)
        self.assertIn("Plan B", new_sub.title)
        self.assertIn("Plan B", speech)
        state = self.engine.get_state()
        self.assertIsNotNone(state["last_strategy_pivot"])

    def test_autonomous_select_next_activity(self):
        # When competitive mood is high
        chosen, speech = self.engine.autonomous_select_next_activity(mood_dimensions={"competitiveness": 0.85})
        self.assertIsNotNone(chosen)
        self.assertIn("speedrun", chosen.title.lower())
        self.assertIn("agenda mandiri", speech)

        # When curiosity mood is high
        chosen_soc, speech_soc = self.engine.autonomous_select_next_activity(mood_dimensions={"curiosity": 0.90, "competitiveness": 0.1})
        self.assertIsNotNone(chosen_soc)
        self.assertEqual(chosen_soc.tier, GoalTier.SOCIAL.value)

    def test_sync_to_markdown_file(self):
        self.engine.sync_to_markdown()
        md_path = Path(self.test_dir) / "agenda.md"
        self.assertTrue(md_path.exists())
        content = md_path.read_text(encoding="utf-8")
        self.assertIn("Autonomous Goal & Planning Agenda", content)
        self.assertIn("Active Streaming Agenda", content)
        self.assertIn("Daily Goals", content)

    def test_goal_directive_generation(self):
        directive = self.engine.get_goal_directive()
        self.assertIn("AUTONOMOUS GOALS & ACTIVE AGENDA", directive)
        self.assertIn("Active Stream Objective", directive)
        self.assertIn("Current Step", directive)


class TestGoalBrainIntegration(unittest.TestCase):
    def setUp(self):
        self.brain = Brain("config/settings.json", "config/character.json")

    def test_brain_goals_property_and_state(self):
        self.assertIsNotNone(self.brain.goals)
        state = self.brain.get_conversation_state()
        self.assertIn("goals", state)
        self.assertIn("active_goal", state["goals"])
        self.assertIn("goals_by_tier", state["goals"])

    def test_system_prompt_includes_goal_directive(self):
        prompt = self.brain.conversation.build_system_prompt("Creator", "Halo Eve!")
        self.assertIn("AUTONOMOUS GOALS & ACTIVE AGENDA", prompt)

    def test_mock_response_answers_goal_query(self):
        resp = self.brain.conversation.generate_mock_response("Creator", "Eve, apa target atau rencanamu hari ini?")
        self.assertTrue("agenda" in resp.lower() or "misi" in resp.lower() or "progres" in resp.lower())


if __name__ == "__main__":
    unittest.main()
