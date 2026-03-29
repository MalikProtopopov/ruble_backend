#!/usr/bin/env bash
# Deploy script for По Рублю backend
# Target: backend.porublyu.parmenid.tech on 5.42.108.203
set -euo pipefail

SERVER="root@5.42.108.203"
DOMAIN="backend.porublyu.parmenid.tech"
ADMIN_DOMAIN="adminfront.porublyu.parmenid.tech"
PROJECT_DIR="/opt/porubly"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Deploying По Рублю backend to $SERVER ==="

# 1. Install system deps + docker on server
echo "→ Step 1: Setting up server..."
ssh $SERVER 'bash -s' << 'REMOTE_SETUP'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# Update & install essentials
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx curl git ufw

# Install Docker if missing
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi

# Install docker-compose plugin if missing
if ! docker compose version &>/dev/null; then
    apt-get install -y -qq docker-compose-plugin
fi

# Firewall
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable 2>/dev/null || true

# Create project dir
mkdir -p /opt/porubly

echo "Server setup complete"
REMOTE_SETUP

# 2. Sync project files to server
echo "→ Step 2: Syncing project files..."
rsync -azP --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='.env' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='node_modules' \
    --exclude='.ruff_cache' \
    "$REPO_DIR/" "$SERVER:$PROJECT_DIR/"

# 3. Configure environment and SSL on server
echo "→ Step 3: Configuring server..."
ssh $SERVER 'bash -s' << 'REMOTE_CONFIG'
set -euo pipefail
cd /opt/porubly

# Generate JWT keys
mkdir -p backend/keys
if [ ! -f backend/keys/private.pem ]; then
    openssl genrsa -out backend/keys/private.pem 2048 2>/dev/null
    openssl rsa -in backend/keys/private.pem -pubout -out backend/keys/public.pem 2>/dev/null
    echo "JWT keys generated"
fi

# Create .env for backend
cat > backend/.env << 'ENV'
DEBUG=false
SECRET_KEY=$(openssl rand -hex 32)

DATABASE_URL=postgresql+asyncpg://porubly:porubly@postgres:5432/porubly
REDIS_URL=redis://redis:6379/0

JWT_PRIVATE_KEY_PATH=keys/private.pem
JWT_PUBLIC_KEY_PATH=keys/public.pem
JWT_AUDIENCE=porubly-api
JWT_ISSUER=porubly

CORS_ALLOWED_ORIGINS=["*"]

S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=porubly
S3_PUBLIC_URL=https://backend.porublyu.parmenid.tech/s3/porubly

YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=

NOTIFICATION_PROVIDER=mock
EMAIL_PROVIDER=mock

PUBLIC_API_URL=https://backend.porublyu.parmenid.tech
FRONTEND_URL=https://adminfront.porublyu.parmenid.tech
ENV

# Fix the SECRET_KEY (shell expansion didn't work in heredoc)
ACTUAL_SECRET=$(openssl rand -hex 32)
sed -i "s/SECRET_KEY=.*/SECRET_KEY=$ACTUAL_SECRET/" backend/.env

echo "Environment configured"
REMOTE_CONFIG

# 4. Setup nginx
echo "→ Step 4: Configuring Nginx..."
ssh $SERVER 'bash -s' << 'REMOTE_NGINX'
set -euo pipefail

# Backend nginx config
cat > /etc/nginx/sites-available/porubly-backend << 'NGINX'
server {
    listen 80;
    server_name backend.porublyu.parmenid.tech;

    client_max_body_size 550M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
    }
}
NGINX

