#!/usr/bin/env bash
set -euo pipefail

# Infrastructure Setup Script
# Responsibility: Ensure MongoDB and Qdrant are running via Docker

echo ">>> Initializing Infrastructure..."

# Check dependencies
for cmd in docker docker-compose; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "Error: $cmd is not installed."
        exit 1
    fi
done

# Start services
echo ">>> Starting MongoDB, Qdrant, and Redis..."
docker-compose up -d mongodb qdrant redis

# Wait for MongoDB
echo ">>> Waiting for MongoDB to be ready..."
until docker exec email_summarizer_mongo mongosh --eval "db.adminCommand('ping')" &> /dev/null; do
  sleep 2
done

echo ">>> Infrastructure is READY."
