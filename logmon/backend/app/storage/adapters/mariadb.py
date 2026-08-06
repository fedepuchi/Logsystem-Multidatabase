from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncmy  # type: ignore
from asyncmy.cursors import DictCursor  # type: ignore

from app.models import Estado, LogRecord, LogStep, ParentType, StepType
from app.storage.base import (
    LogFilters,
    RepositoryStats,
    StatsFilters,
    aggregate_stats,
)


class MariaDbAdapter:
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
        self._pool: Optional[asyncmy.Pool] = None

    async def _get_pool(self) -> asyncmy.Pool:
        if self._pool is None:
            self._pool = await asyncmy.create_pool(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                db=self._database,
                charset="utf8mb4",
                minsize=self._pool_minsize,
                maxsize=self._pool_maxsize,
                autocommit=False,
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    async def ensure_schema(self) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS logs (
                        id CHAR(26) PRIMARY KEY,
                        source_id VARCHAR(64) NOT NULL,
                        parent_type VARCHAR(16) NOT NULL,
                        entrada TEXT NOT NULL,
                        resultado TEXT NOT NULL,
                        metodo VARCHAR(16) NOT NULL,
                        tiempo_ms INT NOT NULL DEFAULT 0,
                        estado VARCHAR(8) NOT NULL,
                        fecha DATETIME(3) NOT NULL,
                        created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
                        INDEX idx_logs_source_fecha (source_id, fecha),
                        INDEX idx_logs_estado (estado),
                        INDEX idx_logs_metodo (metodo)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS log_steps (
                        log_id CHAR(26) NOT NULL,
                        orden INT NOT NULL,
                        tipo VARCHAR(16) NOT NULL,
                        contenido TEXT NOT NULL,
                        duration_ms INT NULL,
                        PRIMARY KEY (log_id, orden),
                        CONSTRAINT fk_log_steps_log
                            FOREIGN KEY (log_id) REFERENCES logs(id)
                            ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
            await conn.commit()

    async def ping(self) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
        return True

    async def save(self, record: LogRecord) -> None:
        error = (await self.save_many([record]))[0]
        if error is not None:
            raise RuntimeError(error)

    async def save_many(self, records: List[LogRecord]) -> List[Optional[str]]:
        if not records:
            return []

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.executemany(
                        """
                        INSERT INTO logs (
                            id, source_id, parent_type, entrada, resultado,
                            metodo, tiempo_ms, estado, fecha
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        [
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
                            )
                            for record in records
                        ],
                    )

                    steps = [
                        (
                            record.id,
                            step.orden,
                            step.tipo.value,
                            step.contenido,
                            step.duration_ms,
                        )
                        for record in records
                        for step in record.steps
                    ]
                    if steps:
                        await cur.executemany(
                            """
                            INSERT INTO log_steps
                                (log_id, orden, tipo, contenido, duration_ms)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            steps,
                        )
                await conn.commit()
            except Exception as exc:  # noqa: BLE001 - contrato de respuesta parcial
                await conn.rollback()
                error = f"{type(exc).__name__}: {exc}"
                return [error] * len(records)

        return [None] * len(records)

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

        async with pool.acquire() as conn:
            async with conn.cursor(cursor=DictCursor) as cur:
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
                placeholders = ", ".join(["%s"] * len(log_ids))
                await cur.execute(
                    f"""
                    SELECT log_id, orden, tipo, contenido, duration_ms
                    FROM log_steps
                    WHERE log_id IN ({placeholders})
                    ORDER BY log_id, orden
                    """,
                    tuple(log_ids),
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
        async with pool.acquire() as conn:
            async with conn.cursor(cursor=DictCursor) as cur:
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

    async def stats(self, filters: StatsFilters) -> RepositoryStats:
        pool = await self._get_pool()
        clauses: List[str] = []
        params: List[Any] = []
        if filters.source_id is not None:
            clauses.append("source_id = %s")
            params.append(filters.source_id)
        if filters.fecha_desde is not None:
            clauses.append("fecha >= %s")
            params.append(filters.fecha_desde)
        if filters.fecha_hasta is not None:
            clauses.append("fecha <= %s")
            params.append(filters.fecha_hasta)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        async with pool.acquire() as conn:
            async with conn.cursor(cursor=DictCursor) as cur:
                await cur.execute(
                    f"SELECT fecha, estado FROM logs {where_sql}",
                    tuple(params),
                )
                rows = await cur.fetchall()

        return aggregate_stats(
            ((row["fecha"], row["estado"]) for row in rows),
            filters.bucket_minutes,
        )

    async def delete_before(self, cutoff: datetime) -> int:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute("DELETE FROM logs WHERE fecha < %s", (cutoff,))
                    deleted = max(cur.rowcount or 0, 0)
                await conn.commit()
                return deleted
            except Exception:
                await conn.rollback()
                raise

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
