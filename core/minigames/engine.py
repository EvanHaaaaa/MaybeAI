import re
import json
import time
import random
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from core.minigames.models import (
    MiniGameType,
    GameStatus,
    PlayerScore,
    MiniGameSession,
    TriviaQuestion,
    RiddleItem,
    WouldYouRatherItem,
    SongQuizItem
)
from core.minigames.game_catalog import GameCatalog


class MiniGameEngine:
    """
    Interactive Mini-Game Engine for Eve Maybe.
    Empowers audience participation via Twitch/Web chat:
    Trivia, Guess the Number, Word Association, Riddles,
    Would You Rather polls, and Guess the Song.
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        second_brain_dir: str = "data/second_brain",
        data_dir: Optional[str] = None
    ):
        if storage_path is None:
            if data_dir:
                storage_path = str(Path(data_dir) / "leaderboard.json")
            else:
                storage_path = "data/minigames/leaderboard.json"

        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if data_dir and second_brain_dir == "data/second_brain":
            self.second_brain_dir = Path(data_dir) / "second_brain"
        else:
            self.second_brain_dir = Path(second_brain_dir)

        self.session: MiniGameSession = MiniGameSession()
        self.leaderboard: Dict[str, PlayerScore] = {}
        self.game_event_log: List[Dict[str, Any]] = []

        self._load_or_seed()
        self.sync_to_second_brain()

    def _load_or_seed(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for u, s_data in data.get("players", {}).items():
                        self.leaderboard[u.lower()] = PlayerScore.from_dict(s_data)
            except Exception as e:
                print(f"[MiniGameEngine] Error loading leaderboard: {e}")
        else:
            self._seed_default_leaderboard()
        self.save()

    def _seed_default_leaderboard(self):
        self.leaderboard = {
            "diamondhunter": PlayerScore("DiamondHunter", score=120, correct_answers=9, games_won=3, streak=2),
            "alex": PlayerScore("Alex", score=95, correct_answers=7, games_won=2, streak=1),
            "steve": PlayerScore("Steve", score=80, correct_answers=6, games_won=1, streak=0),
            "creator": PlayerScore("Creator", score=150, correct_answers=11, games_won=4, streak=3)
        }

    def save(self):
        try:
            data = {
                "players": {u: p.to_dict() for u, p in self.leaderboard.items()}
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[MiniGameEngine] Error saving leaderboard: {e}")

    def get_or_create_player(self, username: str) -> PlayerScore:
        clean = username.strip() or "Chatter"
        key = clean.lower()
        if key not in self.leaderboard:
            self.leaderboard[key] = PlayerScore(username=clean)
        return self.leaderboard[key]

    # --- Game Lifecycle ---
    def start_game(
        self,
        game_type: str = MiniGameType.TRIVIA.value,
        total_rounds: int = 3,
        time_limit_sec: int = 35
    ) -> Tuple[MiniGameSession, str]:
        """Starts a fresh interactive minigame session."""
        clean_type = game_type.strip().lower()
        if clean_type not in [t.value for t in MiniGameType]:
            clean_type = MiniGameType.TRIVIA.value

        self.session = MiniGameSession(
            game_type=clean_type,
            status=GameStatus.ACTIVE.value,
            round_number=1,
            total_rounds=max(1, total_rounds),
            time_limit_sec=time_limit_sec,
            started_at=time.time(),
            expires_at=time.time() + time_limit_sec
        )

        self._setup_round()

        # Host greeting based on game mode
        g_name = clean_type.replace('_', ' ').title()
        if clean_type == MiniGameType.TRIVIA.value:
            speech = (
                f"[emotion: excited] Mini-Game Dimulai: TRIVIA QUIZ! [action: wink] "
                f"Ronde 1/{self.session.total_rounds}: Jawab di chat dengan A, B, C, atau D! Siapa paling cepat dan tepat?!"
            )
        elif clean_type == MiniGameType.GUESS_NUMBER.value:
            speech = (
                f"[emotion: smug] Mini-Game: GUESS THE NUMBER! Aku sudah memikirkan sebuah angka rahasia antara 1 sampai 100. "
                f"Tebak di chat sekarang, nanti Eve kasih tahu ketinggian atau kerendahan! [action: giggle]"
            )
        elif clean_type == MiniGameType.WOULD_YOU_RATHER.value:
            speech = (
                f"[emotion: happy] Waktunya WOULD YOU RATHER! Ketik '!A' atau '!B' di chat untuk voting pilihan kalian. "
                f"Setelah polling selesai, Eve bakal kasih hot take pedas! [action: wink]"
            )
        elif clean_type == MiniGameType.RIDDLE.value:
            speech = (
                f"[emotion: smug] Waktunya TEKA-TEKI ASAH OTAK (Riddle)! Dengarkan baik-baik dan tebak jawabannya di chat. "
                f"Kalau bingung, kalian bisa minta hint ke Eve! [action: wink]"
            )
        elif clean_type == MiniGameType.WORD_ASSOCIATION.value:
            theme = self.session.active_theme
            start_w = self.session.word_chain[0] if self.session.word_chain else "Start"
            speech = (
                f"[emotion: excited] ASOSIASI KATA aktif! Tema kita: **{theme}**. "
                f"Kata pembuka dari Eve: '{start_w}'. Balas dengan kata yang berasosiasi di chat! [action: wink]"
            )
        elif clean_type == MiniGameType.GUESS_SONG.value:
            speech = (
                f"[emotion: excited] TEBAK LAGU (Guess the Song)! Dengarkan penggalan lirik atau petunjuk dari Eve, "
                f"lalu tebak judul lagunya di chat! [action: wink]"
            )
        else:
            speech = f"[emotion: happy] Mini-Game {g_name} dimulai! Ayo chat, tunjukkan kemampuan kalian! [action: wink]"

        self.session.host_speech = speech
        self._log_event("game_started", {"game_type": clean_type, "speech": speech})
        return self.session, speech

    def _setup_round(self):
        """Initializes challenges and states for the active round."""
        g_type = self.session.game_type
        self.session.round_attempts = []
        self.session.round_winner = None
        self.session.round_correct_answer = None
        self.session.revealed_hints = []
        self.session.expires_at = time.time() + self.session.time_limit_sec

        if g_type == MiniGameType.TRIVIA.value:
            triv = GameCatalog.get_random_trivia()
            self.session.current_challenge = triv.to_dict()
            self.session.round_correct_answer = triv.options[triv.correct_index]

        elif g_type == MiniGameType.GUESS_NUMBER.value:
            self.session.min_number = 1
            self.session.max_number = 100
            self.session.target_number = random.randint(1, 100)
            self.session.last_guess_feedback = "Tebak angka antara 1 sampai 100!"
            self.session.last_guess_val = None
            self.session.current_challenge = {
                "instruction": "Tebak angka rahasia Eve antara 1 - 100!",
                "range": [1, 100]
            }

        elif g_type == MiniGameType.WOULD_YOU_RATHER.value:
            wyr = GameCatalog.get_random_would_you_rather()
            self.session.current_challenge = wyr.to_dict()
            self.session.poll_votes = {"A": 0, "B": 0}
            self.session.voters = {}

        elif g_type == MiniGameType.RIDDLE.value:
            rid = GameCatalog.get_random_riddle()
            self.session.current_challenge = rid.to_dict()
            self.session.round_correct_answer = rid.answer

        elif g_type == MiniGameType.WORD_ASSOCIATION.value:
            theme, seed_word = GameCatalog.get_word_association_theme()
            self.session.active_theme = theme
            self.session.word_chain = [seed_word]
            self.session.current_challenge = {
                "theme": theme,
                "current_word": seed_word,
                "streak": 0
            }

        elif g_type == MiniGameType.GUESS_SONG.value:
            song = GameCatalog.get_random_song_quiz()
            self.session.current_challenge = song.to_dict()
            self.session.round_correct_answer = f"{song.title} - {song.artist}"

    def next_round(self) -> Tuple[MiniGameSession, str]:
        """Advances to the next round or concludes the game."""
        if self.session.status != GameStatus.ACTIVE.value and self.session.status != GameStatus.ROUND_END.value:
            return self.session, "Tidak ada permainan aktif untuk dilanjutkan."

        if self.session.round_number >= self.session.total_rounds:
            return self.stop_game()

        self.session.round_number += 1
        self.session.status = GameStatus.ACTIVE.value
        self._setup_round()

        speech = (
            f"[emotion: excited] Masuk ke Ronde {self.session.round_number}/{self.session.total_rounds}! "
            f"Fokus ya chat, tantangan baru sudah siap! [action: wink]"
        )
        self.session.host_speech = speech
        self._log_event("round_started", {"round": self.session.round_number})
        return self.session, speech

    def stop_game(self) -> Tuple[MiniGameSession, str]:
        """Concludes the minigame and declares winners."""
        self.session.status = GameStatus.GAME_OVER.value
        self.session.expires_at = 0.0

        top_players = self.get_leaderboard(limit=3)
        if top_players:
            winner = top_players[0]
            winner.games_won += 1
            speech = (
                f"[emotion: happy] Permainan SELESAI! 🎉 Selamat kepada {winner.username} "
                f"sebagai juara dengan total {winner.score} poin! Chat lain jangan berkecil hati, kalian main keren banget hari ini! [action: wink]"
            )
        else:
            speech = "[emotion: happy] Permainan selesai! Terima kasih sudah seru-seruan bareng Eve! [action: wink]"

        self.session.host_speech = speech
        self.save()
        self.sync_to_second_brain()
        self._log_event("game_over", {"speech": speech})
        return self.session, speech

    # --- Chat Turn Processing ---
    def process_chat_input(self, user: str, message: str) -> Optional[Tuple[bool, str]]:
        """
        Processes an incoming chat message against the active mini-game.
        Returns (is_handled, host_reaction_speech) or None if ignored.
        """
        if self.session.status != GameStatus.ACTIVE.value:
            return None

        # Check timeout
        if self.session.is_expired():
            return self._handle_round_timeout()

        clean_msg = message.strip()
        msg_lower = clean_msg.lower()
        g_type = self.session.game_type
        player = self.get_or_create_player(user)

        # 1. TRIVIA QUIZ
        if g_type == MiniGameType.TRIVIA.value:
            triv = self.session.current_challenge
            if not triv:
                return None

            # Detect option answer: A, B, C, D or !A, !B or full text match
            opt_chosen = None
            opt_match = re.search(r'\b([A-Da-d])\b', msg_lower)
            if opt_match:
                opt_chosen = opt_match.group(1).upper()
            elif triv.get("correct_answer_text", "").lower() in msg_lower:
                opt_chosen = chr(ord('A') + triv.get("correct_index", 0))

            if not opt_chosen:
                return None

            correct_letter = chr(ord('A') + triv.get("correct_index", 0))
            is_correct = (opt_chosen == correct_letter)

            self.session.round_attempts.append({
                "user": user,
                "choice": opt_chosen,
                "is_correct": is_correct,
                "time": time.strftime("%H:%M:%S")
            })

            if is_correct:
                pts = triv.get("points", 10)
                player.add_points(pts)
                self.session.chat_score += pts
                self.session.round_winner = user
                self.session.status = GameStatus.ROUND_END.value

                speech = (
                    f"[emotion: happy] TEPAT SEKALI! 🎉 {user} berhasil menjawab {correct_letter} ({triv.get('correct_answer_text')})! "
                    f"+{pts} poin buat kamu! {triv.get('explanation', '')} [action: wink]"
                )
                self.session.host_speech = speech
                self.save()
                self._log_event("trivia_win", {"user": user, "points": pts, "round": self.session.round_number})
                return True, speech
            else:
                player.reset_streak()
                # Occasional playful roast on wrong answer
                roasts = [
                    f"[emotion: smug] Yaaah salah {user}! Pilihan {opt_chosen} kurang tepat, ayo yang lain coba lagi! [action: giggle]",
                    f"[emotion: surprised] Waduh {user}, yakin pilih {opt_chosen}? Bukan itu jawabannya! [action: shrug]"
                ]
                return False, random.choice(roasts)

        # 2. GUESS THE NUMBER
        elif g_type == MiniGameType.GUESS_NUMBER.value:
            # Find integers in message
            num_match = re.search(r'\b(\d{1,3})\b', clean_msg)
            if not num_match:
                return None

            guess = int(num_match.group(1))
            target = self.session.target_number
            self.session.last_guess_val = guess

            self.session.round_attempts.append({
                "user": user,
                "guess": guess,
                "time": time.strftime("%H:%M:%S")
            })

            if guess == target:
                pts = 20
                player.add_points(pts)
                self.session.chat_score += pts
                self.session.round_winner = user
                self.session.status = GameStatus.ROUND_END.value
                self.session.last_guess_feedback = f"BINGOOO! 🎉 {user} menebak tepat: {target}!"

                speech = (
                    f"[emotion: excited] BINGO! 🎉 Angka rahasia Eve adalah **{target}**! "
                    f"Selamat {user}, tebakanmu luar biasa jitu! +{pts} poin masuk ke kantongmu! [action: wink]"
                )
                self.session.host_speech = speech
                self.save()
                self._log_event("guess_number_win", {"user": user, "number": target})
                return True, speech

            elif guess > target:
                self.session.max_number = min(self.session.max_number, guess - 1)
                self.session.last_guess_feedback = f"{guess} Terlalu TINGGI ⬇️"
                speech = f"[emotion: smug] {guess} masih terlalu TINGGI, {user}! Coba angka yang lebih kecil! [action: wink]"
                return False, speech

            else:
                self.session.min_number = max(self.session.min_number, guess + 1)
                self.session.last_guess_feedback = f"{guess} Terlalu RENDAH ⬆️"
                speech = f"[emotion: happy] {guess} masih terlalu RENDAH, {user}! Naikkin lagi angkanya! [action: wink]"
                return False, speech

        # 3. WOULD YOU RATHER
        elif g_type == MiniGameType.WOULD_YOU_RATHER.value:
            vote = None
            if any(w in msg_lower for w in ["!a", "opsi a", "pilih a"]) or msg_lower == "a" or msg_lower == "1":
                vote = "A"
            elif any(w in msg_lower for w in ["!b", "opsi b", "pilih b"]) or msg_lower == "b" or msg_lower == "2":
                vote = "B"

            if not vote:
                return None

            prev_vote = self.session.voters.get(user)
            if prev_vote:
                self.session.poll_votes[prev_vote] = max(0, self.session.poll_votes.get(prev_vote, 1) - 1)

            self.session.voters[user] = vote
            self.session.poll_votes[vote] = self.session.poll_votes.get(vote, 0) + 1

            player.add_points(2)  # Participation points
            pcts = self.session._calculate_poll_percentages()

            wyr = self.session.current_challenge
            speech = (
                f"[emotion: happy] Suara dari {user} tercatat untuk Opsi {vote}! "
                f"Polling saat ini: A ({pcts['A']}%) vs B ({pcts['B']}%)! Eve sendiri pilih Opsi {wyr.get('eve_choice', 'A')}: '{wyr.get('eve_hot_take', '')}' [action: wink]"
            )
            self.session.host_speech = speech
            return True, speech

        # 4. RIDDLE CHALLENGE
        elif g_type == MiniGameType.RIDDLE.value:
            rid = self.session.current_challenge
            keywords = [k.lower() for k in rid.get("accepted_keywords", [])]

            is_correct = any(k in msg_lower for k in keywords)
            self.session.round_attempts.append({
                "user": user,
                "answer": clean_msg,
                "is_correct": is_correct,
                "time": time.strftime("%H:%M:%S")
            })

            if is_correct:
                pts = rid.get("points", 15)
                player.add_points(pts)
                self.session.chat_score += pts
                self.session.round_winner = user
                self.session.status = GameStatus.ROUND_END.value

                speech = (
                    f"[emotion: excited] PINTAR BANGET! 🎉 Jawabannya memang **{rid.get('answer')}**! "
                    f"{user} sukses memecahkan teka-teki ini (+{pts} poin)! {rid.get('explanation', '')} [action: wink]"
                )
                self.session.host_speech = speech
                self.save()
                self._log_event("riddle_win", {"user": user, "answer": rid.get("answer")})
                return True, speech
            else:
                # If chat struggled with 3 attempts, auto reveal hint
                if len(self.session.round_attempts) % 3 == 0:
                    hint = self.request_hint()
                    return False, f"[emotion: smug] Masih salah, {user}! Nih Eve kasih hint biar gak pusing: '{hint}' [action: wink]"
                return False, f"[emotion: neutral] Hmm, '{clean_msg}' bukan jawaban teka-teki kali ini, {user}. Coba pikirkan lagi! [action: shrug]"

        # 5. WORD ASSOCIATION
        elif g_type == MiniGameType.WORD_ASSOCIATION.value:
            # Word must be alphabetic, len >= 3, not already in chain
            candidate = clean_msg.strip().title()
            if len(candidate) < 3 or not candidate.replace(' ', '').isalpha():
                return None

            existing = [w.lower() for w in self.session.word_chain]
            if candidate.lower() in existing:
                return False, f"[emotion: surprised] Kata '{candidate}' sudah pernah dipakai, {user}! Cari kata lain yang belum ada di rantai! [action: shrug]"

            self.session.word_chain.append(candidate)
            streak = len(self.session.word_chain)
            pts = 5 + min(10, streak)
            player.add_points(pts)
            self.session.chat_score += pts

            speech = (
                f"[emotion: happy] '{candidate}' masuk ke rantai kata tema {self.session.active_theme}! "
                f"Streak kita sekarang: {streak} kata berturut-turut! (+{pts} poin buat {user}) [action: wink]"
            )
            self.session.host_speech = speech
            self.save()
            return True, speech

        # 6. GUESS THE SONG
        elif g_type == MiniGameType.GUESS_SONG.value:
            song = self.session.current_challenge
            accepted = [a.lower() for a in song.get("accepted_titles", [])]

            is_correct = any(a in msg_lower for a in accepted)
            self.session.round_attempts.append({
                "user": user,
                "guess": clean_msg,
                "is_correct": is_correct,
                "time": time.strftime("%H:%M:%S")
            })

            if is_correct:
                pts = song.get("points", 10)
                player.add_points(pts)
                self.session.chat_score += pts
                self.session.round_winner = user
                self.session.status = GameStatus.ROUND_END.value

                speech = (
                    f"[emotion: excited] TEBAKAN TEPAT! 🎶 Lagu ini adalah **{song.get('title')}** oleh **{song.get('artist')}**! "
                    f"Telinga musik {user} bener-bener tajam (+{pts} poin)! [action: wink]"
                )
                self.session.host_speech = speech
                self.save()
                self._log_event("song_quiz_win", {"user": user, "song": song.get("title")})
                return True, speech
            else:
                return False, f"[emotion: neutral] '{clean_msg}' bukan lagu yang Eve maksud, {user}! Dengerin lagi lirik clue-nya! [action: giggle]"

        return None

    def request_hint(self) -> str:
        """Reveals and returns the next hint for Riddle or Song Quiz."""
        c = self.session.current_challenge
        hints = c.get("hints", [])
        if not hints:
            if self.session.game_type == MiniGameType.GUESS_SONG.value:
                return f"Genre lagu ini: {c.get('genre', 'Musik')}!"
            return "Pikirkan benda atau konsep sehari-hari di sekitarmu!"

        unrevealed = [h for h in hints if h not in self.session.revealed_hints]
        if unrevealed:
            chosen = unrevealed[0]
            self.session.revealed_hints.append(chosen)
            return chosen
        return self.session.revealed_hints[-1] if self.session.revealed_hints else "Tidak ada hint tersisa!"

    def _handle_round_timeout(self) -> Tuple[bool, str]:
        """Handles time expiration of an active round."""
        self.session.status = GameStatus.ROUND_END.value
        ans = self.session.round_correct_answer or "Waktu Habis"
        self.session.ai_score += 10  # Point to AI when chat fails to answer in time

        speech = (
            f"[emotion: smug] Waktu habis, chat! ⏰ Sayang sekali belum ada yang berhasil menebak. "
            f"Jawaban yang benar adalah: **{ans}**! Poin ronde ini Eve ambil ya! [action: giggle]"
        )
        self.session.host_speech = speech
        self._log_event("round_timeout", {"correct_answer": ans})
        return True, speech

    # --- Leaderboard & Stats ---
    def get_leaderboard(self, limit: int = 10) -> List[PlayerScore]:
        return sorted(self.leaderboard.values(), key=lambda p: p.score, reverse=True)[:limit]

    def _log_event(self, event_type: str, data: Dict[str, Any]):
        entry = {
            "type": event_type,
            "data": data,
            "time": time.strftime("%H:%M:%S")
        }
        self.game_event_log.append(entry)
        if len(self.game_event_log) > 30:
            self.game_event_log.pop(0)

    # --- Second Brain Sync ---
    def sync_to_second_brain(self):
        try:
            m_dir = self.second_brain_dir / "minigames"
            m_dir.mkdir(parents=True, exist_ok=True)
            f_path = m_dir / "leaderboard.md"

            lines = [
                "# 🎮 Interactive Mini-Game Hall of Fame & Leaderboard",
                f"> Last synchronized: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "## 🏆 Top Audience Champions",
                "| Rank | Player | Score | Correct | Wins | Streak |",
                "|:----:|:-------|:-----:|:-------:|:----:|:------:|"
            ]
            top = self.get_leaderboard(10)
            medals = ["🥇", "🥈", "🥉"]
            for i, p in enumerate(top):
                medal = medals[i] if i < 3 else f"#{i+1}"
                lines.append(f"| {medal} | **{p.username}** | {p.score} | {p.correct_answers} | {p.games_won} | {p.streak} |")

            lines.append("")
            lines.append("## 🕹️ Active Match Status")
            lines.append(f"- Game Mode: `{self.session.game_type}`")
            lines.append(f"- Status: `{self.session.status}`")
            lines.append(f"- Round: {self.session.round_number}/{self.session.total_rounds}")
            lines.append(f"- AI vs Chat Score: Eve ({self.session.ai_score}) vs Chat ({self.session.chat_score})")

            f_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:
            print(f"[MiniGameEngine] Error syncing Second Brain: {e}")

    # --- Prompt Directive ---
    def get_prompt_directive(self) -> str:
        if self.session.status != GameStatus.ACTIVE.value:
            return (
                "[🎮 INTERACTIVE MINI-GAME ENGINE & AUDIENCE CROWD PLAY]\n"
                "Game Status: IDLE (No mini-game active).\n"
                "You can invite chat to play: Trivia, Guess the Number, Word Association, Riddles, Would You Rather, or Guess the Song!"
            )

        g_type = self.session.game_type.replace('_', ' ').upper()
        c = self.session.current_challenge
        q_text = c.get("question") or c.get("riddle") or c.get("instruction") or c.get("topic") or c.get("clue_lyrics") or ""

        return (
            f"[🎮 LIVE INTERACTIVE MINI-GAME: {g_type}]\n"
            f"You are hosting an energetic live mini-game with your stream audience!\n"
            f"- Round: {self.session.round_number} of {self.session.total_rounds}\n"
            f"- Active Challenge: \"{q_text}\"\n"
            f"- Scoreboard: Eve {self.session.ai_score} pts vs Chat {self.session.chat_score} pts\n"
            f"- Time Remaining: {self.session.get_remaining_seconds()} seconds\n\n"
            "HOSTING DIRECTIVES:\n"
            "1. Hype up the game! Cheer when chatters guess correctly, tease funny mistakes, and banter competitively.\n"
            "2. If chatters submit answers in chat, acknowledge their attempts with emotion tags.\n"
            "3. Keep the stream pace lively and engaging."
        )

    # --- Unified State ---
    def get_state(self) -> Dict[str, Any]:
        return {
            "session": self.session.to_dict(),
            "leaderboard": [p.to_dict() for p in self.get_leaderboard(8)],
            "event_log": list(reversed(self.game_event_log[-10:])),
            "total_players": len(self.leaderboard),
            "ai_score": self.session.ai_score,
            "chat_score": self.session.chat_score
        }
