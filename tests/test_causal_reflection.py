import tempfile
import unittest
from pathlib import Path

from core.planning.decomposer import GoalDecomposer
from core.planning.engine import GoalEngine
from core.planning.executor import AutonomousMissionExecutor
from core.planning.models import Goal, GoalCategory, GoalStatus, GoalTier, ReflectionLesson, Subtask
from core.planning.replanner import StrategyReplanner


class TestCausalReflection(unittest.TestCase):
    def setUp(self):
        StrategyReplanner.reset_learning_state()
        StrategyReplanner.set_use_causal_reflection(True)
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.engine = GoalEngine(storage_dir=self._tmp.name)

    def tearDown(self):
        StrategyReplanner.reset_learning_state()
        StrategyReplanner.set_use_causal_reflection(True)
        self._tmp.cleanup()

    def test_structured_reflection_lesson_roundtrip_and_legacy_compat(self):
        goal = Goal(id="g1", title="Mining Iron", category=GoalCategory.MINECRAFT.value)
        lesson = goal.add_reflection_lesson(
            strategy_used="Cari iron di ravine terbuka",
            failure_reason="Diserang creeper",
            root_cause="hostile_mob_ambush",
            recommended_alternative="Buat Shield (Perisai) & gali Strip Mine tangga aman di Y=16 dengan penerangan penuh.",
            subtask_title="Eksplorasi gua",
        )
        self.assertEqual(len(goal.reflection_lessons), 1)
        self.assertIn("hostile_mob_ambush", goal.reflection)
        self.assertEqual(lesson.root_cause, "hostile_mob_ambush")

        data = goal.to_dict()
        restored = Goal.from_dict(data)
        self.assertEqual(len(restored.reflection_lessons), 1)
        self.assertEqual(restored.reflection_lessons[0].strategy_used, "Cari iron di ravine terbuka")

        # Legacy goal dict without reflection_lessons still deserializes cleanly
        legacy_data = dict(data)
        legacy_data.pop("reflection_lessons", None)
        legacy_goal = Goal.from_dict(legacy_data)
        self.assertEqual(legacy_goal.reflection_lessons, [])
        self.assertEqual(len(legacy_goal.get_recent_lessons(limit=5)), 1)

    def test_strategy_success_rate_scoring_and_selection(self):
        StrategyReplanner.record_strategy_outcome("strat_alpha", success=False, category="minecraft", failure_reason="mob")
        StrategyReplanner.record_strategy_outcome("strat_alpha", success=False, category="minecraft", failure_reason="mob")
        StrategyReplanner.record_strategy_outcome("strat_beta", success=True, category="minecraft")

        rate_alpha = StrategyReplanner.get_strategy_success_rate("strat_alpha", "minecraft")
        rate_beta = StrategyReplanner.get_strategy_success_rate("strat_beta", "minecraft")
        self.assertLess(rate_alpha, 0.5)
        self.assertGreater(rate_beta, 0.5)

        candidates = [
            {"id": "a", "title": "A", "strategy": "strat_alpha"},
            {"id": "b", "title": "B", "strategy": "strat_beta"},
        ]
        chosen = StrategyReplanner.select_best_strategy(
            category="minecraft",
            root_cause="hostile_mob_ambush",
            failed_strategies=["strat_alpha"],
            candidates=candidates,
        )
        self.assertEqual(chosen["strategy"], "strat_beta")

    def test_decomposer_uses_bounded_recent_reflections(self):
        # Create 7 lessons; decomposer should bound to max_lessons=5
        lessons = [
            ReflectionLesson(
                strategy_used=f"old_strat_{i}",
                failure_reason="timeout",
                root_cause="general_execution_failure",
                recommended_alternative=f"alt_{i}",
                category=GoalCategory.MINECRAFT.value,
            )
            for i in range(6)
        ]
        lessons.append(
            ReflectionLesson(
                strategy_used="Tebang pohon oak terdekat dengan axe.",
                failure_reason="Diserang creeper saat menebang kayu",
                root_cause="hostile_mob_ambush",
                recommended_alternative="Tebang kayu hanya di siang hari dengan perimeter obor.",
                category=GoalCategory.MINECRAFT.value,
                subtask_title="Tebang pohon & kumpulkan 32 Oak Logs",
            )
        )

        context = GoalDecomposer.build_reflection_context(lessons, category=GoalCategory.MINECRAFT.value, max_lessons=5)
        self.assertEqual(len(context.splitlines()), 5)

        subtasks = GoalDecomposer.decompose(
            goal_title="Membangun rumah di Minecraft",
            tier=GoalTier.DAILY.value,
            category=GoalCategory.MINECRAFT.value,
            reflections=lessons,
            max_lessons=5,
        )
        self.assertEqual(subtasks[0].strategy, "Tebang kayu hanya di siang hari dengan perimeter obor.")
        self.assertIn("Adapted from reflection", subtasks[0].description)

    def test_repeated_failure_selects_distinct_strategy_on_attempt_2(self):
        goal = Goal(
            id="g_repeat",
            title="Mengumpulkan 64 iron",
            category=GoalCategory.MINECRAFT.value,
            subtasks=[
                Subtask(
                    id="s1",
                    title="Tambang Iron di Gua Terbuka",
                    category=GoalCategory.MINECRAFT.value,
                    status=GoalStatus.IN_PROGRESS.value,
                    target_count=64.0,
                    unit="iron_ore",
                    strategy="Masuk gua terbuka tanpa perisai.",
                    attempts=1,
                )
            ],
        )

        # Attempt 1 failure -> selects first Plan B strategy
        sub_attempt_2, _ = StrategyReplanner.replan_subtask(
            goal=goal,
            failed_subtask=goal.subtasks[0],
            failure_reason="Diserang creeper dan mati di gua",
        )
        self.assertIsNotNone(sub_attempt_2)
        self.assertEqual(len(goal.reflection_lessons), 1)
        strat_1 = sub_attempt_2.strategy

        # Attempt 2 failure -> must select a DISTINCT strategy using stored reflection
        sub_attempt_3, _ = StrategyReplanner.replan_subtask(
            goal=goal,
            failed_subtask=sub_attempt_2,
            failure_reason="Diserang creeper lagi di terowongan",
        )
        self.assertIsNotNone(sub_attempt_3)
        self.assertNotEqual(sub_attempt_3.strategy, strat_1)
        self.assertNotEqual(sub_attempt_3.strategy, "Masuk gua terbuka tanpa perisai.")
        self.assertEqual(len(goal.reflection_lessons), 2)

    def test_keyword_fallback_when_causal_reflection_disabled(self):
        StrategyReplanner.set_use_causal_reflection(False)
        goal = Goal(
            id="g_legacy",
            title="Mining Iron",
            category=GoalCategory.MINECRAFT.value,
            subtasks=[
                Subtask(
                    id="s1",
                    title="Cari Iron",
                    category=GoalCategory.MINECRAFT.value,
                    status=GoalStatus.IN_PROGRESS.value,
                    strategy="Masuk gua",
                    attempts=1,
                )
            ],
        )
        sub_b, speech_b = StrategyReplanner.replan_subtask(
            goal=goal,
            failed_subtask=goal.subtasks[0],
            failure_reason="Diserang creeper",
        )
        self.assertIsNotNone(sub_b)
        self.assertIn("Plan B", sub_b.title)
        self.assertIn("perisai", speech_b.lower())
        # Legacy keyword mode does not populate structured reflection_lessons
        self.assertEqual(goal.reflection_lessons, [])
        self.assertTrue(bool(goal.reflection))


