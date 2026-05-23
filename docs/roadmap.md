# Roadmap — chesslens

## Fase 1 — MVP Personal (CLI + HTML)

**Objetivo:** Herramienta personal que genera reportes reales con datos reales.

### Core
- [ ] Project scaffolding — pyproject.toml, estructura de carpetas, Typer skeleton
- [ ] chess.com API fetcher — `core/fetcher.py`
- [ ] PGN parser — `core/parser.py` con python-chess
- [ ] Stockfish analyzer — `core/analyzer.py` (accuracy, centipawn loss, timeout detection)
- [ ] Statistical pattern extractor — `core/patterns.py` (win rate, aperturas, tiempo)
- [ ] LiteLLM narrative generator — `core/reporter.py`
- [ ] SQLite persistence — `db/models.py` + `db/session.py`

### CLI + HTML
- [ ] `chesslens stats` — quick stats en terminal con Rich
- [ ] `chesslens report` — reporte mensual Wrapped (Jinja2 + Chart.js)
- [ ] `chesslens game` — analisis de partida especifica (HTML)
- [ ] `chesslens opening` — breakdown de una apertura (HTML)

**Criterio de done:** Genera un reporte real con datos de krix0s, lo abre en el browser, tiene graficos, narrativa LLM y 3 recomendaciones accionables.

---

## Fase 2 — Multi-usuario (Web App)

**Objetivo:** Invitar amigos a usarlo sin que instalen nada.

- [ ] FastAPI delivery layer — misma logica de core, nuevo delivery
- [ ] PostgreSQL migration — SQLAlchemy schema sin cambios
- [ ] JWT auth — registro y login basico
- [ ] Background jobs — reportes automaticos mensuales (APScheduler)
- [ ] Docker Compose deploy — VPS Netcup

**Criterio de done:** Un amigo entra a una URL, pone su username de chess.com, y ve su reporte sin instalar nada.

---

## Fase 3 — Producto de Pago

**Objetivo:** Modelo de suscripcion sostenible.

- [ ] Stripe integration — $3-5/mes por usuario premium
- [ ] Ollama free tier — analisis narrativo con modelo local para usuarios gratis
- [ ] Maia model integration — analisis ajustado al nivel real del oponente
- [ ] Web dashboard frontend — React o Next.js, reemplaza HTML estatico
- [ ] Lichess integration — segunda fuente de datos

**Criterio de done:** Un usuario desconocido paga $5/mes y usa el producto sin friccion.
