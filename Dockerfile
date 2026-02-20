FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml ./
RUN uv sync --no-dev

# Copy source
COPY . .

CMD ["uv", "run", "python", "-m", "bot.main"]
