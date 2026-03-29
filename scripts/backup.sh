#!/bin/bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"

set -a
source .env.prod
set +a

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="porubly_${TIMESTAMP}.sql.gz"

echo "Backing up database..."
docker compose -f docker-compose.prod.yml exec -T postgres \
    pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "${BACKUP_DIR}/${FILENAME}"

echo "Backup saved: ${BACKUP_DIR}/${FILENAME}"

echo "Cleaning backups older than 30 days..."
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete

echo "Done."
