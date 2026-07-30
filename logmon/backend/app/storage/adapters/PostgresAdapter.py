from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, List, Optional

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.models import Estado, LogRecord, LogStep, ParentType, StepType
from app.storage.base import LogFilters


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS logs (
    id          CHAR(26)     PRIMARY KEY,
    source_id   VARCHAR(64)  NOT NULL,
    parent_type VARCHAR(16)  NOT NULL,
    entrada     TEXT         NOT NULL,
    resultado   TEXT         NOT NULL,
    metodo      VARCHAR(16)  NOT NULL,
    tiempo_ms   INT          NOT NULL DEFAULT 0,
    estado      VARCHAR(8)   NOT NULL,
    fecha       TIMESTAMPTZ  NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS log_steps (
    log_id      CHAR(26) NOT NULL REFERENCES logs(id) ON DELETE CASCADE,
    orden       INT      NOT NULL,
    tipo        VARCHAR(16) NOT NULL,
    contenido   TEXT     NOT NULL,
    duration_ms INT      NULL,
    PRIMARY KEY (log_id, orden)
);

CREATE INDEX IF NOT EXISTS idx_logs_source_fecha ON logs (source_id, fecha);
CREATE INDEX IF NOT EXISTS idx_logs_estado        ON logs (estado);
CREATE INDEX IF NOT EXISTS idx_logs_metodo         ON logs (metodo);
"""


class PostgresAdapter:

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        pool_minsize: int = 1,
        pool_maxsize: int = 10,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._pool_minsize = pool_minsize
        self._pool_maxsize = pool_maxsize
        self._pool: Optional[AsyncConnectionPool] = None

    def _dsn(self) -> str:
        return (
            f"postgresql://{self._user}:{self._password}"
            f"@{self._host}:{self._port}/{self._database}"
        )

    async def _get_pool(self) -> AsyncConnectionPool:
        if self._pool is None:
            self._pool = AsyncConnectionPool(
                conninfo=self._dsn(),
                min_size=self._pool_minsize,
                max_size=self._pool_maxsize,
                open=False,
                kwargs={"row_factory": dict_row},
            )
            await self._pool.open(wait=True)
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def ensure_schema(self) -> None:
        pool = await self._get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(SCHEMA_SQL)
            await conn.commit()

    async def ping(self) -> bool:
        pool = await self._get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
        return True

    async def save(self, record: LogRecord) -> None:
        pool = await self._get_pool()
        async with pool.connection() as conn:
            async with conn.transaction():  
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO logs (
                            id, source_id, parent_type, entrada, resultado,
                            metodo, tiempo_ms, estado, fecha
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            record.id,
                            record.source_id,
                            record.parent_type.value,
                            record.entrada,
                            record.resultado,
                            record.metodo,
                            record.tiempo_ms,
                            record.estado.value,
                            record.fecha,
                        ),
                    )
                    if record.steps:
                        await cur.executemany(
                            """
                            INSERT INTO log_steps (log_id, orden, tipo, contenido, duration_ms)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            [
                                (
                                    record.id,
                                    step.orden,
                                    step.tipo.value,
                                    step.contenido,
                                    step.duration_ms,
                                )
                                for step in record.steps
                            ],
                        )

    async def query(self, filters: LogFilters) -> List[LogRecord]:
        pool = await self._get_pool()
        clauses: List[str] = []
        params: List[Any] = []

        if filters.source_id is not None:
            clauses.append("source_id = %s")
            params.append(filters.source_id)
        if filters.estado is not None:
            clauses.append("estado = %s")
            params.append(filters.estado.value)
        if filters.metodo is not None:
            clauses.append("metodo = %s")
            params.append(filters.metodo)
        if filters.fecha_desde is not None:
            clauses.append("fecha >= %s")
            params.append(filters.fecha_desde)
        if filters.fecha_hasta is not None:
            clauses.append("fecha <= %s")
            params.append(filters.fecha_hasta)

    
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    SELECT id, source_id, parent_type, entrada, resultado,
                           metodo, tiempo_ms, estado, fecha
                    FROM logs
                    {where_sql}
                    ORDER BY fecha DESC
                    LIMIT %s OFFSET %s
                    """,
                    (*params, filters.limit, filters.offset),
                )
                log_rows = await cur.fetchall()

                if not log_rows:
                    return []

                log_ids = [row["id"] for row in log_rows]
                await cur.execute(
                    """
                    SELECT log_id, orden, tipo, contenido, duration_ms
                    FROM log_steps
                    WHERE log_id = ANY(%s)
                    ORDER BY log_id, orden
                    """,
                    (log_ids,),
                )
                step_rows = await cur.fetchall()

        steps_by_log: Dict[str, List[LogStep]] = {}
        for row in step_rows:
            steps_by_log.setdefault(row["log_id"], []).append(
                LogStep(
                    orden=row["orden"],
                    tipo=StepType(row["tipo"]),
                    contenido=row["contenido"],
                    duration_ms=row["duration_ms"],
                )
            )

        return [self._row_to_record(row, steps_by_log.get(row["id"], [])) for row in log_rows]

    async def get(self, log_id: str) -> Optional[LogRecord]:
        pool = await self._get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, source_id, parent_type, entrada, resultado,
                           metodo, tiempo_ms, estado, fecha
                    FROM logs
                    WHERE id = %s
                    """,
                    (log_id,),
                )
                log_row = await cur.fetchone()
                if log_row is None:
                    return None

                await cur.execute(
                    """
                    SELECT log_id, orden, tipo, contenido, duration_ms
                    FROM log_steps
                    WHERE log_id = %s
                    ORDER BY orden
                    """,
                    (log_id,),
                )
                step_rows = await cur.fetchall()

        steps = [
            LogStep(
                orden=row["orden"],
                tipo=StepType(row["tipo"]),
                contenido=row["contenido"],
                duration_ms=row["duration_ms"],
            )
            for row in step_rows
        ]
        return self._row_to_record(log_row, steps)

    @staticmethod
    def _row_to_record(row: Dict[str, Any], steps: List[LogStep]) -> LogRecord:
        fecha = row["fecha"]
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        return LogRecord(
            id=row["id"],
            source_id=row["source_id"],
            parent_type=ParentType(row["parent_type"]),
            entrada=row["entrada"],
            resultado=row["resultado"],
            metodo=row["metodo"],
            tiempo_ms=row["tiempo_ms"],
            estado=Estado(row["estado"]),
            fecha=fecha,
            steps=steps,
        )

        