# Plan — Sistema de Monitoreo de Logs (multi-base de datos)

## Estructura de proyecto

```
logmon/
├─ docker-compose.yml            # 5 motores + backend (red, healthchecks, volúmenes)
├─ .env.example                  # credenciales/URLs por motor, SQLITE_PATH, WEB_CONCURRENCY=1
├─ Makefile                      # up / down / seed / dev / test
├─ README.md                     # pasos de ejecución + guion de demo
├─ backend/
│  ├─ Dockerfile                 # python:3.12-slim + FreeTDS (pymssql), uvicorn 1 worker
│  ├─ pyproject.toml             # dependencias
│  └─ app/
│     ├─ main.py                 # FastAPI + lifespan (init metadata, rebuild router, pools) + StaticFiles
│     ├─ config.py               # Settings (pydantic-settings)
│     ├─ models.py               # LogRecord, LogStep, LogSummary, ConnectionIn, SourceIn, SwitchIn
│     ├─ ids.py                  # helper ULID
│     ├─ metadata/
│     │  ├─ schema.sql           # DDL: connections, sources, source_bindings, switch_audit
│     │  ├─ db.py                # bootstrap aiosqlite
│     │  └─ repo.py              # CRUD + historial de bindings + audit
│     ├─ storage/
│     │  ├─ base.py              # LogRepository (Protocol) + LogFilters
│     │  ├─ registry.py          # AdapterRegistry: pools keyed por connection_id
│     │  ├─ router.py            # StorageRouter: locks por fuente, switch(), resolve(), rebuild()
│     │  └─ adapters/
│     │     ├─ postgres.py       # PostgresAdapter (psycopg v3 async)
│     │     ├─ mariadb.py        # MariaDbAdapter (asyncmy)
│     │     ├─ sqlserver.py      # SqlServerAdapter (pymssql + threadpool)
│     │     ├─ mongo.py          # MongoAdapter (pymongo async)
│     │     └─ redis.py          # RedisAdapter (redis.asyncio, hash + sorted sets)
│     ├─ api/
│     │  ├─ logs.py              # POST/GET /api/logs, GET /api/logs/{id}?conn=, POST /api/logs/demo
│     │  ├─ connections.py       # CRUD + POST /{id}/test
│     │  └─ sources.py           # CRUD/asignación + POST /{source}/switch
│     ├─ seed.py                 # C1..C5, asignaciones APP1→C3/APP2→C2/SIS3→C1, logs OK+ERROR
│     └─ tests/
│        ├─ test_adapters.py     # round-trip por motor
│        ├─ test_switch.py       # switch sin pérdida
│        └─ test_concurrency.py  # N escrituras + switch a mitad
└─ frontend/                     # React + Vite (TS)
   └─ src/
      ├─ api/client.ts           # cliente fetch tipado
      ├─ components/
      │  ├─ ConnectionForm.tsx   # form "Add conexión" + Test
      │  ├─ SourceAssign.tsx     # asignación fuente→conexión
      │  ├─ SwitchControl.tsx    # cambio de base en vivo
      │  ├─ LogTable.tsx         # tabla filtrable
      │  ├─ LogDetail.tsx        # detalle con pasos
      │  ├─ StepBadge.tsx        # color por tipo (ENTRADA/SALIDA verde, ERROR rojo)
      │  └─ DbOriginBadge.tsx    # badge del motor de origen
      └─ pages/
         ├─ Dashboard.tsx        # conexiones + asignaciones + switch
         └─ LogViewer.tsx        # VISUALIZAR LOGS
```

Demo: `vite build` → `frontend/dist` servido por FastAPI `StaticFiles`, así `http://localhost:8000`
sirve API y SPA en un solo proceso.

---

## Modelo de datos

**Registro canónico:**
`LogRecord{ id (ULID), source_id, parent_type (API|WEB|SISTEMA), entrada, resultado, metodo,
tiempo_ms, estado (OK|ERROR), fecha (UTC), steps: [LogStep] }`
`LogStep{ orden, tipo (ENTRADA|SALIDA|ERROR), contenido, duration_ms? }`

Reglas de la pizarra: `tiempo_ms` del header = **suma** de `duration_ms` de los pasos ("suma tiempo").
`estado` = ERROR si **algún** paso es `tipo==ERROR`, si no OK.

