"""baseline schema

Revision ID: 0001
Revises:
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_class", sa.String(), nullable=False),
        sa.Column("color", sa.String(), nullable=False),
        sa.Column("result", sa.String(), nullable=False),
        sa.Column("end_reason", sa.String(), nullable=False),
        sa.Column("opponent", sa.String(), nullable=False),
        sa.Column("player_rating", sa.Integer(), nullable=False),
        sa.Column("opponent_rating", sa.Integer(), nullable=False),
        sa.Column("opening_eco", sa.String(), nullable=True),
        sa.Column("opening_name", sa.String(), nullable=True),
        sa.Column("move_count", sa.Integer(), nullable=False),
        sa.Column("pgn", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_games_username"), "games", ["username"], unique=False)

    op.create_table(
        "analysis",
        sa.Column("game_id", sa.String(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=False),
        sa.Column("avg_centipawn_loss", sa.Float(), nullable=False),
        sa.Column("blunders", sa.Integer(), nullable=False),
        sa.Column("mistakes", sa.Integer(), nullable=False),
        sa.Column("inaccuracies", sa.Integer(), nullable=False),
        sa.Column("timeout_move", sa.Integer(), nullable=True),
        sa.Column("remaining_clock", sa.Integer(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"]),
        sa.PrimaryKeyConstraint("game_id"),
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("month", sa.String(), nullable=False),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", "month"),
    )


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_table("analysis")
    op.drop_index(op.f("ix_games_username"), table_name="games")
    op.drop_table("games")
