# 0002 — Typer sobre Click para CLI

**Status:** Accepted
**Date:** 2026-05-23

## Context

Phase 1 es CLI. Necesitamos un framework de CLI Python que sea limpio, tipado, y que no cree friccion cuando agreguemos FastAPI en Phase 2.

## Decision

Usar Typer. Es del mismo autor que FastAPI, usa type hints nativamente, genera help automatico, y tiene Rich integrado para output bonito en terminal.

## Consequences

- El estilo de codigo es consistente entre Typer (Phase 1) y FastAPI (Phase 2)
- Typer depende de Click internamente — no es una dependencia extra significativa
- Auto-completion de shell disponible sin configuracion adicional
