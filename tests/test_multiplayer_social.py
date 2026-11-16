import unittest
import os
import shutil
from pathlib import Path
from core.minecraft.multiplayer.models import (
    TeamRole,
    PlayerContribution,
    Team,
    TradeProposal,
    GroupDiscussionTurn
)
from core.minecraft.multiplayer.contribution_ledger import ContributionLedger
from core.minecraft.multiplayer.team_manager import TeamManager
from core.minecraft.multiplayer.negotiation import NegotiationEngine
from core.minecraft.multiplayer.group_chat import GroupChatTracker
from core.minecraft.multiplayer.engine import MultiplayerSocialEngine
from core.conversation.engine import ConversationEngine
from core.brain import Brain


class TestMultiplayerModels(unittest.TestCase):
    def test_player_contribution_methods(self):
        p = PlayerContribution(player_name="TestHero")
        self.assertEqual(p.reputation, 75.0)

        # Donation
        p.add_donation("diamond", 2)
        self.assertEqual(p.items_donated.get("diamond"), 2)
        self.assertGreater(p.reputation, 75.0)

        # Combat help
        p.record_combat_help("Zombie")
        self.assertEqual(p.mobs_killed_for_team, 1)

        # PVP strike
        rep_before = p.reputation
        p.record_pvp_strike(5.0)
        self.assertEqual(p.times_attacked_eve, 1)
        self.assertLess(p.reputation, rep_before)

        # Serialization
        data = p.to_dict()
        p2 = PlayerContribution.from_dict(data)
        self.assertEqual(p2.player_name, "TestHero")
        self.assertEqual(p2.mobs_killed_for_team, 1)
        self.assertEqual(p2.times_attacked_eve, 1)

    def test_team_methods(self):
        team = Team(id="team_test", name="Test Squad", leader="EveMaybe")
        team.add_member("Alex", TeamRole.VANGUARD.value)
        self.assertIn("Alex", team.members)
        self.assertEqual(team.member_roles.get("Alex"), TeamRole.VANGUARD.value)

        # Serialization
        d = team.to_dict()
        t2 = Team.from_dict(d)
        self.assertEqual(t2.name, "Test Squad")
        self.assertIn("Alex", t2.members)

        team.remove_member("Alex")
        self.assertNotIn("Alex", team.members)

    def test_trade_and_chat_models(self):
        tr = TradeProposal(
            id="t1",
            proposer="Steve",
            offering={"iron_ingot": 8},
            requesting={"diamond": 1},
            status="accepted",
            eve_verdict="Deal adil!"
        )
        d_tr = tr.to_dict()
        tr2 = TradeProposal.from_dict(d_tr)
        self.assertEqual(tr2.proposer, "Steve")
        self.assertEqual(tr2.status, "accepted")

        turn = GroupDiscussionTurn(speaker="Alex", message="Siap ke Nether!")
        d_turn = turn.to_dict()
        turn2 = GroupDiscussionTurn.from_dict(d_turn)
        self.assertEqual(turn2.speaker, "Alex")


