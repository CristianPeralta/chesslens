"""FastAPI web delivery layer for chesslens.

Routes mirror delivery/cli.py call chains but accept `username` as a request
parameter instead of reading settings.username (multi-request isolation).

Start with:
    uvicorn chesslens.delivery.api:app --reload
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select

from chesslens.core.analyzer import GameAnalysis, analyze_game, analyze_game_detail
from chesslens.core.fetcher import UserNotFoundError, get_games
from chesslens.core.openings import extract_opening_breakdown
from chesslens.core.parser import Game as DomainGame
from chesslens.core.parser import parse_games
from chesslens.core.patterns import extract_patterns
from chesslens.core.renderer import render_game, render_opening, render_report
from chesslens.core.reporter import generate_narrative
from chesslens.db.models import AnalysisRow, GameRow, ReportRow
from chesslens.db.session import get_session, init_db

# WHY: import settings only for the username-isolation test (patch target);
# no route handler reads settings.username.
from chesslens.config import settings  # noqa: F401

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)


# --- async bridge ---

def run_async(coro):
    """Run a coroutine from a sync route handler, safe when a loop is already running.

    WHY: uvicorn sync route handlers run in a threadpool. The thread normally has
    no running event loop, so asyncio.run() works. If somehow called from a thread
    with a running loop (e.g. certain test harnesses), fall back to anyio's
    run_sync_from_thread portal which can submit async work to the existing loop.
    """
    try:
        asyncio.get_running_loop()
        # A loop is running in this thread — use anyio's thread-safe coroutine runner.
        import anyio.from_thread
        return anyio.from_thread.run(coro)
    except RuntimeError:
        # No running loop in this thread — safe to call asyncio.run().
        return asyncio.run(coro)


# --- lifespan ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    init_db()
    yield


# --- app ---

app = FastAPI(title="chesslens", lifespan=lifespan)


# --- global error handler ---

@app.exception_handler(Exception)
async def on_error(request, exc):
    """Return a plain-text 500 for unhandled exceptions (no traceback leaks)."""
    return PlainTextResponse("Internal server error", status_code=500)


# --- helpers ---

def _weekly_ratings(games) -> list[int]:
    """Average player rating per calendar week, ordered chronologically.

    WHY: duplicated from cli.py — importing from a delivery sibling would
    couple the two delivery modules. Three similar lines > abstraction.
    """
    weeks: dict[int, list[int]] = defaultdict(list)
    for g in games:
        week = (g.played_at.day - 1) // 7 + 1
        weeks[week].append(g.player_rating)
    return [round(sum(v) / len(v)) for _, v in sorted(weeks.items())]


def _row_to_domain(row: GameRow) -> DomainGame:
    """Convert a GameRow ORM object to a domain Game instance."""
    return DomainGame(
        id=row.id,
        username=row.username,
        played_at=row.played_at,
        time_class=row.time_class,
        color=row.color,
        result=row.result,
        end_reason=row.end_reason,
        opponent=row.opponent,
        player_rating=row.player_rating,
        opponent_rating=row.opponent_rating,
        opening_eco=row.opening_eco,
        opening_name=row.opening_name,
        move_count=row.move_count,
        pgn=row.pgn,
    )


# ===================================================================
# Routes
# ===================================================================

# 4.1 — Health
@app.get("/health")
def health():
    """Liveness probe — always returns 200 + {"status": "ok"}."""
    return {"status": "ok"}


# 4.2 — Stats
@app.get("/stats", response_class=HTMLResponse)
def stats(username: str = Query(...)):
    """Quick stats page — last 30 days from DB for the given username."""
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    with get_session() as session:
        rows = session.execute(
            select(GameRow)
            .where(GameRow.username == username)
            .where(GameRow.played_at >= thirty_days_ago)
            .order_by(GameRow.played_at.desc())
        ).scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No games found for user '{username}'")

    last10 = rows[:10]
    wins10 = sum(1 for g in last10 if g.result == "win")
    losses10 = sum(1 for g in last10 if g.result == "loss")
    draws10 = sum(1 for g in last10 if g.result == "draw")
    wr10 = wins10 / len(last10) if last10 else 0.0

    current_rating = rows[0].player_rating
    week_rows = [g for g in rows if g.played_at >= seven_days_ago]
    rating_delta = None
    if week_rows:
        oldest_this_week = min(week_rows, key=lambda g: g.played_at)
        rating_delta = current_rating - oldest_this_week.player_rating

    timeouts_7d = sum(1 for g in week_rows if g.end_reason == "timeout")

    opening_stats: dict[str, dict] = {}
    for g in rows:
        if not g.opening_name:
            continue
        s = opening_stats.setdefault(g.opening_name, {"games": 0, "wins": 0})
        s["games"] += 1
        if g.result == "win":
            s["wins"] += 1

    qualified = {k: v for k, v in opening_stats.items() if v["games"] >= 3}
    best_opening = worst_opening = None
    if qualified:
        best_item = max(qualified.items(), key=lambda x: x[1]["wins"] / x[1]["games"])
        worst_item = min(qualified.items(), key=lambda x: x[1]["wins"] / x[1]["games"])
        best_wr = best_item[1]["wins"] / best_item[1]["games"]
        worst_wr = worst_item[1]["wins"] / worst_item[1]["games"]
        best_opening = f"{best_item[0]} ({best_wr:.0%})"
        if worst_item[0] != best_item[0]:
            worst_opening = f"{worst_item[0]} ({worst_wr:.0%})"

    template = _env.get_template("stats.html")
    html = template.render(
        username=username,
        current_rating=current_rating,
        rating_delta=rating_delta,
        wins10=wins10,
        losses10=losses10,
        draws10=draws10,
        wr10=wr10,
        best_opening=best_opening,
        worst_opening=worst_opening,
        timeouts_7d=timeouts_7d,
    )
    return HTMLResponse(html)


# 4.3 — Report
@app.get("/report", response_class=HTMLResponse)
def report(
    username: str = Query(...),
    month: str | None = Query(None),
):
    """Monthly Wrapped report. Checks DB cache before generating."""
    if month is None:
        month = datetime.now(timezone.utc).strftime("%Y-%m")

    try:
        year, mon = map(int, month.split("-"))
        if len(month) != 7 or month[4] != "-":
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid month format: '{month}'. Use YYYY-MM.")

    # Check cache
    with get_session() as session:
        cached = session.execute(
            select(ReportRow)
            .where(ReportRow.username == username)
            .where(ReportRow.month == month)
        ).scalar_one_or_none()

    if cached:
        return HTMLResponse(cached.html)

    # Fetch games
    try:
        raw_games = run_async(get_games(username, year, mon))
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found on chess.com")

    if not raw_games:
        raise HTTPException(status_code=404, detail=f"No blitz games found for {username} in {month}")

    games = parse_games(raw_games, username)

    # Upsert games to DB
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

    # Analyze games not yet analyzed
    with get_session() as session:
        analyzed_ids = set(
            r[0] for r in session.execute(
                select(AnalysisRow.game_id).where(AnalysisRow.game_id.in_([g.id for g in games]))
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

    # Load existing analyses
    with get_session() as session:
        for a in session.execute(
            select(AnalysisRow).where(AnalysisRow.game_id.in_([g.id for g in games]))
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

    return HTMLResponse(html)


# 4.4 — Game last  (MUST be declared BEFORE /game/{game_id})
@app.get("/game/last", response_class=HTMLResponse)
def game_last(username: str = Query(...)):
    """Return the most recently played game for the given username."""
    with get_session() as session:
        game_row = session.execute(
            select(GameRow)
            .where(GameRow.username == username)
            .order_by(GameRow.played_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    if game_row is None:
        raise HTTPException(status_code=404, detail=f"No games found for user '{username}'")

    domain_game = _row_to_domain(game_row)
    detail = analyze_game_detail(domain_game)
    if detail is None:
        raise HTTPException(status_code=500, detail="Stockfish unavailable — analysis failed")

    html = render_game(detail, domain_game)
    return HTMLResponse(html)


# 4.5 — Game by ID  (MUST be declared AFTER /game/last)
@app.get("/game/{game_id}", response_class=HTMLResponse)
def game_by_id(game_id: str):
    """Return the analysis for a specific game by its chess.com ID."""
    with get_session() as session:
        game_row = session.execute(
            select(GameRow).where(GameRow.id == game_id)
        ).scalar_one_or_none()

    if game_row is None:
        raise HTTPException(status_code=404, detail=f"Game '{game_id}' not found")

    domain_game = _row_to_domain(game_row)
    detail = analyze_game_detail(domain_game)
    if detail is None:
        raise HTTPException(status_code=500, detail="Stockfish unavailable — analysis failed")

    html = render_game(detail, domain_game)
    return HTMLResponse(html)


# 4.6 — Opening breakdown
@app.get("/opening/{name}", response_class=HTMLResponse)
def opening(name: str, username: str = Query(...)):
    """Return an opening breakdown for the given opening name and username."""
    with get_session() as session:
        rows = session.execute(
            select(GameRow).where(GameRow.username == username)
        ).scalars().all()

    games = [_row_to_domain(r) for r in rows]

    game_ids = [g.id for g in games]
    with get_session() as session:
        analysis_rows = session.execute(
            select(AnalysisRow).where(AnalysisRow.game_id.in_(game_ids))
        ).scalars().all()

    analyses = {
        a.game_id: GameAnalysis(
            game_id=a.game_id,
            accuracy=a.accuracy,
            avg_centipawn_loss=a.avg_centipawn_loss,
            blunders=a.blunders,
            mistakes=a.mistakes,
            inaccuracies=a.inaccuracies,
            timeout_move=a.timeout_move,
        )
        for a in analysis_rows
    }

    breakdown = extract_opening_breakdown(games, analyses, name)
    if breakdown is None:
        raise HTTPException(status_code=404, detail=f"Not enough data for opening '{name}'")

    html = render_opening(breakdown)
    return HTMLResponse(html)
