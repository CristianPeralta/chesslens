"""chesslens.db — SQLite persistence layer.

Public API:
    Base, GameRow, AnalysisRow, ReportRow  — ORM model classes
    engine, SessionLocal                   — SQLAlchemy engine and session factory
    get_session                            — context-manager session (commit/rollback)
    init_db                                — create all tables (idempotent)
"""
from chesslens.db.models import AnalysisRow, Base, GameRow, ReportRow
from chesslens.db.session import SessionLocal, engine, get_session, init_db

__all__ = [
    "Base",
    "GameRow",
    "AnalysisRow",
    "ReportRow",
    "engine",
    "SessionLocal",
    "get_session",
    "init_db",
]
