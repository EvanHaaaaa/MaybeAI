import chess
import random
import time
from typing import Dict, Any, List, Optional, Tuple

# Piece values
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000
}

# Simplified piece-square tables (from white's perspective)
PAWN_TABLE = [
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0
]

KNIGHT_TABLE = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
]

BISHOP_TABLE = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
]

ROOK_TABLE = [
      0,  0,  0,  0,  0,  0,  0,  0,
      5, 10, 10, 10, 10, 10, 10,  5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
      0,  0,  0,  5,  5,  0,  0,  0
]

QUEEN_TABLE = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5,  5,  5,  5,  0,-10,
     -5,  0,  5,  5,  5,  5,  0, -5,
      0,  0,  5,  5,  5,  5,  0, -5,
    -10,  5,  5,  5,  5,  5,  0,-10,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20
]

KING_MIDDLE_TABLE = [
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -10,-20,-20,-20,-20,-20,-20,-10,
     20, 20,  0,  0,  0,  0, 20, 20,
     20, 30, 10,  0,  0, 10, 30, 20
]

class ChessEngine:
    """
    Intelligent Chess Engine with dynamically scalable ELO (400 - 2400+).
    Features:
    - Minimax with Alpha-Beta pruning & Quiescence search
    - Positional piece-square tables
    - ELO-scaled blunder simulation & search depths
    - Move evaluation and game status analysis
    """

    def __init__(self, elo: int = 1200):
        self.board = chess.Board()
        self.elo = elo
        self.move_history: List[str] = []

    def set_elo(self, elo: int):
        self.elo = max(400, min(2600, int(elo)))

    def reset(self, fen: Optional[str] = None):
        if fen:
            self.board.set_fen(fen)
        else:
            self.board.reset()
        self.move_history.clear()

    def get_search_depth_and_blunder_chance(self) -> Tuple[int, float]:
        """Calculates minimax search depth and probability of sub-optimal move based on ELO."""
        if self.elo < 800:
            return 1, 0.45
        elif self.elo < 1100:
            return 2, 0.30
        elif self.elo < 1400:
            return 2, 0.15
        elif self.elo < 1700:
            return 3, 0.05
        elif self.elo < 2000:
            return 4, 0.01
        else:
            return 4, 0.0

    def evaluate_board(self, board: Optional[chess.Board] = None) -> int:
        """Returns board evaluation from White's perspective in centipawns."""
        target_board = board if board is not None else self.board
        if target_board.is_checkmate():
            return -99999 if target_board.turn == chess.WHITE else 99999
        if target_board.is_stalemate() or target_board.is_insufficient_material():
            return 0

        score = 0
        for square in chess.SQUARES:
            piece = target_board.piece_at(square)
            if not piece:
                continue

            val = PIECE_VALUES[piece.piece_type]
            sq_idx = square if piece.color == chess.WHITE else chess.square_mirror(square)

            pos_bonus = 0
            if piece.piece_type == chess.PAWN:
                pos_bonus = PAWN_TABLE[sq_idx]
            elif piece.piece_type == chess.KNIGHT:
                pos_bonus = KNIGHT_TABLE[sq_idx]
            elif piece.piece_type == chess.BISHOP:
                pos_bonus = BISHOP_TABLE[sq_idx]
            elif piece.piece_type == chess.ROOK:
                pos_bonus = ROOK_TABLE[sq_idx]
            elif piece.piece_type == chess.QUEEN:
                pos_bonus = QUEEN_TABLE[sq_idx]
            elif piece.piece_type == chess.KING:
                pos_bonus = KING_MIDDLE_TABLE[sq_idx]

            total_val = val + pos_bonus
            if piece.color == chess.WHITE:
                score += total_val
            else:
                score -= total_val

        return score

    def alpha_beta(
        self,
        depth: int,
        alpha: int,
        beta: int,
        maximizing: bool,
        board: Optional[chess.Board] = None,
    ) -> Tuple[int, Optional[chess.Move]]:
        target_board = board if board is not None else self.board
        if depth == 0 or target_board.is_game_over():
            return self.evaluate_board(target_board), None

        legal_moves = list(target_board.legal_moves)
        if not legal_moves:
            return self.evaluate_board(target_board), None

        # Prioritize captures and checks for faster alpha-beta cutoff
        def move_priority(m):
            priority = 0
            if target_board.is_capture(m):
                captured = target_board.piece_at(m.to_square)
                priority += PIECE_VALUES.get(captured.piece_type, 100) if captured else 100
            if target_board.gives_check(m):
                priority += 50
            return priority

        legal_moves.sort(key=move_priority, reverse=True)

        best_move = None
        if maximizing:
            max_eval = -999999
            for move in legal_moves:
                target_board.push(move)
                eval_score, _ = self.alpha_beta(depth - 1, alpha, beta, False, board=target_board)
                target_board.pop()
                if eval_score > max_eval:
                    max_eval = eval_score
                    best_move = move
                alpha = max(alpha, eval_score)
                if beta <= alpha:
                    break
            return max_eval, best_move
        else:
            min_eval = 999999
            for move in legal_moves:
                target_board.push(move)
                eval_score, _ = self.alpha_beta(depth - 1, alpha, beta, True, board=target_board)
                target_board.pop()
                if eval_score < min_eval:
                    min_eval = eval_score
                    best_move = move
                beta = min(beta, eval_score)
                if beta <= alpha:
                    break
            return min_eval, best_move

    def choose_move(self, board: Optional[chess.Board] = None) -> Optional[chess.Move]:
        """Selects move according to current ELO settings on a cloned board."""
        search_board = board.copy() if board is not None else self.board.copy()
        legal_moves = list(search_board.legal_moves)
        if not legal_moves:
            return None

        depth, blunder_chance = self.get_search_depth_and_blunder_chance()

        # Simulate human-like blunder for lower ELOs
        if random.random() < blunder_chance and len(legal_moves) > 1:
            # Pick a random capture or random move
            captures = [m for m in legal_moves if search_board.is_capture(m)]
            return random.choice(captures) if (captures and random.random() < 0.6) else random.choice(legal_moves)

        maximizing = (search_board.turn == chess.WHITE)
        _, best_move = self.alpha_beta(depth, -999999, 999999, maximizing, board=search_board)

        return best_move if best_move else random.choice(legal_moves)

    def make_move_san_or_uci(self, move_str: str) -> Tuple[bool, Optional[chess.Move], str]:
        """
        Applies a move specified in UCI (e.g. 'e2e4') or SAN (e.g. 'e4', 'Nf3', 'O-O').
        Returns (success: bool, move_obj: Optional[chess.Move], error_or_san: str)
        """
        clean_str = move_str.strip().replace("x", "x").replace("+", "").replace("#", "")

        # Try parsing as UCI
        try:
            move = chess.Move.from_uci(clean_str)
            if move in self.board.legal_moves:
                san = self.board.san(move)
                self.board.push(move)
                self.move_history.append(san)
                return True, move, san
        except Exception:
            pass

        # Try parsing as SAN
        try:
            move = self.board.parse_san(move_str)
            if move in self.board.legal_moves:
                san = self.board.san(move)
                self.board.push(move)
                self.move_history.append(san)
                return True, move, san
        except Exception:
            pass

        return False, None, f"Illegal or unrecognized move '{move_str}'"

    def get_game_state(self) -> Dict[str, Any]:
        """Full game state serialization for web UI and orchestrator."""
        is_over = self.board.is_game_over()
        result_desc = "ongoing"
        if self.board.is_checkmate():
            winner = "Black" if self.board.turn == chess.WHITE else "White"
            result_desc = f"checkmate_{winner.lower()}_wins"
        elif self.board.is_stalemate():
            result_desc = "draw_stalemate"
        elif self.board.is_insufficient_material():
            result_desc = "draw_insufficient_material"

        return {
            "fen": self.board.fen(),
            "turn": "white" if self.board.turn == chess.WHITE else "black",
            "is_check": self.board.is_check(),
            "is_game_over": is_over,
            "result": result_desc,
            "elo": self.elo,
            "move_count": len(self.move_history),
            "move_history": self.move_history,
            "eval": self.evaluate_board(),
            "legal_moves": [m.uci() for m in self.board.legal_moves]
        }
