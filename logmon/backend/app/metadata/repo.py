from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.ids import new_ulid
from app.metadata.db import get_metadata_db
from app.models import ConnectionIn, SourceIn

# Las fuentes se identifican por su nombre (APP1, APP2, SIS3...): es lo que
# viaja en LogRecord.source_id y en las URLs de la API, así que sources.id y
# sources.name son siempre el mismo valor.

_NUMERIC_CONNECTION_ID = re.compile(r"^C(\d+)$")


def _row_to_dict(row: Any) -> Dict[str, Any]:
    return {key: row[key] for key in row.keys()}


# --------------------------------------------------------------------------
# Conexiones
# --------------------------------------------------------------------------


async def list_connections() -> List[Dict[str, Any]]:
    db = get_metadata_db()
    async with db.execute(
        """
        SELECT id, name, engine, host, port, "user", password, "database"
        FROM connections
        ORDER BY id
        """
    ) as cur:
        return [_row_to_dict(row) for row in await cur.fetchall()]


async def get_connection(connection_id: str) -> Optional[Dict[str, Any]]:
    db = get_metadata_db()
    async with db.execute(
        """
        SELECT id, name, engine, host, port, "user", password, "database"
        FROM connections
        WHERE id = ?
        """,
        (connection_id,),
    ) as cur:
        row = await cur.fetchone()
    return _row_to_dict(row) if row is not None else None


async def connection_name_exists(name: str, exclude_id: Optional[str] = None) -> bool:
    db = get_metadata_db()
    async with db.execute(
        """
        SELECT 1 FROM connections
        WHERE lower(name) = lower(?) AND (? IS NULL OR id <> ?)
        LIMIT 1
        """,
        (name, exclude_id, exclude_id),
    ) as cur:
        return await cur.fetchone() is not None


async def next_connection_id() -> str:
    """Devuelve el siguiente id libre de la serie C1, C2, C3...

    Mantener la numeración de la pizarra hace la demo mucho más legible que un
    UUID, y se corresponde con los C1..C5 que crea el seed.
    """

    db = get_metadata_db()
    async with db.execute("SELECT id FROM connections") as cur:
        rows = await cur.fetchall()

    used = set()
    for row in rows:
        match = _NUMERIC_CONNECTION_ID.match(row["id"])
        if match:
            used.add(int(match.group(1)))

    candidate = 1
    while candidate in used:
        candidate += 1
    return f"C{candidate}"


