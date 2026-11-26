import unittest
import os
import tempfile
from pathlib import Path

from core.minigames.models import (
    MiniGameType,
    GameStatus,
    PlayerScore,
    TriviaQuestion,
    RiddleItem,
    WouldYouRatherItem,
    SongQuizItem,
    MiniGameSession
)
from core.minigames.game_catalog import GameCatalog
from core.minigames.engine import MiniGameEngine
from core.brain import Brain
from core.conversation.engine import ConversationEngine


class TestMiniGameModels(unittest.TestCase):
    def test_player_score_mechanics(self):
        player = PlayerScore(username="Tester", score=50, correct_answers=4, games_won=1, streak=2)
        self.assertEqual(player.username, "Tester")
        
        # Test add points with streak
        player.add_points(10)
        self.assertEqual(player.score, 60)
        self.assertEqual(player.correct_answers, 5)
        self.assertEqual(player.streak, 3)

        # Test reset streak
        player.reset_streak()
        self.assertEqual(player.streak, 0)

        # Test serialization
        d = player.to_dict()
        self.assertEqual(d["username"], "Tester")
        self.assertEqual(d["score"], 60)
        restored = PlayerScore.from_dict(d)
        self.assertEqual(restored.username, "Tester")
        self.assertEqual(restored.score, 60)

    def test_session_lifecycle_models(self):
        sess = MiniGameSession(
            game_type=MiniGameType.TRIVIA.value,
            status=GameStatus.ACTIVE.value,
            total_rounds=3
        )
        self.assertEqual(sess.game_type, "trivia")
        self.assertEqual(sess.round_number, 1)
        self.assertTrue(sess.get_remaining_seconds() <= 35)

        d = sess.to_dict()
        self.assertEqual(d["game_type"], "trivia")
        self.assertEqual(d["status"], "active")


class TestGameCatalog(unittest.TestCase):
    def setUp(self):
        self.catalog = GameCatalog()

    def test_trivia_generation(self):
        t = self.catalog.get_random_trivia()
        self.assertIsInstance(t, TriviaQuestion)
        self.assertTrue(len(t.question) > 5)
        self.assertTrue(any(opt.startswith("A)") for opt in t.options))
        self.assertTrue(any(opt.startswith("B)") for opt in t.options))
        self.assertIn(t.correct_index, [0, 1, 2, 3])

    def test_riddle_generation(self):
        r = self.catalog.get_random_riddle()
        self.assertIsInstance(r, RiddleItem)
        self.assertTrue(len(r.riddle) > 5)
        self.assertTrue(len(r.accepted_keywords) > 0)
        self.assertTrue(len(r.hints) > 0)
        self.assertTrue(len(r.answer) > 0)

    def test_would_you_rather_generation(self):
        w = self.catalog.get_random_would_you_rather()
        self.assertIsInstance(w, WouldYouRatherItem)
        self.assertTrue(len(w.option_a) > 3)
        self.assertTrue(len(w.option_b) > 3)

    def test_song_quiz_generation(self):
        s = self.catalog.get_random_song_quiz()
        self.assertIsInstance(s, SongQuizItem)
        self.assertTrue(len(s.title) > 0)
        self.assertTrue(len(s.clue_lyrics) > 0)

    def test_word_association_theme(self):
        theme, start_w = self.catalog.get_word_association_theme()
        bank = self.catalog.get_word_bank(theme)
        self.assertTrue(len(theme) > 0)
        self.assertTrue(len(bank) > 5)
        self.assertIn(start_w, bank)


