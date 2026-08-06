from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

import pytest

from app.models import LogRecord, LogStep, ParentType, StepType
from app.storage.base import LogFilters

# Con LOGMON_REQUIRE_ENGINES=1 un motor caído es un fallo, no un skip. Sin la
# variable los tests de adapters se saltan, que es lo que se quiere en una
# máquina sin Docker; el problema sería que se saltaran *en silencio*, así que
# el motivo del skip siempre queda escrito en el reporte.
REQUIRE_ENGINES = os.getenv("LOGMON_REQUIRE_ENGINES", "").strip().lower() in {
    "1",
    "true",
    "yes",
}


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


# Las contraseñas de las conexiones se guardan cifradas, así que los tests
# necesitan su propia clave.
@pytest.fixture(autouse=True)
def clave_de_cifrado(monkeypatch) -> None:
    from app.config import get_settings
    from app.crypto import validate_secret_key

    monkeypatch.setenv("LOGMON_SECRET_KEY", "A9zNkc28EKOZryEO6lBC5SwKLBIBoJ4azXAkQX1CBE4=")
    get_settings.cache_clear()
    validate_secret_key()


# --------------------------------------------------------------------------
# Adapters reales (necesitan los motores levantados)
# --------------------------------------------------------------------------


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _postgres_factory() -> Any:
    from app.storage.adapters.postgres import PostgresAdapter

    return PostgresAdapter(
        host=_env("POSTGRES_HOST", "localhost"),
        port=int(_env("POSTGRES_PORT", "5432")),
        user=_env("POSTGRES_USER", "loguser"),
        password=_env("POSTGRES_PASSWORD", "logpass"),
        database=_env("POSTGRES_DB", "logdb"),
    )


def _mariadb_factory() -> Any:
    from app.storage.adapters.mariadb import MariaDbAdapter

    return MariaDbAdapter(
        host=_env("MARIADB_HOST", "localhost"),
        port=int(_env("MARIADB_PORT", "3306")),
        user=_env("MARIADB_USER", "loguser"),
        password=_env("MARIADB_PASSWORD", "logpass"),
        database=_env("MARIADB_DATABASE", "logdb"),
    )


def _sqlserver_factory() -> Any:
    from app.storage.adapters.sqlserver import SqlServerAdapter

    return SqlServerAdapter(
        host=_env("SQLSERVER_HOST", "localhost"),
        port=int(_env("SQLSERVER_PORT", "1433")),
        user=_env("SQLSERVER_USER", "sa"),
        password=_env("MSSQL_SA_PASSWORD", "Alec2026!SecureSQL"),
        database=_env("SQLSERVER_DATABASE", "logdb"),
    )


def _mongo_factory() -> Any:
    from app.storage.adapters.mongo import MongoAdapter

    return MongoAdapter(
        host=_env("MONGO_HOST", "localhost"),
        port=int(_env("MONGO_PORT", "27017")),
        user=_env("MONGO_USER", ""),
        password=_env("MONGO_PASSWORD", ""),
        database=_env("MONGO_DATABASE", "logdb"),
    )


def _redis_factory() -> Any:
    from app.storage.adapters.redis import RedisAdapter

    return RedisAdapter(
        host=_env("REDIS_HOST", "localhost"),
        port=int(_env("REDIS_PORT", "6379")),
        user=_env("REDIS_USER", ""),
        password=_env("REDIS_PASSWORD", ""),
        database=_env("REDIS_DB", "0"),
    )


ENGINE_FACTORIES: Dict[str, Callable[[], Any]] = {
    "postgres": _postgres_factory,
    "mariadb": _mariadb_factory,
    "sqlserver": _sqlserver_factory,
    "mongo": _mongo_factory,
    "redis": _redis_factory,
}


# Si un motor no está, no tiene sentido reintentar la conexión en cada test:
# se memoriza el motivo y los siguientes se saltan al instante.
_UNAVAILABLE: Dict[str, str] = {}


def _unavailable(engine: str, exc: BaseException) -> None:
    message = f"{engine} no disponible: {type(exc).__name__}: {exc}"
    _UNAVAILABLE[engine] = message
    if REQUIRE_ENGINES:
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture(params=sorted(ENGINE_FACTORIES))
async def adapter(request: pytest.FixtureRequest):
    engine = request.param

    if engine in _UNAVAILABLE:
        pytest.skip(_UNAVAILABLE[engine])

    try:
        instance = ENGINE_FACTORIES[engine]()
    except ImportError as exc:
        _unavailable(engine, exc)
        return

    try:
        await instance.ensure_schema()
    except Exception as exc:  # noqa: BLE001
        await instance.close()
        _unavailable(engine, exc)
        return

    yield instance

    await instance.close()


# --------------------------------------------------------------------------
# Adapters falsos (para probar router y switch sin depender de los motores)
# --------------------------------------------------------------------------


class FakeStore:
    """Guarda los logs por connection_id y permite simular motores caídos."""

    def __init__(self) -> None:
        self.data: Dict[str, List[LogRecord]] = {}
        self.failing: Set[str] = set()
        self.save_latency = 0.0

    def build(self, connection: Dict[str, Any]) -> "FakeAdapter":
        connection_id = str(connection["id"])
        self.data.setdefault(connection_id, [])
        return FakeAdapter(self, connection_id)

    def rows(self, connection_id: str) -> List[LogRecord]:
        return self.data.setdefault(connection_id, [])

    def count(self, *connection_ids: str) -> int:
        return sum(len(self.rows(cid)) for cid in connection_ids)


