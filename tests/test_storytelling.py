import unittest
import tempfile
from pathlib import Path

from core.storytelling.models import (
    StoryGenre,
    EveRole,
    CampaignStatus,
    StoryChoice,
    PartyState,
    DiceRollResult,
    StoryScene,
    CampaignSession
)
from core.storytelling.preset_campaigns import (
    PRESET_CAMPAIGNS,
    get_preset_campaign,
    create_initial_scene_from_preset
)
from core.storytelling.engine import StoryEngine
from core.brain import Brain
from core.conversation.engine import ConversationEngine


class TestStoryModels(unittest.TestCase):
    def test_story_choice_and_party_state(self):
        choice = StoryChoice(
            id="opt_1",
            label="Gelar Wol",
            description="Menyelinap",
            dc_check=10,
            stat_affinity="Agility"
        )
        choice.votes.append("PlayerOne")
        d = choice.to_dict()
        self.assertEqual(d["id"], "opt_1")
        self.assertEqual(d["vote_count"], 1)

        party = PartyState(hp=100, morale=80, gold=40, inventory=["Pedang"])
        party.apply_impact(hp_delta=-15, morale_delta=10, gold_delta=20, item_add="Perisai")
        self.assertEqual(party.hp, 85)
        self.assertEqual(party.morale, 90)
        self.assertEqual(party.gold, 60)
        self.assertIn("Perisai", party.inventory)

        # Test item removal and boundaries
        party.apply_impact(hp_delta=-200, item_remove="Pedang")
        self.assertEqual(party.hp, 0)
        self.assertNotIn("Pedang", party.inventory)

    def test_dice_roll_result_mechanics(self):
        res_crit = DiceRollResult(
            roller="Hero",
            d20_value=20,
            modifier=2,
            total=22,
            dc_target=15,
            is_critical_success=True,
            is_success=True,
            outcome_text="Natural 20!"
        )
        self.assertTrue(res_crit.is_critical_success)
        self.assertTrue(res_crit.is_success)

        res_fail = DiceRollResult(
            roller="Noob",
            d20_value=1,
            modifier=0,
            total=1,
            dc_target=10,
            is_critical_fail=True,
            is_success=False,
            outcome_text="Natural 1!"
        )
        self.assertTrue(res_fail.is_critical_fail)
        self.assertFalse(res_fail.is_success)

        d = res_crit.to_dict()
        self.assertEqual(d["d20_value"], 20)
        self.assertIn("timestamp_str", d)


class TestPresetCampaigns(unittest.TestCase):
    def test_presets_exist_and_load(self):
        self.assertIn("petualangan_netherite", PRESET_CAMPAIGNS)
        self.assertIn("heist_neo_jakarta", PRESET_CAMPAIGNS)
        self.assertIn("guild_petualang_noob", PRESET_CAMPAIGNS)

        sc = create_initial_scene_from_preset("petualangan_netherite")
        self.assertIsInstance(sc, StoryScene)
        self.assertTrue(len(sc.title) > 0)
        self.assertTrue(len(sc.choices) >= 2)
        self.assertTrue(sc.requires_dice_roll)


class TestStoryEngine(unittest.TestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.test_dir = Path(self._temp_dir_obj.name)
        self.engine = StoryEngine(data_dir=str(self.test_dir))

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    def test_campaign_lifecycle_and_choices(self):
        # Start campaign
        sess, speech = self.engine.start_campaign("petualangan_netherite")
        self.assertEqual(sess.status, CampaignStatus.VOTING.value)
        self.assertIn("Misteri Mahkota Netherite", sess.title)
        self.assertIn("Petualangan RPG Dimulai", speech)

        # Chat vote choice 1
        res_v1 = self.engine.process_chat_input("ViewerA", "!1")
        self.assertIsNotNone(res_v1)
        self.assertTrue(res_v1[0])
        self.assertIn("ViewerA", sess.current_scene.choices[0].votes)

        # Chat vote choice 2
        res_v2 = self.engine.process_chat_input("ViewerB", "!2")
        self.assertIsNotNone(res_v2)
        self.assertTrue(res_v2[0])
        self.assertIn("ViewerB", sess.current_scene.choices[1].votes)

        # Freeform action proposal
        res_act = self.engine.process_chat_input("CreativeUser", "!action lempar kembang api ke langit-langit")
        self.assertIsNotNone(res_act)
        self.assertTrue(res_act[0])
        self.assertEqual(len(sess.freeform_suggestions), 1)

        # Dice roll command
        res_roll = self.engine.process_chat_input("DiceMaster", "!roll")
        self.assertIsNotNone(res_roll)
        self.assertTrue(res_roll[0])
        self.assertIsNotNone(sess.last_dice_roll)

        # Advance scene
        next_sc, adv_speech = self.engine.advance_scene()
        self.assertIsNotNone(next_sc)
        self.assertEqual(len(sess.scenes_history), 1)
        self.assertIn("Babak", next_sc.title)

        # Conclude campaign
        end_sess, end_speech = self.engine.end_campaign()
        self.assertEqual(end_sess.status, CampaignStatus.COMPLETED.value)
        self.assertTrue(len(self.engine.campaigns_history) >= 1)
        self.assertIn("PETUALANGAN SELESAI", end_speech)

    def test_dice_roll_mechanics(self):
        self.engine.start_campaign("heist_neo_jakarta")
        res, speech = self.engine.roll_dice(roller="TestRoller", dc_target=10, stat_type="Agility")
        self.assertIsInstance(res, DiceRollResult)
        self.assertTrue(1 <= res.d20_value <= 20)
        self.assertTrue(
            any(tok in speech for tok in ("D20", "NATURAL 20", "NATURAL 1")),
            f"Unexpected dice roll speech: {speech}",
        )

    def test_second_brain_sync(self):
        self.engine.start_campaign("guild_petualang_noob")
        f_path = self.test_dir / "second_brain" / "storytelling" / "campaigns.md"
        self.assertTrue(f_path.exists())
        content = f_path.read_text(encoding="utf-8")
        self.assertIn("Dynamic Storytelling & Community Roleplay Chronicles", content)
        self.assertIn("Guild Petualang Noob", content)


class TestStoryBrainIntegration(unittest.TestCase):
    def test_brain_exposure_and_mock(self):
        brain = Brain()
        self.assertIsNotNone(brain.storytelling)
        state = brain.get_conversation_state()
        self.assertIn("storytelling", state)
        self.assertIn("session", state["storytelling"])

        # System prompt directive check
        engine = brain.conversation
        prompt = engine.build_system_prompt("Creator")
        self.assertIn("STORYTELLING", prompt)

        # Mock conversation query response
        resp = engine.generate_mock_response("Gamer", "Ayo kita main petualangan RPG di Minecraft!")
        self.assertIn("Petualangan RPG", resp)


if __name__ == "__main__":
    unittest.main()
