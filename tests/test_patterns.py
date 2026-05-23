from datetime import datetime, timezone

import pytest

from chesslens.core.analyzer import GameAnalysis
from chesslens.core.parser import Game
from chesslens.core.patterns import (
    ColorStats,
    OpeningStats,
    PatternReport,
    WeekStats,
    extract_patterns,
)

MONTH = "2026-05"


def _make_game(
    id: str,
    color: str = "white",
    result: str = "win",
    end_reason: str = "resigned",
    opening_eco: str | None = "D00",
    opening_name: str | None = "Queens Pawn",
    move_count: int = 20,
    played_at: datetime | None = None,
) -> Game:
    return Game(
        id=id,
        username="krix0s",
        played_at=played_at or datetime(2026, 5, 10, tzinfo=timezone.utc),
        time_class="blitz",
        color=color,
        result=result,
        end_reason=end_reason,
        opponent="opponent",
        player_rating=1245,
        opponent_rating=1230,
        opening_eco=opening_eco,
        opening_name=opening_name,
        move_count=move_count,
        pgn="",
    )


def _make_analysis(game_id: str, accuracy: float = 85.0, cpl: float = 40.0, blunders: int = 0) -> GameAnalysis:
    return GameAnalysis(
        game_id=game_id,
        accuracy=accuracy,
        avg_centipawn_loss=cpl,
        blunders=blunders,
        mistakes=0,
        inaccuracies=1,
        timeout_move=None,
    )


# --- Empty input ---

def test_extract_patterns_empty_games():
    report = extract_patterns([], {}, MONTH)
    assert report.total_games == 0
    assert report.win_rate == 0.0
    assert report.main_pain == "balanced"
    assert report.top_openings == []
    assert report.worst_opening is None


# --- Basic totals ---

def test_extract_patterns_totals():
    games = [
        _make_game("g1", result="win"),
        _make_game("g2", result="win"),
        _make_game("g3", result="loss"),
        _make_game("g4", result="draw"),
    ]
    report = extract_patterns(games, {}, MONTH)

    assert report.total_games == 4
    assert report.wins == 2
    assert report.losses == 1
    assert report.draws == 1
    assert report.win_rate == 0.5


# --- Color stats ---

def test_color_stats_white_and_black():
    games = [
        _make_game("g1", color="white", result="win"),
        _make_game("g2", color="white", result="loss"),
        _make_game("g3", color="black", result="win"),
    ]
    report = extract_patterns(games, {}, MONTH)

    assert report.as_white.games == 2
    assert report.as_white.wins == 1
    assert report.as_white.win_rate == 0.5

    assert report.as_black.games == 1
    assert report.as_black.wins == 1
    assert report.as_black.win_rate == 1.0


def test_color_stats_zero_games_for_color():
    games = [_make_game("g1", color="white", result="win")]
    report = extract_patterns(games, {}, MONTH)

    assert report.as_black.games == 0
    assert report.as_black.win_rate == 0.0


# --- Timeout stats ---

def test_timeout_count_and_rate():
    games = [
        _make_game("g1", end_reason="timeout", result="loss"),
        _make_game("g2", end_reason="timeout", result="loss"),
        _make_game("g3", end_reason="resigned", result="loss"),
        _make_game("g4", end_reason="resigned", result="win"),
        _make_game("g5", end_reason="resigned", result="win"),
    ]
    report = extract_patterns(games, {}, MONTH)

    assert report.timeout_count == 2
    assert report.timeout_rate == 0.4


def test_avg_timeout_ply_from_analyses():
    g1 = _make_game("g1", end_reason="timeout", result="loss", move_count=30)
    g2 = _make_game("g2", end_reason="timeout", result="loss", move_count=50)

    a1 = GameAnalysis("g1", 60.0, 80.0, 1, 1, 2, timeout_move=30)
    a2 = GameAnalysis("g2", 55.0, 90.0, 2, 1, 1, timeout_move=50)

    report = extract_patterns([g1, g2], {"g1": a1, "g2": a2}, MONTH)
    assert report.avg_timeout_ply == 40.0


def test_avg_timeout_ply_none_when_no_analyses():
    games = [_make_game("g1", end_reason="timeout", result="loss")]
    report = extract_patterns(games, {}, MONTH)
    assert report.avg_timeout_ply is None


# --- Accuracy / CPL / Blunders ---

def test_avg_accuracy_from_analyses():
    games = [_make_game("g1"), _make_game("g2")]
    analyses = {
        "g1": _make_analysis("g1", accuracy=80.0),
        "g2": _make_analysis("g2", accuracy=60.0),
    }
    report = extract_patterns(games, analyses, MONTH)
    assert report.avg_accuracy == 70.0


def test_avg_accuracy_none_when_no_analyses():
    games = [_make_game("g1")]
    report = extract_patterns(games, {}, MONTH)
    assert report.avg_accuracy is None