**Por motor:**
- **SQL (MariaDB/Postgres/SQL Server)** — 2 tablas:
  - `logs(id PK CHAR(26), source_id, parent_type, entrada, resultado, metodo, tiempo_ms, estado,
    fecha, created_at)`; índices `(source_id, fecha)`, `(estado)`, `(metodo)`.
  - `log_steps(log_id FK ON DELETE CASCADE, orden, tipo, contenido, duration_ms)`; PK `(log_id, orden)`.
  - `save()` = `BEGIN; INSERT logs; INSERT log_steps (batch); COMMIT;` (todo-o-nada).
  - Dialecto: MariaDB InnoDB/utf8mb4, `DATETIME(3)`, `TEXT`; Postgres `TIMESTAMPTZ`/`TEXT`;
    SQL Server `DATETIME2`/`NVARCHAR(MAX)`.
- **MongoDB** — 1 colección `logs`, **pasos embebidos** en el documento (escritura de 1 doc es
  atómica, sin transacción). Índices `{source_id:1, fecha:-1}`, `{estado:1}`, `{metodo:1}`.
- **Redis** — Hash `log:{id}` (pasos serializados en `steps_json`) + Sorted Sets de índice
  (`idx:src:{source_id}` y `idx:all`, score = `fecha_ms`) para query por fuente/fecha; `save()` en
  un pipeline `MULTI/EXEC`. Correr con `--appendonly yes` para persistencia.

**Metadata (SQLite, separada de los targets):** `connections`, `sources`, `source_bindings`
(historial append-only fuente→conexión), `switch_audit`. Es la **fuente de verdad**; el router en
memoria es un cache que se reconstruye al arrancar.

---

## docker-compose (5 motores + app)

Una red Docker; en contenedor la app llega a las DBs por nombre de servicio; desde el host, por
puerto mapeado. `backend` con `depends_on: condition: service_healthy` para cada DB.

| Servicio | Imagen | Puerto | Healthcheck | Volumen |
|---|---|---|---|---|
| mariadb (C1) | `mariadb:11` | 3306 | `healthcheck.sh --connect` / `mysqladmin ping` | `mariadb_data` |
| postgres (C2) | `postgres:16` | 5432 | `pg_isready` | `pg_data` |
| sqlserver (C3) | arm64: `azure-sql-edge:latest` **o** `mssql/server:2022-latest` + `platform: linux/amd64` | 1433 | probe TCP/py (azure-sql-edge puede no traer `sqlcmd`) | `mssql_data` |
| mongo (C4) | `mongo:7` | 27017 | `mongosh --eval "db.adminCommand('ping')"` | `mongo_data` |
| redis (C5) | `redis:7` (`--appendonly yes`) | 6379 | `redis-cli ping` | `redis_data` |
| backend | build `./backend` | 8000 | `curl -f /health` | `meta_data` |

Gotchas a incorporar: la **password SA de SQL Server** debe cumplir complejidad o el contenedor
falla en silencio; SQL Server tarda 30–60s en estar healthy y "healthy" ≠ "schema creado" (el schema
lo crea `ensure_schema()`); mantener **un worker** (`WEB_CONCURRENCY=1`; el lock y el mapa activo
viven en un proceso, multi-worker rompería la exclusión). *Recomendación:* `azure-sql-edge` para demo
fluida en arm64, documentando el cambio a la imagen oficial `mssql/server` si se quiere fidelidad total.

---

## Tareas a realizar

Cada tarea indica **archivo** y **función**. Orden recomendado: los grupos posteriores dependen de
los previos. Raíz del proyecto: `logmon/`.

### 1. Infraestructura / Docker
- [ ] **`logmon/docker-compose.yml`** — define los 5 motores (mariadb, postgres, sqlserver, mongo,
  redis) + servicio `backend`, red compartida, `healthcheck` y volúmenes por motor, y
  `depends_on: condition: service_healthy` en `backend`. Es lo que levanta todo con un comando.
- [ ] **`logmon/backend/Dockerfile`** — imagen `python:3.12-slim` (sortea el Python 3.9 del host);
  instala FreeTDS (para `pymssql`) + dependencias; arranca `uvicorn` con **1 worker**.
- [ ] **`logmon/backend/pyproject.toml`** — declara dependencias: `fastapi`, `uvicorn[standard]`,
  `pydantic` v2, `pydantic-settings`, `python-ulid`, `aiosqlite`, `psycopg[binary,pool]`, `asyncmy`,
  `pymssql`, `pymongo`, `redis`, `anyio`, `pytest`/`httpx` (tests).
