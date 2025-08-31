# syntax=docker/dockerfile:1.6

# Dockerfile optimized for Railway root directory = /backend
# Frontend will be pre-built and copied into backend/static before deployment

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies and ensure build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install UV (the proper way)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Copy project files for UV
COPY pyproject.toml uv.lock ./
COPY app ./app
COPY config.json ./config.json
COPY config.local.json ./config.local.json

# Copy frontend static files (pre-built and copied by build-frontend.sh)
COPY static ./static

# Install dependencies using UV
RUN uv sync --frozen

# Create virtual environment activation script
RUN echo '#!/bin/bash\nsource .venv/bin/activate\nexec "$@"' > /entrypoint.sh && chmod +x /entrypoint.sh

# Expose port
EXPOSE 8080

ENV PORT=8080
ENV CONFIG_JSON_PATH=/app/config.local.json

# Start command using UV virtual environment
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
