# --- etapa 1: build del frontend ----------------------------------------
FROM node:20-slim AS frontend

WORKDIR /ui

# El glob toma package-lock.json si esta versionado, para que el build sea
# reproducible, y no falla si no esta.
COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build


# --- etapa 2: build de dependencias Python -------------------------------
# Esta etapa tiene el toolchain de compilacion (build-essential + freetds-dev),
# necesario porque asyncmy no publica wheel para linux/aarch64 (Apple
# Silicon compila desde el fuente). Nada de esta etapa llega a la imagen
# final: solo se copia el venv ya armado.
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        freetds-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Se instalan solo las dependencias primero para aprovechar la cache de capas:
# el pyproject declara `py-modules = []`, asi que `pip install` no intenta
# empaquetar app/ (que todavia no fue copiado) y la app corre desde el fuente.
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[test]" \
    && pip uninstall -y pip setuptools wheel || true



# --- etapa 3: imagen final ------------------------------------------------
# Parte de una imagen python:3.12-slim limpia: sin build-essential ni
# freetds-dev, asi que el toolchain de compilacion nunca llega aca.
FROM python:3.12-slim

WORKDIR /app

# freetds-bin (runtime, no -dev) es lo que necesita pymssql para conectarse;
# curl es solo para el healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        freetds-bin \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

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