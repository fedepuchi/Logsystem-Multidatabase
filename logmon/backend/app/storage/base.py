from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

from app.models import Estado, LogRecord


@dataclass
class LogFilters:
    source_id: Optional[str] = None
    estado: Optional[Estado] = None
    metodo: Optional[str] = None
    fecha_desde: Optional[datetime] = None
    fecha_hasta: Optional[datetime] = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class StatsFilters:
    source_id: Optional[str] = None
    fecha_desde: Optional[datetime] = None
    fecha_hasta: Optional[datetime] = None
    bucket_minutes: int = 60


@dataclass(frozen=True)
class StatsBucket:
    start: datetime
    total: int
    errors: int


@dataclass(frozen=True)
class RepositoryStats:
    total: int
    errors: int
    buckets: List[StatsBucket]


@dataclass(frozen=True)
class BatchSaveResult:
    """Resultado de una escritura dentro de un lote.

    ``error`` es ``None`` cuando el registro fue persistido. La lista devuelta
    por ``save_many`` conserva exactamente el mismo orden de entrada.
    """

    connection_id: Optional[str] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


def as_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def aggregate_stats(
    rows: Iterable[Tuple[datetime, Estado | str]],
    bucket_minutes: int,
) -> RepositoryStats:
    """Agrupa pares ``(fecha, estado)`` en franjas UTC.

    Los adapters consultan únicamente las dos columnas necesarias y realizan
    la agregación en el backend, nunca sobre la página visible del frontend.
    """

    if bucket_minutes < 1:
        raise ValueError("bucket_minutes debe ser mayor que cero")

    bucket_seconds = bucket_minutes * 60
    counters: dict[datetime, list[int]] = {}
    total = 0
    errors = 0

    for fecha, estado in rows:
        total += 1
        is_error = estado == Estado.ERROR or str(estado) == Estado.ERROR.value
        errors += int(is_error)

        epoch = int(as_utc(fecha).timestamp())
        bucket_epoch = (epoch // bucket_seconds) * bucket_seconds
        start = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)
        values = counters.setdefault(start, [0, 0])
        values[0] += 1
        values[1] += int(is_error)

    buckets = [
        StatsBucket(start=start, total=values[0], errors=values[1])
        for start, values in sorted(counters.items())
    ]
    return RepositoryStats(total=total, errors=errors, buckets=buckets)


def merge_stats(items: Sequence[RepositoryStats]) -> RepositoryStats:
    total = sum(item.total for item in items)
    errors = sum(item.errors for item in items)
    buckets: dict[datetime, list[int]] = {}

    for item in items:
        for bucket in item.buckets:
            values = buckets.setdefault(as_utc(bucket.start), [0, 0])
            values[0] += bucket.total
            values[1] += bucket.errors

    return RepositoryStats(
        total=total,
        errors=errors,
        buckets=[
            StatsBucket(start=start, total=values[0], errors=values[1])
            for start, values in sorted(buckets.items())
        ],
    )


@runtime_checkable
class LogRepository(Protocol):
    async def ensure_schema(self) -> None: ...

    async def ping(self) -> bool: ...

    async def save(self, record: LogRecord) -> None: ...

    async def save_many(self, records: List[LogRecord]) -> List[Optional[str]]: ...

    async def query(self, filters: LogFilters) -> List[LogRecord]: ...

    async def get(self, log_id: str) -> Optional[LogRecord]: ...

    async def stats(self, filters: StatsFilters) -> RepositoryStats: ...

    async def delete_before(self, cutoff: datetime) -> int: ...

    async def close(self) -> None: ...
