"""
PGN parser — converts raw chess.com game dicts into structured Game objects.
Receives raw JSON from core/fetcher.py. No HTTP calls here.
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import chess.pgn

logger = logging.getLogger(__name__)

DRAW_RESULTS = frozenset({
    "agreed", "repetition", "stalemate", "insufficient",
    "50move", "timevsinsufficient",
})


@dataclass
class Game:
    id: str
    username: str
    played_at: datetime
    time_class: str
    color: str          # "white" | "black"
    result: str         # "win" | "loss" | "draw" — player perspective
    end_reason: str     # "checkmate" | "timeout" | "resigned" | "draw" | "abandoned"
    opponent: str
    player_rating: int
    opponent_rating: int
    opening_eco: str | None
    opening_name: str | None
    move_count: int
    pgn: str


_CLK_RE = re.compile(r"\[%clk\s+(\d+):(\d+):(\d+)(?:\.\d+)?\]")


def extract_clock(comment: str | None) -> int | None:
    """Extract remaining clock time in seconds from a PGN move comment.

    Parses the standard chess.com format: [%clk H:MM:SS] or [%clk H:MM:SS.f]
    Returns total seconds as int, or None if the comment is absent or unparseable.
    MUST NOT raise exceptions to the caller.
    """
    try:
        if comment is None:
            return None
        match = _CLK_RE.search(comment)
        if match is None:
            return None
        hours, minutes, seconds = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return hours * 3600 + minutes * 60 + seconds
    except Exception:
        return None


def _game_id(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def _result(player_raw: str) -> str:
    if player_raw == "win":
        return "win"
    if player_raw in DRAW_RESULTS:
        return "draw"
    return "loss"


def _end_reason(white_raw: str, black_raw: str) -> str:
    # WHY: "win" only tells us who won, not how. The losing side's result
    # carries the termination reason (resigned, timeout, checkmated, etc).
    for r in (white_raw, black_raw):
        if r != "win":
            return "draw" if r in DRAW_RESULTS else r
    return "unknown"


def _opening_name(pgn_str: str) -> str | None:
    for line in pgn_str.splitlines():
        if line.startswith("[ECOUrl "):
            path = line.split('"')[1].rstrip("/").split("/")[-1]
            return path.replace("-", " ")
    return None


def _opening_eco(pgn_str: str) -> str | None:
    for line in pgn_str.splitlines():
        if line.startswith("[ECO "):
            return line.split('"')[1]
    return None


def _count_moves(pgn_str: str) -> int:
    try:
        game = chess.pgn.read_game(io.StringIO(pgn_str))
        return game.end().board().ply() if game else 0
    except Exception:
        return 0


def parse_game(raw: dict, username: str) -> Game | None:
    """Parse a raw chess.com game dict into a Game. Returns None if malformed."""
    try:
        white = raw["white"]
        black = raw["black"]
        pgn_str = raw["pgn"]

        is_white = white["username"].lower() == username.lower()
        player = white if is_white else black
        opponent = black if is_white else white

        return Game(
            id=_game_id(raw["url"]),
            username=username,
            played_at=datetime.fromtimestamp(raw["end_time"], tz=timezone.utc),
            time_class=raw["time_class"],
            color="white" if is_white else "black",
            result=_result(player["result"]),
            end_reason=_end_reason(white["result"], black["result"]),
            opponent=opponent["username"],
            player_rating=player["rating"],
            opponent_rating=opponent["rating"],
            opening_eco=_opening_eco(pgn_str),
            opening_name=_opening_name(pgn_str),
            move_count=_count_moves(pgn_str),
            pgn=pgn_str,
        )
    except (KeyError, ValueError) as e:
        logger.warning("Skipping malformed game %s: %s", raw.get("url", "unknown"), e)
        return None


def parse_games(raws: list[dict], username: str) -> list[Game]:
    """Parse a list of raw game dicts, skipping malformed ones silently."""
    games = []
    for raw in raws:
        game = parse_game(raw, username)
        if game is not None:
            games.append(game)
    return games
