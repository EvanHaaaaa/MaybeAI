import unittest
import os
import tempfile
from pathlib import Path
from core.relationship.models import (
    RelationshipTier,
    InsideJoke,
    SharedExperience,
    RelationshipProfile
)
from core.relationship.engine import RelationshipEngine
from core.conversation.engine import ConversationEngine
from core.brain import Brain


class TestRelationshipModels(unittest.TestCase):
    def test_default_profile(self):
        p = RelationshipProfile(username="Bob")
        self.assertEqual(p.username, "Bob")
        self.assertEqual(p.tier, RelationshipTier.NEW_FRIEND.value)
        self.assertEqual(p.familiarity, 0.1)
        self.assertEqual(p.trust, 0.2)
        self.assertEqual(p.rivalry, 0.05)
        self.assertEqual(p.gaming_affinity, 0.05)

    def test_recalculate_tier_rival(self):
        p = RelationshipProfile(username="Garry", rivalry=0.6, familiarity=0.4)
        p.recalculate_tier()
        self.assertEqual(p.tier, RelationshipTier.RIVAL.value)

    def test_recalculate_tier_gaming_partner(self):
        p = RelationshipProfile(username="Alex", gaming_affinity=0.55, familiarity=0.35, rivalry=0.1)
        p.recalculate_tier()
        self.assertEqual(p.tier, RelationshipTier.GAMING_PARTNER.value)

    def test_recalculate_tier_trusted_friend(self):
        p = RelationshipProfile(username="Creator", trust=0.85, familiarity=0.7, rivalry=0.05)
        p.recalculate_tier()
        self.assertEqual(p.tier, RelationshipTier.TRUSTED_FRIEND.value)

    def test_recalculate_tier_regular_viewer(self):
        p = RelationshipProfile(username="Lurker", familiarity=0.35, trust=0.3, interaction_count=10)
        p.recalculate_tier()
        self.assertEqual(p.tier, RelationshipTier.REGULAR_VIEWER.value)

    def test_inside_joke_and_experience_addition(self):
        p = RelationshipProfile(username="TestUser")
        joke1 = p.add_inside_joke("Makan Remah Roti", "Ngunyah keyboard", "Stream santai")
        self.assertIsNotNone(joke1)
        self.assertEqual(len(p.inside_jokes), 1)
        self.assertEqual(p.inside_jokes[0].topic, "Makan Remah Roti")

        joke2 = p.add_inside_joke("Begadang Kopi", "Kopi sachet 5 gelas")
        self.assertEqual(len(p.inside_jokes), 2)
        self.assertEqual(joke2.punchline, "Kopi sachet 5 gelas")

        exp = p.record_experience("co-op", "Mabar lawan Ender Dragon", 0.8)
        self.assertEqual(len(p.shared_experiences), 1)
        self.assertEqual(exp.summary, "Mabar lawan Ender Dragon")

    def test_serialization(self):
        p = RelationshipProfile(username="Garry", rivalry=0.7, special_nickname="Rival Abadi")
        p.add_inside_joke("Blunder", "Menteri lenyap")
        p.record_experience("chess", "Kalah skakmat", 0.5)

        data = p.to_dict()
        p2 = RelationshipProfile.from_dict(data)

        self.assertEqual(p2.username, "Garry")
        self.assertEqual(p2.rivalry, 0.7)
        self.assertEqual(p2.special_nickname, "Rival Abadi")
        self.assertEqual(len(p2.inside_jokes), 1)
        self.assertEqual(p2.inside_jokes[0].topic, "Blunder")
        self.assertEqual(len(p2.shared_experiences), 1)


