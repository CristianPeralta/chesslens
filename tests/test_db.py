"""Tests for SQLite persistence layer (db/models.py, db/session.py).

Strict TDD: this file was written BEFORE the implementation.
"""
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    """In-memory SQLite engine with all tables created."""
    # Import here so the test fails (RED) when models don't exist yet
    from chesslens.db.models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """Bare Session (not the context-manager version) for direct ORM operations."""
    session = Session(bind=db_engine)
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Task 4.1 — init_db() delegates to Alembic upgrade head
# ---------------------------------------------------------------------------


def test_init_db_calls_alembic_upgrade():
    """init_db() must invoke alembic command.upgrade(cfg, 'head') — not create_all()."""
    from unittest.mock import patch

    from chesslens.db.session import init_db

    with patch("chesslens.db.session.command") as mock_command:
        init_db()
        mock_command.upgrade.assert_called_once()
        # Second positional argument must be "head"
        assert mock_command.upgrade.call_args[0][1] == "head"


def test_init_db_creates_all_tables(tmp_path):
    """init_db() on a fresh SQLite DB creates games, analysis, and reports tables."""
    from unittest.mock import patch

    from sqlalchemy import create_engine

    db_url = f"sqlite:///{tmp_path}/test.db"

    # Patch settings.db_url so Alembic env.py targets the temp file DB.
    # A file-based SQLite is required because Alembic's NullPool engine
    # creates a new connection per migration step (in-memory would be empty).
    with patch("chesslens.config.settings.database_url", db_url):
        from chesslens.db.session import init_db

        init_db()

    verify_engine = create_engine(db_url)
    table_names = inspect(verify_engine).get_table_names()
    assert "games" in table_names
    assert "analysis" in table_names
    assert "reports" in table_names
    verify_engine.dispose()


# ---------------------------------------------------------------------------
# Task 4.2 — GameRow round-trip (all fields, including None openings)
# ---------------------------------------------------------------------------

_PLAYED_AT = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)


def _game_row():
    from chesslens.db.models import GameRow

    return GameRow(
        id="abc123",
        username="krix0s",
        played_at=_PLAYED_AT,
        time_class="blitz",
        color="white",
        result="win",
        end_reason="resigned",
        opponent="magnus",
        player_rating=1500,
        opponent_rating=1600,
        opening_eco="D00",
        opening_name="Queen's Pawn",
        move_count=30,
        pgn="1. d4 d5 *",
    )


def test_game_row_round_trip(db_session):
    """GameRow can be inserted and retrieved with all non-None fields intact."""
    row = _game_row()
    db_session.add(row)
    db_session.commit()

    fetched: object = db_session.get(type(row), "abc123")
    assert fetched is not None
    assert fetched.id == "abc123"
    assert fetched.username == "krix0s"
    assert fetched.time_class == "blitz"
    assert fetched.color == "white"
    assert fetched.result == "win"
    assert fetched.end_reason == "resigned"
    assert fetched.opponent == "magnus"
    assert fetched.player_rating == 1500
    assert fetched.opponent_rating == 1600
    assert fetched.opening_eco == "D00"
    assert fetched.opening_name == "Queen's Pawn"
    assert fetched.move_count == 30
    assert fetched.pgn == "1. d4 d5 *"


def test_game_row_played_at_utc_value(db_session):
    """played_at UTC value survives the round-trip.

    SQLite stores timestamps without timezone info; we compare the UTC value
    to avoid tz-awareness issues (known SQLite/SQLAlchemy caveat).
    """
    row = _game_row()
    db_session.add(row)
    db_session.commit()

    from chesslens.db.models import GameRow

    fetched = db_session.get(GameRow, "abc123")
    # Compare the actual point in time; SQLite may return naive datetime
    stored_utc = fetched.played_at
    if stored_utc.tzinfo is None:
        # SQLite returned naive — treat as UTC for comparison
        assert stored_utc.replace(tzinfo=timezone.utc) == _PLAYED_AT
    else:
        assert stored_utc == _PLAYED_AT


def test_game_row_none_openings(db_session):
    """GameRow openings can be None (optional fields)."""
    from chesslens.db.models import GameRow

    row = GameRow(
        id="no_eco",
        username="krix0s",
        played_at=_PLAYED_AT,
        time_class="rapid",
        color="black",
        result="loss",
        end_reason="checkmate",
        opponent="hikaru",
        player_rating=1400,
        opponent_rating=1700,
        opening_eco=None,
        opening_name=None,
        move_count=15,
        pgn="1. e4 e5 *",
    )
    db_session.add(row)
    db_session.commit()

    fetched = db_session.get(GameRow, "no_eco")
    assert fetched.opening_eco is None
    assert fetched.opening_name is None


# ---------------------------------------------------------------------------
# Task 4.3 — AnalysisRow FK round-trip (timeout_move=None)
# ---------------------------------------------------------------------------


def test_analysis_row_round_trip(db_session):
    """AnalysisRow inserts and retrieves with timeout_move=None."""
    from chesslens.db.models import AnalysisRow, GameRow

    game = _game_row()
    db_session.add(game)
    db_session.flush()

    analysis = AnalysisRow(
        game_id="abc123",
        accuracy=85.5,
        avg_centipawn_loss=30.2,
        blunders=1,
        mistakes=2,
        inaccuracies=3,
        timeout_move=None,
    )
    db_session.add(analysis)
    db_session.commit()

    fetched = db_session.get(AnalysisRow, "abc123")
    assert fetched is not None
    assert fetched.game_id == "abc123"
    assert fetched.accuracy == pytest.approx(85.5)
    assert fetched.avg_centipawn_loss == pytest.approx(30.2)
    assert fetched.blunders == 1
    assert fetched.mistakes == 2
    assert fetched.inaccuracies == 3
    assert fetched.timeout_move is None


