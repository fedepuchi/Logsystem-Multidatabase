# LogMon — guía de ejecución y demo

Monitoreo de logs sobre 5 motores de base de datos, con cambio de motor en vivo
y sin pérdida de registros.

Para la descripción del proyecto y sus objetivos, ver el [README de la raíz](../README.md).

---

## Requisitos

- Docker Desktop (con Docker Compose v2)
- Para desarrollo sin contenedores: Python 3.12+ y Node 20+

## Arranque rápido

```bash
cd logmon
cp .env.example .env          # opcional: sin .env valen los defaults del compose
make up                       # levanta los 5 motores + el backend
make seed                     # crea C1..C5, APP1/APP2/SIS3 y logs de ejemplo
```

Cuando termine, todo vive en un solo puerto:

- **SPA + API**: http://localhost:8000
- **Documentación interactiva**: http://localhost:8000/docs

El primer `make up` tarda varios minutos: compila el SPA, instala las
dependencias de Python y SQL Server necesita 30–60 s para responder.

## Qué levanta el compose

| Servicio | Imagen | Puerto | Rol en la demo |
|---|---|---|---|
| `mariadb` | `mariadb:11` | 3306 | C1 |
| `postgres` | `postgres:16` | 5432 | C2 |
| `sqlserver` | `azure-sql-edge` | 1433 | C3 |
| `mongo` | `mongo:7` | 27017 | C4 |
| `redis` | `redis:7` (`--appendonly yes`) | 6379 | C5 |
| `backend` | build local | 8000 | API + SPA + metadata SQLite |

La metadata (conexiones, fuentes, historial de bindings y auditoría de switches)
vive en SQLite sobre el volumen `meta_data` y es la **fuente de verdad**: el mapa
de destinos activos que tiene el router en memoria es sólo un cache que se
reconstruye al arrancar.

---

## Guion de demo

Asignaciones que deja `make seed`, según la pizarra:
`APP1 → C3 (SQL Server)`, `APP2 → C2 (PostgreSQL)`, `SIS3 → C1 (MariaDB)`.

### 1. Ingesta

En la pestaña **Visualizar logs** deberían verse los 6 logs del seed, cada uno
con el badge del motor donde está guardado, los pasos coloreados
(ENTRADA/SALIDA en verde, ERROR en rojo) y el `tiempo_ms` como suma de los pasos.

Para agregar uno a mano:

```bash
curl -X POST http://localhost:8000/api/logs \
  -H 'Content-Type: application/json' \
  -d '{
    "source_id": "APP1",
    "parent_type": "API",
    "entrada": "POST /orders",
    "resultado": "Orden creada",
    "metodo": "POST",
    "steps": [
      {"orden": 1, "tipo": "ENTRADA", "contenido": "payload recibido", "duration_ms": 120},
      {"orden": 2, "tipo": "SALIDA",  "contenido": "201 Created",      "duration_ms": 80}
    ]
  }'
```

La respuesta trae el `id` (ULID generado por el servidor), el `connection_id`
donde cayó y los campos derivados `estado` y `tiempo_ms`.

### 2. Switch en vivo: APP1 de C3 a C4

Desde el **Dashboard**, fila `APP1`, elegir `C4` y pulsar *Cambiar base*. O bien:

```bash
curl -X POST http://localhost:8000/api/sources/APP1/switch \
  -H 'Content-Type: application/json' -d '{"connection_id": "C4"}'
```

El switch valida el destino **antes** de mover nada: hace `ping` y
`ensure_schema` sobre C4, persiste el binding y la auditoría, y recién entonces
cambia el mapa en memoria.

### 3. Prueba de cero pérdida

Escribir un log nuevo en APP1 (mismo `curl` del paso 1) y volver al visor
filtrando por `APP1`:

```bash
curl -s "http://localhost:8000/api/logs?source=APP1" \
  | python3 -m json.tool | grep connection_id
```

Se ven **juntos** los logs viejos (etiquetados `C3`) y los nuevos (`C4`): el
visor hace fan-out a todas las conexiones del historial de la fuente y mergea
por fecha. Nada se movió ni se perdió; los registros viejos siguen físicamente
en SQL Server.

El historial y la auditoría se consultan con:

```bash
curl -s http://localhost:8000/api/sources/APP1/history | python3 -m json.tool
```

### 4. Prueba negativa: switch a un motor caído

```bash
docker compose stop redis
curl -i -X POST http://localhost:8000/api/sources/APP2/switch \
  -H 'Content-Type: application/json' -d '{"connection_id": "C5"}'
```

Responde **409** y el mensaje explica que la fuente sigue escribiendo en su
destino anterior. Verificado:

```bash
curl -s http://localhost:8000/api/sources/APP2      # connection_id sigue en C2
curl -s http://localhost:8000/api/sources/APP2/history | python3 -m json.tool
```

