from datetime import datetime, timedelta, timezone

import pytest

from chesslens.core.analyzer import GameAnalysis
from chesslens.core.openings import extract_opening_breakdown
from chesslens.core.parser import Game


def _make_game(
    id: str = "g1",
    opening_name: str | None = "French Defense",
    opening_eco: str | None = "C00",
    result: str = "win",
    opponent: str = "opponent",
    opponent_rating: int = 1500,
    played_at: datetime | None = None,
) -> Game:
    return Game(
        id=id,
        username="testuser",
        played_at=played_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        time_class="blitz",
        color="white",
        result=result,
        end_reason="resigned",
        opponent=opponent,
        player_rating=1400,
        opponent_rating=opponent_rating,
        opening_eco=opening_eco,
        opening_name=opening_name,
        move_count=20,
        pgn="",
    )


def _make_analysis(
    game_id: str = "g1",
    blunders: int = 0,
    mistakes: int = 0,
    inaccuracies: int = 0,
) -> GameAnalysis:
    return GameAnalysis(
        game_id=game_id,
        accuracy=85.0,
        avg_centipawn_loss=50.0,
        blunders=blunders,
        mistakes=mistakes,
        inaccuracies=inaccuracies,
        timeout_move=None,
    )


def test_returns_none_when_zero_games_match():
    games = [_make_game(id=str(i), opening_name="Sicilian Defense") for i in range(5)]
    assert extract_opening_breakdown(games, {}, "french") is None


def test_returns_none_when_fewer_than_5_matches():
    games = [_make_game(id=str(i), opening_name="French Defense") for i in range(3)]
    games += [_make_game(id=str(i + 3), opening_name="Sicilian Defense") for i in range(10)]
    assert extract_opening_breakdown(games, {}, "french") is None


def test_returns_breakdown_with_5_or_more_matches():
    results = ["win"] * 5 + ["loss", "draw"]
    games = [
        _make_game(id=str(i), opening_name="French Defense", result=r)
        for i, r in enumerate(results)
    ]
    bd = extract_opening_breakdown(games, {}, "french")
    assert bd is not None
    assert bd.matched_games == 7
    assert bd.wins == 5
    assert bd.losses == 1
    assert bd.draws == 1
    assert abs(bd.win_rate - 5 / 7) < 0.001


def test_lost_to_contains_only_losses_capped_at_10():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    games = [
        _make_game(
            id=str(i),
            opening_name="French Defense",
            result="loss",
            played_at=base + timedelta(days=i),
        )
        for i in range(15)
    ]
    bd = extract_opening_breakdown(games, {}, "french")
    assert bd is not None
    assert len(bd.lost_to) == 10
    # Most recent loss should be first (day 14 is the most recent)
    assert bd.lost_to[0].game_id == "14"


def test_fuzzy_match_case_insensitive_partial_and_null_skip():
    games = [
        _make_game(id="1", opening_name="French Defense"),
        _make_game(id="2", opening_name="FRENCH EXCHANGE"),
        _make_game(id="3", opening_name=None),        # must be skipped silently
        _make_game(id="4", opening_name="Sicilian"),  # must not match
        _make_game(id="5", opening_name="french advance"),
        _make_game(id="6", opening_name="French Classical"),
        _make_game(id="7", opening_name="French Tarrasch"),
    ]
    bd = extract_opening_breakdown(games, {}, "french")
    assert bd is not None
    assert bd.matched_games == 5  # not the None row, not Sicilian; 7 total - 1 None - 1 Sicilian = 5


def test_error_totals_sum_from_analyses():
    games = [_make_game(id=str(i), opening_name="French Defense") for i in range(5)]
    analyses = {
        "0": _make_analysis(game_id="0", blunders=1, mistakes=2, inaccuracies=3),
        "1": _make_analysis(game_id="1", blunders=0, mistakes=1, inaccuracies=0),
        # game "2", "3", "4" have no analysis — must be skipped, not crash
    }
    bd = extract_opening_breakdown(games, analyses, "french")
    assert bd is not None
    assert bd.total_blunders == 1
    assert bd.total_mistakes == 3
    assert bd.total_inaccuracies == 3


def test_variants_sorted_by_games_desc():
    games = [
        _make_game(id="1", opening_name="French Defense: Classical Variation"),
        _make_game(id="2", opening_name="French Defense: Classical Variation"),
        _make_game(id="3", opening_name="French Defense: Classical Variation"),
        _make_game(id="4", opening_name="French Defense: Advance Variation"),
        _make_game(id="5", opening_name="French Defense: Advance Variation"),
        _make_game(id="6", opening_name="French Defense: Exchange Variation"),
    ]
    bd = extract_opening_breakdown(games, {}, "french")
    assert bd is not None
    # Classical (3 games) should come first
    assert bd.variants[0].name == "French Defense: Classical Variation"
    assert bd.variants[0].games == 3
    # Advance (2) second
    assert bd.variants[1].name == "French Defense: Advance Variation"
    assert bd.variants[1].games == 2
    # Exchange (1) last
    assert bd.variants[2].games == 1


def test_win_rate_boundary_exactly_5_games():
    games = [_make_game(id=str(i), opening_name="French Defense", result="win") for i in range(5)]
    bd = extract_opening_breakdown(games, {}, "french")
    assert bd is not None
    assert bd.win_rate == 1.0


def test_returns_none_with_exactly_4_matches():
    games = [_make_game(id=str(i), opening_name="French Defense") for i in range(4)]
    assert extract_opening_breakdown(games, {}, "french") is None
