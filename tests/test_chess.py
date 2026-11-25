import unittest
import asyncio
import chess
from unittest.mock import AsyncMock
from core.chess.chess_engine import ChessEngine
from core.chess.chess_agent import ChessAgent
from core.chess.controller import ChessController
from core.conversation.chat_curator import ChatCurator
from core.orchestrator import Orchestrator

class TestChessEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ChessEngine(elo=1200)

    def test_initial_state(self):
        self.assertEqual(self.engine.elo, 1200)
        self.assertEqual(self.engine.board.fen(), chess.STARTING_FEN)
        state = self.engine.get_game_state()
        self.assertEqual(state["turn"], "white")
        self.assertFalse(state["is_game_over"])
        self.assertEqual(len(state["legal_moves"]), 20)

    def test_elo_scaling(self):
        # Test low ELO
        self.engine.set_elo(600)
        depth, blunder = self.engine.get_search_depth_and_blunder_chance()
        self.assertEqual(depth, 1)
        self.assertGreater(blunder, 0.4)

        # Test high ELO
        self.engine.set_elo(2200)
        depth, blunder = self.engine.get_search_depth_and_blunder_chance()
        self.assertEqual(depth, 4)
        self.assertEqual(blunder, 0.0)

    def test_make_move_uci_and_san(self):
        # 1. e4 (via UCI)
        success, move, san = self.engine.make_move_san_or_uci("e2e4")
        self.assertTrue(success)
        self.assertEqual(san, "e4")

        # 1... e5 (via SAN)
        success, move, san = self.engine.make_move_san_or_uci("e5")
        self.assertTrue(success)
        self.assertEqual(san, "e5")

        # Illegal move
        success, move, err = self.engine.make_move_san_or_uci("e4e5")
        self.assertFalse(success)

    def test_choose_move_generates_legal_move(self):
        self.engine.set_elo(1400)
        move = self.engine.choose_move()
        self.assertIsNotNone(move)
        self.assertIn(move, self.engine.board.legal_moves)

    def test_evaluation(self):
        # Starting position evaluation is roughly equal
        eval_score = self.engine.evaluate_board()
        self.assertIsInstance(eval_score, int)
        self.assertLess(abs(eval_score), 50)


class TestChessAgent(unittest.TestCase):
    def setUp(self):
        self.agent = ChessAgent(bot_name="EveMaybe")

    def test_commentary_generation(self):
        start_speech = self.agent.on_game_start(elo=1400, player_name="Creator", eve_color="black")
        self.assertIn("Creator", start_speech)
        self.assertIn("1400", start_speech)

        elo_speech = self.agent.on_elo_changed(1800)
        self.assertIn("1800", elo_speech)

        bot_move_speech = self.agent.on_bot_move(san="Nf3", is_check=False, is_capture=False)
        self.assertIn("Nf3", bot_move_speech)

        check_speech = self.agent.on_bot_move(san="Qh5+", is_check=True, is_capture=False)
        self.assertTrue("skak" in check_speech.lower() or "check" in check_speech.lower())

        queen_capture_speech = self.agent.on_bot_move(san="Qxd8", is_check=False, is_capture=True, is_queen_capture=True)
        self.assertTrue("queen" in queen_capture_speech.lower() or "menteri" in queen_capture_speech.lower() or "ratu" in queen_capture_speech.lower())


class TestChessController(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.controller = ChessController(bot_name="EveMaybe", default_elo=1000)
        self.commentary_log = []
        self.state_log = []

        self.controller.set_callbacks(
            on_commentary=lambda s: self.commentary_log.append(s),
            on_state_change=lambda st: self.state_log.append(st)
        )

    async def test_game_flow(self):
        # Start game with Player as White
        intro = await self.controller.start_game(player_name="Evan", player_color="white", elo=1200)
        self.assertTrue(self.controller.is_active)
        self.assertEqual(self.controller.engine.elo, 1200)
        self.assertGreater(len(self.commentary_log), 0)
        self.assertGreater(len(self.state_log), 0)

        # Player moves e2e4
        success, san = await self.controller.make_player_move("e2e4")
        self.assertTrue(success)
        self.assertEqual(san, "e4")

        # Wait for delayed bot move
        await asyncio.sleep(0.8)
        self.assertEqual(len(self.controller.engine.move_history), 2)

        # Set ELO mid-game
        await self.controller.set_elo(1800)
        self.assertEqual(self.controller.engine.elo, 1800)

        # Resign
        resign_speech = await self.controller.resign_game()
        self.assertFalse(self.controller.is_active)
        self.assertIn("Evan", resign_speech)


class TestChessOrchestration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.orchestrator = Orchestrator()
        self.orchestrator.tts.speak = AsyncMock()
        self.received_events = []
        self.orchestrator.register_listener(lambda e: self.received_events.append(e))

    async def asyncTearDown(self):
        await self.orchestrator.shutdown()

    async def test_chess_commands(self):
        # 1. Start game via chat command
        await self.orchestrator.chat.put_message(user="Admin", text="!chess new", source="creator")
        # Process 1 iteration of curator/chat
        msg = await self.orchestrator.chat.get_next_message()
        await self.orchestrator._ingest_message(msg)
        interaction = self.orchestrator.brain.conversation.select_next_interaction()
        self.assertIsNotNone(interaction)
        await self.orchestrator._execute_interaction(interaction)

        self.assertTrue(self.orchestrator.chess.is_active)
        self.assertEqual(self.orchestrator.chess.player_name, "Admin")

        # 2. Change ELO via chat command
        await self.orchestrator.chat.put_message(user="Admin", text="!chess elo 1500", source="creator")
        msg = await self.orchestrator.chat.get_next_message()
        await self.orchestrator._ingest_message(msg)
        interaction = self.orchestrator.brain.conversation.select_next_interaction()
        await self.orchestrator._execute_interaction(interaction)
        self.assertEqual(self.orchestrator.chess.engine.elo, 1500)

        # 3. Make move via chat command
        await self.orchestrator.chat.put_message(user="Admin", text="!chess move e2e4", source="creator")
        msg = await self.orchestrator.chat.get_next_message()
        await self.orchestrator._ingest_message(msg)
        interaction = self.orchestrator.brain.conversation.select_next_interaction()
        await self.orchestrator._execute_interaction(interaction)
        self.assertEqual(self.orchestrator.chess.engine.move_history[0], "e4")

    async def test_admin_username_on_web_source_is_not_creator(self):
        curator = ChatCurator()
        queued_msg = curator.add_message("Admin", "!chess elo 2500", source="web", is_creator=None)
        self.assertFalse(queued_msg.is_creator)

        initial_elo = self.orchestrator.chess.engine.elo
        await self.orchestrator.chat.put_message(
            user="Admin", text="!chess elo 2500", source="web", is_creator=None
        )
        msg = await self.orchestrator.chat.get_next_message()
        self.assertFalse(msg.is_creator)
        await self.orchestrator._ingest_message(msg)
        interaction = self.orchestrator.brain.conversation.select_next_interaction()
        self.assertIsNotNone(interaction)
        self.assertFalse(interaction.primary_message.is_creator)
        await self.orchestrator._execute_interaction(interaction)

        self.orchestrator.tts.speak.assert_called()
        last_speech = self.orchestrator.tts.speak.call_args[0][0]
        self.assertIn("cuma Creator yang berhak atur level ELO", last_speech)
        self.assertEqual(self.orchestrator.chess.engine.elo, initial_elo)

if __name__ == "__main__":
    unittest.main()
