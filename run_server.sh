#!/usr/bin/env bash
set -euo pipefail

# Server Execution Script
# Responsibility: Start the FastAPI server with proper environment

echo ">>> Starting Email Summarizer API..."

source .env || true  # Load MONGO_URI first
export MONGO_URI="${MONGO_URI:-mongodb://localhost:27017}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Check if venv exists
if [ -d "venv" ]; then
    echo ">>> Using virtual environment..."
    source venv/bin/activate
fi

# Start server
exec uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
