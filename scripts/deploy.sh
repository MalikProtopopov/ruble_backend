#!/bin/bash
set -euo pipefail

echo "=== Deploy started ==="

set -a
source .env.prod
set +a

echo "Pulling latest code..."
git pull origin main

echo "Building backend..."
docker compose -f docker-compose.prod.yml build backend

echo "Running migrations..."
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head

echo "Starting services..."
docker compose -f docker-compose.prod.yml up -d --no-deps --build backend worker

echo "Restarting nginx..."
docker compose -f docker-compose.prod.yml restart nginx

echo "Pruning old images..."
docker image prune -f

echo "Health check..."
sleep 5
curl -sf "https://${API_DOMAIN}/api/v1/health" && echo " OK" || echo " FAILED"

echo "=== Deploy complete ==="
