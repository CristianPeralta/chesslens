"""
chess.com public API client.
Returns raw JSON — no parsing, no transformation.
Parsing is handled by core/parser.py.
"""
from __future__ import annotations

import httpx

BASE_URL = "https://api.chess.com/pub/player"
HEADERS = {"User-Agent": "chesslens/0.1.0 (github.com/CristianPeralta/chesslens)"}
TIMEOUT = 30.0


class ChessComError(Exception):
    pass


class UserNotFoundError(ChessComError):
    pass


async def get_archives(username: str) -> list[str]:
    """Return list of monthly archive URLs available for a player."""
    async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT) as client:
        response = await client.get(f"{BASE_URL}/{username}/games/archives")
        if response.status_code == 404:
            raise UserNotFoundError(f"chess.com user '{username}' not found")
        response.raise_for_status()
        return response.json()["archives"]


async def get_games(
    username: str, year: int, month: int, time_class: str = "blitz"
) -> list[dict]:
    """Return raw game dicts for a specific month, filtered by time_class."""
    async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT) as client:
        url = f"{BASE_URL}/{username}/games/{year}/{month:02d}"
        response = await client.get(url)
        if response.status_code == 404:
            raise UserNotFoundError(f"No games found for '{username}' in {year}/{month:02d}")
        response.raise_for_status()
        games = response.json().get("games", [])
        return [g for g in games if g.get("time_class") == time_class]


async def get_recent_games(
    username: str, months: int = 1, time_class: str = "blitz"
) -> list[dict]:
    """Return raw game dicts for the last N months, filtered by time_class."""
    archives = await get_archives(username)
    if not archives:
        return []

    recent_urls = archives[-months:]
    all_games: list[dict] = []

    async with httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT) as client:
        for url in recent_urls:
            response = await client.get(url)
            response.raise_for_status()
            games = response.json().get("games", [])
            all_games.extend(g for g in games if g.get("time_class") == time_class)

    return all_games