class TestExecutorCausalReflectionLoop(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        StrategyReplanner.reset_learning_state()
        StrategyReplanner.set_use_causal_reflection(True)

    async def test_executor_repeated_mission_failure_pivots_to_distinct_strategy(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            StrategyReplanner.reset_learning_state()
            StrategyReplanner.set_use_causal_reflection(True)
            engine = GoalEngine(storage_dir=tmpdir)

            async def failing_perf(song_id=None):
                return {"success": False, "error": "Audio stage mic failure"}

            goal = engine.create_goal(
                title="Konser Karaoke Uji Causal",
                description="Tes causal replanning",
                tier=GoalTier.DAILY.value,
                category=GoalCategory.PERFORMANCE.value,
                priority=10,
            )
            engine.set_active_goal(goal.id)

            executor = AutonomousMissionExecutor(
                goal_engine=engine,
                performance_runner=failing_perf,
                use_causal_reflection=True,
            )

            # Failure 1 -> replans to Plan B strategy 1
            res1 = await executor.step_once()
            self.assertEqual(res1["status"], "replanned")
            strat1 = res1["new_subtask"]["strategy"]

            # Failure 2 -> replans to DISTINCT Plan B strategy 2 using stored reflection
            res2 = await executor.step_once()
            self.assertEqual(res2["status"], "replanned")
            strat2 = res2["new_subtask"]["strategy"]
            self.assertNotEqual(strat2, strat1)

            # Re-decomposing a new mission of the same goal uses stored reflection
            new_subs = GoalDecomposer.decompose(
                goal_title="Konser Karaoke Uji Causal",
                tier=GoalTier.DAILY.value,
                category=GoalCategory.PERFORMANCE.value,
            )
            self.assertTrue(len(new_subs) >= 1)


if __name__ == "__main__":
    unittest.main()
