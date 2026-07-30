.PHONY: up down down-v logs ps seed seed-meta dev test test-all build restart health shell

COMPOSE := docker compose
BACKEND := backend
ENGINES := mariadb postgres sqlserver mongo redis


up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

down-v:
	$(COMPOSE) down -v

restart: down up

build:
	$(COMPOSE) build


logs:
	$(COMPOSE) logs -f $(BACKEND)

ps:
	$(COMPOSE) ps


health:
	curl -fsS http://localhost:8000/health && echo


seed:
	$(COMPOSE) up -d $(ENGINES)
	$(COMPOSE) run --rm $(BACKEND) python -m app.seed


seed-meta:
	$(COMPOSE) run --rm $(BACKEND) python -m app.seed --metadata-only

dev:
	$(COMPOSE) up -d $(ENGINES)
	cd backend && WEB_CONCURRENCY=1 uvicorn app.main:app --reload --host 0.0.0.0 --port 8000


test:
	$(COMPOSE) up -d $(ENGINES)
	$(COMPOSE) run --rm $(BACKEND) pytest -v


test-all:
	$(COMPOSE) up -d $(ENGINES)
	$(COMPOSE) run --rm -e LOGMON_REQUIRE_ENGINES=1 $(BACKEND) pytest -v

shell:
	$(COMPOSE) run --rm $(BACKEND) bash