def test_blunders_per_game():
    games = [_make_game("g1"), _make_game("g2")]
    analyses = {
        "g1": _make_analysis("g1", blunders=2),
        "g2": _make_analysis("g2", blunders=4),
    }
    report = extract_patterns(games, analyses, MONTH)
    assert report.blunders_per_game == 3.0


# --- Openings ---

def test_top_openings_sorted_by_games():
    games = [
        _make_game("g1", opening_name="London", opening_eco="D00"),
        _make_game("g2", opening_name="London", opening_eco="D00"),
        _make_game("g3", opening_name="Sicilian", opening_eco="B20"),
        _make_game("g4", opening_name="London", opening_eco="D00"),
    ]
    report = extract_patterns(games, {}, MONTH)

    assert len(report.top_openings) == 2
    assert report.top_openings[0].name == "London"
    assert report.top_openings[0].games == 3
    assert report.top_openings[1].name == "Sicilian"


def test_top_openings_capped_at_five():
    games = [
        _make_game(f"g{i}", opening_name=f"Opening{i}", opening_eco="A00")
        for i in range(10)
    ]
    report = extract_patterns(games, {}, MONTH)
    assert len(report.top_openings) <= 5


def test_top_openings_skips_none_names():
    games = [
        _make_game("g1", opening_name=None, opening_eco=None),
        _make_game("g2", opening_name="London", opening_eco="D00"),
    ]
    report = extract_patterns(games, {}, MONTH)
    assert len(report.top_openings) == 1
    assert report.top_openings[0].name == "London"


def test_worst_opening_below_threshold():
    games = (
        [_make_game(f"l{i}", opening_name="Sicilian", result="loss") for i in range(4)]
        + [_make_game("w1", opening_name="London", result="win")]
        + [_make_game("w2", opening_name="London", result="win")]
        + [_make_game("w3", opening_name="London", result="win")]
    )
    report = extract_patterns(games, {}, MONTH)
    assert report.worst_opening is not None
    assert report.worst_opening.name == "Sicilian"


def test_worst_opening_none_below_min_games():
    games = [
        _make_game("g1", opening_name="Sicilian", result="loss"),
        _make_game("g2", opening_name="Sicilian", result="loss"),
    ]
    report = extract_patterns(games, {}, MONTH)
    assert report.worst_opening is None


# --- Weekly performance ---

def test_weekly_performance_groups_by_week():
    games = [
        _make_game("g1", played_at=datetime(2026, 5, 1, tzinfo=timezone.utc), result="win"),
        _make_game("g2", played_at=datetime(2026, 5, 2, tzinfo=timezone.utc), result="loss"),
        _make_game("g3", played_at=datetime(2026, 5, 15, tzinfo=timezone.utc), result="win"),
    ]
    report = extract_patterns(games, {}, MONTH)

    weeks = {w.week: w for w in report.weekly_performance}
    assert len(weeks) == 2
    week1 = weeks[min(weeks)]
    assert week1.games == 2


# --- main_pain ---

def test_main_pain_timeout():
    games = [
        _make_game(f"t{i}", end_reason="timeout", result="loss") for i in range(5)
    ] + [_make_game("w1", result="win")]
    report = extract_patterns(games, {}, MONTH)
    assert report.main_pain == "timeout"


def test_main_pain_opening():
    # 5+ games on one opening with very low win rate, timeout rate < 20%
    games = (
        [_make_game(f"l{i}", opening_name="Sicilian", result="loss", end_reason="resigned") for i in range(5)]
        + [_make_game("w1", opening_name="London", result="win", end_reason="resigned")]
    )
    report = extract_patterns(games, {}, MONTH)
    assert report.main_pain == "opening"


def test_main_pain_accuracy():
    games = [_make_game(f"g{i}") for i in range(3)]
    analyses = {f"g{i}": _make_analysis(f"g{i}", accuracy=60.0) for i in range(3)}
    report = extract_patterns(games, analyses, MONTH)
    assert report.main_pain == "accuracy"


def test_main_pain_blunders():
    games = [_make_game(f"g{i}") for i in range(3)]
    analyses = {f"g{i}": _make_analysis(f"g{i}", accuracy=75.0, blunders=3) for i in range(3)}
    report = extract_patterns(games, analyses, MONTH)
    assert report.main_pain == "blunders"


def test_main_pain_balanced():
    games = [_make_game(f"g{i}") for i in range(4)]
    analyses = {f"g{i}": _make_analysis(f"g{i}", accuracy=80.0, blunders=0) for i in range(4)}
    report = extract_patterns(games, analyses, MONTH)
    assert report.main_pain == "balanced"


# --- PatternReport metadata ---

def test_report_username_and_month():
    games = [_make_game("g1")]
    report = extract_patterns(games, {}, MONTH)
    assert report.username == "krix0s"
    assert report.month == MONTH
