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
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip to avoid build issues
RUN pip install --no-cache-dir --upgrade pip

# Copy project metadata for dependency install
COPY pyproject.toml ./

# Provide README expected by pyproject metadata during build
RUN echo "# ChatAI Backend" > README.md

# Install project and all runtime dependencies system-wide
# This installs the package defined by pyproject and its [project.dependencies]
RUN pip install --no-cache-dir .

# Copy backend project files and source
COPY uv.lock ./
COPY app ./app
COPY config.json ./config.json
COPY config.local.json ./config.local.json

# Create static directory for frontend files (may be empty for backend-only deploys)
RUN mkdir -p ./static

# Expose port
EXPOSE 8080

ENV PORT=8080
ENV CONFIG_JSON_PATH=/app/config.local.json

# Start command - uvicorn is installed system-wide by pip
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
