"""SQLAlchemy 2.0 ORM models for chesslens.

WHY: Uses DeclarativeBase + Mapped[] (SQLAlchemy 2.0 style) for type-safe
column declarations without runtime magic. No Alembic yet — create_all()
is sufficient for Phase 1.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class GameRow(Base):
    """Cached game from chess.com API."""

    __tablename__ = "games"

    id: Mapped[str] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(index=True)
    played_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    time_class: Mapped[str]
    color: Mapped[str]  # "white" | "black" from user perspective
    result: Mapped[str]  # win | loss | draw
    end_reason: Mapped[str]  # checkmate | timeout | resigned | draw | abandoned
    opponent: Mapped[str]
    player_rating: Mapped[int]
    opponent_rating: Mapped[int]
    opening_eco: Mapped[str | None]
    opening_name: Mapped[str | None]
    move_count: Mapped[int]
    pgn: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class AnalysisRow(Base):
    """Stockfish analysis results per game."""

    __tablename__ = "analysis"

    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), primary_key=True)
    accuracy: Mapped[float]
    avg_centipawn_loss: Mapped[float]
    blunders: Mapped[int] = mapped_column(default=0)
    mistakes: Mapped[int] = mapped_column(default=0)
    inaccuracies: Mapped[int] = mapped_column(default=0)
    timeout_move: Mapped[int | None]  # ply at timeout, null if not timeout
    remaining_clock: Mapped[int | None]  # seconds left on player's clock at last move
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class ReportRow(Base):
    """Generated monthly reports (cache)."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str]
    month: Mapped[str]  # YYYY-MM
    html: Mapped[str] = mapped_column(Text)
    narrative: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    __table_args__ = (UniqueConstraint("username", "month"),)