def test_analysis_row_timeout_move_value(db_session):
    """AnalysisRow stores a non-None timeout_move ply correctly."""
    from chesslens.db.models import AnalysisRow, GameRow

    game = GameRow(
        id="timeout_game",
        username="krix0s",
        played_at=_PLAYED_AT,
        time_class="blitz",
        color="white",
        result="loss",
        end_reason="timeout",
        opponent="somebody",
        player_rating=1500,
        opponent_rating=1500,
        opening_eco=None,
        opening_name=None,
        move_count=40,
        pgn="1. e4 *",
    )
    db_session.add(game)
    db_session.flush()

    analysis = AnalysisRow(
        game_id="timeout_game",
        accuracy=60.0,
        avg_centipawn_loss=80.0,
        blunders=3,
        mistakes=4,
        inaccuracies=5,
        timeout_move=38,
    )
    db_session.add(analysis)
    db_session.commit()

    fetched = db_session.get(AnalysisRow, "timeout_game")
    assert fetched.timeout_move == 38


# ---------------------------------------------------------------------------
# Task 4.4 — ReportRow unique constraint
# ---------------------------------------------------------------------------


def test_report_row_unique_constraint(db_session):
    """Inserting two ReportRows with the same (username, month) raises IntegrityError."""
    from chesslens.db.models import ReportRow

    r1 = ReportRow(
        username="krix0s",
        month="2026-05",
        html="<html>1</html>",
        narrative="First report",
    )
    db_session.add(r1)
    db_session.commit()

    r2 = ReportRow(
        username="krix0s",
        month="2026-05",
        html="<html>2</html>",
        narrative="Duplicate",
    )
    db_session.add(r2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_report_row_different_months_allowed(db_session):
    """Same username with different months does NOT violate the unique constraint."""
    from chesslens.db.models import ReportRow

    r1 = ReportRow(username="krix0s", month="2026-04", html="<h>a</h>", narrative="April")
    r2 = ReportRow(username="krix0s", month="2026-05", html="<h>b</h>", narrative="May")
    db_session.add_all([r1, r2])
    db_session.commit()  # must NOT raise

    from chesslens.db.models import ReportRow as RR

    count = db_session.query(RR).filter_by(username="krix0s").count()
    assert count == 2


# ---------------------------------------------------------------------------
# Task 4.5 — get_session() rollback on exception
# ---------------------------------------------------------------------------


def test_get_session_commits_on_success(db_engine):
    """get_session() commits when the block exits without exception."""
    import chesslens.db.session as db_session_module
    from chesslens.db.models import GameRow
    from chesslens.db.session import get_session

    original_factory = db_session_module.SessionLocal
    from sqlalchemy.orm import sessionmaker

    db_session_module.SessionLocal = sessionmaker(bind=db_engine, expire_on_commit=False)
    try:
        with get_session() as session:
            session.add(_game_row())

        # Verify committed via a fresh session
        with get_session() as session:
            result = session.get(GameRow, "abc123")
            assert result is not None
            assert result.id == "abc123"
    finally:
        db_session_module.SessionLocal = original_factory


def test_get_session_rollback_on_exception(db_engine):
    """get_session() rolls back when the block raises an exception."""
    import chesslens.db.session as db_session_module
    from chesslens.db.models import GameRow
    from chesslens.db.session import get_session

    original_factory = db_session_module.SessionLocal
    from sqlalchemy.orm import sessionmaker

    db_session_module.SessionLocal = sessionmaker(bind=db_engine, expire_on_commit=False)
    try:
        with pytest.raises(RuntimeError):
            with get_session() as session:
                session.add(_game_row())
                raise RuntimeError("forced failure")

        # Row must NOT be in the DB after rollback
        with get_session() as session:
            result = session.get(GameRow, "abc123")
            assert result is None
    finally:
        db_session_module.SessionLocal = original_factory


# ---------------------------------------------------------------------------
# Task 2.1 — UserRow model
# ---------------------------------------------------------------------------


def test_userrow_table_name_is_users():
    """UserRow.__tablename__ must be 'users'."""
    from chesslens.db.models import UserRow

    assert UserRow.__tablename__ == "users"


def test_userrow_has_required_columns(db_engine):
    """UserRow can be inserted and retrieved with all fields intact."""
    from chesslens.db.models import UserRow

    now = datetime.now(timezone.utc)
    user = UserRow(
        email="alice@example.com",
        password_hash="$2b$12$fakehash",
        chess_username="alice_chess",
        created_at=now,
    )
    with Session(bind=db_engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)
        fetched_id = user.id

    with Session(bind=db_engine) as session:
        fetched = session.get(UserRow, fetched_id)
        assert fetched is not None
        assert fetched.email == "alice@example.com"
        assert fetched.password_hash == "$2b$12$fakehash"
        assert fetched.chess_username == "alice_chess"
        assert fetched.id is not None


def test_userrow_email_unique_constraint(db_engine):
    """UserRow email must be unique — duplicate email raises IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    from chesslens.db.models import UserRow

    now = datetime.now(timezone.utc)
    u1 = UserRow(
        email="bob@example.com",
        password_hash="$2b$12$hash1",
        chess_username="bob_chess",
        created_at=now,
    )
    u2 = UserRow(
        email="bob@example.com",
        password_hash="$2b$12$hash2",
        chess_username="bob_chess2",
        created_at=now,
    )
    with Session(bind=db_engine) as session:
        session.add(u1)
        session.commit()

    with Session(bind=db_engine) as session:
        session.add(u2)
        with pytest.raises(IntegrityError):
            session.commit()
