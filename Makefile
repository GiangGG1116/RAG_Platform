.PHONY: help up down build logs ps test lint migrate seed clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Docker ──────────────────────────────────────────────
up: ## Start all services
	docker compose up -d

up-full: ## Start all services + observability
	docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d

down: ## Stop all services
	docker compose -f docker-compose.yml -f docker-compose.observability.yml down

build: ## Build all images
	docker compose build

logs: ## Tail logs for all services
	docker compose logs -f

ps: ## Show running services
	docker compose ps

# ─── Database ────────────────────────────────────────────
migrate: ## Run Alembic migrations
	docker compose exec api-gateway alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create MSG="add users table")
	docker compose exec api-gateway alembic revision --autogenerate -m "$(MSG)"

seed: ## Seed database with sample data
	docker compose exec api-gateway python /app/scripts/seed_data.py

# ─── Testing ─────────────────────────────────────────────
test: ## Run all tests
	docker compose exec api-gateway python -m pytest /app/services/ -v

test-unit: ## Run unit tests only
	docker compose exec api-gateway python -m pytest /app/services/ -v -m "not integration"

test-integration: ## Run integration tests
	docker compose exec api-gateway python -m pytest /app/services/ -v -m "integration"

# ─── Code Quality ────────────────────────────────────────
lint: ## Run linter
	ruff check .

format: ## Format code
	ruff format .

# ─── Kubernetes ──────────────────────────────────────────
k8s-apply: ## Apply K8s manifests
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/configmap.yaml
	kubectl apply -f k8s/secrets.yaml
	kubectl apply -f k8s/postgres/
	kubectl apply -f k8s/rabbitmq/
	kubectl apply -f k8s/redis/
	kubectl apply -f k8s/api-gateway/
	kubectl apply -f k8s/ingestion/
	kubectl apply -f k8s/retrieval/
	kubectl apply -f k8s/llm-service/
	kubectl apply -f k8s/worker/
	kubectl apply -f k8s/observability/

k8s-delete: ## Delete K8s resources
	kubectl delete -f k8s/ --recursive --ignore-not-found

# ─── Cleanup ─────────────────────────────────────────────
clean: ## Remove all containers, volumes, and images
	docker compose -f docker-compose.yml -f docker-compose.observability.yml down -v --rmi local
