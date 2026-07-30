from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Mapping

from app.metadata import repo
from app.storage.base import LogRepository

logger = logging.getLogger(__name__)


class UnknownEngineError(ValueError):
    pass


class UnknownConnectionError(ValueError):
    pass


def build_adapter(connection: Mapping[str, Any]) -> LogRepository:
    """Instancia el adapter que corresponde al motor de la conexión.

    Los drivers se importan acá adentro a propósito: si falta el paquete de un
    motor, sólo se rompe ese motor y el resto del sistema sigue en pie.
    """

    engine = str(connection["engine"]).strip().lower()

    common = {
        "host": connection["host"],
        "port": int(connection["port"]),
        "user": connection["user"],
        "password": connection["password"],
        "database": connection["database"],
    }

    if engine in ("postgres", "postgresql"):
        from app.storage.adapters.postgres import PostgresAdapter

        return PostgresAdapter(**common)

    if engine in ("mariadb", "mysql"):
        from app.storage.adapters.mariadb import MariaDbAdapter

        return MariaDbAdapter(**common)

    if engine in ("sqlserver", "mssql"):
        from app.storage.adapters.sqlserver import SqlServerAdapter

        return SqlServerAdapter(**common)

    if engine in ("mongo", "mongodb"):
        from app.storage.adapters.mongo import MongoAdapter

        return MongoAdapter(**common)

    if engine == "redis":
        from app.storage.adapters.redis import RedisAdapter

        return RedisAdapter(**common)

    raise UnknownEngineError(f"Motor no soportado: {engine!r}")


class AdapterRegistry:
    """Cachea un adapter (y por lo tanto su pool) por connection_id.

    Los adapters se abren de forma perezosa la primera vez que se piden y sólo
    se cierran en el shutdown del proceso. Cerrarlos durante un switch abriría
    una ventana en la que una escritura en vuelo se encontraría con un pool ya
    destruido.
    """

    def __init__(self) -> None:
        self._adapters: Dict[str, LogRepository] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _lock_for(self, connection_id: str) -> asyncio.Lock:
        lock = self._locks.get(connection_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[connection_id] = lock
        return lock

    async def get(self, connection_id: str) -> LogRepository:
        adapter = self._adapters.get(connection_id)
        if adapter is not None:
            return adapter

        async with self._lock_for(connection_id):
            # Puede haberse creado mientras esperábamos el lock.
            adapter = self._adapters.get(connection_id)
            if adapter is not None:
                return adapter

            connection = await repo.get_connection(connection_id)
            if connection is None:
                raise UnknownConnectionError(f"No existe la conexión {connection_id!r}")

            adapter = build_adapter(connection)
            self._adapters[connection_id] = adapter
            logger.info(
                "adapter %s abierto para la conexión %s",
                connection["engine"],
                connection_id,
            )
            return adapter

    def peek(self, connection_id: str) -> LogRepository | None:
        return self._adapters.get(connection_id)

    async def forget(self, connection_id: str) -> None:
        """Descarta el adapter cacheado (al borrar o editar una conexión)."""

        adapter = self._adapters.pop(connection_id, None)
        if adapter is None:
            return
        try:
            await adapter.close()
        except Exception:  # noqa: BLE001 - cerrar nunca debe tumbar la request
            logger.warning("fallo al cerrar el adapter de %s", connection_id, exc_info=True)

    async def close_all(self) -> None:
        adapters = list(self._adapters.items())
        self._adapters.clear()

        for connection_id, adapter in adapters:
            try:
                await adapter.close()
            except Exception:  # noqa: BLE001
                logger.warning("fallo al cerrar el adapter de %s", connection_id, exc_info=True)
