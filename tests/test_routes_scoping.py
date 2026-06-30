"""Tests for protected route scoping.

Covers:
- /stats, /report, /game/last, /game/{game_id}, /opening/{name} require a
  chess_username cookie; missing cookie redirects to / (302)
- /health remains public
- GET / serves the landing page
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    from chesslens.db.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def app_client(db_engine, monkeypatch):
    """TestClient with in-memory DB and init_db patched."""
    import chesslens.db.session as session_module

    test_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(session_module, "SessionLocal", test_factory)

    from chesslens.delivery.api import app

    with patch("chesslens.delivery.api.init_db"):
        with TestClient(app) as c:
            yield c


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


_UNSET = object()


def _make_session_ctx(rows=None, scalar=_UNSET):
    session = MagicMock()
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)
    if scalar is not _UNSET:
        session.execute.return_value.scalar_one_or_none.return_value = scalar
    if rows is not None:
        session.execute.return_value.scalars.return_value.all.return_value = rows
        session.execute.return_value.all.return_value = [(r.id,) for r in rows]
    return session


# ---------------------------------------------------------------------------
# Task 5.1 — GET /stats requires cookie
# ---------------------------------------------------------------------------


class TestStatsScoping:
    def test_stats_without_cookie_returns_302(self, app_client):
        """GET /stats with no cookie redirects to landing (302)."""
        response = app_client.get("/stats", follow_redirects=False)
        assert response.status_code == 302

    def test_stats_with_cookie_returns_200(self, app_client):
        """GET /stats with valid cookie returns 200."""
        rows = [_make_game_row(id=f"g{i}", username="alice") for i in range(3)]
        session_ctx = _make_session_ctx(rows=rows, scalar=rows[0])
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = app_client.get("/stats", cookies={"chess_username": "alice"})
        assert response.status_code == 200

    def test_stats_scoped_to_cookie_username(self, app_client):
        """GET /stats data is scoped to the chess_username cookie value."""
        rows = [_make_game_row(id=f"g{i}", username="alice") for i in range(3)]
        session_ctx = _make_session_ctx(rows=rows, scalar=rows[0])
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = app_client.get("/stats", cookies={"chess_username": "alice"})
        assert response.status_code == 200
        assert "alice" in response.text


# ---------------------------------------------------------------------------
# Task 5.2 — /report, /game/last, /opening/{name} require cookie
# ---------------------------------------------------------------------------


class TestOtherRoutesScoping:
    def test_report_without_cookie_returns_302(self, app_client):
        response = app_client.get("/report", follow_redirects=False)
        assert response.status_code == 302

    def test_game_last_without_cookie_returns_302(self, app_client):
        response = app_client.get("/game/last", follow_redirects=False)
        assert response.status_code == 302

    def test_opening_without_cookie_returns_302(self, app_client):
        response = app_client.get("/opening/Sicilian%20Defense", follow_redirects=False)
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# Task 5.3 — GET /game/{game_id} requires cookie
# ---------------------------------------------------------------------------


class TestGameByIdScoping:
    def test_game_by_id_without_cookie_returns_302(self, app_client):
        """No cookie → redirect to landing."""
        response = app_client.get("/game/abc123", follow_redirects=False)
        assert response.status_code == 302

    def test_game_by_id_not_found_returns_404(self, app_client):
        """Cookie present + game not in DB → 404."""
        session_ctx = _make_session_ctx(scalar=None)
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = app_client.get(
                "/game/missing_game", cookies={"chess_username": "alice"}
            )
        assert response.status_code == 404

    def test_game_by_id_not_found_does_not_return_403(self, app_client):
        """Missing game returns 404, never 403."""
        session_ctx = _make_session_ctx(scalar=None)
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = app_client.get(
                "/game/missing_game", cookies={"chess_username": "alice"}
            )
        assert response.status_code != 403


# ---------------------------------------------------------------------------
# Task 5.4 — /health remains public
# ---------------------------------------------------------------------------


class TestHealthRemainsPublic:
    def test_health_without_cookie_returns_200(self, app_client):
        """Health endpoint is still public — no cookie required."""
        response = app_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------


class TestLandingPage:
    def test_root_returns_200(self, app_client):
        """GET / serves the landing page."""
        response = app_client.get("/")
        assert response.status_code == 200
        assert "chess_username" in response.text
