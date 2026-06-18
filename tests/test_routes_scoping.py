"""Tests for protected route scoping (Tasks 5.1-5.3).

Strict TDD: written BEFORE the route protection is implemented.
Covers:
- /stats, /report, /game/last, /game/{game_id}, /opening/{name} require auth
- /health remains public
- /game/{game_id} returns 404 (not 403) for cross-user access
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
    """TestClient with in-memory DB, JWT secret set, init_db patched."""
    import chesslens.db.session as session_module

    test_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(session_module, "SessionLocal", test_factory)
    monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "test-secret-32-chars-long-padded!")
    monkeypatch.setattr("chesslens.delivery.security.settings.access_token_ttl_minutes", 15)
    monkeypatch.setattr("chesslens.delivery.security.settings.refresh_token_ttl_days", 7)

    from chesslens.delivery.api import app

    with patch("chesslens.delivery.api.init_db"):
        with TestClient(app) as c:
            yield c


@pytest.fixture()
def auth_headers(app_client):
    """Register alice and return auth headers for her."""
    app_client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "secret123", "chess_username": "alice"},
    )
    resp = app_client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "secret123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


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
# Task 5.1 — GET /stats requires auth
# ---------------------------------------------------------------------------


class TestStatsScoping:
    def test_stats_without_token_returns_401(self, app_client):
        """S-08: GET /stats with no auth returns 401."""
        response = app_client.get("/stats")
        assert response.status_code == 401

    def test_stats_with_valid_token_returns_200(self, app_client, auth_headers):
        """S-09: GET /stats with valid token returns 200."""
        rows = [_make_game_row(id=f"g{i}", username="alice") for i in range(3)]
        session_ctx = _make_session_ctx(rows=rows, scalar=rows[0])
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = app_client.get("/stats", headers=auth_headers)
        assert response.status_code == 200

    def test_stats_scoped_to_authenticated_user(self, app_client, auth_headers):
        """S-09: /stats data is scoped to the authenticated user's chess_username.

        The route must use current_user.chess_username as the DB query scope —
        not a query param. We verify this by supplying alice's token and confirming
        a successful response that references alice (via mock game rows).
        """
        rows = [_make_game_row(id=f"g{i}", username="alice") for i in range(3)]
        session_ctx = _make_session_ctx(rows=rows, scalar=rows[0])
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = app_client.get("/stats", headers=auth_headers)
        assert response.status_code == 200
        assert "alice" in response.text


# ---------------------------------------------------------------------------
# Task 5.2 — /report, /game/last, /opening/{name} require auth
# ---------------------------------------------------------------------------


class TestOtherRoutesScoping:
    def test_report_without_token_returns_401(self, app_client):
        response = app_client.get("/report")
        assert response.status_code == 401

    def test_game_last_without_token_returns_401(self, app_client):
        response = app_client.get("/game/last")
        assert response.status_code == 401

    def test_opening_without_token_returns_401(self, app_client):
        response = app_client.get("/opening/Sicilian%20Defense")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Task 5.3 — GET /game/{game_id} with ownership check
# ---------------------------------------------------------------------------


class TestGameByIdScoping:
    def test_game_by_id_without_token_returns_401(self, app_client):
        """S-08 variant: no auth → 401."""
        response = app_client.get("/game/abc123")
        assert response.status_code == 401

    def test_game_by_id_cross_user_returns_404(self, app_client, auth_headers):
        """S-10: alice token + bob's game → 404."""
        bob_game = _make_game_row(id="bob_game", username="bob")
        session_ctx = _make_session_ctx(scalar=bob_game)
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = app_client.get("/game/bob_game", headers=auth_headers)
        assert response.status_code == 404

    def test_game_by_id_cross_user_does_not_return_403(self, app_client, auth_headers):
        """S-10: explicitly assert that 403 is NOT returned for cross-user game."""
        bob_game = _make_game_row(id="bob_game", username="bob")
        session_ctx = _make_session_ctx(scalar=bob_game)
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = app_client.get("/game/bob_game", headers=auth_headers)
        assert response.status_code != 403


# ---------------------------------------------------------------------------
# Task 5.4 — /health remains public
# ---------------------------------------------------------------------------


class TestHealthRemainsPublic:
    def test_health_without_token_returns_200(self, app_client):
        """S-04 variant: health is still public after route protection."""
        response = app_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
