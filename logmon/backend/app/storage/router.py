from __future__ import annotations

import asyncio
import dataclasses
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.ids import new_ulid
from app.metadata import repo
from app.models import LogRecord, LogSummary
from app.storage.base import LogFilters, LogRepository
from app.storage.registry import AdapterRegistry

logger = logging.getLogger(__name__)


class SwitchAborted(ValueError):
    """El destino no pasó la validación: no se cambió nada."""


class UnboundSourceError(ValueError):
    """La fuente no tiene ninguna conexión asignada todavía."""


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class StorageRouter:
    """Decide en qué motor se escribe cada fuente y hace el cambio en vivo.

    La metadata SQLite es la fuente de verdad; ``_active`` es sólo un cache en
    memoria que se reconstruye al arrancar con :meth:`rebuild`.

    Hay un ``asyncio.Lock`` por fuente que cubre tanto el camino de escritura
    como el switch completo. Eso implica que un switch lento (SQL Server puede
    tardar en crear el schema) demora las escrituras de esa fuente, pero las
    demora: no las pierde ni las manda a una base a medio configurar. Es
    exactamente la garantía que pide el requisito.
    """

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
        """Reconstruye el mapa activo desde ``source_bindings``."""

        self._active = await repo.all_current_bindings()
        logger.info("router: %d fuente(s) con conexión activa", len(self._active))

    async def resolve(self, source_id: str) -> str:
        """connection_id activo de la fuente. Lanza si no tiene binding."""

        connection_id = self._active.get(source_id)

        if connection_id is None:
            # Cache frío (fuente creada por otra vía): releemos la metadata.
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

    # -- escritura ---------------------------------------------------------

    async def save(self, record: LogRecord) -> str:
        """Persiste el log en el motor activo de su fuente. Devuelve el connection_id."""

        if not record.id:
            record = record.model_copy(update={"id": new_ulid()})

        async with self._lock_for(record.source_id):
            connection_id, adapter = await self.adapter_for(record.source_id)
            await adapter.save(record)
            return connection_id

    # -- switch ------------------------------------------------------------

    async def switch(self, source_id: str, connection_id: str) -> Dict[str, Any]:
        """Cambia el destino de una fuente con validate-before-flip.

        Orden estricto: validar el destino (ping + ensure_schema) → persistir
        binding y auditoría → recién ahí mover el mapa en memoria. Si algo falla
        antes del flip, la fuente sigue escribiendo donde estaba.
        """

        async with self._lock_for(source_id):
            previous = self._active.get(source_id) or await repo.current_binding(source_id)

            try:
                adapter = await self.registry.get(connection_id)
                if not await adapter.ping():
                    raise RuntimeError("el ping al motor destino devolvió False")
                await adapter.ensure_schema()
            except Exception as exc:  # noqa: BLE001 - queremos auditar cualquier fallo
                detail = f"{type(exc).__name__}: {exc}"
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
        """Fan-out a todas las conexiones del historial y merge-sort por fecha.

        Es la prueba visual de que un switch no perdió nada: los logs viejos
        siguen apareciendo desde el motor anterior, etiquetados con su origen.
        """

        connection_ids = await self._connections_for_query(filters.source_id)
        if not connection_ids:
            return []

        # Cada motor devuelve hasta offset+limit filas porque la paginación
        # real se aplica recién sobre el resultado ya mergeado.
        page_end = filters.offset + filters.limit
        per_adapter = dataclasses.replace(filters, limit=page_end, offset=0)

        results = await asyncio.gather(
            *(self._query_one(cid, per_adapter) for cid in connection_ids),
            return_exceptions=True,
        )

        merged: List[LogSummary] = []
        for connection_id, result in zip(connection_ids, results):
            if isinstance(result, BaseException):
                # Un motor caído degrada el visor, no lo tumba.
                logger.warning(
                    "query a %s falló, se omite del merge: %s", connection_id, result
                )
                continue
            merged.extend(result)

        # ULID desempata: es monotónico, así que ordena estable dentro del ms.
        merged.sort(key=lambda item: (_as_utc(item.fecha), item.id), reverse=True)

        return merged[filters.offset : page_end]

    async def get(self, connection_id: str, log_id: str) -> Optional[LogRecord]:
        adapter = await self.registry.get(connection_id)
        return await adapter.get(log_id)

    # -- demo --------------------------------------------------------------

    async def create_demo_logs(self) -> Dict[str, Any]:
        """Inserta el juego de logs de ejemplo por el camino normal de escritura."""

        from app.seed import build_demo_logs  # import diferido: seed importa el router

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

        return {"creados": len(creados), "detalle": creados, "omitidos": sorted(set(omitidos))}

    # -- ciclo de vida -----------------------------------------------------

    async def close_all(self) -> None:
        await self.registry.close_all()


storage_router = StorageRouter()
