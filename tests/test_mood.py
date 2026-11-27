import unittest
import time
from core.mood.engine import MoodEngine, score_affective_memories
from core.conversation.engine import ConversationEngine
from core.brain import Brain


class TestMoodEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MoodEngine()

    def test_initial_baselines(self):
        state = self.engine.get_state()
        dims = state["dimensions"]
        self.assertAlmostEqual(dims["happiness"], 0.60, places=2)
        self.assertAlmostEqual(dims["annoyance"], 0.10, places=2)
        self.assertAlmostEqual(dims["curiosity"], 0.50, places=2)
        self.assertAlmostEqual(dims["excitement"], 0.40, places=2)
        self.assertAlmostEqual(dims["competitiveness"], 0.30, places=2)
        self.assertEqual(state["dominant_mood"], "CHILL_NEUTRAL")

    def test_decay_toward_baseline(self):
        # Spike annoyance
        self.engine.apply_stimulus("insult", intensity=1.5)
        self.assertGreater(self.engine.dimensions["annoyance"], 0.40)
        
        # Simulate passage of 120 seconds
        self.engine.last_update_time -= 120.0
        # Trigger decay update
        self.engine.update_decay()
        dims = self.engine.dimensions
        # Should have significantly decayed back toward baseline (0.10)
        self.assertLess(dims["annoyance"], 0.25)

    def test_stimulus_effects(self):
        # Donation
        prev_happy = self.engine.dimensions["happiness"]
        prev_excite = self.engine.dimensions["excitement"]
        self.engine.apply_stimulus("donation")
        self.assertGreater(self.engine.dimensions["happiness"], prev_happy)
        self.assertGreater(self.engine.dimensions["excitement"], prev_excite)

        # Chess start -> Tryhard competitive
        self.engine.apply_stimulus("chess_start", intensity=1.5)
        self.assertGreaterEqual(self.engine.dimensions["competitiveness"], 0.70)
        dom_key, _ = self.engine.get_dominant_mood()
        self.assertEqual(dom_key, "TRYHARD_COMPETITIVE")

        # Insult -> Sassy annoyed
        self.engine.reset_to_baseline()
        self.engine.apply_stimulus("insult", intensity=2.0)
        self.assertGreaterEqual(self.engine.dimensions["annoyance"], 0.50)
        dom_key, _ = self.engine.get_dominant_mood()
        self.assertIn(dom_key, ("SASSY_ANNOYED", "DRAMATIC_POUTY"))

        # Curiosity query
        self.engine.reset_to_baseline()
        self.engine.apply_stimulus("philosophical_query", intensity=2.0)
        self.assertGreaterEqual(self.engine.dimensions["curiosity"], 0.70)
        dom_key, _ = self.engine.get_dominant_mood()
        self.assertEqual(dom_key, "CURIOUS_PENSIVE")

    def test_temperature_modifier(self):
        self.engine.reset_to_baseline()
        base_temp = self.engine.get_temperature_modifier()
        
        # Highly excited -> higher temperature (more wild/spontaneous)
        self.engine.dimensions["excitement"] = 0.95
        self.engine.dimensions["curiosity"] = 0.90
        self.engine.dimensions["competitiveness"] = 0.10
        self.assertGreater(self.engine.get_temperature_modifier(), base_temp)

        # Highly competitive -> lower temperature (more deterministic/calculating)
        self.engine.dimensions["excitement"] = 0.10
        self.engine.dimensions["curiosity"] = 0.10
        self.engine.dimensions["competitiveness"] = 0.95
        self.assertLess(self.engine.get_temperature_modifier(), base_temp)

    def test_behavioral_directive(self):
        self.engine.reset_to_baseline()
        self.engine.apply_stimulus("chess_start", intensity=2.0)
        directive = self.engine.get_behavioral_directive()
        self.assertIn("Tryhard & Competitive", directive)
        self.assertIn("smug", directive.lower())

    def test_reset_to_baseline(self):
        self.engine.apply_stimulus("insult", intensity=2.0)
        self.engine.reset_to_baseline()
        self.assertAlmostEqual(self.engine.dimensions["annoyance"], 0.10, places=2)
        self.assertAlmostEqual(self.engine.dimensions["happiness"], 0.60, places=2)

    def test_get_emotional_valence(self):
        self.engine.reset_to_baseline()
        base_v = self.engine.get_emotional_valence()
        self.assertIn("valence", base_v)
        self.assertIn("arousal", base_v)
        self.assertGreaterEqual(base_v["valence"], -1.0)
        self.assertLessEqual(base_v["valence"], 1.0)

        self.engine.apply_stimulus("donation", intensity=1.5)
        happy_v = self.engine.get_emotional_valence()
        self.assertGreater(happy_v["valence"], base_v["valence"])

        self.engine.reset_to_baseline()
        self.engine.apply_stimulus("insult", intensity=2.0)
        annoyed_v = self.engine.get_emotional_valence()
        self.assertLess(annoyed_v["valence"], 0.0)

    def test_score_affective_memories_reranking(self):
        memories = [
            {"id": "neutral", "content": "Checked inventory", "score": 0.60, "valence": 0.0},
            {"id": "sad_angry", "content": "Lost all diamonds in lava", "score": 0.60, "valence": -0.85, "dominant_mood": "SASSY_ANNOYED"},
            {"id": "joyful", "content": "Won the chess match!", "score": 0.60, "valence": 0.85, "dominant_mood": "HYPE_EXCITED"},
        ]

        # Under excited/happy mood, joyful high-valence memory surfaces first
        self.engine.reset_to_baseline()
        self.engine.apply_stimulus("donation", intensity=1.5)
        ranked_happy = self.engine.score_affective_memories(memories)
        self.assertEqual(ranked_happy[0]["id"], "joyful")

        # Under annoyed/negative mood, negative-valence matching memory surfaces first
        self.engine.reset_to_baseline()
        self.engine.apply_stimulus("insult", intensity=2.0)
        ranked_annoyed = score_affective_memories(memories, self.engine.get_emotional_valence())
        self.assertEqual(ranked_annoyed[0]["id"], "sad_angry")


