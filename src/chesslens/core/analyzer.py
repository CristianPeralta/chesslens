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

from chesslens.core.parser import Game, extract_clock

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


@dataclass
class MoveError:
    ply: int
    san: str
    eval_before: int
    eval_after: int
    centipawn_loss: int
    best_line: list[str]
    severity: str


@dataclass
class GameDetailAnalysis:
    game_id: str
    eval_sequence: list[int]
    top_errors: list[MoveError]
    remaining_clock: int | None
    accuracy: float
    avg_centipawn_loss: float
    blunders: int
    mistakes: int
    inaccuracies: int
    timeout_move: int | None


def _find_stockfish(path: str | None = None) -> str:
    if path:
        return path
    found = shutil.which("stockfish")
    if not found:
        raise FileNotFoundError(
            "Stockfish not found. Install it: apt install stockfish / brew install stockfish"
        )
    return found


def _win_prob(cp: float) -> float:
    """Win probability (0–100) from a centipawn score (white's perspective)."""
    return 100.0 / (1.0 + math.exp(-cp / 600.0))


def _accuracy(avg_wpl: float) -> float:
    # WHY: chess.com's formula expects win-probability loss (0–100 scale), not raw CPL.
    # Passing raw CPL (avg ~50) into this formula gives ~9%; passing WPL (~2) gives ~90%.
    return round(max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * avg_wpl) - 3.1669)), 1)


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
    cpl_losses: list[float] = []
    wpl_losses: list[float] = []
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
                        cpl = (before - after) if player_color == chess.WHITE else (after - before)
                        cpl = max(0.0, float(cpl))
                        cpl_losses.append(cpl)
                        wpl = _win_prob(before) - _win_prob(after) if player_color == chess.WHITE \
                            else _win_prob(after) - _win_prob(before)
                        wpl_losses.append(max(0.0, wpl))
                        if cpl >= BLUNDER_THRESHOLD:
                            blunders += 1
                        elif cpl >= MISTAKE_THRESHOLD:
                            mistakes += 1
                        elif cpl >= INACCURACY_THRESHOLD:
                            inaccuracies += 1

                prev_info = curr_info

    except Exception as e:
        logger.warning("Stockfish analysis failed for game %s: %s", game.id, e)
        return None

    avg_cpl = sum(cpl_losses) / len(cpl_losses) if cpl_losses else 0.0
    avg_wpl = sum(wpl_losses) / len(wpl_losses) if wpl_losses else 0.0

    return GameAnalysis(
        game_id=game.id,
        accuracy=_accuracy(avg_wpl),
        avg_centipawn_loss=round(avg_cpl, 1),
        blunders=blunders,
        mistakes=mistakes,
        inaccuracies=inaccuracies,
        timeout_move=game.move_count if game.end_reason == "timeout" else None,
    )


def _severity(cpl: int) -> str:
    if cpl >= 200:
        return "blunder"
    if cpl >= 100:
        return "mistake"
    return "inaccuracy"


def _best_line_san(info: dict, board_before_move: chess.Board) -> list[str]:
    """Convert the principal variation from info into SAN notation (first 5 moves)."""
    pv = info.get("pv", [])[:5]
    board = board_before_move.copy()
    san_moves: list[str] = []
    for move in pv:
        try:
            san_moves.append(board.san(move))
            board.push(move)
        except Exception:
            break
    return san_moves


def analyze_game_detail(
    game: Game,
    engine_path: str | None = None,
    depth: int = DEFAULT_DEPTH,
) -> GameDetailAnalysis | None:
    """Deep analysis of a single game: eval sequence, top errors, remaining clock.

    Uses ONE engine session with multipv=3 to collect both eval and best lines.
    Returns None on any failure (engine not found, PGN error, etc.).
    """
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

    eval_sequence: list[int] = []
    player_errors: list[MoveError] = []
    cpl_losses: list[float] = []
    wpl_losses: list[float] = []
    blunders = mistakes = inaccuracies = 0
    remaining_clock: int | None = None
    last_player_node = None

    try:
        with chess.engine.SimpleEngine.popen_uci(stockfish_path) as engine:
            board = pgn_game.board()

            # Initial position eval (before any moves)
            pre_infos = engine.analyse(board, limit, multipv=3)
            prev_infos = pre_infos if isinstance(pre_infos, list) else [pre_infos]

            for node in pgn_game.mainline():
                mover = board.turn
                board_before = board.copy()

                if mover == player_color:
                    last_player_node = node

                board.push(node.move)
                curr_infos = engine.analyse(board, limit, multipv=3)
                if not isinstance(curr_infos, list):
                    curr_infos = [curr_infos]

                # Build eval sequence from white's perspective, clamped ±1000
                raw_score = curr_infos[0]["score"].white().score(mate_score=10000)
                if raw_score is not None:
                    eval_sequence.append(max(-1000, min(1000, raw_score)))

                # Collect player move errors
                if mover == player_color and prev_infos:
                    before_raw = prev_infos[0]["score"].white().score(mate_score=10000)
                    after_raw = curr_infos[0]["score"].white().score(mate_score=10000)

                    if before_raw is not None and after_raw is not None:
                        if player_color == chess.WHITE:
                            cpl = max(0, before_raw - after_raw)
                        else:
                            cpl = max(0, after_raw - before_raw)

                        cpl_losses.append(float(cpl))
                        wpl = _win_prob(before_raw) - _win_prob(after_raw) if player_color == chess.WHITE \
                            else _win_prob(after_raw) - _win_prob(before_raw)
                        wpl_losses.append(max(0.0, wpl))
                        sev = _severity(cpl) if cpl >= INACCURACY_THRESHOLD else None
                        if sev == "blunder":
                            blunders += 1
                        elif sev == "mistake":
                            mistakes += 1
                        elif sev == "inaccuracy":
                            inaccuracies += 1

                        if cpl >= INACCURACY_THRESHOLD:
                            best_line = _best_line_san(prev_infos[0], board_before)
                            player_errors.append(MoveError(
                                ply=board.ply() - 1,
                                san=board_before.san(node.move),
                                eval_before=max(-1000, min(1000, before_raw)),
                                eval_after=max(-1000, min(1000, after_raw)),
                                centipawn_loss=cpl,
                                best_line=best_line,
                                severity=_severity(cpl),
                            ))

                prev_infos = curr_infos

    except Exception as e:
        logger.warning("Stockfish detail analysis failed for game %s: %s", game.id, e)
        return None

    # Extract remaining clock from last player move's comment
    if last_player_node is not None:
        remaining_clock = extract_clock(last_player_node.comment)

    top_errors = sorted(player_errors, key=lambda e: e.centipawn_loss, reverse=True)[:3]
    avg_cpl = sum(cpl_losses) / len(cpl_losses) if cpl_losses else 0.0
    avg_wpl = sum(wpl_losses) / len(wpl_losses) if wpl_losses else 0.0

    return GameDetailAnalysis(
        game_id=game.id,
        eval_sequence=eval_sequence,
        top_errors=top_errors,
        remaining_clock=remaining_clock,
        accuracy=_accuracy(avg_wpl),
        avg_centipawn_loss=round(avg_cpl, 1),
        blunders=blunders,
        mistakes=mistakes,
        inaccuracies=inaccuracies,
        timeout_move=game.move_count if game.end_reason == "timeout" else None,
    )