class TestMiniGameEngine(unittest.TestCase):
    def setUp(self):
        self._temp_dir_obj = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.test_dir = Path(self._temp_dir_obj.name)
        self.engine = MiniGameEngine(data_dir=str(self.test_dir))

    def tearDown(self):
        self._temp_dir_obj.cleanup()

    def test_trivia_flow(self):
        # Start game
        sess, speech = self.engine.start_game(game_type="trivia", total_rounds=2)
        self.assertEqual(sess.status, GameStatus.ACTIVE.value)
        self.assertIn("TRIVIA QUIZ", speech)

        q = sess.current_challenge
        correct_letter = chr(ord('A') + q["correct_index"])
        wrong_letter = "A" if correct_letter != "A" else "B"

        # Wrong answer test
        res_wrong = self.engine.process_chat_input("ViewerBob", f"aku rasa {wrong_letter}")
        self.assertIsNotNone(res_wrong)
        self.assertFalse(res_wrong[0])

        # Correct answer test
        res_correct = self.engine.process_chat_input("ViewerAlice", f"menurutku {correct_letter}")
        self.assertIsNotNone(res_correct)
        self.assertTrue(res_correct[0])
        self.assertEqual(sess.round_winner, "ViewerAlice")
        self.assertEqual(sess.status, GameStatus.ROUND_END.value)

        # Next round
        sess, speech = self.engine.next_round()
        self.assertEqual(sess.round_number, 2)
        self.assertEqual(sess.status, GameStatus.ACTIVE.value)

    def test_guess_number_flow(self):
        sess, _ = self.engine.start_game(game_type="guess_number", total_rounds=1)
        target = sess.target_number

        # Guess too low
        if target > 1:
            res_low = self.engine.process_chat_input("Guesser1", "1")
            self.assertIsNotNone(res_low)
            self.assertFalse(res_low[0])
            self.assertIn("RENDAH", res_low[1])

        # Guess too high
        if target < 100:
            res_high = self.engine.process_chat_input("Guesser2", "100")
            self.assertIsNotNone(res_high)
            self.assertFalse(res_high[0])
            self.assertIn("TINGGI", res_high[1])

        # Exact guess
        res_exact = self.engine.process_chat_input("Guesser3", f"jawabannya {target} dong!")
        self.assertIsNotNone(res_exact)
        self.assertTrue(res_exact[0])
        self.assertEqual(sess.status, GameStatus.ROUND_END.value)

    def test_would_you_rather_voting(self):
        sess, _ = self.engine.start_game(game_type="would_you_rather", total_rounds=1)
        
        # User 1 votes A
        res_a = self.engine.process_chat_input("Voter1", "!A")
        self.assertIsNotNone(res_a)
        self.assertTrue(res_a[0])
        self.assertEqual(sess.voters.get("Voter1"), "A")

        # User 2 votes B
        res_b = self.engine.process_chat_input("Voter2", "pilih opsi B")
        self.assertIsNotNone(res_b)
        self.assertTrue(res_b[0])
        self.assertEqual(sess.voters.get("Voter2"), "B")

        # Vote update: User 1 changes mind to B
        res_change = self.engine.process_chat_input("Voter1", "!B")
        self.assertIsNotNone(res_change)
        self.assertEqual(sess.voters.get("Voter1"), "B")

        # Percentages check
        pcts = sess._calculate_poll_percentages()
        self.assertEqual(pcts["A"], 0.0)
        self.assertEqual(pcts["B"], 100.0)

    def test_riddle_and_hints(self):
        sess, _ = self.engine.start_game(game_type="riddle", total_rounds=1)
        
        # Request hint
        hint = self.engine.request_hint()
        self.assertTrue(len(hint) > 0)
        self.assertIn(hint, sess.revealed_hints)

        # Guess wrong riddle
        res_wrong = self.engine.process_chat_input("Thinker1", "kuda nil terbang")
        self.assertIsNotNone(res_wrong)
        self.assertFalse(res_wrong[0])

        # Guess correct answer
        keywords = sess.current_challenge["accepted_keywords"]
        target = keywords[0]
        res_right = self.engine.process_chat_input("Thinker2", f"jawabannya pasti {target}!")
        self.assertIsNotNone(res_right)
        self.assertTrue(res_right[0])
        self.assertEqual(sess.status, GameStatus.ROUND_END.value)

    def test_word_association_chain(self):
        sess, _ = self.engine.start_game(game_type="word_association", total_rounds=1)
        theme = sess.active_theme
        bank = GameCatalog.get_word_bank(theme)
        chain = sess.word_chain
        
        # Pick word from bank not in chain
        valid_words = [w for w in bank if w.lower() not in [c.lower() for c in chain]]
        if valid_words:
            next_word = valid_words[0]
            res = self.engine.process_chat_input("WordMaster", f"{next_word}")
            self.assertIsNotNone(res)
            self.assertTrue(res[0])
            self.assertIn(next_word.lower(), [w.lower() for w in sess.word_chain])

    def test_second_brain_sync(self):
        self.engine.start_game("trivia", 1)
        f_path = self.test_dir / "second_brain" / "minigames" / "leaderboard.md"
        self.assertTrue(f_path.exists())
        content = f_path.read_text(encoding="utf-8")
        self.assertIn("Hall of Fame", content)
        self.assertIn("Top Audience Champions", content)


class TestMiniGameBrainIntegration(unittest.TestCase):
    def test_brain_exposure_and_prompt(self):
        brain = Brain()
        self.assertIsNotNone(brain.minigames)
        state = brain.get_conversation_state()
        self.assertIn("minigames", state)
        self.assertIn("session", state["minigames"])

        engine = brain.conversation
        self.assertIsInstance(engine, ConversationEngine)
        prompt = engine.build_system_prompt(current_user="Creator")
        self.assertIn("INTERACTIVE MINI-GAME", prompt)


if __name__ == "__main__":
    unittest.main()
