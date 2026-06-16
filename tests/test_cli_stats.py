"""Tests for the stats CLI command."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from chesslens.delivery.cli import app
from chesslens.db.models import GameRow

runner = CliRunner()


def _make_game(result="win", end_reason="resigned", rating=1245, opening="London System", days_ago=1):
    g = MagicMock(spec=GameRow)
    g.result = result
    g.end_reason = end_reason
    g.player_rating = rating
    g.opening_name = opening
    g.played_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return g


def _run_stats(games):
    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: s
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.scalars.return_value.all.return_value = games

    with patch("chesslens.delivery.cli.settings") as mock_settings:
        mock_settings.username = "testuser"
        with patch("chesslens.delivery.cli.get_session", return_value=mock_session):
            return runner.invoke(app, ["stats"])


def test_stats_no_games():
    result = _run_stats([])
    assert result.exit_code == 0
    assert "No games found" in result.output


def test_stats_shows_rating():
    games = [_make_game(rating=1300)]
    result = _run_stats(games)
    assert result.exit_code == 0
    assert "1300" in result.output


def test_stats_shows_win_loss():
    games = [
        _make_game(result="win"),
        _make_game(result="loss"),
        _make_game(result="draw"),
    ]
    result = _run_stats(games)
    assert result.exit_code == 0
    assert "1W" in result.output
    assert "1L" in result.output


def test_stats_shows_timeout_count():
    games = [
        _make_game(end_reason="timeout", days_ago=2),
        _make_game(end_reason="timeout", days_ago=3),
        _make_game(end_reason="resigned"),
    ]
    result = _run_stats(games)
    assert result.exit_code == 0
    assert "Timeouts" in result.output
