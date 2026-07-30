from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.models import Estado, LogRecord, LogStep, ParentType, StepType
from app.storage.base import LogFilters


class MongoAdapter:
    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._client: Optional[AsyncMongoClient] = None
        self._db: Optional[AsyncDatabase] = None

    async def _get_db(self) -> AsyncDatabase:
        if self._client is None:
            if self._user:
                user = quote_plus(self._user)
                password = quote_plus(self._password or "")
                uri = f"mongodb://{user}:{password}@{self._host}:{self._port}"
            else:
                uri = f"mongodb://{self._host}:{self._port}"
            self._client = AsyncMongoClient(
                uri,
                tz_aware=True,
                uuidRepresentation="standard",
            )
            self._db = self._client[self._database]
        assert self._db is not None
        return self._db

    async def ensure_schema(self) -> None:
        db = await self._get_db()
        await db.logs.create_index(
            [("source_id", ASCENDING), ("fecha", DESCENDING)],
            name="idx_logs_source_fecha",
        )
        await db.logs.create_index("estado", name="idx_logs_estado")
        await db.logs.create_index("metodo", name="idx_logs_metodo")

    async def ping(self) -> bool:
        db = await self._get_db()
        await db.command("ping")
        return True

    async def save(self, record: LogRecord) -> None:
        db = await self._get_db()
        now = datetime.now(timezone.utc)
        doc: Dict[str, Any] = {
            "_id": record.id,
            "source_id": record.source_id,
            "parent_type": record.parent_type.value,
            "entrada": record.entrada,
            "resultado": record.resultado,
            "metodo": record.metodo,
            "tiempo_ms": record.tiempo_ms,
            "estado": record.estado.value,
            "fecha": record.fecha,
            "created_at": now,
            "steps": [
                {
                    "orden": step.orden,
                    "tipo": step.tipo.value,
                    "contenido": step.contenido,
                    "duration_ms": step.duration_ms,
                }
                for step in record.steps
            ],
        }
        await db.logs.insert_one(doc)

    async def query(self, filters: LogFilters) -> List[LogRecord]:
        db = await self._get_db()
        filtro: Dict[str, Any] = {}

        if filters.source_id is not None:
            filtro["source_id"] = filters.source_id
        if filters.estado is not None:
            filtro["estado"] = filters.estado.value
        if filters.metodo is not None:
            filtro["metodo"] = filters.metodo

        fecha_range: Dict[str, Any] = {}
        if filters.fecha_desde is not None:
            fecha_range["$gte"] = filters.fecha_desde
        if filters.fecha_hasta is not None:
            fecha_range["$lte"] = filters.fecha_hasta
        if fecha_range:
            filtro["fecha"] = fecha_range

        cursor = (
            db.logs.find(filtro)
            .sort("fecha", DESCENDING)
            .skip(filters.offset)
            .limit(filters.limit)
        )
        records: List[LogRecord] = []
        async for doc in cursor:
            records.append(self._doc_to_record(doc))
        return records

    async def get(self, log_id: str) -> Optional[LogRecord]:
        db = await self._get_db()
        doc = await db.logs.find_one({"_id": log_id})
        if doc is None:
            return None
        return self._doc_to_record(doc)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._db = None

    @staticmethod
    def _doc_to_record(doc: Dict[str, Any]) -> LogRecord:
        fecha = doc["fecha"]
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)

        steps = [
            LogStep(
                orden=step["orden"],
                tipo=StepType(step["tipo"]),
                contenido=step["contenido"],
                duration_ms=step.get("duration_ms"),
            )
            for step in sorted(doc.get("steps", []), key=lambda s: s["orden"])
        ]

        return LogRecord(
            id=doc["_id"],
            source_id=doc["source_id"],
            parent_type=ParentType(doc["parent_type"]),
            entrada=doc["entrada"],
            resultado=doc["resultado"],
            metodo=doc["metodo"],
            tiempo_ms=doc["tiempo_ms"],
            estado=Estado(doc["estado"]),
            fecha=fecha,
            steps=steps,
        )
