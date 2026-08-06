from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from pymongo import AsyncMongoClient  # type: ignore
from pymongo.errors import BulkWriteError  # type: ignore

from app.models import Estado, LogRecord, LogStep, ParentType, StepType
from app.storage.base import (
    LogFilters,
    RepositoryStats,
    StatsFilters,
    aggregate_stats,
)

COLLECTION = "logs"


class MongoAdapter:
    """Un log es un documento con sus pasos embebidos."""

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
        self._user = user
        self._password = password
        self._database = database or "logdb"
        self._client: Optional[AsyncMongoClient] = None

    def _uri(self) -> str:
        if self._user:
            credentials = f"{quote_plus(self._user)}:{quote_plus(self._password)}@"
            auth = "?authSource=admin"
        else:
            credentials = ""
            auth = ""
        return f"mongodb://{credentials}{self._host}:{self._port}/{auth}"

    def _get_client(self) -> AsyncMongoClient:
        if self._client is None:
            self._client = AsyncMongoClient(
                self._uri(),
                serverSelectionTimeoutMS=5000,
                tz_aware=True,
            )
        return self._client

    def _collection(self) -> Any:
        return self._get_client()[self._database][COLLECTION]

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def ensure_schema(self) -> None:
        collection = self._collection()
        await collection.create_index([("source_id", 1), ("fecha", -1)])
        await collection.create_index([("estado", 1)])
        await collection.create_index([("metodo", 1)])

    async def ping(self) -> bool:
        await self._get_client().admin.command("ping")
        return True

    async def save(self, record: LogRecord) -> None:
        error = (await self.save_many([record]))[0]
        if error is not None:
            raise RuntimeError(error)

    async def save_many(self, records: List[LogRecord]) -> List[Optional[str]]:
        if not records:
            return []

        errors: List[Optional[str]] = [None] * len(records)
        try:
            await self._collection().insert_many(
                [self._record_to_document(record) for record in records],
                ordered=False,
            )
        except BulkWriteError as exc:
            details = exc.details or {}
            for write_error in details.get("writeErrors", []):
                index = int(write_error.get("index", -1))
                if 0 <= index < len(errors):
                    errors[index] = (
                        f"BulkWriteError: {write_error.get('errmsg', 'error de escritura')}"
                    )

            write_concern_errors = details.get("writeConcernErrors", [])
            if write_concern_errors:
                message = f"BulkWriteError: {write_concern_errors}"
                errors = [error or message for error in errors]
        except Exception as exc:  # noqa: BLE001 - respuesta parcial
            message = f"{type(exc).__name__}: {exc}"
            errors = [message] * len(records)

        return errors

    async def query(self, filters: LogFilters) -> List[LogRecord]:
        criteria: Dict[str, Any] = {}
        if filters.source_id is not None:
            criteria["source_id"] = filters.source_id
        if filters.estado is not None:
            criteria["estado"] = filters.estado.value
        if filters.metodo is not None:
            criteria["metodo"] = filters.metodo
        fecha: Dict[str, Any] = {}
        if filters.fecha_desde is not None:
            fecha["$gte"] = _as_utc(filters.fecha_desde)
        if filters.fecha_hasta is not None:
            fecha["$lte"] = _as_utc(filters.fecha_hasta)
        if fecha:
            criteria["fecha"] = fecha

        cursor = (
            self._collection()
            .find(criteria)
            .sort([("fecha", -1), ("_id", -1)])
            .skip(filters.offset)
            .limit(filters.limit)
        )
        return [self._document_to_record(document) async for document in cursor]

    async def get(self, log_id: str) -> Optional[LogRecord]:
        document = await self._collection().find_one({"_id": log_id})
        return self._document_to_record(document) if document is not None else None

    async def stats(self, filters: StatsFilters) -> RepositoryStats:
        criteria: Dict[str, Any] = {}
        if filters.source_id is not None:
            criteria["source_id"] = filters.source_id
        fecha: Dict[str, Any] = {}
        if filters.fecha_desde is not None:
            fecha["$gte"] = _as_utc(filters.fecha_desde)
        if filters.fecha_hasta is not None:
            fecha["$lte"] = _as_utc(filters.fecha_hasta)
        if fecha:
            criteria["fecha"] = fecha

        cursor = self._collection().find(
            criteria,
            {"fecha": 1, "estado": 1},
        )
        rows = [
            (document["fecha"], document["estado"])
            async for document in cursor
        ]
        return aggregate_stats(rows, filters.bucket_minutes)

    async def delete_before(self, cutoff: datetime) -> int:
        result = await self._collection().delete_many({"fecha": {"$lt": _as_utc(cutoff)}})
        return int(result.deleted_count)

    @staticmethod
    def _record_to_document(record: LogRecord) -> Dict[str, Any]:
        return {
            "_id": record.id,
            "source_id": record.source_id,
            "parent_type": record.parent_type.value,
            "entrada": record.entrada,
            "resultado": record.resultado,
            "metodo": record.metodo,
            "tiempo_ms": record.tiempo_ms,
            "estado": record.estado.value,
            "fecha": _as_utc(record.fecha),
            "created_at": datetime.now(timezone.utc),
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

    @staticmethod
    def _document_to_record(document: Dict[str, Any]) -> LogRecord:
        steps = [
            LogStep(
                orden=step["orden"],
                tipo=StepType(step["tipo"]),
                contenido=step["contenido"],
                duration_ms=step.get("duration_ms"),
            )
            for step in sorted(document.get("steps", []), key=lambda item: item["orden"])
        ]
        return LogRecord(
            id=document["_id"],
            source_id=document["source_id"],
            parent_type=ParentType(document["parent_type"]),
            entrada=document["entrada"],
            resultado=document["resultado"],
            metodo=document["metodo"],
            tiempo_ms=document["tiempo_ms"],
            estado=Estado(document["estado"]),
            fecha=_as_utc(document["fecha"]),
            steps=steps,
        )


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
