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

## Docs

See [docs/index.md](./docs/index.md) for full documentation.