class TestRelationshipEngine(unittest.TestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_dir = Path(self._temp_dir_obj.name)
        self.test_storage = str(self.temp_dir / "relationships" / "relationships.json")
        self.test_md_dir = str(self.temp_dir / "second_brain" / "relationships")
        os.makedirs(os.path.dirname(self.test_storage), exist_ok=True)
        os.makedirs(self.test_md_dir, exist_ok=True)
        self.engine = RelationshipEngine(
            storage_path=self.test_storage,
            markdown_dir=self.test_md_dir
        )

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    def test_canonical_seed_profiles(self):
        creator = self.engine.get_relationship("Creator")
        self.assertEqual(creator.tier, RelationshipTier.TRUSTED_FRIEND.value)
        self.assertGreaterEqual(len(creator.inside_jokes), 2)

        gamer = self.engine.get_relationship("DiamondHunter")
        self.assertEqual(gamer.tier, RelationshipTier.GAMING_PARTNER.value)
        self.assertGreaterEqual(gamer.gaming_affinity, 0.7)

        garry = self.engine.get_relationship("GrandmasterGarry")
        self.assertEqual(garry.tier, RelationshipTier.RIVAL.value)
        self.assertGreaterEqual(garry.rivalry, 0.7)

    def test_record_chat_donation(self):
        p = self.engine.record_chat_interaction(
            username="SultanViewer",
            text="Ini buat beli GPU baru ya Eve!",
            is_donation=True,
            donation_amount="Rp 100.000"
        )
        self.assertEqual(p.username, "SultanViewer")
        self.assertGreater(p.trust, 0.25)
        self.assertGreater(p.affection, 0.25)
        self.assertTrue(any(e.category == "donation" for e in p.shared_experiences))

    def test_record_minecraft_gaming_events(self):
        # Diamond gift
        p = self.engine.record_gaming_event(
            username="MinerPro",
            game="minecraft",
            event_type="gift",
            details={"item": "diamond", "amount": 5}
        )
        self.assertGreater(p.gaming_affinity, 0.15)
        self.assertTrue(any("Diamond" in j.topic for j in p.inside_jokes))

        # Attack Eve
        p2 = self.engine.record_gaming_event(
            username="GrieferX",
            game="minecraft",
            event_type="attack",
            details={"damage": 4.0}
        )
        self.assertGreater(p2.rivalry, 0.2)

    def test_record_chess_queen_capture(self):
        p = self.engine.record_gaming_event(
            username="ChessPlayer99",
            game="chess",
            event_type="queen_captured",
            details={"piece": "Q"}
        )
        self.assertGreater(p.rivalry, 0.2)
        self.assertTrue(any("Menteri" in j.topic or "Ratu" in j.topic for j in p.inside_jokes))

    def test_get_prompt_directive(self):
        directive = self.engine.get_prompt_directive("DiamondHunter")
        self.assertIn("Gaming Partner", directive)
        self.assertIn("Gaming Synergy:", directive)
        self.assertIn("Inside Jokes", directive)
        self.assertIn("Pajak Diamond 50%", directive)

    def test_sync_to_markdown(self):
        md_path = self.engine.sync_to_markdown("Creator")
        self.assertIsNotNone(md_path)
        self.assertTrue(os.path.exists(md_path))
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Trusted Friend", content)
        self.assertIn("## 🎭 Shared Inside Jokes & Running Gags", content)
        self.assertIn("Overclock GPU", content)


class TestConversationAndBrainIntegration(unittest.TestCase):
    def setUp(self):
        self.brain = Brain()
        self.conv = self.brain.conversation
        self._temp_dir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_dir = Path(self._temp_dir_obj.name)
        self.test_storage = str(self.temp_dir / "relationships" / "conv_rel.json")
        self.test_md_dir = str(self.temp_dir / "second_brain" / "relationships")
        os.makedirs(os.path.dirname(self.test_storage), exist_ok=True)
        os.makedirs(self.test_md_dir, exist_ok=True)
        self.conv.relationships = RelationshipEngine(
            storage_path=self.test_storage,
            markdown_dir=self.test_md_dir
        )

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    def test_brain_relationship_access(self):
        self.assertIsNotNone(self.brain.relationships)
        state = self.brain.get_conversation_state()
        self.assertIn("relationships", state)
        self.assertIn("profiles", state["relationships"])
        self.assertIn("creator", state["relationships"]["profiles"])

    def test_chat_updates_relationships(self):
        self.conv.record_incoming_chat("NewFan", "Halo Eve, kamu keren banget main Minecraft!")
        profile = self.conv.relationships.get_relationship("NewFan")
        self.assertEqual(profile.interaction_count, 1)
        self.assertGreater(profile.gaming_affinity, 0.05)

    def test_system_prompt_includes_directive(self):
        prompt = self.conv.build_system_prompt("GrandmasterGarry")
        self.assertIn("GrandmasterGarry", prompt)
        self.assertIn("Rival", prompt)
        self.assertIn("Blunder Ratu Langkah 12", prompt)

    def test_mock_response_reflects_relationship_archetypes(self):
        # Rival
        resp_rival = self.conv.generate_mock_response("GrandmasterGarry", "Skakmat kamu sekarang Eve!")
        self.assertTrue(any(word in resp_rival.lower() for word in ["skak", "menteri", "blunder", "evaluasi", "rematch", "garry", "rival", "menang"]))

        # Gaming partner
        resp_partner = self.conv.generate_mock_response("DiamondHunter", "Ayo mabar mining diamond lagi")
        self.assertTrue(any(word in resp_partner.lower() for word in ["mabar", "diamond", "mining", "pajak", "creeper", "iron", "gas", "partner"]))

        # Trusted friend
        resp_trusted = self.conv.generate_mock_response("Creator", "Capek banget hari ini Eve")
        self.assertTrue(any(word in resp_trusted.lower() for word in ["istirahat", "creator", "semangat", "martabak", "teman", "tenang", "sahabat"]))

    def test_synthesize_from_reflection_bounds_and_audit_log(self):
        """H4-05: Relationship synthesis adjusts metrics within [0.05, 0.98] and records audit log."""
        rel_engine = self.conv.relationships
        mood_state = {"dimensions": {"happiness": 0.85, "annoyance": 0.10}}
        before_trust = rel_engine.get_relationship("Steve").trust

        res = rel_engine.synthesize_from_reflection(
            "Steve was very kind and helpful during the Minecraft coop stream.",
            mood_state=mood_state,
            username="Steve",
        )
        self.assertTrue(res["applied"])
        self.assertIn("Steve", res["updated_users"])
        self.assertGreater(rel_engine.get_relationship("Steve").trust, before_trust)

        log = rel_engine.get_evolution_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["bounds"], [0.05, 0.98])

        # Repeated synthesis must stay strictly within [0.05, 0.98]
        for _ in range(50):
            rel_engine.synthesize_from_reflection("trust kind friend game coop", mood_state=mood_state, username="Steve")
        steve = rel_engine.get_relationship("Steve")
        for metric in (steve.familiarity, steve.trust, steve.rivalry, steve.gaming_affinity, steve.affection):
            self.assertGreaterEqual(metric, 0.05)
            self.assertLessEqual(metric, 0.98)

    def test_synthesize_from_reflection_gated_by_dynamic_synthesis(self):
        """H4-05: dynamic_synthesis=False disables relationship synthesis."""
        rel_engine = self.conv.relationships
        rel_engine.dynamic_synthesis = False
        before_trust = rel_engine.get_relationship("Steve").trust

        res = rel_engine.synthesize_from_reflection("Steve was kind and helpful", username="Steve")
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "dynamic_synthesis_disabled")
        self.assertEqual(rel_engine.get_relationship("Steve").trust, before_trust)


if __name__ == "__main__":
    unittest.main()
