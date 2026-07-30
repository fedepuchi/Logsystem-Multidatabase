from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis  # type: ignore

from app.models import Estado, LogRecord, LogStep, ParentType, StepType
from app.storage.base import LogFilters

logger = logging.getLogger(__name__)

ALL_INDEX = "idx:all"

# Redis no sabe filtrar por estado/método, así que esos filtros se aplican en
# cliente sobre una ventana acotada del índice por fecha. El tope evita traerse
# un dataset entero; si se alcanza, se avisa en el log en vez de truncar en
# silencio.
SCAN_CAP = 5000


class RedisAdapter:
    """Adapter clave-valor.

    - ``log:{id}`` es un hash con el header del log y los pasos serializados
      en ``steps_json``.
    - ``idx:src:{source_id}`` e ``idx:all`` son sorted sets con score
      ``fecha_ms``, que dan el orden y el rango por fecha.

    ``save()`` escribe hash e índices en un único pipeline MULTI/EXEC, así que
    nunca queda un log indexado sin cuerpo (ni al revés).
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user or None
        self._password = password or None
        self._db = _to_db_index(database)
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
        """Redis no tiene DDL: los índices se crean solos al escribir.

        Se mantiene el ping para que el validate-before-flip del switch siga
        siendo significativo en este motor.
        """

        await self.ping()

    async def ping(self) -> bool:
        return bool(await self._get_client().ping())

    async def save(self, record: LogRecord) -> None:
        client = self._get_client()
        score = _epoch_ms(record.fecha)

        async with client.pipeline(transaction=True) as pipe:
            pipe.hset(_log_key(record.id), mapping=self._record_to_mapping(record))
            pipe.zadd(_source_index(record.source_id), {record.id: score})
            pipe.zadd(ALL_INDEX, {record.id: score})
            await pipe.execute()

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
                "redis: se alcanzó el tope de %d ids al filtrar %s; "
                "puede haber logs más antiguos sin considerar",
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
            if not raw:
                continue
            record = self._mapping_to_record(raw)
            if filters.estado is not None and record.estado != filters.estado:
                continue
            if filters.metodo is not None and record.metodo != filters.metodo:
                continue
            records.append(record)

        if needs_client_filter:
            return records[filters.offset : page_end]
        return records[filters.offset :]

    async def get(self, log_id: str) -> Optional[LogRecord]:
        raw = await self._get_client().hgetall(_log_key(log_id))
        return self._mapping_to_record(raw) if raw else None

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


def _to_db_index(database: str) -> int:
    try:
        return int(str(database).strip() or 0)
    except ValueError:
        # En Redis la "base de datos" es un número; si llega un nombre se usa 0.
        return 0


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _epoch_ms(value: datetime) -> int:
    return int(_as_utc(value).timestamp() * 1000)
