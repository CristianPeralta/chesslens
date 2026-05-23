"""
Script de prueba manual del fetcher contra la API real de chess.com.
Uso: uv run python scripts/test_fetcher_live.py
"""
import asyncio
from chesslens.core.fetcher import get_archives, get_games, get_recent_games
from datetime import datetime

USERNAME = "krix0s"


async def main():
    now = datetime.now()

    print(f"\n--- get_archives({USERNAME}) ---")
    archives = await get_archives(USERNAME)
    print(f"Total meses disponibles: {len(archives)}")
    print(f"Ultimo: {archives[-1]}")
    print(f"Primero: {archives[0]}")

    print(f"\n--- get_games({USERNAME}, {now.year}, {now.month}, blitz) ---")
    games = await get_games(USERNAME, now.year, now.month)
    print(f"Partidas blitz este mes: {len(games)}")
    if games:
        g = games[0]
        print(f"Ejemplo — white: {g['white']['username']} ({g['white']['result']}) "
              f"vs black: {g['black']['username']} ({g['black']['result']})")
        print(f"Apertura en PGN: {[l for l in g['pgn'].splitlines() if 'ECOUrl' in l]}")

    print(f"\n--- get_recent_games({USERNAME}, months=2, blitz) ---")
    recent = await get_recent_games(USERNAME, months=2)
    print(f"Total partidas blitz ultimos 2 meses: {len(recent)}")

    print("\nOK — fetcher funcionando contra API real.")


asyncio.run(main())
