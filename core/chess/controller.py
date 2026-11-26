import asyncio
import chess
from typing import Dict, Any, Optional, Callable, Tuple
from core.chess.chess_engine import ChessEngine
from core.chess.chess_agent import ChessAgent

class ChessController:
    """
    Master Controller for Eve's Chess Gameplay.
    Coordinates:
    - Chess board engine state & minimax evaluation
    - Adjustable ELO difficulty (600 - 2400+)
    - Player moves (UCI or SAN) and Bot moves
    - Eve's sassy commentary & TTS integration
    """

    def __init__(self, bot_name: str = "EveMaybe", default_elo: int = 1200):
        self.bot_name = bot_name
        self.engine = ChessEngine(elo=default_elo)
        self.agent = ChessAgent(bot_name=bot_name)
        
        self.is_active = False
        self.player_name = "Player"
        self.player_color = "white"  # "white" or "black"
        self.eve_color = "black"

        self.on_commentary_callback: Optional[Callable[[str], Any]] = None
        self.on_state_change_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
        self.on_game_event_callback: Optional[Callable[[str, Dict[str, Any]], Any]] = None

    def set_callbacks(
        self,
        on_commentary: Callable[[str], Any],
        on_state_change: Optional[Callable[[Dict[str, Any]], Any]] = None,
        on_game_event: Optional[Callable[[str, Dict[str, Any]], Any]] = None
    ):
        self.on_commentary_callback = on_commentary
        self.on_state_change_callback = on_state_change
        self.on_game_event_callback = on_game_event

    async def emit_game_event(self, event_type: str, data: Dict[str, Any]):
        if self.on_game_event_callback:
            res = self.on_game_event_callback(event_type, data)
            if asyncio.iscoroutine(res):
                await res

    def get_status(self) -> Dict[str, Any]:
        game_state = self.engine.get_game_state()
        return {
            "is_active": self.is_active,
            "player_name": self.player_name,
            "player_color": self.player_color,
            "eve_color": self.eve_color,
            **game_state
        }

    async def emit_commentary(self, speech: str):
        if self.on_commentary_callback and speech:
            res = self.on_commentary_callback(speech)
            if asyncio.iscoroutine(res):
                await res

    async def emit_state(self):
        if self.on_state_change_callback:
            res = self.on_state_change_callback(self.get_status())
            if asyncio.iscoroutine(res):
                await res

    async def start_game(self, player_name: str = "Player", player_color: str = "white", elo: Optional[int] = None) -> str:
        self.is_active = True
        self.player_name = player_name or "Player"
        self.player_color = player_color.lower()
        self.eve_color = "black" if self.player_color == "white" else "white"
        
        if elo is not None:
            self.engine.set_elo(elo)

        self.engine.reset()

        intro_speech = self.agent.on_game_start(
            elo=self.engine.elo,
            player_name=self.player_name,
            eve_color=self.eve_color
        )
        await self.emit_commentary(intro_speech)
        await self.emit_state()

        # If Eve is White, she makes the first move automatically!
        if self.eve_color == "white":
            await asyncio.sleep(0.8)
            await self.amake_bot_move()

        return intro_speech

    async def set_elo(self, elo: int) -> str:
        self.engine.set_elo(elo)
        comment = self.agent.on_elo_changed(self.engine.elo)
        await self.emit_commentary(comment)
        await self.emit_state()
        return comment

    async def make_player_move(self, move_str: str) -> Tuple[bool, str]:
        """Processes a move made by the human player."""
        if not self.is_active:
            await self.start_game(player_name=self.player_name, player_color=self.player_color)

        current_turn = "white" if self.engine.board.turn == chess.WHITE else "black"
        if current_turn != self.player_color:
            return False, f"Bukan giliranmu! Sekarang giliran {self.bot_name} ({current_turn})."

        # Check capture status before pushing
        is_capture = False
        try:
            m = chess.Move.from_uci(move_str)
            if m in self.engine.board.legal_moves and self.engine.board.is_capture(m):
                is_capture = True
        except Exception:
            pass

        success, move_obj, san_or_err = self.engine.make_move_san_or_uci(move_str)
        if not success:
            return False, san_or_err

        is_check = self.engine.board.is_check()

        # Eve comments on player's move
        player_reaction = self.agent.on_player_move(
            san=san_or_err,
            is_check=is_check,
            is_capture=is_capture,
            player_name=self.player_name
        )
        if player_reaction:
            await self.emit_commentary(player_reaction)

        await self.emit_state()

        # Check if game over after player move
        if self.engine.board.is_game_over():
            await self._handle_game_over()
            return True, san_or_err

        # Automatically trigger Eve's move after a brief delay
        asyncio.create_task(self._delayed_bot_move(delay=0.6))
        return True, san_or_err

    async def _delayed_bot_move(self, delay: float = 0.6):
        await asyncio.sleep(delay)
        if self.is_active and not self.engine.board.is_game_over():
            current_turn = "white" if self.engine.board.turn == chess.WHITE else "black"
            if current_turn == self.eve_color:
                await self.amake_bot_move()

    async def _apply_bot_move(self, best_move: chess.Move) -> str:
        """Applies a chosen bot move, emits commentary/state, and checks game over."""
        is_capture = self.engine.board.is_capture(best_move)
        captured_piece = self.engine.board.piece_at(best_move.to_square)
        is_queen_capture = captured_piece is not None and captured_piece.piece_type == chess.QUEEN

        san = self.engine.board.san(best_move)
        self.engine.board.push(best_move)
        self.engine.move_history.append(san)

        is_check = self.engine.board.is_check()

        if is_queen_capture:
            await self.emit_game_event("queen_captured", {
                "player": self.player_name,
                "san": san
            })

        bot_speech = self.agent.on_bot_move(
            san=san,
            is_check=is_check,
            is_capture=is_capture,
            is_queen_capture=is_queen_capture
        )
        await self.emit_commentary(bot_speech)
        await self.emit_state()

        if self.engine.board.is_game_over():
            await self._handle_game_over()

        return san

    async def make_bot_move(self) -> Optional[str]:
        """Calculates and executes Eve's move synchronously on the current thread."""
        if not self.is_active or self.engine.board.is_game_over():
            return None

        best_move = self.engine.choose_move()
        if not best_move:
            return None

        return await self._apply_bot_move(best_move)

    async def amake_bot_move(self) -> Optional[str]:
        """Calculates Eve's move in a worker thread via asyncio.to_thread and executes it."""
        if not self.is_active or self.engine.board.is_game_over():
            return None

        best_move = await asyncio.to_thread(self.engine.choose_move)
        if not best_move:
            return None

        return await self._apply_bot_move(best_move)

    async def _handle_game_over(self):
        state = self.engine.get_game_state()
        result = state["result"]

        player_won = False
        bot_won = False

        if "checkmate" in result:
            if "white_wins" in result:
                player_won = (self.player_color == "white")
                bot_won = (self.eve_color == "white")
            else:
                player_won = (self.player_color == "black")
                bot_won = (self.eve_color == "black")

        await self.emit_game_event("game_over", {
            "player": self.player_name,
            "eve_won": bot_won,
            "player_won": player_won,
            "result": result,
            "moves_count": len(self.engine.move_history),
            "elo": self.engine.elo
        })

        game_over_comment = self.agent.on_game_over(
            result=result,
            player_won=player_won,
            bot_won=bot_won,
            player_name=self.player_name
        )
        await self.emit_commentary(game_over_comment)
        await self.emit_state()

    async def resign_game(self) -> str:
        self.is_active = False
        speech = f"[emotion: smug] Menyerah ya {self.player_name}? Kemenangan mutlak lagi buat Eve Maybe! GG WP! [action: giggle]"
        await self.emit_game_event("game_over", {
            "player": self.player_name,
            "eve_won": True,
            "player_won": False,
            "result": "player_resigned",
            "moves_count": len(self.engine.move_history),
            "elo": self.engine.elo
        })
        await self.emit_commentary(speech)
        await self.emit_state()
        return speech
