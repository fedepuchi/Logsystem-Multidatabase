.PHONY: up down down-v logs ps seed dev test build restart

COMPOSE := docker compose
BACKEND := backend


up:
	$(COMPOSE) up -d --build
down:
	$(COMPOSE) down

down-v:
	$(COMPOSE) down -v

restart: down up

build:
	$(COMPOSE) build

# Logs en vivo del backend
logs:
	$(COMPOSE) logs -f $(BACKEND)


ps:
	$(COMPOSE) ps


seed:
	$(COMPOSE) up -d mariadb postgres sqlserver mongo redis
	$(COMPOSE) run --rm $(BACKEND) python -m app.scripts.seed

dev:
	$(COMPOSE) up -d mariadb postgres sqlserver mongo redis
	cd backend && WEB_CONCURRENCY=1 uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	$(COMPOSE) run --rm $(BACKEND) pytest -v