- [ ] **`logmon/.env.example`** — plantilla de variables: URLs/credenciales por motor (host = nombre
  de servicio compose), `SQLITE_PATH`, `WEB_CONCURRENCY=1`. Función: configurar sin hardcodear.
- [ ] **`logmon/Makefile`** — targets `up`/`down`/`seed`/`dev`/`test`. Función: atajos de operación.

### 2. Backend base (config, ids, modelos, contrato, metadata)
- [ ] **`logmon/backend/app/config.py`** — clase `Settings` (pydantic-settings) que lee env
  (conexiones por defecto, `SQLITE_PATH`). Función: configuración central tipada.
- [ ] **`logmon/backend/app/ids.py`** — helper `new_ulid()`. Función: IDs únicos globales y ordenables
  por tiempo, para poder mergear logs entre motores tras un switch.
- [ ] **`logmon/backend/app/models.py`** — modelos Pydantic `LogRecord`, `LogStep`, `LogSummary`,
  `ConnectionIn`, `SourceIn`, `SwitchIn`. Función: contrato de datos compartido; deriva/valida
  `estado` (ERROR si algún paso es ERROR) y `tiempo_ms` (suma de `duration_ms`).
- [ ] **`logmon/backend/app/storage/base.py`** — `LogRepository` (Protocol async) con
  `ensure_schema/ping/save/query/get` + `LogFilters`. Función: interfaz común que hace el motor
  invisible por encima del adapter.
- [ ] **`logmon/backend/app/metadata/schema.sql`** — DDL SQLite de `connections`, `sources`,
  `source_bindings`, `switch_audit`. Función: esquema de la metadata (fuente de verdad).
- [ ] **`logmon/backend/app/metadata/db.py`** — bootstrap de `aiosqlite` (crea archivo y aplica el
  schema). Función: inicializar la metadata al arrancar.
- [ ] **`logmon/backend/app/metadata/repo.py`** — CRUD de conexiones/fuentes, `append_binding()`
  (historial), `record_switch()` (audit), y lecturas de binding actual/histórico. Función: acceso
  durable a la metadata que habilita el switch y el visor multi-DB.

### 3. Adapters — un archivo por motor (todos implementan `LogRepository`)
- [ ] **`logmon/backend/app/storage/adapters/postgres.py`** — `PostgresAdapter` con `psycopg` v3
  async + pool (paramstyle `%s`). Función: guardar/consultar logs en Postgres (**hacer primero**,
  end-to-end, para validar el contrato).
- [ ] **`logmon/backend/app/storage/adapters/mariadb.py`** — `MariaDbAdapter` con `asyncmy`
  (utf8mb4). Función: mismo contrato sobre MariaDB.
- [ ] **`logmon/backend/app/storage/adapters/redis.py`** — `RedisAdapter` con `redis.asyncio`; hash
  `log:{id}` + sorted sets `idx:src:*`/`idx:all`, `save()` en pipeline `MULTI/EXEC`. Función:
  almacenamiento clave-valor con índices para query por fuente/fecha.
- [ ] **`logmon/backend/app/storage/adapters/mongo.py`** — `MongoAdapter` con `pymongo` async
  (`AsyncMongoClient`); colección `logs` con pasos embebidos. Función: almacenamiento documental.
- [ ] **`logmon/backend/app/storage/adapters/sqlserver.py`** — `SqlServerAdapter` con `pymssql`
  envuelto en `anyio.to_thread` (método público async). Función: contrato sobre SQL Server (**hacer
  al final**, es el más sensible al entorno/arm64).

### 4. Router y switch sin pérdida (el corazón del requisito)
- [ ] **`logmon/backend/app/storage/registry.py`** — `AdapterRegistry`: crea/cachea adapters keyed
  por `connection_id` (apertura lazy; cierre solo en shutdown). Función: reusar pools entre fuentes y
  **nunca cerrar un pool durante un switch** (evita el race de teardown).
- [ ] **`logmon/backend/app/storage/router.py`** — `StorageRouter`: `asyncio.Lock` por fuente,
  `resolve(source)`, camino de escritura bajo lock, `switch()` con **validate-before-flip**
  (`ping` + `ensure_schema` → persistir binding/audit en metadata → flip en memoria) y `rebuild()`
  desde `source_bindings`. Función: garantiza que ningún log se pierde ni cae en una base a medio
  configurar durante el cambio.
