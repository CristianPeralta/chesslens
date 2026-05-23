"""
Statistical pattern extractor.
Takes Game + GameAnalysis objects and produces a PatternReport.
No HTTP calls, no DB, no LLM — pure data transformation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from chesslens.core.analyzer import GameAnalysis
from chesslens.core.parser import Game


@dataclass
class ColorStats:
    games: int
    wins: int
    losses: int
    draws: int
    win_rate: float


@dataclass
class OpeningStats:
    name: str
    eco: str | None
    games: int
    wins: int
    losses: int
    draws: int
    win_rate: float


@dataclass
class WeekStats:
    week: int
    games: int
    wins: int
    win_rate: float


@dataclass
class PatternReport:
    username: str
    month: str                              # YYYY-MM

    total_games: int
    wins: int
    losses: int
    draws: int
    win_rate: float

    as_white: ColorStats
    as_black: ColorStats

    top_openings: list[OpeningStats]        # top 5 by games played
    worst_opening: OpeningStats | None      # lowest win rate, min 3 games

    timeout_count: int
    timeout_rate: float                     # fraction 0-1
    avg_timeout_ply: float | None           # avg ply when timeout happens

    avg_accuracy: float | None              # None if no analyses available
    avg_centipawn_loss: float | None
    blunders_per_game: float | None

    weekly_performance: list[WeekStats]

    main_pain: str                          # "timeout" | "opening" | "accuracy" | "balanced"


def _week_of_month(dt: datetime) -> int:
    first_day = dt.replace(day=1)
    return (dt.day + first_day.weekday()) // 7 + 1


def _color_stats(df: pd.DataFrame) -> ColorStats:
    total = len(df)
    if total == 0:
        return ColorStats(games=0, wins=0, losses=0, draws=0, win_rate=0.0)
    wins = int((df["result"] == "win").sum())
    losses = int((df["result"] == "loss").sum())
    draws = int((df["result"] == "draw").sum())
    return ColorStats(
        games=total,
        wins=wins,
        losses=losses,
        draws=draws,
        win_rate=round(wins / total, 3),
    )


def _opening_stats(group: pd.DataFrame, name: str, eco: str | None) -> OpeningStats:
    total = len(group)
    wins = int((group["result"] == "win").sum())
    losses = int((group["result"] == "loss").sum())
    draws = int((group["result"] == "draw").sum())
    return OpeningStats(
        name=name,
        eco=eco,
        games=total,
        wins=wins,
        losses=losses,
        draws=draws,
        win_rate=round(wins / total, 3) if total > 0 else 0.0,
    )


def _top_openings(df: pd.DataFrame, n: int = 5) -> list[OpeningStats]:
    df_named = df[df["opening_name"].notna()].copy()
    if df_named.empty:
        return []

    grouped = df_named.groupby("opening_name")
    opening_list = []
    for name, group in grouped:
        eco = group["opening_eco"].iloc[0]
        opening_list.append(_opening_stats(group, str(name), eco))

    opening_list.sort(key=lambda o: o.games, reverse=True)
    return opening_list[:n]


def _worst_opening(df: pd.DataFrame, min_games: int = 3) -> OpeningStats | None:
    df_named = df[df["opening_name"].notna()].copy()
    if df_named.empty:
        return None

    candidates = []
    for name, group in df_named.groupby("opening_name"):
        if len(group) >= min_games:
            eco = group["opening_eco"].iloc[0]
            candidates.append(_opening_stats(group, str(name), eco))

    if not candidates:
        return None

    return min(candidates, key=lambda o: o.win_rate)


def _weekly_performance(df: pd.DataFrame) -> list[WeekStats]:
    df = df.copy()
    df["week"] = df["played_at"].apply(_week_of_month)
    result = []
    for week in sorted(df["week"].unique()):
        wdf = df[df["week"] == week]
        wins = int((wdf["result"] == "win").sum())
        total = len(wdf)
        result.append(WeekStats(
            week=int(week),
            games=total,
            wins=wins,
            win_rate=round(wins / total, 3) if total > 0 else 0.0,
        ))
    return result


def _main_pain(
    timeout_rate: float,
    worst_opening: OpeningStats | None,
    avg_accuracy: float | None,
    blunders_per_game: float | None,
) -> str:
    if timeout_rate >= 0.20:
        return "timeout"
    if worst_opening and worst_opening.win_rate < 0.30 and worst_opening.games >= 5:
        return "opening"
    if avg_accuracy is not None and avg_accuracy < 70.0:
        return "accuracy"
    if blunders_per_game is not None and blunders_per_game >= 2.0:
        return "blunders"
    return "balanced"


def extract_patterns(
    games: list[Game],
    analyses: dict[str, GameAnalysis],
    month: str,
) -> PatternReport:
    """Extract statistical patterns from a list of games and their analyses."""
    username = games[0].username if games else ""

    if not games:
        empty_color = ColorStats(games=0, wins=0, losses=0, draws=0, win_rate=0.0)
        return PatternReport(
            username=username, month=month, total_games=0,
            wins=0, losses=0, draws=0, win_rate=0.0,
            as_white=empty_color, as_black=empty_color,
            top_openings=[], worst_opening=None,
            timeout_count=0, timeout_rate=0.0, avg_timeout_ply=None,
            avg_accuracy=None, avg_centipawn_loss=None, blunders_per_game=None,
            weekly_performance=[], main_pain="balanced",
        )

    rows = []
    for g in games:
        a = analyses.get(g.id)
        rows.append({
            "result": g.result,
            "color": g.color,
            "end_reason": g.end_reason,
            "opening_eco": g.opening_eco,
            "opening_name": g.opening_name,
            "player_rating": g.player_rating,
            "played_at": g.played_at,
            "accuracy": a.accuracy if a else None,
            "avg_centipawn_loss": a.avg_centipawn_loss if a else None,
            "blunders": a.blunders if a else None,
            "timeout_move": a.timeout_move if a else None,
        })

    df = pd.DataFrame(rows)

    total = len(df)
    wins = int((df["result"] == "win").sum())
    losses = int((df["result"] == "loss").sum())
    draws = int((df["result"] == "draw").sum())

    timeout_rows = df[df["end_reason"] == "timeout"]
    timeout_count = len(timeout_rows)
    timeout_plies = df["timeout_move"].dropna().tolist()
    avg_timeout_ply = round(sum(timeout_plies) / len(timeout_plies), 1) if timeout_plies else None

    accuracies = df["accuracy"].dropna().tolist()
    cpls = df["avg_centipawn_loss"].dropna().tolist()
    blunders_list = df["blunders"].dropna().tolist()

    avg_accuracy = round(sum(accuracies) / len(accuracies), 1) if accuracies else None
    avg_cpl = round(sum(cpls) / len(cpls), 1) if cpls else None
    blunders_per_game = round(sum(blunders_list) / len(blunders_list), 2) if blunders_list else None

    worst = _worst_opening(df)
    main_pain = _main_pain(
        timeout_count / total if total > 0 else 0.0,
        worst, avg_accuracy, blunders_per_game,
    )

    return PatternReport(
        username=username,
        month=month,
        total_games=total,
        wins=wins,
        losses=losses,
        draws=draws,
        win_rate=round(wins / total, 3) if total > 0 else 0.0,
        as_white=_color_stats(df[df["color"] == "white"]),
        as_black=_color_stats(df[df["color"] == "black"]),
        top_openings=_top_openings(df),
        worst_opening=worst,
        timeout_count=timeout_count,
        timeout_rate=round(timeout_count / total, 3) if total > 0 else 0.0,
        avg_timeout_ply=avg_timeout_ply,
        avg_accuracy=avg_accuracy,
        avg_centipawn_loss=avg_cpl,
        blunders_per_game=blunders_per_game,
        weekly_performance=_weekly_performance(df),
        main_pain=main_pain,
    )
