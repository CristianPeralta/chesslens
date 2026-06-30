"""FastAPI web delivery layer for chesslens.

Routes mirror delivery/cli.py call chains but accept `username` as a request
parameter instead of reading settings.username (multi-request isolation).

Start with:
    uvicorn chesslens.delivery.api:app --workers 1 --reload
    WHY --workers 1: in-process APScheduler; multiple workers would each start
    a scheduler and trigger duplicate monthly report runs.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select

import httpx
from chesslens.config import settings
from chesslens.core.analyzer import GameAnalysis, analyze_game, analyze_game_detail
from chesslens.core.fetcher import UserNotFoundError, get_games, get_recent_games
from chesslens.core.jobs import generate_report_for_user
from chesslens.core.openings import extract_opening_breakdown
from chesslens.core.parser import Game as DomainGame
from chesslens.core.parser import parse_games
from chesslens.core.patterns import extract_patterns
from chesslens.core.renderer import render_game, render_opening, render_report
from chesslens.core.reporter import generate_narrative
from chesslens.db.models import AnalysisRow, GameRow, ReportRow, UserRow
from chesslens.db.session import get_session, init_db

logger = logging.getLogger(__name__)

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

async def _run_monthly_reports() -> None:
    """Regenerate previous-month reports for every registered user.

    WHY run_in_executor: generate_report_for_user runs Stockfish (sync,
    CPU-bound) — running it inline would block the event loop / API.
    """
    prev = (datetime.now(timezone.utc).replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    with get_session() as session:
        usernames = list(session.execute(
            select(UserRow.chess_username).distinct()
        ).scalars().all())
    loop = asyncio.get_running_loop()
    for username in usernames:
        try:
            # ponytail: run_in_executor is mandatory here (sync Stockfish in async context)
            await loop.run_in_executor(None, generate_report_for_user, username, prev)
        except Exception:
            logger.exception("Failed to generate report for user %r — skipping", username)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database and start the monthly report scheduler."""
    init_db()
    # ponytail: inline CronTrigger — no config class needed for one cadence
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _run_monthly_reports,
        CronTrigger(day=1, hour=0, minute=5, timezone="UTC"),
        id="monthly_reports",
        replace_existing=True,
    )
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


# --- app ---

app = FastAPI(title="chesslens", lifespan=lifespan)


# --- global error handler ---

@app.exception_handler(Exception)
async def on_error(request, exc):
    """Return a plain-text 500 for unhandled exceptions (no traceback leaks)."""
    logger.exception("Unhandled error on %s %s", request.method, request.url)
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

# 4.0 — Landing
@app.get("/", response_class=HTMLResponse)
def index():
    """Landing page — username entry form."""
    template = _env.get_template("landing.html")
    return HTMLResponse(template.render())


