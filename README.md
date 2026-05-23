# chesslens

Your chess, through a clear lens.

Personal chess analysis tool that connects to chess.com, analyzes your games with Stockfish, and generates monthly Wrapped-style reports with AI narrative — free, no chess.com premium required.

## Install

```bash
# Requires: Python 3.11+, uv, Stockfish
git clone https://github.com/CristianPeralta/chesslens
cd chesslens
uv sync
```

## Usage

```bash
chesslens config --username your_username   # setup once
chesslens stats                             # quick stats in terminal
chesslens report                            # monthly Wrapped report (HTML)
chesslens game --last                       # last game analysis (HTML)
chesslens opening "French Defense"          # opening breakdown (HTML)
```

## Usage with Docker

No need to install Python or Stockfish manually:

```bash
cp .env.example .env
docker compose run --rm chesslens config --username your_username
docker compose run --rm chesslens report
```

> **Linux note:** if `docker compose build` fails resolving apt repos, run `docker compose build --no-cache` with `network_mode: host` in the compose file, or configure Docker daemon DNS: add `{"dns": ["8.8.8.8"]}` to `/etc/docker/daemon.json` and restart Docker.

## Docs

See [docs/index.md](./docs/index.md) for full documentation.