- [ ] **`logmon/backend/app/main.py`** — app FastAPI + `lifespan` (init metadata, `rebuild()` del
  router, abrir/cerrar pools) + montaje de routers y `StaticFiles`. Función: ensamblar y arrancar.

### 5. API REST
- [ ] **`logmon/backend/app/api/logs.py`** — `POST /api/logs` (ingesta vía router),
  `GET /api/logs` (filtros source/estado/fecha/método **con merge multi-DB**),
  `GET /api/logs/{id}?conn=<id>` (detalle en el motor de origen), `POST /api/logs/demo` (genera logs
  de ejemplo). Función: endpoints de logs.
- [ ] **`logmon/backend/app/api/connections.py`** — CRUD de conexiones + `POST /{id}/test` (ping).
  Función: gestionar el "Add conexión" de la pizarra.
- [ ] **`logmon/backend/app/api/sources.py`** — CRUD/asignación de fuentes + `POST /{source}/switch`.
  Función: asignar fuente→conexión y disparar el cambio de base en vivo.

### 6. Visor multi-DB (lectura sin pérdida)
- [ ] **`logmon/backend/app/storage/router.py`** (método de lectura) **+ `api/logs.py`** — fan-out
  `asyncio.gather` de `query()` a cada conexión del historial de la fuente, etiqueta cada fila con su
  `connection_id`/motor de origen y merge-sort por `fecha` (ULID desempata). Función: mostrar logs
  repartidos entre 2+ motores tras un switch (la prueba visual de "no se perdió nada").

### 7. Seed y datos de demo (según la pizarra)
- [ ] **`logmon/backend/app/seed.py`** — crea conexiones **C1..C5**, asigna **APP1→C3 (API)**,
  **APP2→C2 (WEB)**, **SIS3→C1 (SISTEMA)** e inserta logs de ejemplo OK y ERROR con pasos coloreados
  (p.ej. `APP1/ERROR POST /orders` → paso `ERROR "DB timeout 3000ms"`). Función: dejar la demo lista
  con un comando (`make seed`).

### 8. Frontend (React + Vite, TS)
- [ ] **`logmon/frontend/src/api/client.ts`** — cliente `fetch` tipado del API. Función: única capa de
  acceso HTTP.
- [ ] **`logmon/frontend/src/components/ConnectionForm.tsx`** — formulario "Add conexión" (nombre,
  engine C1..C5, host, port, user, password, database) + botón "Test". Función: alta/prueba de conexiones.
- [ ] **`logmon/frontend/src/components/SourceAssign.tsx`** — asignación fuente→conexión. Función:
  reproducir el mapeo APP1→C3, etc.
- [ ] **`logmon/frontend/src/components/SwitchControl.tsx`** — selector + botón de cambio de base en
  vivo, con feedback de éxito/aborto. Función: disparar `POST /{source}/switch`.
- [ ] **`logmon/frontend/src/components/LogTable.tsx` · `LogDetail.tsx` · `StepBadge.tsx` ·
  `DbOriginBadge.tsx`** — tabla filtrable, detalle con pasos, badge de color (ENTRADA/SALIDA verde,
  ERROR rojo) y badge del motor de origen. Función: visualizar logs (la parte "VISUALIZAR LOGS").
- [ ] **`logmon/frontend/src/pages/Dashboard.tsx` · `LogViewer.tsx`** — páginas que componen lo
  anterior. Build `vite build` → `frontend/dist`, servido por FastAPI. Función: SPA de la demo.

### 9. Tests
- [ ] **`logmon/backend/app/tests/test_adapters.py`** — round-trip `save`→`get`/`query` por cada
  motor. Función: probar que cada adapter cumple el contrato.
- [ ] **`logmon/backend/app/tests/test_switch.py`** — switch: los logs viejos quedan intactos en la
  base anterior y los nuevos caen en la nueva. Función: verificar el redirect sin pérdida.
- [ ] **`logmon/backend/app/tests/test_concurrency.py`** — N `POST /api/logs` concurrentes + un switch
  a mitad; assert `count(old)+count(new) == N`. Función: probar que ningún log cae en el corte.

### 10. Documentación
- [ ] **`logmon/README.md`** — pasos de ejecución (`docker compose up`, `make seed`) + guion de demo
  (ingesta → switch en vivo APP1 C3→C4 → prueba de cero pérdida → prueba negativa → concurrencia).
  Función: entregable de documentación para la presentación.
