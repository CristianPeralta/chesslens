"""Tests for background job pipeline and scheduler wiring.

TDD-first (RED phase): tests are written before implementation exists.
All imports of chesslens.core.jobs will fail with ImportError until Phase 3.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from chesslens.db.models import Base, ReportRow, UserRow


# --- DB fixture (in-memory SQLite, shared pool) ---

@pytest.fixture()
def db_engine():
    """In-memory SQLite with all tables.

    WHY StaticPool + check_same_thread=False: jobs and test share threads;
    StaticPool keeps one connection so seeded rows are visible inside the job.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine, monkeypatch):
    """Patch chesslens.db.session.SessionLocal to use the in-memory engine."""
    import chesslens.db.session as session_module

    test_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    monkeypatch.setattr(session_module, "SessionLocal", test_factory)
    yield test_factory


# --- helper: seed a ReportRow ---

def _seed_report(db_session, username: str, month: str) -> None:
    with db_session() as s:
        s.add(ReportRow(username=username, month=month, html="<html/>", narrative="n"))
        s.commit()


# --- helper: seed a UserRow ---

def _seed_user(db_session, chess_username: str) -> None:
    with db_session() as s:
        s.add(UserRow(
            email=f"{chess_username}@example.com",
            password_hash="x",
            chess_username=chess_username,
        ))
        s.commit()


# ===================================================================
# 2.1 — Idempotency: early-return when ReportRow already exists
# ===================================================================

def test_generate_report_for_user_skips_when_already_cached(db_session, monkeypatch):
    """generate_report_for_user must not call get_games if report is already cached."""
    from chesslens.core.jobs import generate_report_for_user  # noqa: PLC0415

    _seed_report(db_session, "alice", "2026-05")

    get_games_spy = MagicMock()
    monkeypatch.setattr("chesslens.core.jobs.get_games", get_games_spy)

    generate_report_for_user("alice", "2026-05")

    get_games_spy.assert_not_called()

    # exactly one row still
    with db_session() as s:
        count = s.query(ReportRow).filter_by(username="alice", month="2026-05").count()
    assert count == 1


# ===================================================================
# 2.2 — Happy path: full pipeline inserts one ReportRow
# ===================================================================

