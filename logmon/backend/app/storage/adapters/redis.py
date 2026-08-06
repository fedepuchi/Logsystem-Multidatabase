from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis  # type: ignore

from app.config import get_settings
from app.models import Estado, LogRecord, LogStep, ParentType, StepType
from app.storage.base import (
    LogFilters,
    RepositoryStats,
    StatsFilters,
    aggregate_stats,
)

logger = logging.getLogger(__name__)

ALL_INDEX = "idx:all"
SCAN_CAP = 5000


class RedisAdapter:
    """Adapter clave-valor con TTL por log y pipeline para lotes."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        retention_days: Optional[int] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user or None
        self._password = password or None
        self._db = _to_db_index(database)
        days = retention_days or get_settings().logmon_retention_days
        self._retention_seconds = max(1, days) * 24 * 60 * 60
        self._client: Optional[aioredis.Redis] = None

    def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.Redis(
                host=self._host,
                port=self._port,
                db=self._db,
                username=self._user,
                password=self._password,
                decode_responses=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def ensure_schema(self) -> None:
        await self.ping()

    async def ping(self) -> bool:
        return bool(await self._get_client().ping())

    async def save(self, record: LogRecord) -> None:
        error = (await self.save_many([record]))[0]
        if error is not None:
            raise RuntimeError(error)

    async def save_many(self, records: List[LogRecord]) -> List[Optional[str]]:
        if not records:
            return []

        client = self._get_client()
        try:
            # Un único MULTI/EXEC para todo el lote. Cada hash recibe EXPIRE;
            # no se programa un borrado explícito del cuerpo del log.
            async with client.pipeline(transaction=True) as pipe:
                for record in records:
                    score = _epoch_ms(record.fecha)
                    key = _log_key(record.id)
                    pipe.hset(key, mapping=self._record_to_mapping(record))
                    pipe.expire(key, self._retention_seconds)
                    pipe.zadd(_source_index(record.source_id), {record.id: score})
                    pipe.zadd(ALL_INDEX, {record.id: score})
                await pipe.execute()
        except Exception as exc:  
            error = f"{type(exc).__name__}: {exc}"
            return [error] * len(records)

        return [None] * len(records)

    async def query(self, filters: LogFilters) -> List[LogRecord]:
        client = self._get_client()
        index = _source_index(filters.source_id) if filters.source_id else ALL_INDEX
        min_score = _epoch_ms(filters.fecha_desde) if filters.fecha_desde else "-inf"
        max_score = _epoch_ms(filters.fecha_hasta) if filters.fecha_hasta else "+inf"
        needs_client_filter = filters.estado is not None or filters.metodo is not None
        page_end = filters.offset + filters.limit
        count = SCAN_CAP if needs_client_filter else page_end

        log_ids = await client.zrevrangebyscore(
            index,
            max=max_score,
            min=min_score,
            start=0,
            num=count,
        )
        if needs_client_filter and len(log_ids) == SCAN_CAP:
            logger.warning(
                "redis: se alcanzó el tope de %d ids al filtrar %s",
                SCAN_CAP,
                index,
            )
        if not log_ids:
            return []

        async with client.pipeline(transaction=False) as pipe:
            for log_id in log_ids:
                pipe.hgetall(_log_key(log_id))
            raw_logs = await pipe.execute()

        records: List[LogRecord] = []
        for raw in raw_logs:
            # El hash puede haber expirado aunque el miembro del índice todavía
            # no haya sido retirado por la tarea periódica.
            if not raw:
                continue
            record = self._mapping_to_record(raw)
            if filters.estado is not None and record.estado != filters.estado:
                continue
            if filters.metodo is not None and record.metodo != filters.metodo:
                continue
            records.append(record)

        if needs_client_filter:
            return records[filters.offset:page_end]
        return records[filters.offset:]

    async def get(self, log_id: str) -> Optional[LogRecord]:
        raw = await self._get_client().hgetall(_log_key(log_id))
        return self._mapping_to_record(raw) if raw else None

    async def stats(self, filters: StatsFilters) -> RepositoryStats:
        client = self._get_client()
        index = _source_index(filters.source_id) if filters.source_id else ALL_INDEX
        min_score = _epoch_ms(filters.fecha_desde) if filters.fecha_desde else "-inf"
        max_score = _epoch_ms(filters.fecha_hasta) if filters.fecha_hasta else "+inf"

        ids_with_scores = await client.zrangebyscore(
            index,
            min=min_score,
            max=max_score,
            withscores=True,
        )
        if not ids_with_scores:
            return RepositoryStats(total=0, errors=0, buckets=[])

        async with client.pipeline(transaction=False) as pipe:
            for log_id, _ in ids_with_scores:
                pipe.hget(_log_key(log_id), "estado")
            states = await pipe.execute()

        rows = []
        for (_, score), state in zip(ids_with_scores, states):
            if state is None:
                continue
            fecha = datetime.fromtimestamp(float(score) / 1000, tz=timezone.utc)
            rows.append((fecha, state))
        return aggregate_stats(rows, filters.bucket_minutes)

    async def delete_before(self, cutoff: datetime) -> int:
        """Limpia sólo referencias viejas de índices.

        Los hashes de los logs se eliminan por TTL con EXPIRE. Aquí no se usa
        DEL sobre ``log:{id}``.
        """

        client = self._get_client()
        max_score = _epoch_ms(cutoff)
        removed = int(await client.zremrangebyscore(ALL_INDEX, "-inf", max_score))

        async for key in client.scan_iter(match="idx:src:*"):
            await client.zremrangebyscore(key, "-inf", max_score)
        return removed

    @staticmethod
    def _record_to_mapping(record: LogRecord) -> Dict[str, str]:
        steps = [
            {
                "orden": step.orden,
                "tipo": step.tipo.value,
                "contenido": step.contenido,
                "duration_ms": step.duration_ms,
            }
            for step in record.steps
        ]
        return {
            "id": record.id,
            "source_id": record.source_id,
            "parent_type": record.parent_type.value,
            "entrada": record.entrada,
            "resultado": record.resultado,
            "metodo": record.metodo,
            "tiempo_ms": str(record.tiempo_ms),
            "estado": record.estado.value,
            "fecha": _as_utc(record.fecha).isoformat(),
            "steps_json": json.dumps(steps, ensure_ascii=False),
        }

    @staticmethod
    def _mapping_to_record(raw: Dict[str, Any]) -> LogRecord:
        steps = [
            LogStep(
                orden=step["orden"],
                tipo=StepType(step["tipo"]),
                contenido=step["contenido"],
                duration_ms=step.get("duration_ms"),
            )
            for step in json.loads(raw.get("steps_json") or "[]")
        ]
        return LogRecord(
            id=raw["id"],
            source_id=raw["source_id"],
            parent_type=ParentType(raw["parent_type"]),
            entrada=raw["entrada"],
            resultado=raw["resultado"],
            metodo=raw["metodo"],
            tiempo_ms=int(raw["tiempo_ms"]),
            estado=Estado(raw["estado"]),
            fecha=_as_utc(datetime.fromisoformat(raw["fecha"])),
            steps=steps,
        )


def _log_key(log_id: str) -> str:
    return f"log:{log_id}"


def _source_index(source_id: str) -> str:
    return f"idx:src:{source_id}"


def _epoch_ms(value: datetime) -> int:
    return int(_as_utc(value).timestamp() * 1000)


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _to_db_index(database: str) -> int:
    try:
        return int(database or "0")
    except ValueError as exc:
        raise ValueError("La base de Redis debe ser un índice numérico") from exc
