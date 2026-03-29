.PHONY: dev dev-down dev-logs prod prod-down prod-logs migrate migrate-prod migration deploy backup ssl-init ssl-renew

# Dev
dev:
	docker compose up -d --build

dev-down:
	docker compose down

dev-logs:
	docker compose logs -f

# Prod
prod:
	docker compose -f docker-compose.prod.yml up -d --build

prod-down:
	docker compose -f docker-compose.prod.yml down

prod-logs:
	docker compose -f docker-compose.prod.yml logs -f

# Migrations
migrate:
	docker compose exec backend alembic upgrade head

migrate-prod:
	docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head

migration:
	docker compose exec backend alembic revision --autogenerate -m "$(msg)"

# Deploy
deploy:
	./scripts/deploy.sh

# Backup
backup:
	./scripts/backup.sh

# SSL
ssl-init:
	./scripts/init-ssl.sh

ssl-renew:
	docker compose -f docker-compose.prod.yml run --rm certbot renew
	docker compose -f docker-compose.prod.yml restart nginx
