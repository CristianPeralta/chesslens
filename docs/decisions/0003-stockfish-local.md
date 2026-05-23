# 0003 — Stockfish local sobre API remota

**Status:** Accepted
**Date:** 2026-05-23

## Context

El analisis de partidas requiere un motor de ajedrez. Opciones: Stockfish local, Lichess Analysis API (remota, gratuita), chess.com analysis API (paywalled).

## Decision

Stockfish local via el paquete `stockfish` de Python.

## Consequences

- Sin dependencia de servicios externos para analisis — funciona offline
- El usuario necesita instalar Stockfish (`apt install stockfish` / `brew install stockfish`)
- La velocidad de analisis depende del hardware local — aceptable para Phase 1
- En Phase 2 (servidor), Stockfish corre en el VPS sin costo adicional
- WHY: Lichess API tiene rate limits que no escalan bien para analizar 50+ partidas en lote
