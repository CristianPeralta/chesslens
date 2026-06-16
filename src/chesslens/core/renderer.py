"""Jinja2 HTML renderer for report templates."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from chesslens.core.analyzer import GameDetailAnalysis
from chesslens.core.parser import Game
from chesslens.core.patterns import PatternReport

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)


def render_report(report: PatternReport, narrative: str, weekly_ratings: list[int]) -> str:
    """Render the monthly Wrapped report to an HTML string."""
    template = _env.get_template("report.html")

    opening_names = [o.name for o in report.top_openings]
    opening_winrates = [round(o.win_rate * 100) for o in report.top_openings]
    opening_colors = [
        "#4ade80" if wr >= 50 else "#f87171" for wr in opening_winrates
    ]

    weekly_labels = [f"Week {w.week}" for w in report.weekly_performance]

    return template.render(
        username=report.username,
        month=report.month,
        report=report,
        narrative=narrative,
        weekly_labels=weekly_labels,
        weekly_ratings=weekly_ratings,
        opening_names=opening_names,
        opening_winrates=opening_winrates,
        opening_colors=opening_colors,
    )


def render_game(detail: GameDetailAnalysis, game: Game) -> str:
    """Render a single-game analysis to an HTML string."""
    template = _env.get_template("game.html")
    return template.render(
        detail=detail,
        game=game,
        eval_labels=list(range(len(detail.eval_sequence))),
        eval_data=detail.eval_sequence,
        top_errors=detail.top_errors,
    )
