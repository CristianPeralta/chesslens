"""
Script de prueba manual del parser contra partidas reales de chess.com.
Uso: uv run python scripts/test_parser_live.py
"""
import asyncio
from datetime import datetime

from chesslens.core.fetcher import get_games
from chesslens.core.parser import parse_games

USERNAME = "krix0s"


async def main():
    now = datetime.now()
    print(f"\nFetching blitz games for {USERNAME} — {now.year}/{now.month:02d}...")
    raws = await get_games(USERNAME, now.year, now.month, time_class="blitz")
    games = parse_games(raws, USERNAME)

    print(f"Parsed: {len(games)} games\n")

    results = {"win": 0, "loss": 0, "draw": 0}
    end_reasons: dict[str, int] = {}
    for g in games:
        results[g.result] += 1
        end_reasons[g.end_reason] = end_reasons.get(g.end_reason, 0) + 1

    print(f"Results:    W {results['win']} / L {results['loss']} / D {results['draw']}")
    print(f"End reasons: {end_reasons}")

    timeouts = [g for g in games if g.end_reason == "timeout"]
    print(f"Timeouts:   {len(timeouts)}")

    print("\n--- Last 3 games ---")
    for g in games[-3:]:
        print(
            f"  [{g.color:5}] {g.result:4} by {g.end_reason:12} "
            f"vs {g.opponent} ({g.opponent_rating}) — {g.opening_name or 'unknown'}"
        )


asyncio.run(main())
