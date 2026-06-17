"""Tests for the FastAPI web delivery layer.

TDD-first: tests are written before implementation exists.
Uses starlette.testclient.TestClient (sync) and patches core functions.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

# --- helpers ---

def _make_game_row(
    id: str = "game1",
    username: str = "alice",
    result: str = "win",
    end_reason: str = "checkmate",
    player_rating: int = 1500,
    opponent_rating: int = 1490,
    opening_name: str | None = "Sicilian Defense",
    opening_eco: str | None = "B20",
    time_class: str = "blitz",
    color: str = "white",
    move_count: int = 30,
    pgn: str = "[Event ?]\n1. e4 e5",
    played_at: datetime | None = None,
) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.username = username
    row.result = result
    row.end_reason = end_reason
    row.player_rating = player_rating
    row.opponent_rating = opponent_rating
    row.opening_name = opening_name
    row.opening_eco = opening_eco
    row.time_class = time_class
    row.color = color
    row.move_count = move_count
    row.pgn = pgn
    row.opponent = "bob"
    row.played_at = played_at or datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    return row


_UNSET = object()  # sentinel for "caller did not pass a value"


def _make_session_ctx(rows=None, scalar=_UNSET):
    """Return a mock context manager for get_session().

    scalar=None explicitly means "scalar_one_or_none() returns None".
    Omitting scalar means the attribute is left as MagicMock default.
    """
    session = MagicMock()
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)
    if scalar is not _UNSET:
        session.execute.return_value.scalar_one_or_none.return_value = scalar
    if rows is not None:
        session.execute.return_value.scalars.return_value.all.return_value = rows
        session.execute.return_value.all.return_value = [(r.id,) for r in rows]
    return session


# --- fixtures ---

@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with a temp SQLite DB and init_db patched."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("CHESSLENS_DB_URL", f"sqlite:///{db_path}")

    # Patch init_db so lifespan does not try to create real tables
    with patch("chesslens.delivery.api.init_db"):
        from chesslens.delivery.api import app
        with TestClient(app) as c:
            yield c


# ===================================================================
# Phase 5 tests — written before implementation exists (RED phase)
# ===================================================================


# 5.2 — GET /health
class TestHealth:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_ok_body(self, client):
        response = client.get("/health")
        assert response.json() == {"status": "ok"}

    def test_health_content_type_json(self, client):
        response = client.get("/health")
        assert "application/json" in response.headers["content-type"]


# 5.3 — App boot smoke
class TestBoot:
    def test_app_boots_without_error(self, tmp_path, monkeypatch):
        """Confirm lifespan (init_db) runs without raising."""
        monkeypatch.setenv("CHESSLENS_DB_URL", f"sqlite:///{tmp_path}/smoke.db")
        with patch("chesslens.delivery.api.init_db") as mock_init:
            from chesslens.delivery.api import app
            with TestClient(app):
                pass
        mock_init.assert_called_once()


# 5.4 — run_async helper
class TestRunAsync:
    def test_run_async_returns_coroutine_result(self):
        """run_async executes a coroutine and returns its result from sync context."""
        from chesslens.delivery.api import run_async

        async def coro():
            return 42

        result = run_async(coro())
        assert result == 42

    def test_run_async_propagates_return_value(self):
        """run_async with a string-returning coroutine."""
        from chesslens.delivery.api import run_async

        async def greet(name: str) -> str:
            return f"hello {name}"

        result = run_async(greet("world"))
        assert result == "hello world"


# 5.5 — GET /stats happy path
class TestStats:
    def test_stats_happy_path_returns_200_html(self, client):
        rows = [_make_game_row(id=f"g{i}", username="alice") for i in range(3)]
        session_ctx = _make_session_ctx(rows=rows, scalar=rows[0])
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = client.get("/stats?username=alice")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    # 5.6 — missing username → 422
    def test_stats_missing_username_returns_422(self, client):
        response = client.get("/stats")
        assert response.status_code == 422


# 5.7 — GET /report — cached
class TestReportCached:
    def test_report_cached_returns_200_with_cached_html(self, client):
        cached_row = MagicMock()
        cached_row.html = "<html>cached</html>"
        session_ctx = _make_session_ctx(scalar=cached_row)
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = client.get("/report?username=alice&month=2026-05")
        assert response.status_code == 200
        assert "cached" in response.text


# 5.8 — GET /report — cache miss (generate fresh)
class TestReportCacheMiss:
    def test_report_cache_miss_generates_and_returns_html(self, client):
        from chesslens.core.parser import Game as DomainGame

        domain_game = MagicMock(spec=DomainGame)
        domain_game.id = "g1"

        # Session: no cached report; mark game as already existing so no INSERT is attempted
        no_cache = _make_session_ctx(rows=[])
        no_cache.execute.return_value.scalar_one_or_none.return_value = None
        # all() returns [("g1",)] so existing_ids = {"g1"} — skips GameRow insertion
        no_cache.execute.return_value.all.return_value = [("g1",)]

        with patch("chesslens.delivery.api.get_session", return_value=no_cache), \
             patch("chesslens.delivery.api.get_games", return_value=[MagicMock()]), \
             patch("chesslens.delivery.api.parse_games", return_value=[domain_game]), \
             patch("chesslens.delivery.api.analyze_game", return_value=None), \
             patch("chesslens.delivery.api.extract_patterns", return_value=MagicMock()), \
             patch("chesslens.delivery.api.generate_narrative", return_value="narrative"), \
             patch("chesslens.delivery.api._weekly_ratings", return_value=[1500]), \
             patch("chesslens.delivery.api.render_report", return_value="<html>report</html>"):
            response = client.get("/report?username=alice&month=2026-06")
        assert response.status_code == 200
        assert "<html>report</html>" in response.text


# 5.9 — GET /report — bad month format → 400
class TestReportBadMonth:
    def test_report_bad_month_returns_400(self, client):
        response = client.get("/report?username=alice&month=not-a-date")
        assert response.status_code == 400


# 5.10 — GET /report — unknown user → 404
class TestReportUnknownUser:
    def test_report_unknown_user_returns_404(self, client):
        from chesslens.core.fetcher import UserNotFoundError

        no_cache = _make_session_ctx(scalar=None, rows=[])
        no_cache.execute.return_value.scalar_one_or_none.return_value = None

        with patch("chesslens.delivery.api.get_session", return_value=no_cache), \
             patch("chesslens.delivery.api.get_games", side_effect=UserNotFoundError("alice")):
            response = client.get("/report?username=alice&month=2026-06")
        assert response.status_code == 404


# 5.11 — GET /game/last — happy path
class TestGameLast:
    def test_game_last_returns_200_html(self, client):
        game_row = _make_game_row(id="last1", username="alice")
        session_ctx = _make_session_ctx(scalar=game_row)

        with patch("chesslens.delivery.api.get_session", return_value=session_ctx), \
             patch("chesslens.delivery.api.analyze_game_detail", return_value=MagicMock()), \
             patch("chesslens.delivery.api.render_game", return_value="<html>game</html>"):
            response = client.get("/game/last?username=alice")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    # 5.12 — no games → 404
    def test_game_last_no_games_returns_404(self, client):
        session_ctx = _make_session_ctx(scalar=None)
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = client.get("/game/last?username=nobody")
        assert response.status_code == 404


# 5.13 — GET /game/{game_id} — found
class TestGameById:
    def test_game_by_id_returns_200(self, client):
        game_row = _make_game_row(id="abc123", username="alice")
        session_ctx = _make_session_ctx(scalar=game_row)

        with patch("chesslens.delivery.api.get_session", return_value=session_ctx), \
             patch("chesslens.delivery.api.analyze_game_detail", return_value=MagicMock()), \
             patch("chesslens.delivery.api.render_game", return_value="<html>game</html>"):
            response = client.get("/game/abc123")
        assert response.status_code == 200

    # 5.14 — not found → 404
    def test_game_by_id_not_found_returns_404(self, client):
        session_ctx = _make_session_ctx(scalar=None)
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = client.get("/game/missing")
        assert response.status_code == 404


# 5.15 — GET /opening/{name} — found
class TestOpening:
    def test_opening_found_returns_200(self, client):
        rows = [_make_game_row(id=f"g{i}", username="alice", opening_name="Sicilian Defense") for i in range(5)]
        session_ctx = _make_session_ctx(rows=rows)
        breakdown = MagicMock()

        with patch("chesslens.delivery.api.get_session", return_value=session_ctx), \
             patch("chesslens.delivery.api.extract_opening_breakdown", return_value=breakdown), \
             patch("chesslens.delivery.api.render_opening", return_value="<html>opening</html>"):
            response = client.get("/opening/Sicilian%20Defense?username=alice")
        assert response.status_code == 200

    # 5.16 — not found → 404
    def test_opening_not_found_returns_404(self, client):
        rows = [_make_game_row(id=f"g{i}", username="alice") for i in range(3)]
        session_ctx = _make_session_ctx(rows=rows)

        with patch("chesslens.delivery.api.get_session", return_value=session_ctx), \
             patch("chesslens.delivery.api.extract_opening_breakdown", return_value=None):
            response = client.get("/opening/Kings%20Gambit?username=alice")
        assert response.status_code == 404


# 5.17 — Username isolation (no route reads settings.username)
class TestUsernameIsolation:
    def test_report_uses_request_username_not_settings(self, client):
        """Route must use 'alice' from query param, not 'other' from settings."""
        cached_row = MagicMock()
        cached_row.html = "<html>alice-data</html>"
        session_ctx = _make_session_ctx(scalar=cached_row)

        with patch("chesslens.delivery.api.get_session", return_value=session_ctx), \
             patch("chesslens.delivery.api.settings") as mock_settings:
            mock_settings.username = "other"
            response = client.get("/report?username=alice&month=2026-05")
        assert response.status_code == 200
        assert "alice-data" in response.text
