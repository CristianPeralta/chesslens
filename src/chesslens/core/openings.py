"""
Opening breakdown extractor.
Takes Game + GameAnalysis objects and produces an OpeningBreakdown.
No HTTP calls, no DB, no LLM, no Stockfish — pure data transformation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from chesslens.core.analyzer import GameAnalysis
from chesslens.core.parser import Game


@dataclass
class VariantStat:
    name: str
    eco: str | None
    games: int
    wins: int
    losses: int
    draws: int
    win_rate: float


@dataclass
class OpponentLoss:
    opponent: str
    opponent_rating: int
    game_id: str
    opening_name: str


@dataclass
class OpeningBreakdown:
    query: str
    matched_games: int
    wins: int
    losses: int
    draws: int
    win_rate: float
    variants: list[VariantStat]        # sorted by games desc
    total_blunders: int
    total_mistakes: int
    total_inaccuracies: int
    lost_to: list[OpponentLoss]        # losses only, played_at desc, max 10


def extract_opening_breakdown(
    games: list[Game],
    analyses: dict[str, GameAnalysis],
    query: str,
) -> OpeningBreakdown | None:
    """Extract opening breakdown from a list of games filtered by opening name query.

    Returns None when fewer than 5 games match the query.
    The query is matched case-insensitively as a substring of opening_name.
    Games with opening_name == None are skipped silently.
    """
    q = query.lower().strip()
    matched = [g for g in games if q in (g.opening_name or "").lower()]

    if len(matched) < 5:
        return None

    wins = sum(1 for g in matched if g.result == "win")
    losses = sum(1 for g in matched if g.result == "loss")
    draws = sum(1 for g in matched if g.result == "draw")
    win_rate = wins / len(matched)

    # Group by opening_name to build VariantStat list
    variant_map: dict[str, list[Game]] = {}
    for g in matched:
        key = g.opening_name or ""
        variant_map.setdefault(key, []).append(g)

    variants: list[VariantStat] = []
    for name, group in variant_map.items():
        v_wins = sum(1 for g in group if g.result == "win")
        v_losses = sum(1 for g in group if g.result == "loss")
        v_draws = sum(1 for g in group if g.result == "draw")
        eco = next((g.opening_eco for g in group if g.opening_eco), None)
        variants.append(VariantStat(
            name=name,
            eco=eco,
            games=len(group),
            wins=v_wins,
            losses=v_losses,
            draws=v_draws,
            win_rate=v_wins / len(group) if group else 0.0,
        ))

    variants.sort(key=lambda v: v.games, reverse=True)

    # Sum error counts from available analyses
    total_blunders = 0
    total_mistakes = 0
    total_inaccuracies = 0
    for g in matched:
        a = analyses.get(g.id)
        if a is not None:
            total_blunders += a.blunders
            total_mistakes += a.mistakes
            total_inaccuracies += a.inaccuracies

    # Lost-to: losses only, sorted by played_at desc, capped at 10
    loss_games = [g for g in matched if g.result == "loss"]
    loss_games_sorted = sorted(loss_games, key=lambda g: g.played_at, reverse=True)[:10]
    lost_to = [
        OpponentLoss(
            opponent=g.opponent,
            opponent_rating=g.opponent_rating,
            game_id=g.id,
            opening_name=g.opening_name or "",
        )
        for g in loss_games_sorted
    ]

    return OpeningBreakdown(
        query=query,
        matched_games=len(matched),
        wins=wins,
        losses=losses,
        draws=draws,
        win_rate=win_rate,
        variants=variants,
        total_blunders=total_blunders,
        total_mistakes=total_mistakes,
        total_inaccuracies=total_inaccuracies,
        lost_to=lost_to,
    )
