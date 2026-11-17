import unittest
import shutil
from pathlib import Path

from core.performance.models import (
    PerformanceStatus,
    SongMoodCategory,
    StageMovement,
    ChoreographyStep,
    SetlistItem,
    PerformanceSession
)
from core.performance.director import PerformanceDirector
from core.brain import Brain
from core.conversation.engine import ConversationEngine


class TestPerformanceModels(unittest.TestCase):
    def test_choreography_step_and_setlist_item(self):
        step = ChoreographyStep(
            section="chorus",
            emotion="blush",
            action="wink",
            movement="sparkle_pose",
            stage_lighting="golden_glow",
            crowd_callout="Mana glowstick-nya chat?!"
        )
        d = step.to_dict()
        self.assertEqual(d["section"], "chorus")
        self.assertEqual(d["movement"], "sparkle_pose")
        self.assertEqual(d["crowd_callout"], "Mana glowstick-nya chat?!")

        item = SetlistItem(
            order=1,
            song_id="digital_world",
            title="Digital World",
            mood_category="hype_energetic",
            status="current"
        )
        d_item = item.to_dict()
        self.assertEqual(d_item["order"], 1)
        self.assertEqual(d_item["status"], "current")

    def test_performance_session_serialization(self):
        sess = PerformanceSession(
            status=PerformanceStatus.PERFORMING.value,
            current_song_id="digital_world",
            current_title="Digital World",
            audience_glowsticks=75,
            performance_score=98
        )
        d = sess.to_dict()
        self.assertEqual(d["status"], "performing")
        self.assertEqual(d["audience_glowsticks"], 75)
        self.assertEqual(d["performance_score"], 98)


class TestPerformanceDirector(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("data/test_perf_env")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.director = PerformanceDirector(data_dir=str(self.test_dir))

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_songs_catalog_loaded(self):
        self.assertTrue(len(self.director.songs_catalog) >= 5)
        self.assertIn("digital_world", self.director.songs_catalog)
        self.assertIn("midnight_starlight", self.director.songs_catalog)
        self.assertIn("glitch_overclock", self.director.songs_catalog)
        self.assertIn("tsundere_anthem", self.director.songs_catalog)
        self.assertIn("minecraft_creeper_lullaby", self.director.songs_catalog)

    def test_autonomous_song_recommendation_by_mood(self):
        # 1. Hype Excited
        song_hype, reason_hype = self.director.get_autonomous_song_recommendation("HYPE_EXCITED")
        self.assertEqual(song_hype, "digital_world")
        self.assertIn("hype", reason_hype.lower())

        # 2. Curious Pensive (Chill Ballad)
        song_chill, reason_chill = self.director.get_autonomous_song_recommendation("CURIOUS_PENSIVE")
        self.assertEqual(song_chill, "midnight_starlight")
        self.assertIn("tenang", reason_chill.lower())

        # 3. Tryhard Competitive (Fast Cyber-Rock)
        song_fast, reason_fast = self.director.get_autonomous_song_recommendation("TRYHARD_COMPETITIVE")
        self.assertEqual(song_fast, "glitch_overclock")
        self.assertIn("adrenalin", reason_fast.lower())

        # 4. Sassy Annoyed (Tsundere Anthem)
        song_sassy, reason_sassy = self.director.get_autonomous_song_recommendation("SASSY_ANNOYED")
        self.assertEqual(song_sassy, "tsundere_anthem")
        self.assertIn("tsundere", reason_sassy.lower())

    def test_setlist_planning(self):
        setlist = self.director.plan_concert_setlist("Konser Uji Coba")
        self.assertEqual(len(setlist), 4)
        self.assertEqual(setlist[0].song_id, "digital_world")
        self.assertEqual(setlist[0].status, "current")
        self.assertEqual(setlist[1].status, "queued")

    def test_performance_lifecycle(self):
        # 1. Pre-show MC
        song_id, mc_intro = self.director.start_performance(
            song_id="digital_world",
            dominant_mood="HYPE_EXCITED",
            dedication_user="DiamondHunter"
        )
        self.assertEqual(song_id, "digital_world")
        self.assertIn("PERTUNJUKAN SPESIAL DIMULAI", mc_intro)
        self.assertIn("DiamondHunter", mc_intro)
        self.assertEqual(self.director.session.status, PerformanceStatus.MC_INTRO.value)

        # 2. Line Choreography Step
        step = self.director.get_choreography_step_for_line("digital_world", line_idx=0)
        self.assertIsInstance(step, ChoreographyStep)
        self.assertEqual(step.section, "intro")
        self.assertEqual(self.director.session.status, PerformanceStatus.PERFORMING.value)

        # 3. Audience Glowstick Cheer
        cheers = self.director.record_audience_cheer("Fan123", cheer_type="glowstick")
        self.assertTrue(cheers > 0)
        self.assertEqual(self.director.session.audience_glowsticks, cheers)

        # 4. Post-Show MC & Review
        mc_outro, score = self.director.finish_performance()
        self.assertIn("PERFORMANCE SELESAI", mc_outro)
        self.assertTrue(85 <= score <= 100)
        self.assertEqual(self.director.session.status, PerformanceStatus.MC_OUTRO.value)
        self.assertTrue(len(self.director.concert_history) >= 1)

    def test_second_brain_sync(self):
        self.director.plan_concert_setlist()
        self.director.finish_performance()
        f_path = self.test_dir / "second_brain" / "performance" / "setlist.md"
        self.assertTrue(f_path.exists())
        content = f_path.read_text(encoding="utf-8")
        self.assertIn("Dynamic Performance Director & Idol Concert Setlist", content)
        self.assertIn("Digital World", content)


class TestPerformanceBrainIntegration(unittest.TestCase):
    def test_brain_exposure_and_mock(self):
        brain = Brain()
        self.assertIsNotNone(brain.performance)
        state = brain.get_conversation_state()
        self.assertIn("performance", state)
        self.assertIn("session", state["performance"])

        # System prompt directive
        engine = brain.conversation
        prompt = engine.build_system_prompt("Creator")
        self.assertIn("PERFORMANCE DIRECTOR", prompt)

        # Mock conversation inquiry
        resp = engine.generate_mock_response("GlowFan", "Eve, lagu apa yang cocok sama mood kamu sekarang?")
        self.assertIn("mood Eve", resp)


if __name__ == "__main__":
    unittest.main()
