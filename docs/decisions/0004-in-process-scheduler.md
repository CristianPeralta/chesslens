# ADR 0004 — In-Process Scheduler for Monthly Report Generation

**Status**: Accepted
**Date**: 2026-06-17

## Context

chesslens needs to regenerate monthly Wrapped reports automatically for all users on the 1st of each month. The options considered were:

| Option | Infra required | Notes |
|--------|---------------|-------|
| **In-process `AsyncIOScheduler`** (APScheduler) | None beyond existing uvicorn | Runs inside the API process; no broker, no extra service |
| Celery + Redis/RabbitMQ | Redis or RabbitMQ broker, Celery worker process | Justified when tasks are frequent, heavy, or need distributed retries |
| arq + Redis | Redis broker, arq worker process | Lighter than Celery; still requires a broker and separate worker |
| OS cron + script | Cron daemon, management of credentials/env | Decoupled but brittle; no visibility from the app |

## Decision

Use APScheduler's `AsyncIOScheduler` wired into the FastAPI `lifespan`. The job fires on a `CronTrigger(day=1, hour=0, minute=5, timezone="UTC")`. No broker, no separate worker process, no config class.

## Rationale

- **Ponytail**: monthly cadence is 12 triggers/year. Introducing a broker for that is over-engineering.
- **Infra cost**: single SQLite-backed deployment. Adding Redis would double the ops surface for zero user-visible benefit at this scale.
- **Simplicity**: the scheduler starts with the app and stops when the app stops — the same lifecycle contract as `init_db()`.
- **Code surface**: ~30 lines in `api.py` lifespan + `core/jobs.py`; no new config, no new service.

## Single-Worker Constraint

**CRITICAL**: deploy with `--workers 1`.

```
uvicorn chesslens.delivery.api:app --workers 1
```

Multiple uvicorn workers each instantiate a separate `AsyncIOScheduler`. N workers = N schedulers = N duplicate batch runs on the 1st of the month. The `UNIQUE(username, month)` constraint on `reports` prevents duplicate rows, but the extra Stockfish/API work is wasted.

This constraint is documented in the `api.py` module docstring.

## Phase 2 Exit Path

When chesslens moves to multi-worker / multi-instance deployments (Phase 2), replace the in-process scheduler with **arq** (async Redis queue) or **APScheduler with a distributed job store** (e.g., SQLAlchemy job store with a PostgreSQL lock). At that point:

1. Remove `AsyncIOScheduler` from `lifespan`.
2. Add an arq worker entrypoint that calls `generate_report_for_user` — the pipeline in `core/jobs.py` does not change.
3. Remove the `--workers 1` constraint.

The `core/jobs.py` pipeline is already isolated from FastAPI, so the migration is additive.

## Consequences

- Monthly reports are generated automatically without any external trigger.
- Deployments must use `--workers 1` (documented; enforced by convention, not code).
- Stockfish analysis runs via `run_in_executor` to avoid blocking the event loop during the batch.
- A failure for one user is logged and swallowed; other users' reports are unaffected.
