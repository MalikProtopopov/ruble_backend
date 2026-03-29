#!/usr/bin/env bash
# Setup test environment: generate JWT keys, create test database, install deps.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
cd "$BACKEND_DIR"

echo "=== Setting up test environment ==="

# 1. Generate RSA keys for JWT (if not exist)
KEYS_DIR="$BACKEND_DIR/keys"
if [ ! -f "$KEYS_DIR/private.pem" ]; then
    echo "→ Generating RSA keys for JWT..."
    mkdir -p "$KEYS_DIR"
    openssl genrsa -out "$KEYS_DIR/private.pem" 2048 2>/dev/null
    openssl rsa -in "$KEYS_DIR/private.pem" -pubout -out "$KEYS_DIR/public.pem" 2>/dev/null
    echo "  Keys created at $KEYS_DIR/"
else
    echo "  Keys already exist at $KEYS_DIR/"
fi

# 2. Create test database (requires postgres running)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-porubly}"
DB_PASSWORD="${DB_PASSWORD:-porubly}"
TEST_DB="porubly_test"

echo "→ Creating test database '$TEST_DB'..."
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -tc \
    "SELECT 1 FROM pg_database WHERE datname='$TEST_DB'" | grep -q 1 \
    || PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c \
    "CREATE DATABASE $TEST_DB OWNER $DB_USER"
echo "  Database '$TEST_DB' ready"

# 3. Create .env.test if not exists
ENV_TEST="$BACKEND_DIR/.env.test"
if [ ! -f "$ENV_TEST" ]; then
    echo "→ Creating .env.test..."
    cat > "$ENV_TEST" << 'EOF'
DEBUG=true
SECRET_KEY=test-secret-key

DATABASE_URL=postgresql+asyncpg://porubly:porubly@localhost:5432/porubly_test
REDIS_URL=redis://localhost:6379/1

JWT_PRIVATE_KEY_PATH=keys/private.pem
JWT_PUBLIC_KEY_PATH=keys/public.pem
JWT_AUDIENCE=porubly-api
JWT_ISSUER=porubly

S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=porubly-test
S3_PUBLIC_URL=http://localhost:9000/porubly-test

YOOKASSA_SHOP_ID=test-shop
YOOKASSA_SECRET_KEY=test-secret

NOTIFICATION_PROVIDER=mock
EMAIL_PROVIDER=mock

CORS_ALLOWED_ORIGINS=["http://localhost:3000"]
EOF
    echo "  Created $ENV_TEST"
else
    echo "  .env.test already exists"
fi

# 4. Install dev dependencies
echo "→ Installing dependencies (with dev extras)..."
pip install -q -e ".[dev]" 2>/dev/null || pip install -q ".[dev]"
echo "  Dependencies installed"

echo ""
echo "=== Test environment ready ==="
echo ""
echo "Run tests with:"
echo "  cd $BACKEND_DIR"
echo "  make test                 # all tests"
echo "  make test-integration     # integration only"
echo "  make test-api             # API tests only"
echo "  pytest tests/ -x -v       # verbose with stop on first failure"
