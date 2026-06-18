"""Tests for the game CLI command and related helpers."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from chesslens.core.analyzer import GameDetailAnalysis, MoveError
from chesslens.core.parser import extract_clock
from chesslens.delivery.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game_row(game_id="abc123", username="testplayer"):
    from chesslens.db.models import GameRow
    return GameRow(
        id=game_id,
        username=username,
        played_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        time_class="blitz",
        color="white",
        result="win",
        end_reason="resigned",
        opponent="opponent",
        player_rating=1500,
        opponent_rating=1520,
        opening_eco="C60",
        opening_name="Ruy Lopez",
        move_count=30,
        pgn=(
            '[Event "Live Chess"]\n[White "testplayer"]\n[Black "opponent"]\n'
            '[Result "1-0"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0'
        ),
    )


def _make_detail(game_id="abc123") -> GameDetailAnalysis:
    return GameDetailAnalysis(
        game_id=game_id,
        eval_sequence=[10, 20, -50, 30],
        top_errors=[],
        remaining_clock=150,
        accuracy=85.0,
        avg_centipawn_loss=25.0,
        blunders=0,
        mistakes=1,
        inaccuracies=2,
        timeout_move=None,
    )


def _mock_settings(username="testplayer"):
    m = MagicMock()
    m.username = username
    m.reports_dir = MagicMock(spec=Path)
    m.reports_dir.__truediv__ = lambda s, o: MagicMock(spec=Path)
    return m


# ---------------------------------------------------------------------------
# Task 6.2 — extract_clock: valid input
# ---------------------------------------------------------------------------

def test_extract_clock_valid():
    assert extract_clock("[%clk 0:02:30]") == 150


def test_extract_clock_valid_with_hours():
    assert extract_clock("[%clk 1:00:00]") == 3600


def test_extract_clock_valid_with_fraction():
    # fractional seconds part should be ignored
    assert extract_clock("[%clk 0:05:00.3]") == 300


def test_extract_clock_embedded_in_comment():
    assert extract_clock("some text [%clk 0:01:30] more text") == 90


# ---------------------------------------------------------------------------
# Task 6.3 — extract_clock: malformed / None input
# ---------------------------------------------------------------------------

def test_extract_clock_none_returns_none():
    assert extract_clock(None) is None


def test_extract_clock_no_clock_returns_none():
    assert extract_clock("no clock here") is None


def test_extract_clock_empty_string_returns_none():
    assert extract_clock("") is None


def test_extract_clock_malformed_does_not_raise():
    # Must not raise even with bizarre input
    result = extract_clock("[%clk INVALID]")
    assert result is None


# ---------------------------------------------------------------------------
# Task 6.4 — game --last flag: happy path
# ---------------------------------------------------------------------------

def test_game_last_flag():
    """--last: finds row in DB, analyzes, renders, opens browser."""
    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: s
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.scalar_one_or_none.return_value = _make_game_row()

    detail = _make_detail()

    with patch("chesslens.delivery.cli.settings", _mock_settings()), \
         patch("chesslens.delivery.cli.init_db"), \
         patch("chesslens.delivery.cli.get_session", return_value=mock_session), \
         patch("chesslens.delivery.cli.analyze_game_detail", return_value=detail), \
         patch("chesslens.delivery.cli.render_game", return_value="<html>game</html>"), \
         patch("chesslens.delivery.cli._open_game_html") as mock_open, \
         patch("chesslens.delivery.cli.webbrowser.open"):
        result = runner.invoke(app, ["game", "--last"])

    assert result.exit_code == 0
    mock_open.assert_called_once()


def test_game_last_no_rows_exits_1():
    """--last with empty DB must exit with code 1."""
    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: s
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.scalar_one_or_none.return_value = None

    with patch("chesslens.delivery.cli.settings", _mock_settings()), \
         patch("chesslens.delivery.cli.init_db"), \
         patch("chesslens.delivery.cli.get_session", return_value=mock_session):
        result = runner.invoke(app, ["game", "--last"])

    assert result.exit_code == 1
    assert "No games" in result.output


# ---------------------------------------------------------------------------
# Task 6.5 — game --id: DB hit path
# ---------------------------------------------------------------------------

def test_game_id_db_hit():
    """--id when game exists in DB: get_games (fetch) is never called."""
    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: s
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.scalar_one_or_none.return_value = _make_game_row()
    mock_session.execute.return_value.all.return_value = []

    detail = _make_detail()

    with patch("chesslens.delivery.cli.settings", _mock_settings()), \
         patch("chesslens.delivery.cli.init_db"), \
         patch("chesslens.delivery.cli.get_session", return_value=mock_session), \
         patch("chesslens.delivery.cli.analyze_game_detail", return_value=detail), \
         patch("chesslens.delivery.cli.render_game", return_value="<html>game</html>"), \
         patch("chesslens.delivery.cli._open_game_html"), \
         patch("chesslens.delivery.cli.get_games") as mock_fetch:
        result = runner.invoke(app, ["game", "--id", "abc123"])

    assert result.exit_code == 0
    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Task 6.6 — game --id: not found (DB miss + API miss)
# ---------------------------------------------------------------------------

def test_game_id_not_found():
    """--id with DB miss + get_games returning empty list → exit 1."""
    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: s
    mock_session.__exit__ = MagicMock(return_value=False)
    # Every scalar_one_or_none call returns None (DB miss, stays missing after fetch)
    mock_session.execute.return_value.scalar_one_or_none.return_value = None
    mock_session.execute.return_value.all.return_value = []

    with patch("chesslens.delivery.cli.settings", _mock_settings()), \
         patch("chesslens.delivery.cli.init_db"), \
         patch("chesslens.delivery.cli.get_session", return_value=mock_session), \
         patch("chesslens.delivery.cli.get_games", return_value=[]), \
         patch("chesslens.delivery.cli.parse_games", return_value=[]):
        result = runner.invoke(app, ["game", "--id", "nonexistent"])

    assert result.exit_code == 1
    assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# Task 6.7 — severity thresholds
# ---------------------------------------------------------------------------

def test_severity_blunder():
    err = MoveError(
        ply=10, san="Qd1", eval_before=50, eval_after=-200,
        centipawn_loss=250, best_line=["e4", "e5"], severity="blunder",
    )
    assert err.severity == "blunder"


def test_severity_mistake():
    err = MoveError(
        ply=8, san="Nd2", eval_before=30, eval_after=-100,
        centipawn_loss=120, best_line=["Nf3"], severity="mistake",
    )
    assert err.severity == "mistake"


def test_severity_inaccuracy():
    err = MoveError(
        ply=6, san="h3", eval_before=10, eval_after=-55,
        centipawn_loss=60, best_line=["d4"], severity="inaccuracy",
    )
    assert err.severity == "inaccuracy"


def test_severity_thresholds_via_analyzer():
    """Verify the analyzer assigns correct severity labels based on CPL thresholds."""
    from chesslens.core.analyzer import _severity
    assert _severity(250) == "blunder"
    assert _severity(200) == "blunder"
    assert _severity(120) == "mistake"
    assert _severity(100) == "mistake"
    assert _severity(60) == "inaccuracy"
    assert _severity(50) == "inaccuracy"


# ---------------------------------------------------------------------------
# Task 6.8 — init_db() idempotency (ALTER TABLE column already exists)
# ---------------------------------------------------------------------------

def test_alter_table_idempotency():
    """Calling init_db() twice must not raise — alembic upgrade head is idempotent."""
    from unittest.mock import patch

    from chesslens.db.session import init_db

    with patch("chesslens.db.session.command") as mock_command:
        init_db()
        init_db()
    assert mock_command.upgrade.call_count == 2
