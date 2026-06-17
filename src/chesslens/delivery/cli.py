import asyncio
import tempfile
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from chesslens.config import save_user_config, settings
from chesslens.core.analyzer import GameAnalysis, GameDetailAnalysis, analyze_game, analyze_game_detail
from chesslens.core.fetcher import UserNotFoundError, get_games
from chesslens.core.parser import parse_games
from chesslens.core.patterns import extract_patterns
from chesslens.core.renderer import render_game, render_report
from chesslens.core.reporter import generate_narrative
from chesslens.db.models import AnalysisRow, GameRow, ReportRow
from chesslens.db.session import get_session, init_db

app = typer.Typer(
    name="chesslens",
    help="chesslens — your chess, through a clear lens.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def config(
    username: str = typer.Option(..., help="chess.com username"),
    model: str = typer.Option(None, help="LiteLLM model string (e.g. claude-sonnet-4-6, gpt-4o, ollama/llama3)"),
):
    """Save chess.com username and preferences."""
    updates: dict[str, str] = {"username": username}
    if model:
        updates["model"] = model
    save_user_config(**updates)
    console.print(f"[green]Saved.[/green] Username set to [bold]{username}[/bold].")


@app.command()
def stats():
    """Quick stats in terminal — last 30 days from DB."""
    _require_username()

    with get_session() as session:
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

        rows = session.execute(
            select(GameRow)
            .where(GameRow.username == settings.username)
            .where(GameRow.played_at >= thirty_days_ago)
            .order_by(GameRow.played_at.desc())
        ).scalars().all()

    if not rows:
        console.print("[yellow]No games found. Run chesslens fetch first.[/yellow]")
        raise typer.Exit(0)

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
        best_opening = max(qualified.items(), key=lambda x: x[1]["wins"] / x[1]["games"])
        worst_opening = min(qualified.items(), key=lambda x: x[1]["wins"] / x[1]["games"])

    # --- render ---
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column()

    delta_str = ""
    if rating_delta is not None:
        color = "green" if rating_delta >= 0 else "red"
        sign = "▲" if rating_delta >= 0 else "▼"
        delta_str = f" ([{color}]{sign}{abs(rating_delta)} this week[/{color}])"
    table.add_row("Rating", f"{current_rating}{delta_str}")

    last10_str = (
        f"[green]{wins10}W[/green] [red]{losses10}L[/red] [dim]{draws10}D[/dim]"
        f"  — {wr10:.0%} win rate"
    )
    table.add_row("Last 10", last10_str)

    if best_opening:
        wr = best_opening[1]["wins"] / best_opening[1]["games"]
        table.add_row("Best opening", f"{best_opening[0]}  [green]{wr:.0%}[/green]")
    if worst_opening and worst_opening[0] != (best_opening[0] if best_opening else None):
        wr = worst_opening[1]["wins"] / worst_opening[1]["games"]
        table.add_row("Worst opening", f"{worst_opening[0]}  [red]{wr:.0%}[/red]")

    timeout_color = "red" if timeouts_7d >= 3 else "yellow" if timeouts_7d >= 1 else "green"
    table.add_row("Timeouts (7d)", f"[{timeout_color}]{timeouts_7d}[/{timeout_color}]")

    console.print(table)


