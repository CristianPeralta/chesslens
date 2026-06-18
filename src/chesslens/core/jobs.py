"""Background job pipeline for chesslens.

Holds the shared report-generation function used by both the scheduled job
and the HTTP route. ZERO FastAPI imports — framework-free by design.

WHY extracted from api.py: DRY; scheduler and route share one code path.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from sqlalchemy import select

from chesslens.core.analyzer import GameAnalysis, analyze_game
from chesslens.core.fetcher import get_games
from chesslens.core.parser import Game as DomainGame
from chesslens.core.parser import parse_games
from chesslens.core.patterns import extract_patterns
from chesslens.core.renderer import render_report
from chesslens.core.reporter import generate_narrative
from chesslens.db.models import AnalysisRow, GameRow, ReportRow
from chesslens.db.session import get_session

logger = logging.getLogger(__name__)


def _weekly_ratings(games: list[DomainGame]) -> list[int]:
    """Average player rating per calendar week, ordered chronologically.

    WHY duplicated from api.py: core/ must not import from delivery/.
    Three similar lines > cross-layer import.
    """
    weeks: dict[int, list[int]] = defaultdict(list)
    for g in games:
        week = (g.played_at.day - 1) // 7 + 1
        weeks[week].append(g.player_rating)
    return [round(sum(v) / len(v)) for _, v in sorted(weeks.items())]


def generate_report_for_user(username: str, month: str) -> None:
    """Generate and cache the monthly Wrapped report for one user.

    Idempotent: if a ReportRow for (username, month) already exists, returns early.
    Reuses existing GameRow/AnalysisRow cache; only fills gaps.

    WHY extracted from api.py GET /report: route + scheduler share one code path.
    WHY sync: called via loop.run_in_executor in the scheduler; sync is required
    for run_in_executor.
    """
    # --- idempotency guard ---
    with get_session() as session:
        if session.execute(
            select(ReportRow).where(
                ReportRow.username == username,
                ReportRow.month == month,
            )
        ).scalar_one_or_none():
            return  # ponytail: already cached, nothing to do

    year, mon = map(int, month.split("-"))

    # --- fetch games (async get_games driven from sync context) ---
    # ponytail: asyncio.run() is stdlib; no extra wrapper needed
    raw_games = asyncio.run(get_games(username, year, mon))
    if not raw_games:
        return  # ponytail: no games → no report, no error

    games = parse_games(raw_games, username)

    # --- upsert GameRows ---
    with get_session() as session:
        existing_ids = set(
            r[0] for r in session.execute(
                select(GameRow.id).where(GameRow.id.in_([g.id for g in games]))
            ).all()
        )
        for g in games:
            if g.id not in existing_ids:
                session.add(GameRow(
                    id=g.id, username=g.username, played_at=g.played_at,
                    time_class=g.time_class, color=g.color, result=g.result,
                    end_reason=g.end_reason, opponent=g.opponent,
                    player_rating=g.player_rating, opponent_rating=g.opponent_rating,
                    opening_eco=g.opening_eco, opening_name=g.opening_name,
                    move_count=g.move_count, pgn=g.pgn,
                ))

    # --- analyze games not yet analyzed ---
    with get_session() as session:
        analyzed_ids = set(
            r[0] for r in session.execute(
                select(AnalysisRow.game_id).where(
                    AnalysisRow.game_id.in_([g.id for g in games])
                )
            ).all()
        )

    to_analyze = [g for g in games if g.id not in analyzed_ids]
    analyses: dict[str, GameAnalysis] = {}

    if to_analyze:
        with get_session() as session:
            for g in to_analyze:
                result = analyze_game(g)
                if result:
                    analyses[g.id] = result
                    session.add(AnalysisRow(
                        game_id=result.game_id,
                        accuracy=result.accuracy,
                        avg_centipawn_loss=result.avg_centipawn_loss,
                        blunders=result.blunders,
                        mistakes=result.mistakes,
                        inaccuracies=result.inaccuracies,
                        timeout_move=result.timeout_move,
                    ))

    # --- load existing analyses ---
    with get_session() as session:
        for a in session.execute(
            select(AnalysisRow).where(
                AnalysisRow.game_id.in_([g.id for g in games])
            )
        ).scalars().all():
            if a.game_id not in analyses:
                analyses[a.game_id] = GameAnalysis(
                    game_id=a.game_id, accuracy=a.accuracy,
                    avg_centipawn_loss=a.avg_centipawn_loss, blunders=a.blunders,
                    mistakes=a.mistakes, inaccuracies=a.inaccuracies,
                    timeout_move=a.timeout_move,
                )

    pattern_report = extract_patterns(games, analyses, month)
    narrative = generate_narrative(pattern_report)
    weekly = _weekly_ratings(games)
    html = render_report(pattern_report, narrative, weekly)

    with get_session() as session:
        session.add(ReportRow(
            username=username, month=month, html=html, narrative=narrative,
        ))
