FROM python:3.12-slim

# Install system deps
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd --create-home app

# Install Python deps
WORKDIR /app

# Multi-stage inspired: install deps first, copy code last
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source (filtered by .dockerignore)
COPY . .

# Switch to app user, non-root
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health/live || exit 1

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
