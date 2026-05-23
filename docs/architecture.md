# Arquitectura — chesslens

## Principio central

El `core/` no sabe que existe Typer, FastAPI, ni ninguna interfaz de usuario.
El `delivery/` es una capa delgada que toma input del usuario y llama al core.
Cambiar de CLI a web no requiere reescribir logica de negocio.

```
┌─────────────────────────┐
│     delivery/cli.py     │  Typer commands (Phase 1)
│     delivery/api.py     │  FastAPI routes (Phase 2)
└──────────┬──────────────┘
           │ calls
┌──────────▼──────────────┐
│     core/               │  Domain logic — framework-free
│   fetcher.py            │  chess.com API
│   parser.py             │  PGN → structured data
│   analyzer.py           │  Stockfish analysis
│   patterns.py           │  Statistical patterns
│   reporter.py           │  LiteLLM narrative
└──────────┬──────────────┘
           │
    ┌──────┴──────┐
    │             │
┌───▼────┐  ┌────▼─────┐
│ SQLite │  │ Stockfish│
│  (DB)  │  │ (local)  │
└────────┘  └──────────┘
```

## Flujo principal: `chesslens report`

```
1. fetcher.py    → GET https://api.chess.com/pub/player/{user}/games/{year}/{month}
2. parser.py     → PGN string → Game objects (python-chess)
3. analyzer.py   → Game → StockfishAnalysis (accuracy, blunders, timeout_move)
4. patterns.py   → [Game + Analysis] → PatternReport (win rates, openings, time stats)
5. reporter.py   → PatternReport → LLM prompt → narrative string
6. template      → PatternReport + narrative → HTML file
7. cli.py        → open HTML in browser
```

## Modelo de datos

Ver [AGENTS.md](../AGENTS.md#data-model) para el schema completo.

Tablas: `games`, `analysis`, `reports`.
Dedup por `game_id` en `games` — re-fetch es seguro (acumulativo).

## AI pipeline

chesslens separa analisis de dominio de generacion de lenguaje:

```
Stockfish + patterns.py   → metricas objetivas (numeros)
reporter.py (LiteLLM)     → convierte metricas en narrativa humana
```

El LLM nunca analiza posiciones de ajedrez directamente — eso lo hace Stockfish.
El LLM recibe JSON estructurado con las metricas y genera texto.

## Infraestructura

- **Phase 1:** Local, SQLite en `~/.chesslens/`, reportes HTML en `./reports/`
- **Phase 2:** Docker Compose en VPS Netcup (4c/8GB), PostgreSQL, FastAPI
- **Dev local:** `uv run chesslens` o `docker compose up`

## Decisiones arquitectonicas

Ver `docs/decisions/` para ADRs completos.

| Decision | Eleccion | ADR |
|---|---|---|
| AI provider abstraction | LiteLLM | 0001 |
| CLI framework | Typer sobre Click | 0002 |
| Chess engine | Stockfish local sobre API remota | 0003 |
