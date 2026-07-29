from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import anyio
import pymssql  # type: ignore

from app.models import Estado, LogRecord, LogStep, ParentType, StepType
from app.storage.base import LogFilters


class SqlServerAdapter:
    """Adapter de LogRepository para SQL Server.

    pymssql es una librería sincrónica (bloqueante), así que cada método
    público async delega el trabajo real a un thread worker vía
    ``anyio.to_thread.run_sync``. La conexión se crea de forma perezosa y se
    reutiliza entre llamadas; como pymssql no es thread-safe para uso
    concurrente sobre la misma conexión, el acceso se serializa con un lock.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        login_timeout: int = 10,
        timeout: int = 30,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._login_timeout = login_timeout
        self._timeout = timeout
        self._conn: Optional["pymssql.Connection"] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Conexión                                                          #
    # ------------------------------------------------------------------ #
    def _get_conn_sync(self) -> "pymssql.Connection":
        if self._conn is None:
            self._conn = pymssql.connect(
                server=self._host,
                port=str(self._port),
                user=self._user,
                password=self._password,
                database=self._database,
                login_timeout=self._login_timeout,
                timeout=self._timeout,
                autocommit=False,
            )
        return self._conn

    def _close_sync(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    async def close(self) -> None:
        await anyio.to_thread.run_sync(self._close_sync)

    # ------------------------------------------------------------------ #
    # ensure_schema                                                     #
    # ------------------------------------------------------------------ #
    def _ensure_schema_sync(self) -> None:
        with self._lock:
            conn = self._get_conn_sync()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    IF OBJECT_ID(N'dbo.logs', N'U') IS NULL
                    BEGIN
                        CREATE TABLE dbo.logs (
                            id CHAR(26) NOT NULL PRIMARY KEY,
                            source_id VARCHAR(64) NOT NULL,
                            parent_type VARCHAR(16) NOT NULL,
                            entrada NVARCHAR(MAX) NOT NULL,
                            resultado NVARCHAR(MAX) NOT NULL,
                            metodo VARCHAR(16) NOT NULL,
                            tiempo_ms INT NOT NULL DEFAULT 0,
                            estado VARCHAR(8) NOT NULL,
                            fecha DATETIME2(3) NOT NULL,
                            created_at DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
                        )
                    END
                    """
                )
                cur.execute(
                    """
                    IF OBJECT_ID(N'dbo.log_steps', N'U') IS NULL
                    BEGIN
                        CREATE TABLE dbo.log_steps (
                            log_id CHAR(26) NOT NULL,
                            orden INT NOT NULL,
                            tipo VARCHAR(16) NOT NULL,
                            contenido NVARCHAR(MAX) NOT NULL,
                            duration_ms INT NULL,
                            CONSTRAINT pk_log_steps PRIMARY KEY (log_id, orden),
                            CONSTRAINT fk_log_steps_log
                                FOREIGN KEY (log_id) REFERENCES dbo.logs(id)
                                ON DELETE CASCADE
                        )
                    END
                    """
                )
                cur.execute(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM sys.indexes
                        WHERE name = 'idx_logs_source_fecha'
                          AND object_id = OBJECT_ID('dbo.logs')
                    )
                        CREATE INDEX idx_logs_source_fecha ON dbo.logs(source_id, fecha)
                    """
                )
                cur.execute(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM sys.indexes
                        WHERE name = 'idx_logs_estado'
                          AND object_id = OBJECT_ID('dbo.logs')
                    )
                        CREATE INDEX idx_logs_estado ON dbo.logs(estado)
                    """
                )
                cur.execute(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM sys.indexes
                        WHERE name = 'idx_logs_metodo'
                          AND object_id = OBJECT_ID('dbo.logs')
                    )
                        CREATE INDEX idx_logs_metodo ON dbo.logs(metodo)
                    """
                )
            conn.commit()

    async def ensure_schema(self) -> None:
        await anyio.to_thread.run_sync(self._ensure_schema_sync)

    # ------------------------------------------------------------------ #
    # ping                                                              #
    # ------------------------------------------------------------------ #
    def _ping_sync(self) -> bool:
        with self._lock:
            conn = self._get_conn_sync()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True

    async def ping(self) -> bool:
        return await anyio.to_thread.run_sync(self._ping_sync)

    # ------------------------------------------------------------------ #
    # save                                                              #
    # ------------------------------------------------------------------ #
    def _save_sync(self, record: LogRecord) -> None:
        with self._lock:
            conn = self._get_conn_sync()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dbo.logs (
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
                    cur.executemany(
                        """
                        INSERT INTO dbo.log_steps (log_id, orden, tipo, contenido, duration_ms)
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
            conn.commit()

    async def save(self, record: LogRecord) -> None:
        await anyio.to_thread.run_sync(self._save_sync, record)

    # ------------------------------------------------------------------ #
    # query                                                             #
    # ------------------------------------------------------------------ #
    def _query_sync(self, filters: LogFilters) -> List[LogRecord]:
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

        with self._lock:
            conn = self._get_conn_sync()
            with conn.cursor(as_dict=True) as cur:
                cur.execute(
                    f"""
                    SELECT id, source_id, parent_type, entrada, resultado,
                           metodo, tiempo_ms, estado, fecha
                    FROM dbo.logs
                    {where_sql}
                    ORDER BY fecha DESC
                    OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
                    """,
                    (*params, filters.offset, filters.limit),
                )
                log_rows = cur.fetchall()

                if not log_rows:
                    return []

                log_ids = [row["id"] for row in log_rows]
                placeholders = ", ".join(["%s"] * len(log_ids))
                cur.execute(
                    f"""
                    SELECT log_id, orden, tipo, contenido, duration_ms
                    FROM dbo.log_steps
                    WHERE log_id IN ({placeholders})
                    ORDER BY log_id, orden
                    """,
                    tuple(log_ids),
                )
                step_rows = cur.fetchall()

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

    async def query(self, filters: LogFilters) -> List[LogRecord]:
        return await anyio.to_thread.run_sync(self._query_sync, filters)

    # ------------------------------------------------------------------ #
    # get                                                               #
    # ------------------------------------------------------------------ #
    def _get_sync(self, log_id: str) -> Optional[LogRecord]:
        with self._lock:
            conn = self._get_conn_sync()
            with conn.cursor(as_dict=True) as cur:
                cur.execute(
                    """
                    SELECT id, source_id, parent_type, entrada, resultado,
                           metodo, tiempo_ms, estado, fecha
                    FROM dbo.logs
                    WHERE id = %s
                    """,
                    (log_id,),
                )
                log_row = cur.fetchone()
                if log_row is None:
                    return None

                cur.execute(
                    """
                    SELECT log_id, orden, tipo, contenido, duration_ms
                    FROM dbo.log_steps
                    WHERE log_id = %s
                    ORDER BY orden
                    """,
                    (log_id,),
                )
                step_rows = cur.fetchall()

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

    async def get(self, log_id: str) -> Optional[LogRecord]:
        return await anyio.to_thread.run_sync(self._get_sync, log_id)

    # ------------------------------------------------------------------ #
    # helpers                                                           #
    # ------------------------------------------------------------------ #
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
