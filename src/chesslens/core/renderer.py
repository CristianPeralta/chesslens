"""Jinja2 HTML renderer for report templates."""
from __future__ import annotations

import json
from pathlib import Path

import markdown as md
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
        narrative=md.markdown(narrative),
        weekly_labels=weekly_labels,
        weekly_ratings=weekly_ratings,
        opening_names=opening_names,
        opening_winrates=opening_winrates,
        opening_colors=opening_colors,
    )


def render_game(detail: GameDetailAnalysis, game: Game) -> str:
    """Render a single-game analysis to an HTML string."""
    template = _env.get_template("game.html")

    replay_errors = sorted(
        [
            {
                "ply": e.ply,
                "fen": e.fen,
                "san": e.san,
                "centipawn_loss": e.centipawn_loss,
                "severity": e.severity,
                "best_line": e.best_line,
                "remaining_clock_at_ply": e.remaining_clock_at_ply,
            }
            for e in detail.top_errors
        ],
        key=lambda x: x["centipawn_loss"],
        reverse=True,
    )
    replay_json = json.dumps(
        {"game_id": game.id, "pgn": game.pgn, "player_color": game.color, "errors": replay_errors}
    )
    chessdotcom_url = (
        f"https://www.chess.com/game/daily/{game.id}"
        if game.time_class == "daily"
        else f"https://www.chess.com/game/live/{game.id}"
    )

    return template.render(
        detail=detail,
        game=game,
        eval_labels=list(range(len(detail.eval_sequence))),
        eval_data=detail.eval_sequence,
        top_errors=detail.top_errors,
        replay_json=replay_json,
        replay_errors=replay_errors,
        replay_pgn=game.pgn,
        chessdotcom_url=chessdotcom_url,
    )


def render_opening(breakdown: "OpeningBreakdown") -> str:  # noqa: F821
    """Render an opening breakdown to an HTML string."""
    from chesslens.core.openings import OpeningBreakdown  # noqa: F401  # local import to avoid circular
    template = _env.get_template("opening.html")
    variant_names = [v.name for v in breakdown.variants]
    variant_winrates = [round(v.win_rate * 100, 1) for v in breakdown.variants]
    variant_colors = ["#4ade80" if wr >= 50 else "#f87171" for wr in variant_winrates]
    return template.render(
        breakdown=breakdown,
        variant_names=variant_names,
        variant_winrates=variant_winrates,
        variant_colors=variant_colors,
    )
