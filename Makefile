# OpenLivery — developer commands
# Run `make` or `make help` to list targets.
#
# Override host ports if they clash with other local services, e.g.:
#   API_PORT=8001 WEB_PORT=3001 make up
# Expose on a server (not just localhost):
#   BIND_HOST=0.0.0.0 make up

API_PORT  ?= 8000
WEB_PORT  ?= 3000
DB_PORT   ?= 5432
BIND_HOST ?= 127.0.0.1
# Keep the browser's API URL in sync with API_PORT unless set explicitly.
NEXT_PUBLIC_API_URL ?= http://localhost:$(API_PORT)
export API_PORT WEB_PORT DB_PORT BIND_HOST NEXT_PUBLIC_API_URL

COMPOSE := docker compose --env-file .env.docker

.DEFAULT_GOAL := help
.PHONY: help env up deploy down stop start restart build logs ps migrate test shell-api shell-db destroy

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}'

env: ## Generate .env.docker with random secrets (only if missing)
	@test -f .env.docker || ./scripts/generate-docker-env.sh

up: env ## Build and start the whole stack (detached)
	$(COMPOSE) up --build -d
	@echo ""
	@echo "  App:  http://localhost:$(WEB_PORT)"
	@echo "  API:  http://localhost:$(API_PORT)/docs"

deploy: env ## Build and start with the Caddy HTTPS reverse proxy (set DOMAIN in .env.docker)
	@grep -q '^DOMAIN=..*' .env.docker || { echo "Set DOMAIN=your.domain in .env.docker first."; exit 1; }
	$(COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml up --build -d
	@echo ""
	@echo "  Serving https://$$(grep '^DOMAIN=' .env.docker | cut -d= -f2) once DNS points here and ports 80/443 are open."

down: ## Stop and remove containers (keeps data volumes)
	$(COMPOSE) down

stop: ## Stop containers without removing them
	$(COMPOSE) stop

start: ## Start previously created containers
	$(COMPOSE) start

restart: ## Restart all services
	$(COMPOSE) restart

build: env ## Build images without starting them
	$(COMPOSE) build

logs: ## Follow logs from all services (SERVICE=api to filter)
	$(COMPOSE) logs -f $(SERVICE)

ps: ## Show service status
	$(COMPOSE) ps

migrate: ## Apply Alembic migrations in the running api container
	$(COMPOSE) exec api alembic upgrade head

test: ## Run backend tests + rebuild web/whatsapp validation stages
	$(COMPOSE) exec api pytest -q
	$(COMPOSE) build web whatsapp

shell-api: ## Open a shell in the api container
	$(COMPOSE) exec api sh

shell-db: ## Open psql in the database container
	$(COMPOSE) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

destroy: ## DANGER: remove containers AND volumes (deletes all data)
	$(COMPOSE) down --volumes --remove-orphans
