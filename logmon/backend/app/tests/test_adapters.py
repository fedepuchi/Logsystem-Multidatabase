"""Round-trip por motor: cada adapter tiene que cumplir el mismo contrato.

Necesita los motores levantados (`make test`). Sin ellos los casos se saltan
indicando el motivo; con LOGMON_REQUIRE_ENGINES=1 fallan en vez de saltarse.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.models import Estado, StepType
from app.storage.base import LogFilters
from app.tests.conftest import make_record, unique_source


@pytest.mark.anyio
async def test_ping(adapter: Any) -> None:
    assert await adapter.ping() is True


@pytest.mark.anyio
async def test_save_get_round_trip(adapter: Any) -> None:
    record = make_record(unique_source())

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
    record = make_record(unique_source(), with_error=True)

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
    source_a = unique_source()
    source_b = unique_source()

    await adapter.save(make_record(source_a))
    await adapter.save(make_record(source_a))
    await adapter.save(make_record(source_b))

    found = await adapter.query(LogFilters(source_id=source_a))

    assert len(found) == 2
    assert {r.source_id for r in found} == {source_a}


@pytest.mark.anyio
async def test_query_filters_by_estado_and_metodo(adapter: Any) -> None:
    source_id = unique_source()

    await adapter.save(make_record(source_id, metodo="POST"))
    await adapter.save(make_record(source_id, metodo="GET", with_error=True))

    solo_error = await adapter.query(LogFilters(source_id=source_id, estado=Estado.ERROR))
    assert len(solo_error) == 1
    assert solo_error[0].metodo == "GET"

    solo_post = await adapter.query(LogFilters(source_id=source_id, metodo="POST"))
    assert len(solo_post) == 1
    assert solo_post[0].estado == Estado.OK


@pytest.mark.anyio
async def test_query_filters_by_date_range(adapter: Any) -> None:
    source_id = unique_source()
    ahora = datetime.now(timezone.utc)
    viejo = ahora - timedelta(days=7)

    await adapter.save(make_record(source_id, fecha=viejo))
    await adapter.save(make_record(source_id, fecha=ahora))

    recientes = await adapter.query(
        LogFilters(source_id=source_id, fecha_desde=ahora - timedelta(hours=1))
    )

    assert len(recientes) == 1
    assert recientes[0].fecha >= ahora - timedelta(hours=1)


@pytest.mark.anyio
async def test_query_orders_desc_and_respects_limit(adapter: Any) -> None:
    source_id = unique_source()
    base = datetime.now(timezone.utc)

    for offset in range(3):
        await adapter.save(make_record(source_id, fecha=base - timedelta(minutes=offset)))

    pagina = await adapter.query(LogFilters(source_id=source_id, limit=2))

    assert len(pagina) == 2
    assert pagina[0].fecha >= pagina[1].fecha


@pytest.mark.anyio
async def test_query_offset_pagination(adapter: Any) -> None:
    source_id = unique_source()
    base = datetime.now(timezone.utc)

    for offset in range(3):
        await adapter.save(make_record(source_id, fecha=base - timedelta(minutes=offset)))

    primera = await adapter.query(LogFilters(source_id=source_id, limit=2, offset=0))
    segunda = await adapter.query(LogFilters(source_id=source_id, limit=2, offset=2))

    assert len(primera) == 2
    assert len(segunda) == 1
    assert {r.id for r in primera}.isdisjoint({r.id for r in segunda})


@pytest.mark.anyio
async def test_ensure_schema_is_idempotent(adapter: Any) -> None:
    # El switch llama a ensure_schema en cada validación, así que repetirlo
    # tiene que ser inofensivo.
    await adapter.ensure_schema()
    await adapter.ensure_schema()
    assert await adapter.ping() is True
