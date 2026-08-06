"""Pruebas de la tarea, batch, stats y retención del router."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from app.models import LogRecord
from app.storage.base import LogFilters, RepositoryStats, StatsFilters, aggregate_stats
from app.tests.conftest import FakeAdapter


async def _fake_save_many(
    self: FakeAdapter,
    records: List[LogRecord],
) -> List[Optional[str]]:
    self._guard()
    self._store.rows(self.connection_id).extend(records)
    return [None] * len(records)


async def _fake_stats(self: FakeAdapter, filters: StatsFilters) -> RepositoryStats:
    self._guard()
    rows = list(self._store.rows(self.connection_id))
    if filters.source_id is not None:
        rows = [row for row in rows if row.source_id == filters.source_id]
    if filters.fecha_desde is not None:
        rows = [row for row in rows if row.fecha >= filters.fecha_desde]
    if filters.fecha_hasta is not None:
        rows = [row for row in rows if row.fecha <= filters.fecha_hasta]
    return aggregate_stats(
        ((row.fecha, row.estado) for row in rows),
        filters.bucket_minutes,
    )


async def _fake_delete_before(self: FakeAdapter, cutoff: datetime) -> int:
    self._guard()
    rows = self._store.rows(self.connection_id)
    remaining = [row for row in rows if row.fecha >= cutoff]
    deleted = len(rows) - len(remaining)
    self._store.data[self.connection_id] = remaining
    return deleted


FakeAdapter.save_many = _fake_save_many  
FakeAdapter.stats = _fake_stats  
FakeAdapter.delete_before = _fake_delete_before  


class CountingLock:
    def __init__(self) -> None:
        import asyncio

        self._lock = asyncio.Lock()
        self.entries = 0

    async def __aenter__(self) -> "CountingLock":
        self.entries += 1
        await self._lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._lock.release()


def connection(name: str, engine: str = "postgres") -> Dict[str, Any]:
    return {
        "name": name,
        "engine": engine,
        "host": "db",
        "port": 5432,
        "user": "loguser",
        "password": "logpass",
        "database": "logdb",
    }


def log_payload(
    source: str = "APP1",
    *,
    error: bool = False,
    fecha: Optional[datetime] = None,
) -> Dict[str, Any]:
    steps = [
        {"orden": 1, "tipo": "ENTRADA", "contenido": "payload", "duration_ms": 10},
        {
            "orden": 2,
            "tipo": "ERROR" if error else "SALIDA",
            "contenido": "falló" if error else "ok",
            "duration_ms": 20,
        },
    ]
    payload: Dict[str, Any] = {
        "source_id": source,
        "parent_type": "API",
        "entrada": "POST /batch",
        "resultado": "procesado",
        "metodo": "POST",
        "steps": steps,
    }
    if fecha is not None:
        payload["fecha"] = fecha.isoformat()
    return payload


async def prepare(client) -> None:
    await client.post("/api/connections", json=connection("C1 Postgres"))
    await client.post("/api/sources", json={"name": "APP1", "parent_type": "API"})
    await client.post("/api/sources/APP1/switch", json={"connection_id": "C1"})


@pytest.mark.anyio
async def test_batch_de_100_toma_el_lock_una_sola_vez(api_client) -> None:
    client, router, store = api_client
    await prepare(client)

    counting_lock = CountingLock()
    router._locks["APP1"] = counting_lock

    response = await client.post(
        "/api/logs/batch",
        json=[log_payload() for _ in range(100)],
    )

    assert response.status_code == 200
    assert response.json()["saved"] == 100
    assert response.json()["failed"] == 0
    assert counting_lock.entries == 1
    assert store.count("C1") == 100


@pytest.mark.anyio
async def test_log_invalido_en_medio_no_tumba_el_lote(api_client) -> None:
    client, _, store = api_client
    await prepare(client)

    invalid = log_payload()
    invalid.pop("parent_type")
    response = await client.post(
        "/api/logs/batch",
        json=[log_payload(), invalid, log_payload(error=True)],
    )
    body = response.json()

    assert response.status_code == 200
    assert body["received"] == 3
    assert body["saved"] == 2
    assert body["failed"] == 1
    assert body["items"][1]["success"] is False
    assert body["items"][0]["success"] is True
    assert body["items"][2]["success"] is True
    assert store.count("C1") == 2


@pytest.mark.anyio
async def test_stats_cuadra_con_get_logs(api_client) -> None:
    client, _, _ = api_client
    await prepare(client)

    payloads = [
        log_payload(error=False),
        log_payload(error=True),
        log_payload(error=False),
        log_payload(error=True),
    ]
    assert (await client.post("/api/logs/batch", json=payloads)).status_code == 200

    logs = (await client.get("/api/logs", params={"source": "APP1", "limit": 1000})).json()
    stats = (
        await client.get(
            "/api/stats",
            params={"source": "APP1", "bucket_minutes": 60},
        )
    ).json()

    assert stats["total_logs"] == len(logs)
    assert stats["error_count"] == sum(1 for item in logs if item["estado"] == "ERROR")
    assert sum(bucket["total"] for engine in stats["engines"] for bucket in engine["volume"]) == len(logs)


@pytest.mark.anyio
async def test_cleanup_expired_conserva_logs_recientes(seeded_router) -> None:
    router, store = seeded_router
    await router.switch("APP1", "C1")

    now = datetime.now(timezone.utc)
    old = log_payload(fecha=now - timedelta(days=60))
    recent = log_payload(fecha=now)

    # Se usa la API de modelos para no depender del endpoint en esta prueba.
    from app.ids import new_ulid
    from app.models import LogCreate

    await router.save_many(
        [
            LogCreate.model_validate(old).to_record(new_ulid()),
            LogCreate.model_validate(recent).to_record(new_ulid()),
        ]
    )
    result = await router.cleanup_expired(retention_days=30)
    remaining = await router.query(LogFilters(source_id="APP1", limit=100))

    assert result["deleted"] == 1
    assert len(remaining) == 1
    assert store.count("C1") == 1
