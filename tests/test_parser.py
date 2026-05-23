import json
from pathlib import Path

import pytest

from chesslens.core.parser import Game, parse_game, parse_games

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def games_payload():
    return json.loads((FIXTURES / "games_2026_05.json").read_text())["games"]


def test_parse_game_as_white(games_payload):
    # games_payload[0]: krix0s is white, won
    game = parse_game(games_payload[0], "krix0s")

    assert isinstance(game, Game)
    assert game.color == "white"
    assert game.result == "win"
    assert game.opponent == "opponent1"
    assert game.username == "krix0s"


def test_parse_game_as_black(games_payload):
    # games_payload[1]: krix0s is black, won
    game = parse_game(games_payload[1], "krix0s")

    assert game.color == "black"
    assert game.result == "win"
    assert game.opponent == "opponent2"


def test_parse_game_end_reason_resigned(games_payload):
    # games_payload[0]: black resigned
    game = parse_game(games_payload[0], "krix0s")
    assert game.end_reason == "resigned"


def test_parse_game_end_reason_timeout(games_payload):
    # games_payload[2]: krix0s (white) timed out → end_reason = "timeout"
    game = parse_game(games_payload[2], "krix0s")
    assert game.end_reason == "timeout"
    assert game.result == "loss"


def test_parse_game_extracts_opening(games_payload):
    game = parse_game(games_payload[0], "krix0s")
    assert game.opening_eco == "D00"
    assert game.opening_name == "Queens Pawn Opening London System"


def test_parse_game_extracts_ratings(games_payload):
    game = parse_game(games_payload[0], "krix0s")
    assert game.player_rating == 1245
    assert game.opponent_rating == 1230


def test_parse_game_counts_moves(games_payload):
    game = parse_game(games_payload[0], "krix0s")
    # PGN fixture has "1. d4 d5 2. Bf4 Nf6 3. e3 1-0" → 5 half-moves
    assert game.move_count == 5


def test_parse_game_malformed_returns_none():
    assert parse_game({}, "krix0s") is None
    assert parse_game({"url": "https://chess.com/game/1"}, "krix0s") is None


def test_parse_games_skips_malformed(games_payload):
    raws = games_payload + [{"broken": True}]
    games = parse_games(raws, "krix0s")

    # 3 valid + 1 malformed → 3 parsed
    assert len(games) == 3
    assert all(isinstance(g, Game) for g in games)


def test_parse_games_returns_all_time_classes(games_payload):
    # Fixture has 2 blitz + 1 rapid — parser doesn't filter by time_class
    games = parse_games(games_payload, "krix0s")
    time_classes = {g.time_class for g in games}
    assert "blitz" in time_classes
    assert "rapid" in time_classes
