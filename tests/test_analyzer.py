import shutil
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import chess
import chess.engine
import pytest

from chesslens.core.analyzer import (
    DEFAULT_DEPTH,
    GameAnalysis,
    _accuracy,
    _find_stockfish,
    analyze_game,
)
from chesslens.core.parser import Game

STOCKFISH_AVAILABLE = bool(shutil.which("stockfish"))

SAMPLE_PGN = (
    '[Event "Live Chess"]\n[Site "Chess.com"]\n[Date "2026.05.10"]\n'
    '[White "krix0s"]\n[Black "opponent1"]\n[Result "1-0"]\n'
    '[WhiteElo "1245"]\n[BlackElo "1230"]\n[TimeControl "180+2"]\n'
    '[ECO "D00"]\n\n1. d4 d5 2. Bf4 Nf6 3. e3 Bf5 4. Nf3 e6 5. Bd3 Bxd3 6. Qxd3 1-0'
)


@pytest.fixture
def blitz_game():
    return Game(
        id="111111111",
        username="krix0s",
        played_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        time_class="blitz",
        color="white",
        result="win",
        end_reason="resigned",
        opponent="opponent1",
        player_rating=1245,
        opponent_rating=1230,
        opening_eco="D00",
        opening_name="Queens Pawn Opening London System",
        move_count=11,
        pgn=SAMPLE_PGN,
    )


@pytest.fixture
def timeout_game(blitz_game):
    return Game(**{**blitz_game.__dict__, "result": "loss", "end_reason": "timeout", "move_count": 20})


# --- Unit tests (no Stockfish needed) ---

def test_accuracy_perfect():
    assert _accuracy(0) == 100.0


def test_accuracy_high_cpl():
    # high centipawn loss → low accuracy
    assert _accuracy(200) < 50.0


def test_accuracy_clamped():
    assert 0.0 <= _accuracy(0) <= 100.0
    assert 0.0 <= _accuracy(1000) <= 100.0


def test_find_stockfish_uses_provided_path():
    assert _find_stockfish("/usr/bin/stockfish") == "/usr/bin/stockfish"


def test_find_stockfish_raises_if_missing():
    with patch("shutil.which", return_value=None):
        with pytest.raises(FileNotFoundError):
            _find_stockfish()


def test_analyze_game_returns_none_on_missing_stockfish(blitz_game):
    with patch("shutil.which", return_value=None):
        result = analyze_game(blitz_game)
    assert result is None


def test_analyze_game_returns_none_on_empty_pgn(blitz_game):
    blitz_game.pgn = ""
    with patch("chess.engine.SimpleEngine.popen_uci"):
        result = analyze_game(blitz_game)
    assert result is None


def test_analyze_game_timeout_move_set(timeout_game):
    mock_score = MagicMock()
    mock_score.white.return_value.score.return_value = 20

    mock_info = {"score": mock_score}
    mock_engine = MagicMock()
    mock_engine.analyse.return_value = mock_info
    mock_engine.__enter__ = lambda s: s
    mock_engine.__exit__ = MagicMock(return_value=False)

    with patch("chess.engine.SimpleEngine.popen_uci", return_value=mock_engine):
        result = analyze_game(timeout_game)

    assert result is not None
    assert result.timeout_move == timeout_game.move_count


def test_analyze_game_no_timeout_move(blitz_game):
    mock_score = MagicMock()
    mock_score.white.return_value.score.return_value = 20

    mock_info = {"score": mock_score}
    mock_engine = MagicMock()
    mock_engine.analyse.return_value = mock_info
    mock_engine.__enter__ = lambda s: s
    mock_engine.__exit__ = MagicMock(return_value=False)

    with patch("chess.engine.SimpleEngine.popen_uci", return_value=mock_engine):
        result = analyze_game(blitz_game)

    assert result is not None
    assert result.timeout_move is None


# --- Integration tests (require Stockfish) ---

@pytest.mark.skipif(not STOCKFISH_AVAILABLE, reason="Stockfish not installed")
def test_analyze_game_real_stockfish(blitz_game):
    result = analyze_game(blitz_game, depth=10)

    assert isinstance(result, GameAnalysis)
    assert result.game_id == "111111111"
    assert 0.0 <= result.accuracy <= 100.0
    assert result.avg_centipawn_loss >= 0.0
    assert result.blunders >= 0
    assert result.mistakes >= 0
    assert result.inaccuracies >= 0
    assert result.timeout_move is None


@pytest.mark.skipif(not STOCKFISH_AVAILABLE, reason="Stockfish not installed")
def test_analyze_game_blunder_detection(blitz_game):
    # A game with a massive blunder move
    blunder_pgn = (
        '[Event "Live Chess"]\n[White "krix0s"]\n[Black "opponent"]\n'
        '[Result "0-1"]\n[WhiteElo "1245"]\n[BlackElo "1230"]\n\n'
        # krix0s plays Ke2?? blundering the king into the center
        "1. e4 e5 2. Ke2 Nf6 3. Kd3 d5 4. exd5 Nxd5 0-1"
    )
    game = Game(
        id="blunder_test",
        username="krix0s",
        played_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        time_class="blitz",
        color="white",
        result="loss",
        end_reason="resigned",
        opponent="opponent",
        player_rating=1245,
        opponent_rating=1230,
        opening_eco=None,
        opening_name=None,
        move_count=8,
        pgn=blunder_pgn,
    )
    result = analyze_game(game, depth=10)
    assert result is not None
    assert result.blunders >= 1