La auditoría registra el intento con `status: "ABORTED"` y el detalle del error.
Después: `docker compose start redis`.

### 5. Concurrencia: switch a mitad de N escrituras

```bash
for i in $(seq 1 40); do
  curl -s -o /dev/null -X POST http://localhost:8000/api/logs \
    -H 'Content-Type: application/json' \
    -d '{"source_id":"APP2","parent_type":"WEB","entrada":"GET /users",
         "resultado":"ok","metodo":"GET",
         "steps":[{"orden":1,"tipo":"ENTRADA","contenido":"in","duration_ms":10}]}' &
  if [ "$i" -eq 10 ]; then
    curl -s -o /dev/null -X POST http://localhost:8000/api/sources/APP2/switch \
      -H 'Content-Type: application/json' -d '{"connection_id":"C1"}' &
  fi
done
wait

curl -s "http://localhost:8000/api/logs?source=APP2&limit=1000" | python3 -c "
import sys, json, collections
rows = json.load(sys.stdin)
print('total:', len(rows), '| por motor:', collections.Counter(r['connection_id'] for r in rows))"
```

El total incluye los 40 nuevos: unos quedaron en C2 y otros en C1, ninguno cayó
en el corte. Es la misma propiedad que verifica `app/tests/test_concurrency.py`
de forma determinista.

---

## Comandos

| Comando | Qué hace |
|---|---|
| `make up` / `make down` | Levanta / baja el stack |
| `make down-v` | Baja y **borra los volúmenes** (resetea la demo) |
| `make seed` | Crea C1..C5, las fuentes, sus asignaciones y logs de ejemplo |
| `make seed-meta` | Igual, pero sin insertar logs |
| `make logs` | Sigue el log del backend |
| `make ps` / `make health` | Estado de los servicios |
| `make test` | Tests dentro del contenedor (los de adapters se saltan si falta un motor) |
| `make test-all` | Igual, pero un motor caído **falla** en vez de saltarse |
| `make dev` | Motores en Docker + backend con `--reload` en el host |
| `make front` | Vite dev server en http://localhost:5173 con proxy al backend |
| `make shell` | Shell dentro del contenedor del backend |

## Desarrollo sin Docker

```bash
make dev      # terminal 1: motores en Docker, backend en el host con reload
make front    # terminal 2: SPA en modo dev con hot reload
make seed-dev # una vez, para cargar los datos de demo
```

En este modo el backend llega a los motores por `localhost` y guarda la metadata
en `backend/data/logmon.db`.

---

## Cómo se garantiza el "sin pérdida"

1. **Un lock por fuente** cubre tanto el camino de escritura como el switch
   completo. Un switch lento demora las escrituras de esa fuente, pero las
   demora: no las pierde ni las manda a una base a medio configurar.
2. **Validate-before-flip**: `ping` + `ensure_schema` sobre el destino →
   persistir binding y auditoría → recién ahí cambiar el mapa en memoria. Si
   algo falla antes del flip, la fuente sigue donde estaba.
3. **Los pools nunca se cierran durante un switch.** El `AdapterRegistry`
   cachea un adapter por `connection_id` y sólo los cierra en el shutdown, para
   que ninguna escritura en vuelo se encuentre con un pool destruido.
4. **Nada se migra.** El switch sólo cambia dónde se escribe de ahora en más;
   los logs viejos se siguen leyendo por fan-out desde el historial de bindings.

## Cosas a tener en cuenta

- **Un solo worker.** Los locks y el mapa activo viven en memoria del proceso,
  así que `WEB_CONCURRENCY=1` no es negociable: con varios workers se rompe la
  exclusión del switch.
- **La password de SA de SQL Server** debe cumplir la política de complejidad o
  el contenedor arranca y muere sin un mensaje claro.
- **`healthy` no significa "schema creado".** El healthcheck de SQL Server sólo
  comprueba que el puerto acepta TCP; la base `logdb` y las tablas las crea
  `SqlServerAdapter` en su primer uso.
- **`azure-sql-edge`** se usa porque tiene imagen arm64 nativa y hace la demo
  fluida en Mac con Apple Silicon. Para fidelidad total, cambiar en el
  `docker-compose.yml` por `mcr.microsoft.com/mssql/server:2022-latest` con
  `platform: linux/amd64`.
- **Mongo y Redis corren sin autenticación** en esta demo. Si se les activa,
  hay que completar `MONGO_USER`/`MONGO_PASSWORD` y `REDIS_PASSWORD` en el
  `.env`.
- **`docker compose` no interpola variables dentro de un `env_file`**: en el
  `.env` cada valor va escrito completo, sin `${OTRA_VARIABLE}`.
