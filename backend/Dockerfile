FROM python:3.12-slim

WORKDIR /app

# Install system dependencies and ensure build tools
RUN apt-get update && apt-get install -y \
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

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

ENV PORT=8080

# Start command - uvicorn is installed system-wide by pip
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