class FakeAdapter:
    def __init__(self, store: FakeStore, connection_id: str) -> None:
        self._store = store
        self.connection_id = connection_id
        self.closed = False

    def _guard(self) -> None:
        if self.connection_id in self._store.failing:
            raise ConnectionRefusedError(f"{self.connection_id} inalcanzable")

    async def ensure_schema(self) -> None:
        self._guard()

    async def ping(self) -> bool:
        self._guard()
        return True

    async def save(self, record: LogRecord) -> None:
        self._guard()
        if self._store.save_latency:
            await asyncio.sleep(self._store.save_latency)
        self._store.rows(self.connection_id).append(record)

    async def save_many(self, records: List[LogRecord]) -> List[Optional[str]]:
        """Contrato de lote: un elemento por resultado, None si salió bien.

        Vive acá y no parcheado desde `test_api_batch` porque el fake tiene que
        cumplir toda la interfaz de LogRepository: si sólo lo define ese módulo,
        cualquier otro test que ejercite el lote pasa o falla según si ese
        archivo se importó, que es una dependencia invisible entre tests.
        """

        self._guard()
        if self._store.save_latency:
            await asyncio.sleep(self._store.save_latency)
        self._store.rows(self.connection_id).extend(records)
        return [None] * len(records)

    async def query(self, filters: LogFilters) -> List[LogRecord]:
        self._guard()
        rows = list(self._store.rows(self.connection_id))

        if filters.source_id is not None:
            rows = [r for r in rows if r.source_id == filters.source_id]
        if filters.estado is not None:
            rows = [r for r in rows if r.estado == filters.estado]
        if filters.metodo is not None:
            rows = [r for r in rows if r.metodo == filters.metodo]
        if filters.fecha_desde is not None:
            rows = [r for r in rows if r.fecha >= filters.fecha_desde]
        if filters.fecha_hasta is not None:
            rows = [r for r in rows if r.fecha <= filters.fecha_hasta]

        rows.sort(key=lambda r: (r.fecha, r.id), reverse=True)
        return rows[filters.offset : filters.offset + filters.limit]

    async def get(self, log_id: str) -> Optional[LogRecord]:
        self._guard()
        for record in self._store.rows(self.connection_id):
            if record.id == log_id:
                return record
        return None

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
async def router(tmp_path, monkeypatch):
    """StorageRouter sobre una metadata temporal y adapters en memoria.

    Devuelve ``(router, store)``. No necesita Docker: prueba la lógica de
    enrutado y switch, que es donde vive la garantía de no perder logs.
    """

    from app.metadata import db as metadata_db
    from app.storage import registry as registry_module
    from app.storage.router import StorageRouter

    store = FakeStore()
    monkeypatch.setattr(registry_module, "build_adapter", store.build)

    await metadata_db.init_metadata_db(str(tmp_path / "meta.db"))

    instance = StorageRouter()
    await instance.rebuild()

    try:
        yield instance, store
    finally:
        await instance.close_all()
        await metadata_db.close_metadata_db()


@pytest.fixture
async def api_client(router):
    """Cliente HTTP contra la app real, con el router de adapters en memoria.

    Devuelve ``(client, router, store)``. No se usa el lifespan de FastAPI: la
    metadata ya la inicializó el fixture ``router`` sobre un SQLite temporal,
    así que cada test arranca con una base limpia.
    """

    import httpx

    from app.api.dependencies import get_storage_router
    from app.main import app

    instance, store = router
    app.dependency_overrides[get_storage_router] = lambda: instance

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, instance, store
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def seeded_router(router):
    """Router con C1..C5 y las fuentes APP1/APP2/SIS3 ya creadas (sin binding)."""

    from app.metadata import repo
    from app.models import ConnectionIn, SourceIn

    instance, store = router

    engines = ["mariadb", "postgres", "sqlserver", "mongo", "redis"]
    for index, engine in enumerate(engines, start=1):
        await repo.create_connection(
            ConnectionIn(
                name=f"C{index} {engine}",
                engine=engine,
                host=engine,
                port=1000 + index,
                user="u",
                password="p",
                database="logdb",
            ),
            connection_id=f"C{index}",
        )

    for name, parent_type in (
        ("APP1", ParentType.API),
        ("APP2", ParentType.WEB),
        ("SIS3", ParentType.SISTEMA),
    ):
        await repo.create_source(SourceIn(name=name, parent_type=parent_type))

    return instance, store


# --------------------------------------------------------------------------
# Helpers de datos
# --------------------------------------------------------------------------


def make_record(
    source_id: str,
    metodo: str = "POST",
    with_error: bool = False,
    fecha: Optional[datetime] = None,
    log_id: Optional[str] = None,
) -> LogRecord:
    steps = [
        LogStep(orden=1, tipo=StepType.ENTRADA, contenido="payload recibido", duration_ms=120),
    ]
    if with_error:
        steps.append(
            LogStep(orden=2, tipo=StepType.ERROR, contenido="DB timeout 3000ms", duration_ms=3000)
        )
    else:
        steps.append(
            LogStep(orden=2, tipo=StepType.SALIDA, contenido="201 Created", duration_ms=80)
        )

    return LogRecord(
        id=log_id or uuid.uuid4().hex[:26].upper(),
        source_id=source_id,
        parent_type=ParentType.API,
        entrada="POST /orders",
        resultado="orden procesada",
        metodo=metodo,
        fecha=fecha or datetime.now(timezone.utc),
        steps=steps,
    )


def unique_source(prefix: str = "TEST") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"