# Admin frontend nginx config (placeholder)
cat > /etc/nginx/sites-available/porubly-admin << 'NGINX'
server {
    listen 80;
    server_name adminfront.porublyu.parmenid.tech;

    root /var/www/porubly-admin;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX

# Enable sites
ln -sf /etc/nginx/sites-available/porubly-backend /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/porubly-admin /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Create admin frontend placeholder
mkdir -p /var/www/porubly-admin
echo '<html><body><h1>По Рублю - Admin Panel (placeholder)</h1></body></html>' > /var/www/porubly-admin/index.html

nginx -t && systemctl reload nginx
echo "Nginx configured"
REMOTE_NGINX

# 5. SSL certificates
echo "→ Step 5: Getting SSL certificates..."
ssh $SERVER 'bash -s' << 'REMOTE_SSL'
set -euo pipefail

# Get SSL certs via certbot
certbot --nginx -d backend.porublyu.parmenid.tech --non-interactive --agree-tos --email noreply-porublyu@parmenid.tech --redirect 2>&1 || echo "SSL for backend: check DNS"
certbot --nginx -d adminfront.porublyu.parmenid.tech --non-interactive --agree-tos --email noreply-porublyu@parmenid.tech --redirect 2>&1 || echo "SSL for admin: check DNS"

echo "SSL configured"
REMOTE_SSL

# 6. Start Docker services
echo "→ Step 6: Starting services..."
ssh $SERVER 'bash -s' << 'REMOTE_DOCKER'
set -euo pipefail
cd /opt/porubly

# Build and start
docker compose down 2>/dev/null || true
docker compose up -d --build

# Wait for postgres to be healthy
echo "Waiting for postgres..."
for i in {1..30}; do
    if docker compose exec -T postgres pg_isready -U porubly &>/dev/null; then
        echo "Postgres ready"
        break
    fi
    sleep 2
done

# Run migrations (PYTHONPATH=/app: alembic CLI may not see the app package otherwise)
echo "Running migrations..."
docker compose exec -T backend sh -c 'cd /app && PYTHONPATH=/app alembic upgrade head' 2>&1 || echo "Migration note: using auto-create from models"

# If alembic fails, create tables via Python
docker compose exec -T backend python -c "
import asyncio
from app.models.base import Base
from app.core.database import engine

async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print('Tables created')

asyncio.run(init())
"

echo "Docker services started"
REMOTE_DOCKER

# 7. Create admin user
echo "→ Step 7: Creating admin user..."
ssh $SERVER 'bash -s' << 'REMOTE_ADMIN'
set -euo pipefail
cd /opt/porubly

docker compose exec -T backend python -c "
import asyncio
from argon2 import PasswordHasher
from app.models.base import uuid7
from app.models import Admin
from app.core.database import engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

ph = PasswordHasher()

async def create_admin():
    from sqlalchemy.ext.asyncio import async_sessionmaker
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        # Check if admin already exists
        result = await session.execute(select(Admin).where(Admin.email == 'admin@porubly.ru'))
        if result.scalar_one_or_none():
            print('Admin already exists')
            return
        admin = Admin(
            id=uuid7(),
            email='admin@porubly.ru',
            password_hash=ph.hash('PoRubly2026!Adm'),
            name='Главный администратор',
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        print('Admin created: admin@porubly.ru / PoRubly2026!Adm')
    await engine.dispose()

asyncio.run(create_admin())
"
REMOTE_ADMIN

# 8. Health check
echo "→ Step 8: Verifying deployment..."
sleep 5
ssh $SERVER 'bash -s' << 'REMOTE_CHECK'
echo "=== Docker services ==="
cd /opt/porubly && docker compose ps

echo ""
echo "=== Health check ==="
curl -s http://127.0.0.1:8000/api/v1/health || echo "Health check failed"

echo ""
echo "=== Swagger docs ==="
curl -s -o /dev/null -w "Swagger: HTTP %{http_code}\n" http://127.0.0.1:8000/api/v1/docs

echo ""
echo "=== Admin login test ==="
curl -s -X POST http://127.0.0.1:8000/api/v1/admin/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@porubly.ru","password":"PoRubly2026!Adm"}' | python3 -m json.tool 2>/dev/null || echo "Admin login test failed"
REMOTE_CHECK

echo ""
echo "=========================================="
echo "  Deployment complete!"
echo "=========================================="
echo ""
echo "  Backend API: https://backend.porublyu.parmenid.tech"
echo "  Swagger:     https://backend.porublyu.parmenid.tech/api/v1/docs"
echo "  ReDoc:       https://backend.porublyu.parmenid.tech/api/v1/redoc"
echo "  Admin panel: https://adminfront.porublyu.parmenid.tech"
echo ""
echo "  Admin credentials:"
echo "    Email:    admin@porubly.ru"
echo "    Password: PoRubly2026!Adm"
echo ""
