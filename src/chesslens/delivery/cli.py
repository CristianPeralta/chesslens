import typer
from rich.console import Console
from rich.table import Table

from chesslens.config import save_user_config, settings

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
    """Quick stats in terminal — last 30 days."""
    _require_username()
    console.print("[yellow]Coming soon — issue #8[/yellow]")


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
