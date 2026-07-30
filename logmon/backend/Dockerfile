# El contexto de build es logmon/ (no logmon/backend/) porque esta imagen
# también compila el SPA y lo sirve desde FastAPI.

# --- etapa 1: build del frontend ---------------------------------------
FROM node:20-slim AS frontend

WORKDIR /ui

# El glob toma package-lock.json si está versionado, para que el build sea
# reproducible, y no falla si no está.
COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build


# --- etapa 2: backend ---------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# freetds-* es lo que necesita pymssql; curl es para el healthcheck.
#
# build-essential (gcc + g++ + make + libc6-dev) hace falta porque asyncmy no
# publica wheel para linux/aarch64: en Mac con Apple Silicon pip lo compila
# desde el fuente. Con `gcc` a secas y --no-install-recommends falta libc6-dev
# y la compilación se cae.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        freetds-dev \
        freetds-bin \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Se instalan sólo las dependencias primero para aprovechar la cache de capas:
# el pyproject declara `py-modules = []`, así que `pip install` no intenta
# empaquetar app/ (que todavía no fue copiado) y la app corre desde el fuente.
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir ".[test]"

COPY backend/app ./app
COPY --from=frontend /ui/dist ./frontend/dist

RUN mkdir -p /app/data

ENV SQLITE_PATH=/app/data/logmon.db \
    STATIC_DIR=/app/frontend/dist \
    WEB_CONCURRENCY=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Un solo worker: los locks por fuente y el mapa de destinos activos viven en
# memoria del proceso, y multi-worker rompería la exclusión del switch.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
