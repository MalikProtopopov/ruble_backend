#!/bin/bash
set -euo pipefail

set -a
source .env.prod
set +a

echo "Obtaining SSL certificate for ${API_DOMAIN}..."

docker compose -f docker-compose.prod.yml run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    -d "${API_DOMAIN}" \
    --email "${CERT_EMAIL}" \
    --agree-tos \
    --no-eff-email

echo "Restarting nginx..."
docker compose -f docker-compose.prod.yml restart nginx

echo "SSL setup complete."
