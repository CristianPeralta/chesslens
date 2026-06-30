FROM python:3.11-slim-bookworm

# Install Stockfish + curl (Lichess import shells out to curl — LiteLLM
# monkey-patches httpx/requests in-process, breaking redirect handling)
RUN apt-get update && apt-get install -y --no-install-recommends \
    stockfish \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies before copying source — better layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy source and install project
COPY src/ ./src/
COPY README.md ./
COPY alembic.ini ./
COPY migrations/ ./migrations/
RUN uv sync --frozen

# Debian's stockfish package installs to /usr/games, which isn't on
# the default non-login PATH inside containers.
ENV PATH="/app/.venv/bin:/usr/games:$PATH"

EXPOSE 8000
