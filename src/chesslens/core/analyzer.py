"""
Stockfish analyzer — evaluates individual games move by move.
Receives Game objects from core/parser.py. No HTTP calls here.
"""
from __future__ import annotations

import io
import logging
import math
import shutil
from dataclasses import dataclass

import chess
import chess.engine
import chess.pgn

from chesslens.core.parser import Game

logger = logging.getLogger(__name__)

BLUNDER_THRESHOLD = 300
MISTAKE_THRESHOLD = 100
INACCURACY_THRESHOLD = 50
DEFAULT_DEPTH = 12


@dataclass
class GameAnalysis:
    game_id: str
    accuracy: float
    avg_centipawn_loss: float
    blunders: int
    mistakes: int
    inaccuracies: int
    timeout_move: int | None  # ply count at timeout, None otherwise


def _find_stockfish(path: str | None = None) -> str:
    if path:
        return path
    found = shutil.which("stockfish")
    if not found:
        raise FileNotFoundError(
            "Stockfish not found. Install it: apt install stockfish / brew install stockfish"
        )
    return found


def _accuracy(avg_cpl: float) -> float:
    # WHY: approximation of chess.com's accuracy formula, calibrated to human play
    return round(max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * avg_cpl) - 3.1669)), 1)


def analyze_game(
    game: Game,
    engine_path: str | None = None,
    depth: int = DEFAULT_DEPTH,
) -> GameAnalysis | None:
    """Analyze a game move by move with Stockfish. Returns None if analysis fails."""
    try:
        stockfish_path = _find_stockfish(engine_path)
    except FileNotFoundError as e:
        logger.error(str(e))
        return None

    pgn_game = chess.pgn.read_game(io.StringIO(game.pgn))
    if pgn_game is None:
        logger.warning("Could not parse PGN for game %s", game.id)
        return None

    player_color = chess.WHITE if game.color == "white" else chess.BLACK
    limit = chess.engine.Limit(depth=depth)
    losses: list[float] = []
    blunders = mistakes = inaccuracies = 0

    try:
        with chess.engine.SimpleEngine.popen_uci(stockfish_path) as engine:
            board = pgn_game.board()
            prev_info = engine.analyse(board, limit)

            for node in pgn_game.mainline():
                mover = board.turn
                board.push(node.move)
                curr_info = engine.analyse(board, limit)

                if mover == player_color:
                    before = prev_info["score"].white().score(mate_score=10000)
                    after = curr_info["score"].white().score(mate_score=10000)

                    if before is not None and after is not None:
                        loss = (before - after) if player_color == chess.WHITE else (after - before)
                        loss = max(0.0, float(loss))
                        losses.append(loss)
                        if loss >= BLUNDER_THRESHOLD:
                            blunders += 1
                        elif loss >= MISTAKE_THRESHOLD:
                            mistakes += 1
                        elif loss >= INACCURACY_THRESHOLD:
                            inaccuracies += 1

                prev_info = curr_info

    except Exception as e:
        logger.warning("Stockfish analysis failed for game %s: %s", game.id, e)
        return None

    avg_cpl = sum(losses) / len(losses) if losses else 0.0

    return GameAnalysis(
        game_id=game.id,
        accuracy=_accuracy(avg_cpl),
        avg_centipawn_loss=round(avg_cpl, 1),
        blunders=blunders,
        mistakes=mistakes,
        inaccuracies=inaccuracies,
        timeout_move=game.move_count if game.end_reason == "timeout" else None,
    )