async def create_connection(
    data: ConnectionIn,
    connection_id: Optional[str] = None,
) -> Dict[str, Any]:
    db = get_metadata_db()
    new_id = connection_id or await next_connection_id()

    await db.execute(
        """
        INSERT INTO connections (id, name, engine, host, port, "user", password, "database")
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id,
            data.name.strip(),
            data.engine.value,
            data.host.strip(),
            data.port,
            data.user.strip(),
            data.password,
            data.database.strip(),
        ),
    )
    await db.commit()

    created = await get_connection(new_id)
    assert created is not None
    return created


async def update_connection(connection_id: str, data: ConnectionIn) -> Dict[str, Any]:
    db = get_metadata_db()
    await db.execute(
        """
        UPDATE connections
        SET name = ?, engine = ?, host = ?, port = ?, "user" = ?, password = ?,
            "database" = ?,
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id = ?
        """,
        (
            data.name.strip(),
            data.engine.value,
            data.host.strip(),
            data.port,
            data.user.strip(),
            data.password,
            data.database.strip(),
            connection_id,
        ),
    )
    await db.commit()

    updated = await get_connection(connection_id)
    assert updated is not None
    return updated


async def connection_has_bindings(connection_id: str) -> bool:
    """True si alguna fuente escribió alguna vez en esta conexión.

    No alcanza con mirar el binding actual: si borráramos una conexión que sólo
    aparece en el historial, el visor multi-DB perdería el rastro de los logs
    que quedaron ahí.
    """

    db = get_metadata_db()
    async with db.execute(
        "SELECT 1 FROM source_bindings WHERE connection_id = ? LIMIT 1",
        (connection_id,),
    ) as cur:
        return await cur.fetchone() is not None


async def delete_connection(connection_id: str) -> None:
    db = get_metadata_db()
    await db.execute("DELETE FROM connections WHERE id = ?", (connection_id,))
    await db.commit()


# --------------------------------------------------------------------------
# Fuentes
# --------------------------------------------------------------------------


async def list_sources() -> List[Dict[str, Any]]:
    db = get_metadata_db()
    async with db.execute(
        """
        SELECT s.id, s.name, s.parent_type,
               (SELECT b.connection_id
                  FROM source_bindings b
                 WHERE b.source_id = s.id
                 ORDER BY b.id DESC
                 LIMIT 1) AS connection_id
        FROM sources s
        ORDER BY s.name
        """
    ) as cur:
        return [_row_to_dict(row) for row in await cur.fetchall()]


async def get_source(source_id: str) -> Optional[Dict[str, Any]]:
    db = get_metadata_db()
    async with db.execute(
        """
        SELECT s.id, s.name, s.parent_type,
               (SELECT b.connection_id
                  FROM source_bindings b
                 WHERE b.source_id = s.id
                 ORDER BY b.id DESC
                 LIMIT 1) AS connection_id
        FROM sources s
        WHERE s.id = ?
        """,
        (source_id,),
    ) as cur:
        row = await cur.fetchone()
    return _row_to_dict(row) if row is not None else None


async def create_source(data: SourceIn) -> Dict[str, Any]:
    db = get_metadata_db()
    name = data.name.strip()

    await db.execute(
        "INSERT INTO sources (id, name, parent_type) VALUES (?, ?, ?)",
        (name, name, data.parent_type.value),
    )
    await db.commit()

    created = await get_source(name)
    assert created is not None
    return created


async def delete_source(source_id: str) -> None:
    db = get_metadata_db()
    await db.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    await db.commit()


# --------------------------------------------------------------------------
# API keys de ingesta (una fuente puede tener varias)
# --------------------------------------------------------------------------

# Columnas que sí pueden salir de acá: nunca se selecciona key_hash salvo en la
# resolución de una key presentada.
_API_KEY_COLUMNS = "id, source_id, name, preview, created_at, last_used_at, revoked_at"


def _utc_now_iso() -> str:
    """Mismo formato que el DEFAULT de SQLite, para que las fechas se ordenen igual."""

    now = datetime.now(timezone.utc)
    return f"{now:%Y-%m-%dT%H:%M:%S}.{now.microsecond // 1000:03d}Z"


async def create_api_key(source_id: str, name: str, key_hash: str, preview: str) -> Dict[str, Any]:
    db = get_metadata_db()
    key_id = new_ulid()

    await db.execute(
        """
        INSERT INTO source_api_keys (id, source_id, name, preview, key_hash)
        VALUES (?, ?, ?, ?, ?)
        """,
        (key_id, source_id, name, preview, key_hash),
    )
    await db.commit()

    created = await get_api_key(key_id)
    assert created is not None
    return created


async def get_api_key(key_id: str) -> Optional[Dict[str, Any]]:
    db = get_metadata_db()
    async with db.execute(
        f"SELECT {_API_KEY_COLUMNS} FROM source_api_keys WHERE id = ?",
        (key_id,),
    ) as cur:
        row = await cur.fetchone()
    return _row_to_dict(row) if row is not None else None


async def list_api_keys(source_id: str) -> List[Dict[str, Any]]:
    db = get_metadata_db()
    async with db.execute(
        f"""
        SELECT {_API_KEY_COLUMNS} FROM source_api_keys
        WHERE source_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (source_id,),
    ) as cur:
        return [_row_to_dict(row) for row in await cur.fetchall()]


async def find_api_key_by_hash(key_hash: str) -> Optional[Dict[str, Any]]:
    """Resuelve la key presentada en la request. Va por el índice UNIQUE del hash."""

    db = get_metadata_db()
    async with db.execute(
        f"SELECT {_API_KEY_COLUMNS} FROM source_api_keys WHERE key_hash = ?",
        (key_hash,),
    ) as cur:
        row = await cur.fetchone()
    return _row_to_dict(row) if row is not None else None


async def revoke_api_key(key_id: str) -> None:
    """Marca la key como revocada. La fila queda para el historial de uso."""

    db = get_metadata_db()
    await db.execute(
        """
        UPDATE source_api_keys
        SET revoked_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id = ? AND revoked_at IS NULL
        """,
        (key_id,),
    )
    await db.commit()