class TestContributionLedger(unittest.TestCase):
    def setUp(self):
        self.ledger = ContributionLedger()

    def test_default_seeded_members(self):
        self.assertIn("diamondhunter", self.ledger.players)
        self.assertIn("alex", self.ledger.players)
        self.assertIn("steve", self.ledger.players)
        self.assertIn("griefergarry", self.ledger.players)

        dh = self.ledger.players["diamondhunter"]
        self.assertEqual(dh.role_specialty, TeamRole.MINER.value)
        self.assertGreaterEqual(dh.reputation, 85.0)

    def test_record_donation_and_building(self):
        p = self.ledger.record_donation("PlayerX", "gold_ingot", 5)
        self.assertEqual(p.items_donated.get("gold_ingot"), 5)

        p2 = self.ledger.record_building_help("PlayerX", "Bikin Menara Pengawas")
        self.assertEqual(p2.structures_built, 1)
        self.assertIn("Menara Pengawas", p2.notes[-1])

    def test_fitness_evaluation_per_mission(self):
        # Mining expedition: Miner (DiamondHunter) should beat Vanguard (Alex)
        fit_dh_mining = self.ledger.evaluate_partner_fitness("DiamondHunter", "mining")
        fit_alex_mining = self.ledger.evaluate_partner_fitness("Alex", "mining")
        self.assertGreater(fit_dh_mining, fit_alex_mining)

        # Combat / Nether raid: Vanguard (Alex) should beat Miner (DiamondHunter)
        fit_alex_combat = self.ledger.evaluate_partner_fitness("Alex", "nether")
        fit_dh_combat = self.ledger.evaluate_partner_fitness("DiamondHunter", "nether")
        self.assertGreater(fit_alex_combat, fit_dh_combat)

        # Building: Builder (Steve) should beat others
        fit_steve_build = self.ledger.evaluate_partner_fitness("Steve", "building")
        self.assertGreater(fit_steve_build, 80.0)

        # Hostile player (GrieferGarry) should have very low fitness
        fit_garry = self.ledger.evaluate_partner_fitness("GrieferGarry", "mining")
        self.assertLess(fit_garry, 40.0)


class TestTeamManager(unittest.TestCase):
    def setUp(self):
        self.ledger = ContributionLedger()
        self.team_mgr = TeamManager()

    def test_default_squad(self):
        team = self.team_mgr.get_active_team()
        self.assertIsNotNone(team)
        self.assertEqual(team.name, "Squad Maybe ✨")
        self.assertIn("EveMaybe", team.members)
        self.assertIn("DiamondHunter", team.members)

    def test_partner_selection(self):
        best_cand, score, speech = self.team_mgr.select_expedition_partner("mining", self.ledger)
        self.assertEqual(best_cand, "DiamondHunter")
        self.assertGreater(score, 80.0)
        self.assertIn("DiamondHunter", speech)

        best_cand_combat, score_combat, speech_combat = self.team_mgr.select_expedition_partner("nether", self.ledger)
        self.assertEqual(best_cand_combat, "Alex")
        self.assertIn("Alex", speech_combat)


class TestNegotiationEngine(unittest.TestCase):
    def setUp(self):
        self.neg = NegotiationEngine()

    def test_fair_trade_acceptance(self):
        # 8 iron_ingot (8 * 10 = 80) for 1 diamond (80) -> 100% fair
        status, verdict, prop = self.neg.evaluate_incoming_trade(
            "Steve",
            offering={"iron_ingot": 8},
            requesting={"diamond": 1}
        )
        self.assertEqual(status, "accepted")
        self.assertIn("adil", verdict.lower())
        self.assertEqual(len(self.neg.proposals), 2)

    def test_borderline_counter_offer(self):
        # 4 iron (40) for 1 diamond (80) -> ratio 0.5 (between 0.4 and 0.85) -> countered
        status, verdict, prop = self.neg.evaluate_incoming_trade(
            "Steve",
            offering={"iron_ingot": 4},
            requesting={"diamond": 1}
        )
        self.assertEqual(status, "countered")
        self.assertIn("tambah", verdict.lower())

    def test_scam_ripoff_rejection(self):
        # 1 dirt (0.1) for 5 diamond (400) -> ratio 0.00025 -> rejected & roasted
        status, verdict, prop = self.neg.evaluate_incoming_trade(
            "GrieferGarry",
            offering={"dirt": 1},
            requesting={"diamond": 5}
        )
        self.assertEqual(status, "rejected")
        self.assertTrue(any(word in verdict.lower() for word in ["rugi", "scam", "nawar", "becanda", "lawak"]))

    def test_propose_community_trade(self):
        trade_callout = self.neg.propose_community_trade()
        self.assertIn("barter", trade_callout.lower())


class TestGroupChatTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = GroupChatTracker()

    def test_record_turns(self):
        self.tracker.turns = []
        turn, resp = self.tracker.record_turn("Alex", "Halo semua!")
        self.assertEqual(len(self.tracker.turns), 1)
        self.assertIsNone(resp)

    def test_group_consensus_nether_raid(self):
        self.tracker.record_turn("Alex", "Ayo siap-siap ke Nether cari blaze rod!")
        _, consensus_resp = self.tracker.record_turn("Steve", "Siap, aku bawa obsidian sama fire resist potion!")
        self.assertIsNotNone(consensus_resp)
        self.assertIn("Nether", consensus_resp)
        self.assertEqual(self.tracker.last_consensus_topic, "nether_raid")

    def test_group_consensus_mining(self):
        self.tracker.record_turn("DiamondHunter", "Gua di koordinat Y=-58 banyak redstone sama diamond.")
        _, consensus_resp = self.tracker.record_turn("Alex", "Ayo mining bareng di celah gua itu!")
        self.assertIsNotNone(consensus_resp)
        self.assertIn("mining", consensus_resp.lower())


class TestMultiplayerSocialEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path("data/test_mp_temp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.engine = MultiplayerSocialEngine(
            data_dir=str(self.temp_dir / "mp_data"),
            second_brain_dir=str(self.temp_dir / "second_brain")
        )

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_engine_state_and_directive(self):
        state = self.engine.get_state()
        self.assertEqual(state["selected_partner"], "DiamondHunter")
        self.assertEqual(state["active_team"]["name"], "Squad Maybe ✨")
        self.assertGreater(len(state["ledger"]), 0)

        directive = self.engine.get_prompt_directive()
        self.assertIn("MULTIPLAYER SOCIAL INTELLIGENCE & COMMUNITY SQUAD", directive)
        self.assertIn("Squad Maybe ✨", directive)
        self.assertIn("DiamondHunter", directive)

    def test_choose_partner_workflow(self):
        res = self.engine.choose_partner("nether")
        self.assertEqual(res["partner"], "Alex")
        self.assertEqual(self.engine.selected_partner, "Alex")
        self.assertEqual(self.engine.partner_mission, "nether")

    def test_process_in_game_chat_trade(self):
        resp = self.engine.process_in_game_chat("Steve", "Eve mau tukar 8 iron sama 1 diamond ga?")
        self.assertIsNotNone(resp)
        self.assertTrue(len(self.engine.negotiation.proposals) > 0)

    def test_sync_to_second_brain(self):
        self.engine.sync_to_second_brain()
        squad_file = self.temp_dir / "second_brain" / "teams" / "squad_maybe.md"
        comm_file = self.temp_dir / "second_brain" / "community" / "contributions.md"
        self.assertTrue(squad_file.exists())
        self.assertTrue(comm_file.exists())
        content = squad_file.read_text(encoding="utf-8")
        self.assertIn("Squad Maybe ✨", content)


class TestMultiplayerIntegration(unittest.TestCase):
    def setUp(self):
        self.brain = Brain()
        self.conv = self.brain.conversation

    def test_brain_exposure(self):
        self.assertIsNotNone(self.brain.multiplayer)
        state = self.brain.get_conversation_state()
        self.assertIn("multiplayer", state)
        self.assertEqual(state["multiplayer"]["selected_partner"], "DiamondHunter")

    def test_mock_conversation_queries(self):
        # Query squad info
        resp1 = self.conv.generate_mock_response("User", "gimana keadaan squad kita di minecraft?")
        self.assertIn("Squad Maybe ✨", resp1)

        # Query partner
        resp2 = self.conv.generate_mock_response("User", "siapa partner mining kamu?")
        self.assertIn("DiamondHunter", resp2)

        # Query barter
        resp3 = self.conv.generate_mock_response("User", "eve mau barter apa hari ini?")
        self.assertIn("barter", resp3.lower())


if __name__ == "__main__":
    unittest.main()
