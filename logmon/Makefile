.PHONY: up down down-v restart build logs ps health seed seed-meta seed-dev \
        dev front front-build test test-all shell

COMPOSE := docker compose
BACKEND := backend
ENGINES := mariadb postgres sqlserver mongo redis

# En `dev` el backend corre en el host, así que llega a los motores por los
# puertos publicados en localhost y no por el nombre de servicio de compose.
DEV_ENV := WEB_CONCURRENCY=1 \
	SQLITE_PATH=./data/logmon.db \
	STATIC_DIR= \
	MARIADB_HOST=localhost \
	POSTGRES_HOST=localhost \
	SQLSERVER_HOST=localhost \
	MONGO_HOST=localhost \
	REDIS_HOST=localhost


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


# El seed corre en un contenedor aparte y escribe en la metadata compartida.
# Se reinicia el backend para que el router recargue el mapa de destinos
# activos desde source_bindings.
seed:
	$(COMPOSE) up -d $(ENGINES)
	$(COMPOSE) run --rm $(BACKEND) python -m app.seed
	-$(COMPOSE) restart $(BACKEND)

seed-meta:
	$(COMPOSE) run --rm $(BACKEND) python -m app.seed --metadata-only
	-$(COMPOSE) restart $(BACKEND)

# Seed contra el backend que corre en el host (target `dev`).
seed-dev:
	cd backend && $(DEV_ENV) python -m app.seed


dev:
	$(COMPOSE) up -d $(ENGINES)
	cd backend && $(DEV_ENV) uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

front:
	cd frontend && npm install && npm run dev

front-build:
	cd frontend && npm install && npm run build


# Sin motores levantados, los tests de adapters se saltan.
test:
	$(COMPOSE) up -d $(ENGINES)
	$(COMPOSE) run --rm $(BACKEND) pytest -v

# Igual que test, pero un motor caído es un fallo en vez de un skip.
test-all:
	$(COMPOSE) up -d $(ENGINES)
	$(COMPOSE) run --rm -e LOGMON_REQUIRE_ENGINES=1 $(BACKEND) pytest -v

shell:
	$(COMPOSE) run --rm $(BACKEND) bash