@app.command()
def report(
    month: str = typer.Option(
        None, "--month", "-m", help="Month to report (YYYY-MM). Defaults to current month."
    ),
):
    """Monthly Wrapped report — opens in browser."""
    _require_username()
    init_db()

    if month is None:
        month = datetime.now(timezone.utc).strftime("%Y-%m")

    try:
        year, mon = map(int, month.split("-"))
    except ValueError:
        console.print(f"[red]Invalid month format: {month}. Use YYYY-MM.[/red]")
        raise typer.Exit(1)

    # Check cache
    with get_session() as session:
        cached = session.execute(
            select(ReportRow)
            .where(ReportRow.username == settings.username)
            .where(ReportRow.month == month)
        ).scalar_one_or_none()

    if cached:
        console.print(f"[dim]Using cached report for {month}.[/dim]")
        _open_html(cached.html, settings.username, month)
        return

    # Fetch
    console.print(f"Fetching games for [bold]{month}[/bold]...")
    try:
        raw_games = asyncio.run(get_games(settings.username, year, mon))
    except UserNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if not raw_games:
        console.print(f"[yellow]No blitz games found for {month}.[/yellow]")
        raise typer.Exit(0)

    games = parse_games(raw_games, settings.username)
    console.print(f"Parsed [bold]{len(games)}[/bold] games.")

    # Save new games to DB
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

    # Analyze new games with Stockfish (skip already analyzed)
    with get_session() as session:
        analyzed_ids = set(
            r[0] for r in session.execute(
                select(AnalysisRow.game_id).where(AnalysisRow.game_id.in_([g.id for g in games]))
            ).all()
        )

    to_analyze = [g for g in games if g.id not in analyzed_ids]
    analyses: dict[str, GameAnalysis] = {}

    if to_analyze:
        console.print(f"Analyzing [bold]{len(to_analyze)}[/bold] games with Stockfish...")
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

    # Load existing analyses from DB for this month
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

    # Extract patterns → narrative → render
    console.print("Extracting patterns...")
    pattern_report = extract_patterns(games, analyses, month)

    console.print("Generating narrative...")
    narrative = generate_narrative(pattern_report)

    weekly_ratings = _weekly_ratings(games)
    html = render_report(pattern_report, narrative, weekly_ratings)

    # Cache in DB
    with get_session() as session:
        session.add(ReportRow(
            username=settings.username, month=month, html=html, narrative=narrative,
        ))

    _open_html(html, settings.username, month)


