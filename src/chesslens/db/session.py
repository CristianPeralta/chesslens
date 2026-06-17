"""SQLAlchemy session factory and DB initialization for chesslens.

WHY: expire_on_commit=False is required so CLI code can read ORM attributes
after the context manager commits without triggering lazy-load errors.
"""
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from chesslens.config import settings

engine = create_engine(settings.db_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# WHY: resolved from session.py location (src/chesslens/db/session.py → parents[3])
# so init_db() works regardless of the working directory when the CLI is invoked.
ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


def init_db() -> None:
    """Apply pending Alembic migrations up to head (idempotent)."""
    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")


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
