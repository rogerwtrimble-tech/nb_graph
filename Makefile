# nb_graph convenience targets (Linux/macOS, or Windows with WSL / Git Bash).
# Every target is a plain `docker compose` command, see docs/docker-setup.md for the raw equivalents.
COMPOSE ?= docker compose
PSQL = $(COMPOSE) exec -T postgres psql -U netbox -d netbox

.PHONY: help env up down logs ps seed reset psql graph-install graph-stats test ui-dev pgq-info

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

env:             ## create .env with random secrets (from .env.example)
	python3 scripts/gen-env.py

up:              ## build and start the whole stack (first start: ~5-10 min of NetBox migrations)
	@test -f .env || cp .env.example .env
	$(COMPOSE) up -d --build
	@echo "UI      http://localhost:$${UI_PORT:-8080}"
	@echo "NetBox  http://localhost:$${NETBOX_PORT:-8000}   (admin / see .env)"
	@echo "API     http://localhost:$${GRAPH_API_PORT:-8090}/docs"

down:            ## stop the stack (keeps data)
	$(COMPOSE) down

reset:           ## stop and DELETE all data volumes
	$(COMPOSE) down -v

logs:            ## follow logs
	$(COMPOSE) logs -f --tail=100

ps:              ## container status
	$(COMPOSE) ps

seed:            ## (re)run the idempotent FTTH demo seeder
	$(COMPOSE) run --rm seed

psql:            ## psql shell into the NetBox/graph database
	$(COMPOSE) exec postgres psql -U netbox -d netbox

graph-install:   ## re-apply db/graph/*.sql (after editing the projection)
	curl -fsS -X POST http://localhost:$${GRAPH_API_PORT:-8090}/api/admin/graph/install; echo

graph-stats:     ## vertex/edge counts from the live projection
	$(PSQL) -c "SELECT * FROM nbgraph.stats ORDER BY 1,2"

test:            ## run API unit tests (+ integration tests when NBGRAPH_API is reachable)
	cd graph-api && python3 -m pytest -q

ui-dev:          ## run the UI with hot reload against the running graph-api
	cd ui && npm install && GRAPH_API=http://localhost:$${GRAPH_API_PORT:-8090} npm run dev
