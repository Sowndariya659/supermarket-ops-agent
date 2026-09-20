# Production Dockerfile for Supermarket Ops Agent
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies for fonts, matplotlib and PDF/PPTX generation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application codebase
COPY . .

# Create directory for artifacts
RUN mkdir -p /app/generated_artifacts

EXPOSE 8000

# Default command starts FastAPI web server with lifespan hooks
CMD ["python", "-m", "app.main"]
