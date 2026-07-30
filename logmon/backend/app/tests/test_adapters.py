from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from app.models import Estado, LogRecord, LogStep, ParentType, StepType
from app.storage.base import LogFilters


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


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


ENGINE_FACTORIES: List[Tuple[str, Callable[[], Any]]] = [
    ("postgres", _postgres_factory),
    ("mariadb", _mariadb_factory),
    ("sqlserver", _sqlserver_factory),
]


@pytest.fixture(params=[name for name, _ in ENGINE_FACTORIES])
async def adapter(request: pytest.FixtureRequest) -> Any:
    factories: Dict[str, Callable[[], Any]] = dict(ENGINE_FACTORIES)
    engine = request.param

    try:
        instance = factories[engine]()
    except ImportError as exc:
        pytest.skip(f"driver de {engine} no instalado: {exc}")

    try:
        await instance.ensure_schema()
    except Exception as exc:
        await instance.close()
        pytest.skip(f"{engine} no disponible: {exc}")

    yield instance

    await instance.close()


def _make_record(
    source_id: str,
    metodo: str = "POST",
    with_error: bool = False,
    fecha: Optional[datetime] = None,
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
        id=uuid.uuid4().hex[:26].upper(),
        source_id=source_id,
        parent_type=ParentType.API,
        entrada="POST /orders",
        resultado="orden procesada",
        metodo=metodo,
        fecha=fecha or datetime.now(timezone.utc),
        steps=steps,
    )


@pytest.mark.anyio
async def test_ping(adapter: Any) -> None:
    assert await adapter.ping() is True


@pytest.mark.anyio
async def test_save_get_round_trip(adapter: Any) -> None:
    source_id = f"TEST-{uuid.uuid4().hex[:8]}"
    record = _make_record(source_id)

    await adapter.save(record)
    fetched = await adapter.get(record.id)

    assert fetched is not None
    assert fetched.id == record.id
    assert fetched.source_id == record.source_id
    assert fetched.parent_type == record.parent_type
    assert fetched.entrada == record.entrada
    assert fetched.resultado == record.resultado
    assert fetched.metodo == record.metodo
    assert fetched.estado == Estado.OK
    assert fetched.tiempo_ms == 200

    assert [s.orden for s in fetched.steps] == [1, 2]
    assert [s.tipo for s in fetched.steps] == [StepType.ENTRADA, StepType.SALIDA]
    assert [s.contenido for s in fetched.steps] == ["payload recibido", "201 Created"]
    assert [s.duration_ms for s in fetched.steps] == [120, 80]


@pytest.mark.anyio
async def test_save_derives_error_state(adapter: Any) -> None:
    source_id = f"TEST-{uuid.uuid4().hex[:8]}"
    record = _make_record(source_id, with_error=True)

    await adapter.save(record)
    fetched = await adapter.get(record.id)

    assert fetched is not None
    assert fetched.estado == Estado.ERROR
    assert fetched.tiempo_ms == 3120


@pytest.mark.anyio
async def test_get_unknown_id_returns_none(adapter: Any) -> None:
    assert await adapter.get(uuid.uuid4().hex[:26].upper()) is None


@pytest.mark.anyio
async def test_query_filters_by_source(adapter: Any) -> None:
    source_a = f"TEST-{uuid.uuid4().hex[:8]}"
    source_b = f"TEST-{uuid.uuid4().hex[:8]}"

    await adapter.save(_make_record(source_a))
    await adapter.save(_make_record(source_a))
    await adapter.save(_make_record(source_b))

    found = await adapter.query(LogFilters(source_id=source_a))

    assert len(found) == 2
    assert {r.source_id for r in found} == {source_a}


@pytest.mark.anyio
async def test_query_filters_by_estado_and_metodo(adapter: Any) -> None:
    source_id = f"TEST-{uuid.uuid4().hex[:8]}"

    await adapter.save(_make_record(source_id, metodo="POST"))
    await adapter.save(_make_record(source_id, metodo="GET", with_error=True))

    solo_error = await adapter.query(LogFilters(source_id=source_id, estado=Estado.ERROR))
    assert len(solo_error) == 1
    assert solo_error[0].metodo == "GET"

    solo_post = await adapter.query(LogFilters(source_id=source_id, metodo="POST"))
    assert len(solo_post) == 1
    assert solo_post[0].estado == Estado.OK


@pytest.mark.anyio
async def test_query_filters_by_date_range(adapter: Any) -> None:
    source_id = f"TEST-{uuid.uuid4().hex[:8]}"
    ahora = datetime.now(timezone.utc)
    viejo = ahora - timedelta(days=7)

    await adapter.save(_make_record(source_id, fecha=viejo))
    await adapter.save(_make_record(source_id, fecha=ahora))

    recientes = await adapter.query(
        LogFilters(source_id=source_id, fecha_desde=ahora - timedelta(hours=1))
    )

    assert len(recientes) == 1
    assert recientes[0].fecha >= ahora - timedelta(hours=1)


@pytest.mark.anyio
async def test_query_orders_desc_and_respects_limit(adapter: Any) -> None:
    source_id = f"TEST-{uuid.uuid4().hex[:8]}"
    base = datetime.now(timezone.utc)

    for offset in range(3):
        await adapter.save(_make_record(source_id, fecha=base - timedelta(minutes=offset)))

    pagina = await adapter.query(LogFilters(source_id=source_id, limit=2))

    assert len(pagina) == 2
    assert pagina[0].fecha >= pagina[1].fecha


@pytest.mark.anyio
async def test_query_offset_pagination(adapter: Any) -> None:
    source_id = f"TEST-{uuid.uuid4().hex[:8]}"
    base = datetime.now(timezone.utc)

    for offset in range(3):
        await adapter.save(_make_record(source_id, fecha=base - timedelta(minutes=offset)))

    primera = await adapter.query(LogFilters(source_id=source_id, limit=2, offset=0))
    segunda = await adapter.query(LogFilters(source_id=source_id, limit=2, offset=2))

    assert len(primera) == 2
    assert len(segunda) == 1
    assert {r.id for r in primera}.isdisjoint({r.id for r in segunda})