def test_generate_report_for_user_happy_path_inserts_row(db_session, monkeypatch):
    """Happy path: mock pipeline, assert exactly one ReportRow written."""
    from chesslens.core.jobs import generate_report_for_user  # noqa: PLC0415
    from chesslens.core.parser import Game as DomainGame  # noqa: PLC0415

    raw_game = MagicMock()
    raw_game.id = "g1"

    # WHY real DomainGame fields: GameRow insert requires proper Python types (datetime, str, int).
    domain_game = DomainGame(
        id="g1",
        username="bob",
        played_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
        time_class="blitz",
        color="white",
        result="win",
        end_reason="checkmate",
        opponent="eve",
        player_rating=1500,
        opponent_rating=1490,
        opening_eco="B20",
        opening_name="Sicilian Defense",
        move_count=30,
        pgn="[Event ?]\n1. e4 c5",
    )

    # WHY AsyncMock: get_games is a coroutine; asyncio.run() needs an awaitable.
    monkeypatch.setattr("chesslens.core.jobs.get_games", AsyncMock(return_value=[raw_game]))
    monkeypatch.setattr("chesslens.core.jobs.parse_games", MagicMock(return_value=[domain_game]))
    monkeypatch.setattr("chesslens.core.jobs.analyze_game", MagicMock(return_value=None))
    monkeypatch.setattr("chesslens.core.jobs.extract_patterns", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr("chesslens.core.jobs.generate_narrative", MagicMock(return_value="narrative"))
    monkeypatch.setattr("chesslens.core.jobs.render_report", MagicMock(return_value="<html>report</html>"))
    monkeypatch.setattr(
        "chesslens.core.jobs._weekly_ratings",
        MagicMock(return_value=[1500]),
    )

    generate_report_for_user("bob", "2026-05")

    with db_session() as s:
        count = s.query(ReportRow).filter_by(username="bob", month="2026-05").count()
    assert count == 1


# ===================================================================
# 2.3 — No-games path: empty list → no ReportRow, no exception
# ===================================================================

def test_generate_report_for_user_no_games_does_not_raise(db_session, monkeypatch):
    """When get_games returns [], no ReportRow is written and no exception raised."""
    from chesslens.core.jobs import generate_report_for_user  # noqa: PLC0415

    # WHY AsyncMock: get_games is a coroutine; asyncio.run() needs an awaitable.
    monkeypatch.setattr("chesslens.core.jobs.get_games", AsyncMock(return_value=[]))

    generate_report_for_user("charlie", "2026-05")  # must not raise

    with db_session() as s:
        count = s.query(ReportRow).filter_by(username="charlie", month="2026-05").count()
    assert count == 0


# ===================================================================
# 2.4 — Batch iteration: _run_monthly_reports calls generate_report_for_user per user
# ===================================================================

@pytest.mark.asyncio
async def test_run_monthly_reports_calls_job_for_each_user(db_session, monkeypatch):
    """_run_monthly_reports coroutine must call generate_report_for_user once per user."""
    _seed_user(db_session, "alice")
    _seed_user(db_session, "bob")

    spy = MagicMock()
    monkeypatch.setattr("chesslens.delivery.api.generate_report_for_user", spy)

    from chesslens.delivery.api import _run_monthly_reports  # noqa: PLC0415

    await _run_monthly_reports()

    assert spy.call_count == 2
    called_usernames = {c.args[0] for c in spy.call_args_list}
    assert called_usernames == {"alice", "bob"}

    # All calls use the same prev_month string
    prev_months = {c.args[1] for c in spy.call_args_list}
    assert len(prev_months) == 1  # same month for all users


# ===================================================================
# 2.5 — Error isolation: one user failing does not stop the batch
# ===================================================================

@pytest.mark.asyncio
async def test_run_monthly_reports_isolates_errors(db_session, monkeypatch):
    """A RuntimeError for user 2 must not prevent users 1 and 3 from completing."""
    _seed_user(db_session, "user1")
    _seed_user(db_session, "user2")
    _seed_user(db_session, "user3")

    completed: list[str] = []

    def spy(username: str, month: str) -> None:
        if username == "user2":
            raise RuntimeError("pipeline exploded")
        completed.append(username)

    monkeypatch.setattr("chesslens.delivery.api.generate_report_for_user", spy)

    from chesslens.delivery.api import _run_monthly_reports  # noqa: PLC0415

    await _run_monthly_reports()  # must not raise

    assert "user1" in completed
    assert "user3" in completed
    assert "user2" not in completed


# ===================================================================
# 2.6 — Scheduler registration: add_job called with correct args in lifespan
# ===================================================================

def test_scheduler_registered_with_correct_cron_trigger(monkeypatch):
    """Lifespan startup must call scheduler.add_job with CronTrigger(day=1, hour=0, minute=5)
    and id='monthly_reports'."""
    from apscheduler.triggers.cron import CronTrigger
    from starlette.testclient import TestClient

    mock_scheduler = MagicMock()
    mock_scheduler_cls = MagicMock(return_value=mock_scheduler)

    with patch("chesslens.delivery.api.init_db"), \
         patch("chesslens.delivery.api.AsyncIOScheduler", mock_scheduler_cls):
        from chesslens.delivery.api import app
        with TestClient(app):
            pass

    mock_scheduler.add_job.assert_called_once()
    call_kwargs = mock_scheduler.add_job.call_args

    # Second positional arg (or keyword 'trigger') should be a CronTrigger
    trigger = call_kwargs.args[1] if len(call_kwargs.args) > 1 else call_kwargs.kwargs.get("trigger")
    assert isinstance(trigger, CronTrigger), f"Expected CronTrigger, got {type(trigger)}"

    # Inspect field values on the CronTrigger
    fields = {f.name: f for f in trigger.fields}
    assert str(fields["day"]) == "1", f"Expected day=1, got {fields['day']}"
    assert str(fields["hour"]) == "0", f"Expected hour=0, got {fields['hour']}"
    assert str(fields["minute"]) == "5", f"Expected minute=5, got {fields['minute']}"

    # job id
    job_id = call_kwargs.kwargs.get("id") or (call_kwargs.args[2] if len(call_kwargs.args) > 2 else None)
    assert job_id == "monthly_reports"
