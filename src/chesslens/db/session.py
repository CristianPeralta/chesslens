"""SQLAlchemy session factory and DB initialization for chesslens.

WHY: expire_on_commit=False is required so CLI code can read ORM attributes
after the context manager commits without triggering lazy-load errors.

TODO(debt): replace create_all() with Alembic migrations when schema stabilizes.
"""
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from chesslens.config import settings
from chesslens.db.models import Base

engine = create_engine(settings.db_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create all tables defined in Base.metadata (idempotent)."""
    # TODO(debt): replace with Alembic when schema stabilizes
    Base.metadata.create_all(engine)
    # WHY: remaining_clock was added after initial schema; ALTER TABLE makes it
    # available on existing DBs without requiring a full migration tool.
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE analysis ADD COLUMN remaining_clock INTEGER"))
        except (OperationalError, ProgrammingError):
            pass


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a Session, commit on success, rollback on exception."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