class TestMoodConversationIntegration(unittest.TestCase):
    def setUp(self):
        character = {
            "name": "Eve",
            "persona": "Sassy AI VTuber",
            "system_prompt": "You are Eve Maybe.",
            "mock_responses": {
                "default": ["[emotion: happy] Halo semua!"],
                "smug": ["[emotion: smug] Catur ini milikku!"],
                "sarcastic": ["[emotion: annoyed] Hadeh dasar noob."]
            }
        }
        self.conv = ConversationEngine(character)

    def test_chat_stimulus_applied_on_record(self):
        prev_happy = self.conv.mood.dimensions["happiness"]
        # Praise
        self.conv.record_incoming_chat("Alice", "Eve kamu cantik dan keren banget!")
        self.assertGreater(self.conv.mood.dimensions["happiness"], prev_happy)

        # Insult
        prev_annoy = self.conv.mood.dimensions["annoyance"]
        self.conv.record_incoming_chat("Troll", "Eve kamu bego banget dan noob main game")
        self.assertGreater(self.conv.mood.dimensions["annoyance"], prev_annoy)

    def test_system_prompt_includes_mood_directive(self):
        self.conv.mood.apply_stimulus("chess_start", intensity=2.0)
        prompt = self.conv.build_system_prompt("Bob", "Mau tanding catur?")
        self.assertIn("DYNAMIC INTERNAL MOOD & EMOTIONAL STATE", prompt)
        self.assertIn("Tryhard & Competitive", prompt)

    def test_mock_response_flavored_by_mood(self):
        self.conv.mood.apply_stimulus("chess_start", intensity=2.0)
        resp = self.conv.generate_mock_response("Bob", "Ayo main catur")
        self.assertTrue("smug" in resp or "catur" in resp or "menang" in resp)


class TestMoodBrainIntegration(unittest.TestCase):
    def setUp(self):
        self.brain = Brain("config/settings.json", "config/character.json")

    def test_brain_mood_property_and_state(self):
        self.assertIsNotNone(self.brain.mood)
        conv_state = self.brain.get_conversation_state()
        self.assertIn("mood", conv_state)
        self.assertIn("dominant_mood", conv_state["mood"])
        self.assertIn("dimensions", conv_state["mood"])


if __name__ == "__main__":
    unittest.main()
