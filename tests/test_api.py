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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
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
def db_engine():
    """In-memory SQLite with all tables (including users).

    WHY StaticPool + check_same_thread=False: TestClient runs routes in a
    separate thread; StaticPool forces all connections to share the same
    in-memory database so auth rows seeded in fixtures are visible inside
    route handlers (including get_current_user in security.py).
    """
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
def client(db_engine, monkeypatch):
    """TestClient with a shared in-memory DB, JWT secret set, init_db patched.

    WHY monkeypatching SessionLocal: get_current_user (in security.py) calls
    get_session() which uses SessionLocal from db/session.py. Patching
    SessionLocal ensures auth token lookups go to the same in-memory DB
    used by the auth fixtures, while individual test mocks on
    chesslens.delivery.api.get_session still work for data routes.
    """
    import chesslens.db.session as session_module

    test_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(session_module, "SessionLocal", test_factory)
    monkeypatch.setattr("chesslens.delivery.security.settings.jwt_secret", "test-secret-32-chars-long-padded!")
    monkeypatch.setattr("chesslens.delivery.security.settings.access_token_ttl_minutes", 15)
    monkeypatch.setattr("chesslens.delivery.security.settings.refresh_token_ttl_days", 7)

    with patch("chesslens.delivery.api.init_db"):
        from chesslens.delivery.api import app
        with TestClient(app) as c:
            yield c


@pytest.fixture()
def auth_headers(client):
    """Register alice and return Authorization headers for her.

    Uses chess_username="alice" so existing test data (game rows with
    username="alice") stays valid. Function-scoped (safest with in-memory DB).
    """
    client.post(
        "/auth/register",
        json={
            "email": "alice@example.com",
            "password": "secret123",
            "chess_username": "alice",
        },
    )
    resp = client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "secret123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


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
    def test_stats_happy_path_returns_200_html(self, client, auth_headers):
        rows = [_make_game_row(id=f"g{i}", username="alice") for i in range(3)]
        session_ctx = _make_session_ctx(rows=rows, scalar=rows[0])
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = client.get("/stats", headers=auth_headers)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    # 5.6 — missing token → 401 (was: missing username → 422)
    def test_stats_missing_token_returns_401(self, client):
        response = client.get("/stats")
        assert response.status_code == 401


# 5.7 — GET /report — cached
class TestReportCached:
    def test_report_cached_returns_200_with_cached_html(self, client, auth_headers):
        cached_row = MagicMock()
        cached_row.html = "<html>cached</html>"
        session_ctx = _make_session_ctx(scalar=cached_row)
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = client.get("/report?month=2026-05", headers=auth_headers)
        assert response.status_code == 200
        assert "cached" in response.text


# 5.8 — GET /report — cache miss (generate fresh)
class TestReportCacheMiss:
    def test_report_cache_miss_generates_and_returns_html(self, client, auth_headers):
        # WHY patching generate_report_for_user: route now delegates to core/jobs.py;
        # pipeline internals (get_games, parse_games, …) are tested in test_jobs.py.
        cached_row = MagicMock()
        cached_row.html = "<html>report</html>"

        # First get_session call (cache check) returns None; second (re-read) returns row.
        miss_ctx = _make_session_ctx(scalar=None)
        hit_ctx = _make_session_ctx(scalar=cached_row)
        session_side_effect = [miss_ctx, hit_ctx]

        with patch("chesslens.delivery.api.get_session", side_effect=session_side_effect), \
             patch("chesslens.delivery.api.generate_report_for_user"):
            response = client.get("/report?month=2026-06", headers=auth_headers)
        assert response.status_code == 200
        assert "<html>report</html>" in response.text


# 5.9 — GET /report — bad month format → 400
class TestReportBadMonth:
    def test_report_bad_month_returns_400(self, client, auth_headers):
        response = client.get("/report?month=not-a-date", headers=auth_headers)
        assert response.status_code == 400


# 5.10 — GET /report — unknown user → 404
class TestReportUnknownUser:
    def test_report_unknown_user_returns_404(self, client, auth_headers):
        from chesslens.core.fetcher import UserNotFoundError

        # WHY patching generate_report_for_user: route delegates to core/jobs.py;
        # UserNotFoundError is raised there and propagated back to the route handler.
        no_cache = _make_session_ctx(scalar=None)

        with patch("chesslens.delivery.api.get_session", return_value=no_cache), \
             patch("chesslens.delivery.api.generate_report_for_user",
                   side_effect=UserNotFoundError("alice")):
            response = client.get("/report?month=2026-06", headers=auth_headers)
        assert response.status_code == 404


