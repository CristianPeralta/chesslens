from datetime import datetime, timedelta, timezone

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from chesslens.config import save_user_config, settings
from chesslens.db.models import GameRow
from chesslens.db.session import get_session

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
    console.print("[yellow]Coming soon — issue #10[/yellow]")


@app.command()
def game(
    last: bool = typer.Option(False, "--last", help="Analyze last played game."),
    id: str = typer.Option(None, "--id", help="chess.com game ID."),
):
    """Single game analysis — opens in browser."""
    _require_username()
    if not last and not id:
        console.print("[red]Provide --last or --id <game_id>[/red]")
        raise typer.Exit(1)
    console.print("[yellow]Coming soon — issue #11[/yellow]")


@app.command()
def opening(
    name: str = typer.Argument(..., help="Opening name, e.g. 'French Defense'"),
):
    """Opening breakdown — opens in browser."""
    _require_username()
    console.print("[yellow]Coming soon — issue #12[/yellow]")


def _require_username() -> None:
    if not settings.username:
        console.print("[red]No username set. Run: chesslens config --username <your_username>[/red]")
        raise typer.Exit(1)
