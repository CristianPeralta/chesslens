"""Tests for core/renderer.py — HTML rendering."""
from chesslens.core.patterns import ColorStats, OpeningStats, PatternReport, WeekStats
from chesslens.core.renderer import render_report


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
