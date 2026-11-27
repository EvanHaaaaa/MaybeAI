import unittest
import os
import shutil
import tempfile
from pathlib import Path

from core.personality.models import TraitKey, EvolutionProfile
from core.personality.evolution import PersonalityEvolutionEngine
from core.mood import MoodEngine
from core.brain import Brain
from core.conversation.engine import ConversationEngine


class TestPersonalityEvolution(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage_path = os.path.join(self.temp_dir, "evolution.json")
        self.sb_path = os.path.join(self.temp_dir, "evolution.md")
        self.engine = PersonalityEvolutionEngine(
            storage_path=self.storage_path,
            second_brain_path=self.sb_path
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initial_traits_and_archetype(self):
        state = self.engine.get_state()
        self.assertEqual(state["level"], 1)
        self.assertEqual(state["exp"], 0)
        self.assertIn("Rookie Streamer", state["archetype"])
        traits = state["traits"]
        self.assertAlmostEqual(traits["competitiveness"], 0.35, places=2)
        self.assertAlmostEqual(traits["confidence"], 0.50, places=2)
        self.assertAlmostEqual(traits["warmth"], 0.60, places=2)
        self.assertAlmostEqual(traits["sassiness"], 0.40, places=2)
        self.assertAlmostEqual(traits["intellect"], 0.50, places=2)

    def test_game_defeat_increases_competitiveness(self):
        """User requirement: Sering kalah dalam game membuatnya lebih kompetitif."""
        initial_comp = self.engine.profile.traits[TraitKey.COMPETITIVENESS.value]
        initial_conf = self.engine.profile.traits[TraitKey.CONFIDENCE.value]

        res = self.engine.record_experience("game_defeat", {"opponent": "GrandmasterBot", "game": "Chess"})
        new_comp = self.engine.profile.traits[TraitKey.COMPETITIVENESS.value]
        new_conf = self.engine.profile.traits[TraitKey.CONFIDENCE.value]

        self.assertGreater(new_comp, initial_comp)
        self.assertLess(new_conf, initial_conf)
        self.assertGreater(res["exp_gained"], 0)
        self.assertIn("dendam", res["narrative"].lower())

    def test_coop_play_increases_warmth(self):
        """User requirement: Sering bermain bersama seseorang membuatnya lebih akrab/hangat."""
        initial_warmth = self.engine.profile.traits[TraitKey.WARMTH.value]

        res = self.engine.record_experience("coop_play", {"player": "DiamondHunter", "game": "Minecraft"})
        new_warmth = self.engine.profile.traits[TraitKey.WARMTH.value]

        self.assertGreater(new_warmth, initial_warmth)
        self.assertIn("mabar", res["narrative"].lower())

    def test_challenge_completed_increases_confidence(self):
        """User requirement: Berhasil menyelesaikan tantangan membuatnya lebih percaya diri."""
        initial_conf = self.engine.profile.traits[TraitKey.CONFIDENCE.value]

        res = self.engine.record_experience("challenge_completed", {"task": "Speedrun Netherite"})
        new_conf = self.engine.profile.traits[TraitKey.CONFIDENCE.value]

        self.assertGreater(new_conf, initial_conf)
        self.assertGreater(res["exp_gained"], 20)
        self.assertIn("percaya diri", res["narrative"].lower())

    def test_diminishing_returns_and_strict_bounds(self):
        """User requirement: Perubahan dilakukan secara terkontrol, bukan liar / unbounded."""
        # Simulate 100 consecutive defeats
        for _ in range(100):
            self.engine.record_experience("game_defeat", {"opponent": "Stockfish"})

        comp = self.engine.profile.traits[TraitKey.COMPETITIVENESS.value]
        conf = self.engine.profile.traits[TraitKey.CONFIDENCE.value]

        # Competitiveness must be strictly bounded <= 0.98
        self.assertLessEqual(comp, 0.98)
        self.assertGreater(comp, 0.80)

        # Confidence must be strictly bounded >= 0.05
        self.assertGreaterEqual(conf, 0.05)

    def test_level_up_and_milestone_unlocking(self):
        """Accumulated EXP triggers level ups and unlocked character badges."""
        self.assertEqual(self.engine.profile.level, 1)

        # Award enough experiences to level up
        for _ in range(10):
            self.engine.record_experience("challenge_completed", {"task": "Puzzle"})

        self.assertGreaterEqual(self.engine.profile.level, 2)
        # Check that milestones unlocked
        milestone_ids = [m.id for m in self.engine.profile.milestones]
        self.assertIn("iron_will_achiever", milestone_ids)

    def test_sync_to_mood_baselines(self):
        """Personality Evolution directly controls MoodEngine baselines."""
        mood = MoodEngine()
        initial_base_comp = mood.baselines["competitiveness"]

        # Boost competitiveness trait
        for _ in range(15):
            self.engine.record_experience("game_defeat", {"opponent": "Rival"})

        self.engine.sync_to_mood_baselines(mood)
        new_base_comp = mood.baselines["competitiveness"]

        # Evolved personality should shift baseline competitiveness upwards
        self.assertGreater(new_base_comp, initial_base_comp)

    def test_prompt_directive_and_second_brain_export(self):
        """Controlled behavioral directive is structured and non-destructive."""
        directive = self.engine.get_prompt_directive()
        self.assertIn("[🧬 EXPERIENCE-BASED PERSONALITY EVOLUTION]", directive)
        self.assertIn("Competitiveness", directive)
        self.assertIn("Confidence", directive)

        # Check second brain markdown file
        self.assertTrue(os.path.exists(self.sb_path))
        with open(self.sb_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("# 🧬 Eve Maybe - Experience-Based Personality Evolution", content)
            self.assertIn("Long-Term Personality Traits", content)

    def test_brain_exposure_and_mock_response(self):
        """Brain exposes personality and responds accurately to personality queries."""
        brain = Brain()
        self.assertIsNotNone(brain.personality)
        state = brain.get_conversation_state()
        self.assertIn("personality", state)

        # Mock conversation test
        resp = brain.conversation.generate_mock_response("User", "kenapa kamu kompetitif banget?")
        self.assertIn("kompetitif", resp.lower())
        self.assertIn("kekalahan", resp.lower())

    def test_synthesize_from_reflection_bounds_and_audit_log(self):
        """H4-05: Reflection synthesis adjusts traits within [0.05, 0.98] and logs audit trail."""
        mood_state = {"dimensions": {"happiness": 0.85, "annoyance": 0.10, "curiosity": 0.80, "excitement": 0.70, "competitiveness": 0.85}}
        initial_warmth = self.engine.profile.traits[TraitKey.WARMTH.value]

        res = self.engine.synthesize_from_reflection(
            "Great coop stream! Learned new strategy and felt warm support from friends.",
            mood_state=mood_state,
        )
        self.assertTrue(res["applied"])
        self.assertGreater(self.engine.profile.traits[TraitKey.WARMTH.value], initial_warmth)

        log = self.engine.get_evolution_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["source"], "reflection_synthesis")
        self.assertEqual(log[0]["bounds"], [0.05, 0.98])

        # Repeated extreme synthesis must remain strictly within [0.05, 0.98]
        for _ in range(100):
            self.engine.synthesize_from_reflection("win compete rematch proud confident warm learn", mood_state=mood_state)
        for val in self.engine.profile.traits.values():
            self.assertGreaterEqual(val, 0.05)
            self.assertLessEqual(val, 0.98)

        # Verify audit log persists across reload
        reloaded = PersonalityEvolutionEngine(storage_path=self.storage_path, second_brain_path=self.sb_path)
        self.assertGreater(len(reloaded.get_evolution_log()), 1)

    def test_synthesize_from_reflection_gated_by_dynamic_synthesis(self):
        """H4-05: dynamic_synthesis=False gates reflection-based trait adjustments."""
        gated_engine = PersonalityEvolutionEngine(
            storage_path=self.storage_path,
            second_brain_path=self.sb_path,
            dynamic_synthesis=False,
        )
        before = dict(gated_engine.profile.traits)
        res = gated_engine.synthesize_from_reflection("win rematch proud warm learn")
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "dynamic_synthesis_disabled")
        self.assertEqual(gated_engine.profile.traits, before)
        self.assertEqual(len(gated_engine.get_evolution_log()), 0)


if __name__ == "__main__":
    unittest.main()
