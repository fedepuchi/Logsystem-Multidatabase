from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.ids import new_ulid
from app.metadata import repo
from app.models import LogRecord, LogSummary
from app.storage.base import (
    BatchSaveResult,
    LogFilters,
    LogRepository,
    RepositoryStats,
    StatsFilters,
    merge_stats,
)
from app.storage.registry import AdapterRegistry

logger = logging.getLogger(__name__)


class SwitchAborted(ValueError):
    """El destino no pasó la validación: no se cambió nada."""


class UnboundSourceError(ValueError):
    """La fuente no tiene ninguna conexión asignada todavía."""


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _rate(errors: int, total: int) -> float:
    return round((errors / total) * 100, 2) if total else 0.0


class StorageRouter:
    """Enruta escrituras, lecturas, lotes, estadísticas y retención."""

    def __init__(self, registry: Optional[AdapterRegistry] = None) -> None:
        self.registry = registry or AdapterRegistry()
        self._active: Dict[str, str] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    # -- infraestructura interna ------------------------------------------
    def _lock_for(self, source_id: str) -> asyncio.Lock:
        lock = self._locks.get(source_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[source_id] = lock
        return lock

    async def rebuild(self) -> None:
        self._active = await repo.all_current_bindings()
        logger.info("router: %d fuente(s) con conexión activa", len(self._active))

    async def resolve(self, source_id: str) -> str:
        connection_id = self._active.get(source_id)
        if connection_id is None:
            connection_id = await repo.current_binding(source_id)
            if connection_id is not None:
                self._active[source_id] = connection_id

        if connection_id is None:
            raise UnboundSourceError(
                f"La fuente '{source_id}' no tiene una conexión asignada. "
                "Asignale una desde el dashboard antes de registrar logs."
            )
        return connection_id

    async def adapter_for(self, source_id: str) -> Tuple[str, LogRepository]:
        connection_id = await self.resolve(source_id)
        return connection_id, await self.registry.get(connection_id)

    # -- escritura individual ---------------------------------------------
    async def save(self, record: LogRecord) -> str:
        if not record.id:
            record = record.model_copy(update={"id": new_ulid()})

        async with self._lock_for(record.source_id):
            connection_id, adapter = await self.adapter_for(record.source_id)
            await adapter.save(record)
            return connection_id

    # -- escritura por lotes ----------------------------------------------
    async def save_many(self, records: List[LogRecord]) -> List[BatchSaveResult]:
        """Guarda un lote tomando una sola vez el lock de cada fuente.

        Las fuentes diferentes se procesan concurrentemente. Dentro de una
        misma fuente se resuelve una sola vez el destino y se llama una sola vez
        a ``adapter.save_many``. El resultado conserva el orden original.
        """

        if not records:
            return []

        normalized = [
            record if record.id else record.model_copy(update={"id": new_ulid()})
            for record in records
        ]
        positions_by_source: Dict[str, List[int]] = defaultdict(list)
        for index, record in enumerate(normalized):
            positions_by_source[record.source_id].append(index)

        results: List[Optional[BatchSaveResult]] = [None] * len(normalized)

        async def persist_source(source_id: str, positions: List[int]) -> None:
            source_records = [normalized[index] for index in positions]

            # Este es el punto importante de la tarea: un solo lock por fuente
            # para todos los elementos del lote, no uno por cada log.
            async with self._lock_for(source_id):
                try:
                    connection_id, adapter = await self.adapter_for(source_id)
                except Exception as exc:  # noqa: BLE001 - respuesta parcial
                    error = _error_text(exc)
                    for index in positions:
                        results[index] = BatchSaveResult(error=error)
                    return

                try:
                    item_errors = await adapter.save_many(source_records)
                except Exception as exc:  # noqa: BLE001 - respuesta parcial
                    item_errors = [_error_text(exc)] * len(source_records)

                if len(item_errors) != len(source_records):
                    item_errors = [
                        "RuntimeError: el adapter devolvió una cantidad inválida de resultados"
                    ] * len(source_records)

                for index, error in zip(positions, item_errors):
                    results[index] = BatchSaveResult(
                        connection_id=connection_id if error is None else None,
                        error=error,
                    )

        await asyncio.gather(
            *(
                persist_source(source_id, positions)
                for source_id, positions in positions_by_source.items()
            )
        )

        return [
            result
            if result is not None
            else BatchSaveResult(error="RuntimeError: resultado de lote no generado")
            for result in results
        ]

    # -- switch ------------------------------------------------------------
    async def switch(self, source_id: str, connection_id: str) -> Dict[str, Any]:
        async with self._lock_for(source_id):
            previous = self._active.get(source_id) or await repo.current_binding(source_id)
            try:
                adapter = await self.registry.get(connection_id)
                if not await adapter.ping():
                    raise RuntimeError("el ping al motor destino devolvió False")
                await adapter.ensure_schema()
            except Exception as exc:  # noqa: BLE001
                detail = _error_text(exc)
                await repo.record_switch(source_id, previous, connection_id, "ABORTED", detail)
                logger.warning("switch %s -> %s abortado: %s", source_id, connection_id, detail)
                raise SwitchAborted(
                    f"No se pudo validar la conexión {connection_id}: {exc}. "
                    "La fuente sigue escribiendo en su destino anterior."
                ) from exc

            await repo.append_binding(source_id, connection_id)
            await repo.record_switch(source_id, previous, connection_id, "OK", None)
            self._active[source_id] = connection_id
            logger.info("switch %s: %s -> %s", source_id, previous, connection_id)

            return {
                "source_id": source_id,
                "from_connection_id": previous,
                "to_connection_id": connection_id,
            }

    # -- lectura multi-DB --------------------------------------------------
    async def _connections_for_query(self, source_id: Optional[str]) -> List[str]:
        if source_id:
            return await repo.binding_history(source_id)
        return await repo.all_binding_connection_ids()

    async def _query_one(
        self,
        connection_id: str,
        filters: LogFilters,
    ) -> List[LogSummary]:
        adapter = await self.registry.get(connection_id)
        records = await adapter.query(filters)
        return [LogSummary.from_record(record, connection_id) for record in records]

    async def query(self, filters: LogFilters) -> List[LogSummary]:
        connection_ids = await self._connections_for_query(filters.source_id)
        if not connection_ids:
            return []

        page_end = filters.offset + filters.limit
        per_adapter = dataclasses.replace(filters, limit=page_end, offset=0)
        results = await asyncio.gather(
            *(self._query_one(cid, per_adapter) for cid in connection_ids),
            return_exceptions=True,
        )

        merged: List[LogSummary] = []
        for connection_id, result in zip(connection_ids, results):
            if isinstance(result, BaseException):
                logger.warning(
                    "query a %s falló, se omite del merge: %s", connection_id, result
                )
                continue
            merged.extend(result)

        merged.sort(key=lambda item: (_as_utc(item.fecha), item.id), reverse=True)
        return merged[filters.offset:page_end]

    async def get(self, connection_id: str, log_id: str) -> Optional[LogRecord]:
        adapter = await self.registry.get(connection_id)
        return await adapter.get(log_id)

    # -- estadísticas ------------------------------------------------------
    async def stats(self, filters: StatsFilters) -> Dict[str, Any]:
        """Agrega estadísticas reales de todos los motores involucrados."""

        connection_ids = await self._connections_for_query(filters.source_id)
        if not connection_ids:
            return {
                "generated_at": datetime.now(timezone.utc),
                "bucket_minutes": filters.bucket_minutes,
                "total_logs": 0,
                "error_count": 0,
                "error_rate": 0.0,
                "engines": [],
                "unavailable": [],
            }

        async def one(connection_id: str) -> Tuple[str, str, RepositoryStats]:
            connection = await repo.get_connection(connection_id)
            if connection is None:
                raise ValueError(f"No existe la conexión {connection_id!r}")
            engine = str(connection["engine"]).strip().lower()
            adapter = await self.registry.get(connection_id)
            return connection_id, engine, await adapter.stats(filters)

        gathered = await asyncio.gather(
            *(one(connection_id) for connection_id in connection_ids),
            return_exceptions=True,
        )

        by_engine: Dict[str, Dict[str, Any]] = {}
        unavailable: List[Dict[str, str]] = []

        for connection_id, result in zip(connection_ids, gathered):
            if isinstance(result, BaseException):
                connection = await repo.get_connection(connection_id)
                unavailable.append(
                    {
                        "connection_id": connection_id,
                        "engine": str(connection["engine"]) if connection else "unknown",
                        "error": _error_text(result),
                    }
                )
                continue

            cid, engine, repository_stats = result
            group = by_engine.setdefault(
                engine,
                {"connection_ids": [], "stats": []},
            )
            group["connection_ids"].append(cid)
            group["stats"].append(repository_stats)

        engine_rows: List[Dict[str, Any]] = []
        merged_engine_stats: List[RepositoryStats] = []

        for engine in sorted(by_engine):
            group = by_engine[engine]
            combined = merge_stats(group["stats"])
            merged_engine_stats.append(combined)
            engine_rows.append(
                {
                    "engine": engine,
                    "connection_ids": sorted(group["connection_ids"]),
                    "total_logs": combined.total,
                    "error_count": combined.errors,
                    "error_rate": _rate(combined.errors, combined.total),
                    "volume": [
                        {
                            "start": bucket.start,
                            "total": bucket.total,
                            "errors": bucket.errors,
                        }
                        for bucket in combined.buckets
                    ],
                }
            )

        overall = merge_stats(merged_engine_stats)
        return {
            "generated_at": datetime.now(timezone.utc),
            "bucket_minutes": filters.bucket_minutes,
            "total_logs": overall.total,
            "error_count": overall.errors,
            "error_rate": _rate(overall.errors, overall.total),
            "engines": engine_rows,
            "unavailable": unavailable,
        }

    # -- retención ---------------------------------------------------------
    async def cleanup_expired(self, retention_days: int) -> Dict[str, Any]:
        """Elimina datos anteriores al límite en motores persistentes.

        Redis no borra los hashes aquí: cada hash recibe ``EXPIRE`` al guardarse.
        Su adapter sólo limpia miembros antiguos de los índices sorted-set.
        """

        if retention_days < 1:
            raise ValueError("retention_days debe ser mayor que cero")

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        connection_ids = await repo.all_binding_connection_ids()

        async def clean_one(connection_id: str) -> Dict[str, Any]:
            connection = await repo.get_connection(connection_id)
            engine = str(connection["engine"]) if connection else "unknown"
            try:
                adapter = await self.registry.get(connection_id)
                deleted = await adapter.delete_before(cutoff)
                return {
                    "connection_id": connection_id,
                    "engine": engine,
                    "deleted": deleted,
                    "error": None,
                }
            except Exception as exc:  # noqa: BLE001 - una base no frena las otras
                logger.warning("retención falló para %s: %s", connection_id, exc)
                return {
                    "connection_id": connection_id,
                    "engine": engine,
                    "deleted": 0,
                    "error": _error_text(exc),
                }

        details = await asyncio.gather(*(clean_one(cid) for cid in connection_ids))
        return {
            "cutoff": cutoff,
            "deleted": sum(item["deleted"] for item in details),
            "connections": details,
        }

    async def retention_loop(
        self,
        retention_days: int,
        interval_seconds: int,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """Tarea periódica que el lifespan de ``main.py`` debe iniciar."""

        if interval_seconds < 1:
            raise ValueError("interval_seconds debe ser mayor que cero")

        while True:
            try:
                await self.cleanup_expired(retention_days)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - el worker debe seguir vivo
                logger.exception("falló la tarea periódica de retención")

            if stop_event is None:
                await asyncio.sleep(interval_seconds)
                continue

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                return
            except asyncio.TimeoutError:
                pass

    # -- demo --------------------------------------------------------------
    async def create_demo_logs(self) -> Dict[str, Any]:
        from app.seed import build_demo_logs

        creados: List[str] = []
        omitidos: List[str] = []
        for record in build_demo_logs():
            try:
                connection_id = await self.save(record)
            except UnboundSourceError:
                omitidos.append(record.source_id)
                continue
            creados.append(f"{record.source_id}->{connection_id}")

        if not creados:
            raise UnboundSourceError(
                "Ninguna fuente de la demo tiene conexión asignada. "
                "Corré `make seed` o asignalas desde el dashboard."
            )
        return {
            "creados": len(creados),
            "detalle": creados,
            "omitidos": sorted(set(omitidos)),
        }

    # -- ciclo de vida -----------------------------------------------------
    async def close_all(self) -> None:
        await self.registry.close_all()


storage_router = StorageRouter()
