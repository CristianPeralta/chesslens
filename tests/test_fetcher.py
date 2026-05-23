import json
from pathlib import Path

import pytest
import respx
from httpx import Response

from chesslens.core.fetcher import (
    UserNotFoundError,
    get_archives,
    get_games,
    get_recent_games,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def archives_payload():
    return json.loads((FIXTURES / "archives.json").read_text())


@pytest.fixture
def games_payload():
    return json.loads((FIXTURES / "games_2026_05.json").read_text())


@respx.mock
async def test_get_archives_returns_url_list(archives_payload):
    respx.get("https://api.chess.com/pub/player/krix0s/games/archives").mock(
        return_value=Response(200, json=archives_payload)
    )

    result = await get_archives("krix0s")

    assert len(result) == 3
    assert result[-1] == "https://api.chess.com/pub/player/krix0s/games/2026/05"


@respx.mock
async def test_get_archives_raises_on_unknown_user():
    respx.get("https://api.chess.com/pub/player/unknownxxx/games/archives").mock(
        return_value=Response(404)
    )

    with pytest.raises(UserNotFoundError):
        await get_archives("unknownxxx")


@respx.mock
async def test_get_games_filters_by_time_class(games_payload):
    respx.get("https://api.chess.com/pub/player/krix0s/games/2026/05").mock(
        return_value=Response(200, json=games_payload)
    )

    blitz = await get_games("krix0s", 2026, 5, time_class="blitz")
    rapid = await get_games("krix0s", 2026, 5, time_class="rapid")

    # fixture has 2 blitz + 1 rapid
    assert len(blitz) == 2
    assert len(rapid) == 1
    assert all(g["time_class"] == "blitz" for g in blitz)


@respx.mock
async def test_get_games_returns_raw_dicts(games_payload):
    respx.get("https://api.chess.com/pub/player/krix0s/games/2026/05").mock(
        return_value=Response(200, json=games_payload)
    )

    games = await get_games("krix0s", 2026, 5)

    assert "pgn" in games[0]
    assert "white" in games[0]
    assert "black" in games[0]
    assert "time_class" in games[0]


@respx.mock
async def test_get_recent_games_fetches_last_n_months(archives_payload, games_payload):
    respx.get("https://api.chess.com/pub/player/krix0s/games/archives").mock(
        return_value=Response(200, json=archives_payload)
    )
    # last 2 months from fixture: 2026/04 and 2026/05
    respx.get("https://api.chess.com/pub/player/krix0s/games/2026/04").mock(
        return_value=Response(200, json=games_payload)
    )
    respx.get("https://api.chess.com/pub/player/krix0s/games/2026/05").mock(
        return_value=Response(200, json=games_payload)
    )

    games = await get_recent_games("krix0s", months=2, time_class="blitz")

    # 2 blitz per month * 2 months = 4
    assert len(games) == 4


@respx.mock
async def test_get_recent_games_empty_archives():
    respx.get("https://api.chess.com/pub/player/krix0s/games/archives").mock(
        return_value=Response(200, json={"archives": []})
    )

    games = await get_recent_games("krix0s")

    assert games == []
