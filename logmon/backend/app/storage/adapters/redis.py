from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

from app.models import Estado, LogRecord, LogStep, ParentType, StepType
from app.storage.base import LogFilters


class RedisAdapter:
    def __init__(
        self,
        host: str,
        port: int,
        db: int = 0,
        password: Optional[str] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=self._host,
                port=self._port,
                db=self._db,
                password=self._password,
                decode_responses=True,
            )
        return self._redis

    async def ensure_schema(self) -> None:
        """No-op: Redis no tiene esquema; el Protocol exige el metodo."""
        return None

    async def ping(self) -> bool:
        r = await self._get_redis()
        await r.ping()
        return True

    async def save(self, record: LogRecord) -> None:
        r = await self._get_redis()
        fecha_ms = record.fecha.timestamp() * 1000
        header: Dict[str, str] = {
            "id": record.id,
            "source_id": record.source_id,
            "parent_type": record.parent_type.value,
            "entrada": record.entrada,
            "resultado": record.resultado,
            "metodo": record.metodo,
            "tiempo_ms": str(record.tiempo_ms),
            "estado": record.estado.value,
            "fecha": record.fecha.isoformat(),
            "steps_json": json.dumps(
                [
                    {
                        "orden": step.orden,
                        "tipo": step.tipo.value,
                        "contenido": step.contenido,
                        "duration_ms": step.duration_ms,
                    }
                    for step in record.steps
                ]
            ),
        }

        async with r.pipeline(transaction=True) as pipe:
            pipe.hset(f"log:{record.id}", mapping=header)
            pipe.zadd(f"idx:src:{record.source_id}", {record.id: fecha_ms})
            pipe.zadd("idx:all", {record.id: fecha_ms})
            await pipe.execute()

    async def query(self, filters: LogFilters) -> List[LogRecord]:
        r = await self._get_redis()

        if filters.source_id is not None:
            key = f"idx:src:{filters.source_id}"
        else:
            key = "idx:all"

        min_score: Any = (
            filters.fecha_desde.timestamp() * 1000
            if filters.fecha_desde is not None
            else "-inf"
        )
        max_score: Any = (
            filters.fecha_hasta.timestamp() * 1000
            if filters.fecha_hasta is not None
            else "+inf"
        )

        ids: List[str] = await r.zrevrangebyscore(key, max_score, min_score)
        if not ids:
            return []

        async with r.pipeline(transaction=False) as pipe:
            for log_id in ids:
                pipe.hgetall(f"log:{log_id}")
            hashes = await pipe.execute()

        records: List[LogRecord] = []
        for data in hashes:
            if not data:
                continue
            record = self._hash_to_record(data)
            if filters.estado is not None and record.estado != filters.estado:
                continue
            if filters.metodo is not None and record.metodo != filters.metodo:
                continue
            records.append(record)

        return records[filters.offset : filters.offset + filters.limit]

    async def get(self, log_id: str) -> Optional[LogRecord]:
        r = await self._get_redis()
        data = await r.hgetall(f"log:{log_id}")
        if not data:
            return None
        return self._hash_to_record(data)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    @staticmethod
    def _hash_to_record(data: Dict[str, str]) -> LogRecord:
        raw_steps = json.loads(data.get("steps_json") or "[]")
        steps = [
            LogStep(
                orden=step["orden"],
                tipo=StepType(step["tipo"]),
                contenido=step["contenido"],
                duration_ms=step.get("duration_ms"),
            )
            for step in sorted(raw_steps, key=lambda s: s["orden"])
        ]

        fecha = datetime.fromisoformat(data["fecha"])
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)

        return LogRecord(
            id=data["id"],
            source_id=data["source_id"],
            parent_type=ParentType(data["parent_type"]),
            entrada=data["entrada"],
            resultado=data["resultado"],
            metodo=data["metodo"],
            tiempo_ms=int(data["tiempo_ms"]),
            estado=Estado(data["estado"]),
            fecha=fecha,
            steps=steps,
        )
