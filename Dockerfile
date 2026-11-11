FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.32
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts/setup_checkpoints.py ./scripts/setup_checkpoints.py
RUN useradd --uid 10001 --create-home advisor && mkdir -p /data/raw && chown advisor:advisor /data/raw
USER advisor
EXPOSE 8000
