"""Tests for core/renderer.py — HTML rendering."""
import json
import re
from datetime import datetime, timezone

from chesslens.core.analyzer import GameDetailAnalysis, MoveError
from chesslens.core.parser import Game
from chesslens.core.patterns import ColorStats, OpeningStats, PatternReport, WeekStats
from chesslens.core.renderer import render_game, render_report


def _make_report() -> PatternReport:
    return PatternReport(
        username="testuser",
        month="2026-05",
        total_games=30,
        wins=15, losses=12, draws=3,
        win_rate=0.5,
        as_white=ColorStats(games=15, wins=8, losses=6, draws=1, win_rate=0.533),
        as_black=ColorStats(games=15, wins=7, losses=6, draws=2, win_rate=0.467),
        top_openings=[
            OpeningStats("London System", "D00", 10, 7, 2, 1, 0.7),
            OpeningStats("French Defense", "C00", 5, 2, 3, 0, 0.4),
        ],
        worst_opening=OpeningStats("French Defense", "C00", 5, 2, 3, 0, 0.4),
        timeout_count=4, timeout_rate=0.133, avg_timeout_ply=58.0,
        avg_accuracy=74.5, avg_centipawn_loss=42.1, blunders_per_game=1.1,
        weekly_performance=[WeekStats(week=1, games=8, wins=5, win_rate=0.625)],
        main_pain="timeout",
    )


def test_render_report_returns_html():
    html = render_report(_make_report(), "Great month!", [1245, 1260])
    assert "<!DOCTYPE html>" in html


def test_render_report_contains_username():
    html = render_report(_make_report(), "Great month!", [1245])
    assert "testuser" in html


def test_render_report_contains_month():
    html = render_report(_make_report(), "Great month!", [1245])
    assert "2026-05" in html


def test_render_report_contains_narrative():
    html = render_report(_make_report(), "You played well this month.", [1245])
    assert "You played well this month." in html


def test_render_report_contains_opening_names():
    html = render_report(_make_report(), "narrative", [1245])
    assert "London System" in html
    assert "French Defense" in html


# --- render_game replay_json tests (task 1.8 / 1.9) ---

def _make_game(pgn: str = "1. e4 e5 *", color: str = "white") -> Game:
    return Game(
        id="test_game_1",
        username="testplayer",
        played_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        time_class="rapid",
        color=color,
        result="draw",
        end_reason="draw",
        opponent="opponent",
        player_rating=1500,
        opponent_rating=1520,
        opening_eco="C60",
        opening_name="Ruy Lopez",
        move_count=2,
        pgn=pgn,
    )


def _make_detail(errors: list[MoveError]) -> GameDetailAnalysis:
    return GameDetailAnalysis(
        game_id="test_game_1",
        eval_sequence=[10, -10],
        top_errors=errors,
        remaining_clock=120,
        accuracy=85.0,
        avg_centipawn_loss=30.0,
        blunders=0,
        mistakes=1,
        inaccuracies=1,
        timeout_move=None,
    )


def test_render_game_includes_replay_json():
    """Task 1.8: render_game must embed replayData JSON with pgn, player_color, errors."""
    errors = [
        MoveError(
            ply=1, san="e4", eval_before=20, eval_after=-280,
            centipawn_loss=300, best_line=["d4"], severity="blunder",
            fen="fen1", remaining_clock_at_ply=120,
        ),
        MoveError(
            ply=3, san="Nf3", eval_before=10, eval_after=-140,
            centipawn_loss=150, best_line=["Nc3"], severity="mistake",
            fen="fen2", remaining_clock_at_ply=None,
        ),
    ]
    game = _make_game(pgn="1. e4 e5 2. Nf3 *")
    detail = _make_detail(errors)

    html = render_game(detail, game)

    # Extract replayData from the script block
    match = re.search(r"const\s+replayData\s*=\s*(\{.*?\});", html, re.DOTALL)
    assert match is not None, "replayData not found in rendered HTML"

    data = json.loads(match.group(1))

    # Top-level keys
    assert "pgn" in data
    assert "player_color" in data
    assert "errors" in data

    # errors must be sorted descending by centipawn_loss
    assert data["errors"][0]["centipawn_loss"] == 300
    assert data["errors"][1]["centipawn_loss"] == 150

    # Each entry must have the required keys
    for entry in data["errors"]:
        assert "fen" in entry
        assert "san" in entry
        assert "centipawn_loss" in entry
        assert "severity" in entry
        assert "remaining_clock_at_ply" in entry

    # null clock for second entry
    assert data["errors"][1]["remaining_clock_at_ply"] is None