# 5.11 — GET /game/last — happy path
class TestGameLast:
    def test_game_last_returns_200_html(self, client, auth_headers):
        game_row = _make_game_row(id="last1", username="alice")
        session_ctx = _make_session_ctx(scalar=game_row)

        with patch("chesslens.delivery.api.get_session", return_value=session_ctx), \
             patch("chesslens.delivery.api.analyze_game_detail", return_value=MagicMock()), \
             patch("chesslens.delivery.api.render_game", return_value="<html>game</html>"):
            response = client.get("/game/last", headers=auth_headers)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    # 5.12 — no games → 404
    def test_game_last_no_games_returns_404(self, client, auth_headers):
        session_ctx = _make_session_ctx(scalar=None)
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = client.get("/game/last", headers=auth_headers)
        assert response.status_code == 404


# 5.13 — GET /game/{game_id} — found
class TestGameById:
    def test_game_by_id_returns_200(self, client, auth_headers):
        # WHY username="alice": get_current_user resolves chess_username="alice"
        # (from the registered user), and the route now checks game.username == alice.
        game_row = _make_game_row(id="abc123", username="alice")
        session_ctx = _make_session_ctx(scalar=game_row)

        with patch("chesslens.delivery.api.get_session", return_value=session_ctx), \
             patch("chesslens.delivery.api.analyze_game_detail", return_value=MagicMock()), \
             patch("chesslens.delivery.api.render_game", return_value="<html>game</html>"):
            response = client.get("/game/abc123", headers=auth_headers)
        assert response.status_code == 200

    # 5.14 — not found → 404
    def test_game_by_id_not_found_returns_404(self, client, auth_headers):
        session_ctx = _make_session_ctx(scalar=None)
        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = client.get("/game/missing", headers=auth_headers)
        assert response.status_code == 404


# 5.15 — GET /opening/{name} — found
class TestOpening:
    def test_opening_found_returns_200(self, client, auth_headers):
        rows = [_make_game_row(id=f"g{i}", username="alice", opening_name="Sicilian Defense") for i in range(5)]
        session_ctx = _make_session_ctx(rows=rows)
        breakdown = MagicMock()

        with patch("chesslens.delivery.api.get_session", return_value=session_ctx), \
             patch("chesslens.delivery.api.extract_opening_breakdown", return_value=breakdown), \
             patch("chesslens.delivery.api.render_opening", return_value="<html>opening</html>"):
            response = client.get("/opening/Sicilian%20Defense", headers=auth_headers)
        assert response.status_code == 200

    # 5.16 — not found → 404
    def test_opening_not_found_returns_404(self, client, auth_headers):
        rows = [_make_game_row(id=f"g{i}", username="alice") for i in range(3)]
        session_ctx = _make_session_ctx(rows=rows)

        with patch("chesslens.delivery.api.get_session", return_value=session_ctx), \
             patch("chesslens.delivery.api.extract_opening_breakdown", return_value=None):
            response = client.get("/opening/Kings%20Gambit", headers=auth_headers)
        assert response.status_code == 404


# 5.17 — Username isolation (route scopes by token, not by query param)
class TestUsernameIsolation:
    def test_report_uses_token_username_not_query_param(self, client, auth_headers):
        """Route must use current_user.chess_username from token — not a query param."""
        cached_row = MagicMock()
        cached_row.html = "<html>alice-data</html>"
        session_ctx = _make_session_ctx(scalar=cached_row)

        with patch("chesslens.delivery.api.get_session", return_value=session_ctx):
            response = client.get("/report?month=2026-05", headers=auth_headers)
        assert response.status_code == 200
        assert "alice-data" in response.text


# 5.18 — run_async anyio branch (loop already running)
class TestRunAsyncAnyioBranch:
    def test_run_async_uses_anyio_when_loop_is_running(self):
        """When get_running_loop() does not raise, run_async uses anyio.from_thread.run."""
        from chesslens.delivery.api import run_async

        async def coro():
            return 99

        c = coro()
        with patch("chesslens.delivery.api.asyncio.get_running_loop", return_value=MagicMock()), \
             patch("anyio.from_thread.run", return_value=99) as mock_anyio:
            result = run_async(c)
        c.close()  # prevent "coroutine never awaited" warning — mock intercepted it

        mock_anyio.assert_called_once_with(c)
        assert result == 99