async def touch_api_key(key_id: str) -> None:
    """Registra el último uso de la key.

    La ingesta es el camino caliente y la metadata es un SQLite con una única
    conexión compartida, así que escribir en cada log sería agregarle una
    escritura serializada a cada request. El dato sólo se usa para responder
    "¿esta key sigue viva?", así que se guarda con granularidad de minuto: se
    actualiza sólo si el último uso registrado es de otro minuto.
    """

    now = _utc_now_iso()

    db = get_metadata_db()
    await db.execute(
        """
        UPDATE source_api_keys
        SET last_used_at = ?
        WHERE id = ?
          AND (last_used_at IS NULL OR substr(last_used_at, 1, 16) <> substr(?, 1, 16))
        """,
        (now, key_id, now),
    )
    await db.commit()


# --------------------------------------------------------------------------
# Bindings (historial append-only fuente -> conexión)
# --------------------------------------------------------------------------


async def current_binding(source_id: str) -> Optional[str]:
    db = get_metadata_db()
    async with db.execute(
        """
        SELECT connection_id FROM source_bindings
        WHERE source_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (source_id,),
    ) as cur:
        row = await cur.fetchone()
    return row["connection_id"] if row is not None else None


async def append_binding(source_id: str, connection_id: str) -> None:
    """Agrega una entrada al historial, salvo que ya sea el binding vigente."""

    if await current_binding(source_id) == connection_id:
        return

    db = get_metadata_db()
    await db.execute(
        "INSERT INTO source_bindings (source_id, connection_id) VALUES (?, ?)",
        (source_id, connection_id),
    )
    await db.commit()


async def binding_history(source_id: str) -> List[str]:
    """Conexiones distintas en las que esta fuente escribió, en orden cronológico.

    Es la lista sobre la que el visor hace fan-out: cada una puede contener
    logs de la fuente aunque ya no sea el destino activo.
    """

    db = get_metadata_db()
    async with db.execute(
        """
        SELECT connection_id, MIN(id) AS first_id
        FROM source_bindings
        WHERE source_id = ?
        GROUP BY connection_id
        ORDER BY first_id
        """,
        (source_id,),
    ) as cur:
        return [row["connection_id"] for row in await cur.fetchall()]


async def all_current_bindings() -> Dict[str, str]:
    """Mapa fuente -> conexión activa. Es lo que consume StorageRouter.rebuild()."""

    db = get_metadata_db()
    async with db.execute(
        """
        SELECT b.source_id, b.connection_id
        FROM source_bindings b
        WHERE b.id = (
            SELECT MAX(b2.id) FROM source_bindings b2 WHERE b2.source_id = b.source_id
        )
        """
    ) as cur:
        return {row["source_id"]: row["connection_id"] for row in await cur.fetchall()}


async def all_binding_connection_ids() -> List[str]:
    """Todas las conexiones que aparecen en algún binding, sin repetir."""

    db = get_metadata_db()
    async with db.execute(
        """
        SELECT connection_id, MIN(id) AS first_id
        FROM source_bindings
        GROUP BY connection_id
        ORDER BY first_id
        """
    ) as cur:
        return [row["connection_id"] for row in await cur.fetchall()]


# --------------------------------------------------------------------------
# Auditoría de switches
# --------------------------------------------------------------------------


async def record_switch(
    source_id: str,
    from_connection_id: Optional[str],
    to_connection_id: str,
    status: str,
    detail: Optional[str] = None,
) -> None:
    db = get_metadata_db()
    await db.execute(
        """
        INSERT INTO switch_audit (source_id, from_connection_id, to_connection_id, status, detail)
        VALUES (?, ?, ?, ?, ?)
        """,
        (source_id, from_connection_id, to_connection_id, status, detail),
    )
    await db.commit()


async def list_switch_audit(
    source_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    db = get_metadata_db()
    async with db.execute(
        """
        SELECT id, source_id, from_connection_id, to_connection_id, status, detail, created_at
        FROM switch_audit
        WHERE (? IS NULL OR source_id = ?)
        ORDER BY id DESC
        LIMIT ?
        """,
        (source_id, source_id, limit),
    ) as cur:
        return [_row_to_dict(row) for row in await cur.fetchall()]
