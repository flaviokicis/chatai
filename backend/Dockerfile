# syntax=docker/dockerfile:1.6

# Note: This Dockerfile assumes Railway root directory is set to the project root (not /backend)
# If Railway root is /backend, change it to the project root in Railway settings

# Frontend build stage
FROM node:18-alpine AS frontend-builder

WORKDIR /frontend

# Copy frontend package files
COPY frontend/package.json frontend/pnpm-lock.yaml ./

# Install pnpm and dependencies
RUN npm install -g pnpm
RUN pnpm install --frozen-lockfile

# Copy frontend source
COPY frontend/ ./

# Build static export
RUN pnpm run build

# Backend stage
FROM python:3.12-slim AS base

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
COPY backend/pyproject.toml ./

# Provide README expected by pyproject metadata during build
RUN echo "# ChatAI Backend" > README.md

# Install project and all runtime dependencies system-wide
# This installs the package defined by pyproject and its [project.dependencies]
RUN pip install --no-cache-dir .

# Copy backend project files and source
COPY backend/uv.lock ./
COPY backend/app ./app
COPY backend/config.json ./config.json
COPY backend/config.local.json ./config.local.json

# Copy frontend static files from build stage
COPY --from=frontend-builder /frontend/.next ./static

# Install uv for additional dependency management if needed
RUN pip install --no-cache-dir uv

# Expose port
EXPOSE 8080

ENV PORT=8080
ENV CONFIG_JSON_PATH=/app/config.local.json

# Start command - uvicorn is installed system-wide by pip
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
