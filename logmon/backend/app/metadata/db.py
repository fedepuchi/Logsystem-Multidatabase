from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_connection: Optional[aiosqlite.Connection] = None
_connection_path: Optional[str] = None


async def init_metadata_db(sqlite_path: str) -> aiosqlite.Connection:
    """Abre (y crea si hace falta) la base de metadata y aplica el schema.

    aiosqlite serializa cada operación en su propio hilo, así que una única
    conexión compartida es segura para el acceso concurrente de las corrutinas
    del backend.
    """

    global _connection, _connection_path

    if _connection is not None:
        if _connection_path == sqlite_path:
            return _connection
        # Path distinto al de la conexión abierta (p.ej. tests que no
        # cerraron la suya): cerrarla en vez de seguir usando la vieja.
        await _connection.close()
        _connection = None
        _connection_path = None

    path = Path(sqlite_path).expanduser()
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    conn = await aiosqlite.connect(str(path))
    conn.row_factory = aiosqlite.Row

    # executescript hace COMMIT implícito antes de correr, así que el PRAGMA
    # del schema se aplica fuera de transacción; lo repetimos después porque
    # foreign_keys es por conexión y es un no-op si hay una transacción activa.
    await conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    await conn.execute("PRAGMA journal_mode = WAL")
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.commit()

    _connection = conn
    _connection_path = sqlite_path
    logger.info("metadata SQLite lista en %s", path)
    return conn


def get_metadata_db() -> aiosqlite.Connection:
    if _connection is None:
        raise RuntimeError(
            "La metadata no está inicializada. Llamá a init_metadata_db() en el lifespan."
        )
    return _connection


async def close_metadata_db() -> None:
    global _connection, _connection_path

    if _connection is not None:
        await _connection.close()
        _connection = None
        _connection_path = None