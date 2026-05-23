# chesslens — Documentation

## Quick links

- [Vision y estrategia](./vision.md)
- [Roadmap por fases](./roadmap.md)
- [Arquitectura tecnica](./architecture.md)
- [Architecture Decision Records](./decisions/)
- [Research de mercado](./research/)

## What is chesslens

Personal chess analysis tool with monthly Wrapped-style reports.

Connects to chess.com public API, analyzes your games with Stockfish locally, extracts statistical patterns, and generates a narrative report via LLM — free, no chess.com premium required.

## Getting started

```bash
# Install
git clone https://github.com/CristianPeralta/chesslens
cd chesslens
uv sync

# Configure
cp .env.example .env
# Edit .env with your username and API key

# Run
chesslens config --username krix0s
chesslens stats
chesslens report
```

## CLI commands

| Command | Description |
|---|---|
| `chesslens config` | Save chess.com username and preferences |
| `chesslens stats` | Quick stats in terminal (last 30 days) |
| `chesslens report` | Monthly Wrapped report (HTML, opens in browser) |
| `chesslens game` | Single game analysis (HTML) |
| `chesslens opening` | Opening breakdown by name (HTML) |
