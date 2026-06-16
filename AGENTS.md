# chesslens

Automated personal chess coach — the coach you can't afford to pay.
Analyzes your chess.com games with Stockfish, detects real error patterns, and generates a monthly improvement roadmap with actionable study recommendations.

Core differentiator: **time-travel replay** — go back to the exact move where you lost, replay from there with your remaining clock time (or without pressure), with progressive Stockfish hints. No competitor has this (verified 2026-06-15).

See [docs/index.md](./docs/index.md) for complete documentation.

---

## Stack

| Layer        | Technology                        | Why                                                       |
|--------------|-----------------------------------|-----------------------------------------------------------|
| CLI          | Typer + Rich                      | Clean CLI with terminal feedback, same author as FastAPI  |
| Core logic   | Python puro + python-chess        | Zero framework dependency in domain layer                 |
| Chess engine | Stockfish (local)                 | Free, industry standard, runs offline                     |
| Statistics   | pandas                            | Pattern extraction across N games                         |
| AI narrative | LiteLLM + Claude Sonnet (default) | Provider-agnostic, swap model with one config line        |
| Templates    | Jinja2 + Chart.js (CDN)           | Static HTML reports, no build step, reusable en web       |
| DB           | SQLite + SQLAlchemy               | Zero setup, schema-ready for PostgreSQL migration         |
| HTTP client  | httpx                             | Async-ready, clean API for chess.com public endpoints     |

---

## Architecture

```
src/chesslens/
├── core/           — domain logic, zero framework imports
│   ├── fetcher.py      — chess.com API client
│   ├── parser.py       — PGN parsing with python-chess
│   ├── analyzer.py     — Stockfish integration, centipawn loss
│   ├── patterns.py     — statistical pattern extraction (pandas)
│   └── reporter.py     — LiteLLM narrative generation
├── delivery/       — swappable delivery layer
│   └── cli.py          — Typer commands (Phase 1)
│   └── api.py          — FastAPI routes (Phase 2, not yet)
├── templates/      — Jinja2 HTML templates
│   ├── base.html
│   ├── report.html     — monthly Wrapped report
│   ├── game.html       — single game analysis
│   └── opening.html    — opening breakdown
├── db/
│   ├── models.py       — SQLAlchemy models
│   └── session.py      — DB session factory
└── config.py       — settings from .env
```

CLI commands (Phase 1):

```
chesslens config --username <user>   — save chess.com username
chesslens stats                      — quick stats in terminal
chesslens report [--month YYYY-MM]   — monthly Wrapped report (HTML)
chesslens game [--last | --id <id>]  — single game analysis (HTML)
chesslens opening <name>             — opening breakdown (HTML)
```

---

## Data Model

```sql
-- Cached games from chess.com API
games (
    id               varchar primary key,   -- chess.com game ID
    username         varchar not null,
    played_at        timestamptz not null,
    time_class       varchar not null,      -- blitz | rapid | bullet | daily
    color            varchar not null,      -- "white" | "black" from user perspective
    result           varchar not null,      -- win | loss | draw
    end_reason       varchar not null,      -- checkmate | timeout | resigned | draw | abandoned
    opponent         varchar not null,
    player_rating    int not null,
    opponent_rating  int not null,
    opening_eco      varchar,
    opening_name     varchar,
    move_count       int not null,
    pgn              text not null,
    fetched_at       timestamptz default now()
);

-- Stockfish analysis results per game
analysis (
    game_id           varchar primary key references games(id),
    accuracy          float,
    avg_centipawn_loss float,
    blunders          int default 0,
    mistakes          int default 0,
    inaccuracies      int default 0,
    timeout_move      int,                  -- ply at timeout, null if not timeout
    analyzed_at       timestamptz default now()
);

-- Generated monthly reports (cache)
reports (
    id            serial primary key,
    username      varchar not null,
    month         varchar not null,     -- YYYY-MM
    html          text not null,
    narrative     text not null,
    generated_at  timestamptz default now(),
    unique(username, month)
);
```

---

## Development Workflow

### Branch and commit conventions

