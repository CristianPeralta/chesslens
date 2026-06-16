"""Tests for the report CLI command."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from chesslens.delivery.cli import app

runner = CliRunner()


def _mock_settings(username="testuser"):
    m = MagicMock()
    m.username = username
    m.reports_dir = MagicMock()
    m.reports_dir.__truediv__ = lambda s, o: MagicMock()
    return m


def _run_report(month=None, cached_report=None, raw_games=None):
    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: s
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.scalar_one_or_none.return_value = cached_report
    mock_session.execute.return_value.scalars.return_value.all.return_value = []
    mock_session.execute.return_value.all.return_value = []

    args = ["report"]
    if month:
        args += ["--month", month]

    with patch("chesslens.delivery.cli.settings", _mock_settings()), \
         patch("chesslens.delivery.cli.init_db"), \
         patch("chesslens.delivery.cli.get_session", return_value=mock_session), \
         patch("chesslens.delivery.cli.get_games", return_value=raw_games or []), \
         patch("chesslens.delivery.cli.parse_games", return_value=[]), \
         patch("chesslens.delivery.cli.extract_patterns"), \
         patch("chesslens.delivery.cli.generate_narrative", return_value="narrative"), \
         patch("chesslens.delivery.cli.render_report", return_value="<html></html>"), \
         patch("chesslens.delivery.cli.webbrowser.open"), \
         patch("chesslens.delivery.cli._open_html"):
        return runner.invoke(app, args)


def test_report_invalid_month_format():
    result = _run_report(month="2026/05")
    assert result.exit_code == 1
    assert "Invalid month format" in result.output


def test_report_uses_cache_when_available():
    cached = MagicMock()
    cached.html = "<html>cached</html>"
    result = _run_report(cached_report=cached)
    assert result.exit_code == 0
    assert "cached" in result.output.lower()


def test_report_no_games_found():
    result = _run_report(raw_games=[])
    assert result.exit_code == 0
    assert "No blitz games" in result.output


def test_report_requires_username():
    with patch("chesslens.delivery.cli.settings") as m:
        m.username = ""
        result = runner.invoke(app, ["report"])
    assert result.exit_code == 1
    assert "No username set" in result.output