@app.command()
def game(
    last: bool = typer.Option(False, "--last", help="Analyze last played game."),
    id: str = typer.Option(None, "--id", help="chess.com game ID."),
):
    """Single game analysis — opens in browser."""
    _require_username()
    init_db()

    if not last and not id:
        console.print("[red]Provide --last or --id <game_id>[/red]")
        raise typer.Exit(1)

    username = settings.username
    game_row: GameRow | None = None

    if last:
        with get_session() as session:
            result = session.execute(
                select(GameRow)
                .where(GameRow.username == username)
                .order_by(GameRow.played_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            game_row = result
        if game_row is None:
            console.print("[red]No games found in DB. Run chesslens report first.[/red]")
            raise typer.Exit(1)
    else:
        # Try DB first
        with get_session() as session:
            game_row = session.execute(
                select(GameRow).where(GameRow.id == id)
            ).scalar_one_or_none()

        if game_row is None:
            # Fetch current month
            now = datetime.now(timezone.utc)
            console.print(f"Game {id} not in DB — fetching current month...")
            try:
                raw_games = asyncio.run(get_games(username, now.year, now.month))
            except UserNotFoundError as e:
                console.print(f"[red]{e}[/red]")
                raise typer.Exit(1)

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
                game_row = session.execute(
                    select(GameRow).where(GameRow.id == id)
                ).scalar_one_or_none()

        if game_row is None:
            # Fallback: previous month
            prev_month = datetime.now(timezone.utc) - timedelta(days=30)
            console.print("Not found this month — trying previous month...")
            try:
                raw_games = asyncio.run(get_games(username, prev_month.year, prev_month.month))
            except UserNotFoundError:
                raw_games = []

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
                game_row = session.execute(
                    select(GameRow).where(GameRow.id == id)
                ).scalar_one_or_none()

        if game_row is None:
            console.print(f"[red]Game {id} not found in DB or chess.com API.[/red]")
            raise typer.Exit(1)

    # Convert ORM row to domain Game object
    from chesslens.core.parser import Game as DomainGame
    domain_game = DomainGame(
        id=game_row.id,
        username=game_row.username,
        played_at=game_row.played_at,
        time_class=game_row.time_class,
        color=game_row.color,
        result=game_row.result,
        end_reason=game_row.end_reason,
        opponent=game_row.opponent,
        player_rating=game_row.player_rating,
        opponent_rating=game_row.opponent_rating,
        opening_eco=game_row.opening_eco,
        opening_name=game_row.opening_name,
        move_count=game_row.move_count,
        pgn=game_row.pgn,
    )

    console.print("Analyzing with Stockfish...")
    detail = analyze_game_detail(domain_game)
    if detail is None:
        console.print("[red]Stockfish not found or analysis failed. Install stockfish and try again.[/red]")
        raise typer.Exit(1)

    html = render_game(detail, domain_game)
    _open_game_html(html, username, domain_game.id)


@app.command()
def opening(
    name: str = typer.Argument(..., help="Opening name to analyze (fuzzy match)"),
):
    """Single opening breakdown: win rate, variants, errors, opponents who beat you."""
    from chesslens.core.openings import extract_opening_breakdown
    from chesslens.core.parser import Game as DomainGame
    from chesslens.core.renderer import render_opening

    _require_username()
    init_db()
    username = settings.username

    with get_session() as session:
        rows = session.execute(
            select(GameRow).where(GameRow.username == username)
        ).scalars().all()

    if not rows:
        console.print("[yellow]No games in DB — run chesslens report first[/yellow]")
        raise typer.Exit(0)

    games = [
        DomainGame(
            id=r.id,
            username=r.username,
            played_at=r.played_at,
            time_class=r.time_class,
            color=r.color,
            result=r.result,
            end_reason=r.end_reason,
            opponent=r.opponent,
            player_rating=r.player_rating,
            opponent_rating=r.opponent_rating,
            opening_eco=r.opening_eco,
            opening_name=r.opening_name,
            move_count=r.move_count,
            pgn=r.pgn,
        )
        for r in rows
    ]

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
        console.print(f"[yellow]Not enough data: fewer than 5 games found for '{name}'[/yellow]")
        raise typer.Exit(1)

    html = render_opening(breakdown)
    _open_opening_html(html, username, name)


# --- helpers ---

def _require_username() -> None:
    if not settings.username:
        console.print("[red]No username set. Run: chesslens config --username <your_username>[/red]")
        raise typer.Exit(1)


def _weekly_ratings(games) -> list[int]:
    """Average player rating per calendar week, ordered chronologically."""
    from collections import defaultdict
    weeks: dict[int, list[int]] = defaultdict(list)
    for g in games:
        week = (g.played_at.day - 1) // 7 + 1
        weeks[week].append(g.player_rating)
    return [round(sum(v) / len(v)) for _, v in sorted(weeks.items())]


def _open_game_html(html: str, username: str, game_id: str) -> None:
    """Write game HTML to reports dir and open in browser."""
    out_dir = settings.reports_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{username}-game-{game_id}.html"
    out_path.write_text(html, encoding="utf-8")
    console.print(f"[green]Report saved:[/green] {out_path}")
    webbrowser.open(out_path.as_uri())


def _open_opening_html(html: str, username: str, name: str) -> None:
    """Write opening breakdown HTML to reports dir and open in browser."""
    slug = name.lower().replace(" ", "-")
    out_dir = settings.reports_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{username}-opening-{slug}.html"
    path.write_text(html, encoding="utf-8")
    console.print(f"[green]Opening report saved to {path}[/green]")
    webbrowser.open(str(path))


def _open_html(html: str, username: str, month: str) -> None:
    """Write HTML to reports dir and open in browser."""
    out_dir = settings.reports_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{username}-{month}.html"
    out_path.write_text(html, encoding="utf-8")
    console.print(f"[green]Report saved:[/green] {out_path}")
    webbrowser.open(out_path.as_uri())
