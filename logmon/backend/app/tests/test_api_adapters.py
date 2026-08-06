from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.models import Estado
from app.storage.base import LogFilters, StatsFilters
from app.tests.conftest import make_record, unique_source


@pytest.mark.anyio
async def test_save_many_round_trip(adapter: Any) -> None:
    source_id = unique_source("BATCH")
    records = [
        make_record(source_id),
        make_record(source_id, with_error=True),
        make_record(source_id, metodo="GET"),
    ]

    errors = await adapter.save_many(records)
    found = await adapter.query(LogFilters(source_id=source_id, limit=10))

    assert errors == [None, None, None]
    assert {record.id for record in found} == {record.id for record in records}


@pytest.mark.anyio
async def test_adapter_stats_cuadra_con_query(adapter: Any) -> None:
    source_id = unique_source("STATS")
    records = [
        make_record(source_id),
        make_record(source_id, with_error=True),
        make_record(source_id),
    ]
    assert await adapter.save_many(records) == [None, None, None]

    stats = await adapter.stats(StatsFilters(source_id=source_id, bucket_minutes=60))
    found = await adapter.query(LogFilters(source_id=source_id, limit=100))

    assert stats.total == len(found) == 3
    assert stats.errors == sum(record.estado == Estado.ERROR for record in found) == 1
    assert sum(bucket.total for bucket in stats.buckets) == 3


@pytest.mark.anyio
async def test_retention_oculta_registros_viejos(adapter: Any) -> None:
    source_id = unique_source("RETENTION")
    now = datetime.now(timezone.utc)
    old = make_record(source_id, fecha=now - timedelta(days=60))
    recent = make_record(source_id, fecha=now)
    assert await adapter.save_many([old, recent]) == [None, None]

    await adapter.delete_before(now - timedelta(days=30))
    found = await adapter.query(LogFilters(source_id=source_id, limit=100))

    assert {record.id for record in found} == {recent.id}
