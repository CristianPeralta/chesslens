"""
Script de prueba manual del analyzer con partidas reales de chess.com.
Analiza las ultimas 5 partidas blitz para mantenerlo rapido.
Uso: uv run python scripts/test_analyzer_live.py
"""
import asyncio
from datetime import datetime

from chesslens.core.analyzer import analyze_game
from chesslens.core.fetcher import get_games
from chesslens.core.parser import parse_games

USERNAME = "krix0s"
SAMPLE_SIZE = 5
DEPTH = 12


async def main():
    now = datetime.now()
    print(f"Fetching last {SAMPLE_SIZE} blitz games for {USERNAME}...")
    raws = await get_games(USERNAME, now.year, now.month, time_class="blitz")
    games = parse_games(raws, USERNAME)
    sample = games[-SAMPLE_SIZE:]

    print(f"Analyzing {len(sample)} games at depth {DEPTH}...\n")

    for game in sample:
        analysis = analyze_game(game, depth=DEPTH)
        if analysis is None:
            print(f"  {game.id} — analysis failed")
            continue
        timeout_str = f" TIMEOUT@ply{analysis.timeout_move}" if analysis.timeout_move else ""
        print(
            f"  [{game.color:5}] {game.result:4} | "
            f"accuracy={analysis.accuracy:5.1f}% | "
            f"cpl={analysis.avg_centipawn_loss:5.1f} | "
            f"B={analysis.blunders} M={analysis.mistakes} I={analysis.inaccuracies}"
            f"{timeout_str}"
        )

    print("\nOK — analyzer funcionando con Stockfish real.")


asyncio.run(main())