# 4.1 — Lichess redirect
@app.get("/game/{game_id}/lichess")
def lichess_redirect(game_id: str, ply: int = Query(0)):
    """Import a game PGN to Lichess and redirect to the analysis board at the given ply."""
    with get_session() as session:
        row = session.execute(select(GameRow).where(GameRow.id == game_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Game not found")
    # Strip chess.com proprietary tags — Lichess only needs standard PGN
    import re as _re
    _KNOWN_TAGS = {"Event","Site","Date","Round","White","Black","Result","WhiteElo","BlackElo","ECO","Opening","TimeControl","Termination","UTCDate","UTCTime"}
    clean_pgn = _re.sub(
        r'\[(\w+)\s+"[^"]*"\]\s*\n?',
        lambda m: m.group(0) if m.group(1) in _KNOWN_TAGS else "",
        row.pgn,
    )
    headers = {"Authorization": f"Bearer {settings.lichess_token}"} if settings.lichess_token else {}
    import subprocess as _sp, tempfile as _tf, os as _os
    with _tf.NamedTemporaryFile(mode='w', suffix='.pgn', delete=False) as f:
        f.write(clean_pgn)
        pgn_path = f.name
    try:
        curl_args = ["curl", "-s", "-w", "\n%{http_code} %{redirect_url}",
                     "-X", "POST", "--data-urlencode", f"pgn@{pgn_path}",
                     "https://lichess.org/api/import"]
        result = _sp.run(curl_args, capture_output=True, text=True, timeout=15)
    finally:
        _os.unlink(pgn_path)
    last_line = result.stdout.strip().split('\n')[-1]
    parts = last_line.split(' ', 1)
    http_code = parts[0] if parts else ''
    location = parts[1].strip() if len(parts) > 1 else ''
    if location:
        lichess_url = location if location.startswith("http") else f"https://lichess.org{location}"
        return RedirectResponse(f"{lichess_url}/{row.color}#{ply}", status_code=302)
    chessdotcom_url = (
        f"https://www.chess.com/game/daily/{row.id}"
        if row.time_class == "daily"
        else f"https://www.chess.com/game/live/{row.id}"
    )
    return RedirectResponse(chessdotcom_url, status_code=302)


# 4.2 — Health
@app.get("/health")
def health():
    """Liveness probe — always returns 200 + {"status": "ok"}."""
    return {"status": "ok"}


# 4.2 — Stats
@app.get("/stats", response_class=HTMLResponse)
def stats(request: Request):
    """Quick stats page — last 30 days from DB for the authenticated user."""
    username = request.cookies.get("chess_username")
    if not username:
        return RedirectResponse("/", status_code=302)
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
def report(request: Request, month: str | None = Query(None)):
    """Monthly Wrapped report. Checks DB cache before generating."""
    username = request.cookies.get("chess_username")
    if not username:
        return RedirectResponse("/", status_code=302)
    if month is None:
        month = datetime.now(timezone.utc).strftime("%Y-%m")

    try:
        year, mon = map(int, month.split("-"))
        if len(month) != 7 or month[4] != "-":
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid month format: '{month}'. Use YYYY-MM.")

    # Check cache first (fast path)
    with get_session() as session:
        cached = session.execute(
            select(ReportRow)
            .where(ReportRow.username == username)
            .where(ReportRow.month == month)
        ).scalar_one_or_none()

    if cached:
        return HTMLResponse(cached.html)

    # Generate — delegate to shared pipeline in core/jobs.py
    # WHY no run_in_executor here: route runs in uvicorn's sync threadpool,
    # which has no running event loop, so calling the sync function directly is safe.
    try:
        generate_report_for_user(username, month)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found on chess.com")

    # Re-read from DB (generate_report_for_user persists or returns early on no-games)
    with get_session() as session:
        row = session.execute(
            select(ReportRow)
            .where(ReportRow.username == username)
            .where(ReportRow.month == month)
        ).scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail=f"No blitz games found for {username} in {month}")

    return HTMLResponse(row.html)


# 4.4 — Games list
@app.get("/games", response_class=HTMLResponse)
def games_list(request: Request, page: int = Query(1, ge=1)):
    """Paginated list of all games for the authenticated user (10 per page)."""
    username = request.cookies.get("chess_username")
    if not username:
        return RedirectResponse("/", status_code=302)

    with get_session() as session:
        total = session.execute(
            select(func.count()).select_from(GameRow).where(GameRow.username == username)
        ).scalar_one()

    if total == 0:
        # Auto-fetch from chess.com on first visit
        try:
            raw_games = run_async(get_recent_games(username, months=1))
        except UserNotFoundError:
            response = RedirectResponse(f"/?error=not_found&username={username}", status_code=302)
            response.delete_cookie("chess_username")
            return response

        if raw_games:
            games = parse_games(raw_games, username)
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
            with get_session() as session:
                total = session.execute(
                    select(func.count()).select_from(GameRow).where(GameRow.username == username)
                ).scalar_one()

    per_page = 10
    offset = (page - 1) * per_page
    total_pages = max(1, -(-total // per_page))  # ceiling division

    with get_session() as session:
        rows = session.execute(
            select(GameRow)
            .where(GameRow.username == username)
            .order_by(GameRow.played_at.desc())
            .offset(offset)
            .limit(per_page)
        ).scalars().all()
        games_data = [
            {
                "id": r.id,
                "played_at": r.played_at.strftime("%Y-%m-%d %H:%M"),
                "color": r.color,
                "result": r.result,
                "opponent": r.opponent,
                "opponent_rating": r.opponent_rating,
                "player_rating": r.player_rating,
                "opening_name": r.opening_name or "—",
                "move_count": r.move_count,
            }
            for r in rows
        ]

    html = _env.get_template("games.html").render(
        username=username,
        games=games_data,
        page=page,
        total_pages=total_pages,
        total=total,
    )
    return HTMLResponse(html)


# 4.5 — Game last  (MUST be declared BEFORE /game/{game_id})
@app.get("/game/last", response_class=HTMLResponse)
def game_last(request: Request):
    """Return the most recently played game for the authenticated user."""
    username = request.cookies.get("chess_username")
    if not username:
        return RedirectResponse("/", status_code=302)
    with get_session() as session:
        game_row = session.execute(
            select(GameRow)
            .where(GameRow.username == username)
            .order_by(GameRow.played_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    if game_row is None:
        raise HTTPException(status_code=404, detail=f"No games found for '{username}' — visit /games first")

    domain_game = _row_to_domain(game_row)
    detail = analyze_game_detail(domain_game)
    if detail is None:
        raise HTTPException(status_code=500, detail="Stockfish unavailable — analysis failed")

    html = render_game(detail, domain_game)
    return HTMLResponse(html)


# 4.5 — Game by ID  (MUST be declared AFTER /game/last)
@app.get("/game/{game_id}", response_class=HTMLResponse)
def game_by_id(game_id: str, request: Request):
    """Return the analysis for a specific game by its chess.com ID."""
    username = request.cookies.get("chess_username")
    if not username:
        return RedirectResponse("/", status_code=302)

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
def opening(name: str, request: Request):
    """Return an opening breakdown for the authenticated user."""
    username = request.cookies.get("chess_username")
    if not username:
        return RedirectResponse("/", status_code=302)
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
