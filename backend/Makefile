.PHONY: help setup-test test test-integration test-api test-public test-admin lint keys db-test

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Setup ---

setup-test: keys db-test ## Full test environment setup
	pip install -q -e ".[dev]" 2>/dev/null || pip install -q ".[dev]"
	@echo "Test environment ready. Run: make test"

keys: ## Generate JWT RSA keys (if missing)
	@mkdir -p keys
	@test -f keys/private.pem || (openssl genrsa -out keys/private.pem 2048 2>/dev/null && openssl rsa -in keys/private.pem -pubout -out keys/public.pem 2>/dev/null && echo "Keys generated")
	@test -f keys/private.pem && echo "Keys OK"

db-test: ## Create porubly_test database (requires postgres running)
	@docker exec fondback-postgres-1 psql -U porubly -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='porubly_test'" | grep -q 1 \
		|| docker exec fondback-postgres-1 psql -U porubly -d postgres -c "CREATE DATABASE porubly_test OWNER porubly"
	@echo "Test database OK"

# --- Tests ---

test: ## Run all tests
	DATABASE_URL=postgresql+asyncpg://porubly:porubly@localhost:5432/porubly_test \
	REDIS_URL=redis://localhost:6379/1 \
	pytest tests/ -x -v --tb=short

test-integration: ## Run integration tests only
	DATABASE_URL=postgresql+asyncpg://porubly:porubly@localhost:5432/porubly_test \
	REDIS_URL=redis://localhost:6379/1 \
	pytest tests/integration/ -x -v --tb=short

test-api: ## Run all API tests
	DATABASE_URL=postgresql+asyncpg://porubly:porubly@localhost:5432/porubly_test \
	REDIS_URL=redis://localhost:6379/1 \
	pytest tests/api/ -x -v --tb=short

test-public: ## Run public API tests
	DATABASE_URL=postgresql+asyncpg://porubly:porubly@localhost:5432/porubly_test \
	REDIS_URL=redis://localhost:6379/1 \
	pytest tests/api/public/ -x -v --tb=short

test-admin: ## Run admin API tests
	DATABASE_URL=postgresql+asyncpg://porubly:porubly@localhost:5432/porubly_test \
	REDIS_URL=redis://localhost:6379/1 \
	pytest tests/api/admin/ -x -v --tb=short

test-fast: ## Run tests in parallel (requires pytest-xdist)
	DATABASE_URL=postgresql+asyncpg://porubly:porubly@localhost:5432/porubly_test \
	REDIS_URL=redis://localhost:6379/1 \
	pytest tests/ -x --tb=short -q

# --- Code quality ---

lint: ## Run linter
	ruff check app/ tests/

lint-fix: ## Run linter with auto-fix
	ruff check --fix app/ tests/

format: ## Format code
	ruff format app/ tests/

# --- Docker ---

up: ## Start all services (postgres, redis, minio)
	docker compose up -d postgres redis minio minio-init

down: ## Stop all services
	docker compose down

logs: ## Show backend logs
	docker compose logs -f backend