```
# Branches
feature/<issue-number>-short-description
fix/<issue-number>-short-description
chore/short-description
docs/short-description

# Examples
feature/1-project-scaffolding
feature/3-chessdotcom-fetcher
feature/6-litellm-narrative

# Commits — Conventional Commits
feat: add chess.com API fetcher
fix: handle missing ECO code in PGN headers
chore: add pyproject.toml and dependencies
docs: add architecture ADR for LiteLLM abstraction
test: add fetcher unit tests with fixture
```

Rules:
- Every commit authored by Cristian only. No co-authors.
- One feature per branch. One branch per issue.
- PRs include `Closes #<number>` — GitHub auto-closes on merge.
- Merge to `main` via PR. No direct pushes to `main` for features.
- Docs and ADRs can be committed directly to `main`.

### Testing strategy

TDD where it reduces debugging, not for coverage metrics.

| Area              | Approach                                                      | Why                                    |
|-------------------|---------------------------------------------------------------|----------------------------------------|
| core/fetcher.py   | TDD — fixture from real API response, test parsing            | Silent failures on API schema changes  |
| core/patterns.py  | TDD — deterministic stats, easy to unit test                  | Core value prop, must be correct       |
| core/reporter.py  | Integration test with real LiteLLM call (mocked in CI)        | Narrative quality is subjective        |
| CLI commands      | Manual smoke test                                             | Low complexity CRUD-like               |
| HTML templates    | Visual inspection                                             | Faster than snapshot tests             |

Test fixtures in `tests/fixtures/` — real anonymized API responses.

---

## AI Provider

chesslens uses LiteLLM to stay provider-agnostic.

```python
# config.py
AI_MODEL = os.getenv("CHESSLENS_MODEL", "claude-sonnet-4-6")

# core/reporter.py
from litellm import completion

response = completion(
    model=settings.AI_MODEL,
    messages=[{"role": "user", "content": prompt}]
)
```

Switching providers is one env var change:

```bash
CHESSLENS_MODEL=gpt-4o               # OpenAI
CHESSLENS_MODEL=gemini/gemini-2.5-pro # Google
CHESSLENS_MODEL=ollama/llama3        # Local, free
```

---

## Behavioral Rules

- **NEVER import Typer or FastAPI in core/** — domain logic must be framework-free.
- **NEVER hardcode chess.com username** — always from config or CLI arg.
- **NEVER skip SQLAlchemy** — even for simple queries, no raw SQL.
- **No over-engineering** — functional and demonstrable beats perfect.
- **Prefer editing existing files** over creating new ones.
- **Three similar lines > premature abstraction.**
- **Clean commits** — repo is public.

## Documenting Decisions

**`WHY:` inline comment** — file-specific non-obvious decisions.

```python
# WHY: chess.com API returns games in reverse chronological order — we reverse before inserting
```

**ADR in `docs/decisions/`** — cross-cutting architectural decisions. Format: `NNNN-short-title.md`.

---

## Scope

**Phase 1 — MVP personal (CLI + HTML):**
- chess.com API fetcher (blitz games, public endpoint)
- Stockfish analysis (accuracy, centipawn loss, blunders, timeout detection)
- Statistical patterns (win rate by color, opening breakdown, time management)
- LiteLLM narrative (Wrapped monthly report)
- 4 CLI commands: config, stats, report, game, opening
- SQLite persistence

**Phase 2 — Multi-usuario + time-travel replay:**
- FastAPI web delivery (same core)
- PostgreSQL, JWT auth, background jobs
- Time-travel replay UI (Stockfish.js WASM, interactive board, real clock pressure)

**Phase 3 — Producto de pago:**
- Stripe, freemium with Ollama free tier ($3-5/month for Claude/GPT-4)
- Maia model integration (analysis calibrated to opponent ELO, not perfect play)
- Web dashboard frontend

**Out of scope:**
- Multi-tenant in Phase 1
- Lichess integration (Phase 2+)
- Live board analysis

GitHub Project: https://github.com/users/CristianPeralta/projects/4

---

## Documentation

- [`docs/index.md`](./docs/index.md) — Documentation index
- [`docs/vision.md`](./docs/vision.md) — Product vision and strategy
- [`docs/roadmap.md`](./docs/roadmap.md) — Roadmap by phase
- [`docs/architecture.md`](./docs/architecture.md) — Architecture details
- [`docs/decisions/`](./docs/decisions/) — Architecture Decision Records
- [`docs/research/`](./docs/research/) — Market research (read-only reference)
