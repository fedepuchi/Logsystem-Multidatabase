"""Datos de demo según la pizarra.

Crea las conexiones C1..C5, las fuentes APP1/APP2/SIS3, sus asignaciones
(APP1→C3, APP2→C2, SIS3→C1) e inserta logs OK y ERROR con pasos coloreados.

Uso:
    python -m app.seed                  # todo
    python -m app.seed --metadata-only  # sólo conexiones, fuentes y bindings
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List

from app.config import get_settings
from app.ids import new_ulid
from app.metadata import repo
from app.metadata.db import close_metadata_db, init_metadata_db
from app.models import ConnectionIn, LogRecord, LogStep, ParentType, SourceIn, StepType
from app.storage.router import SwitchAborted, storage_router

logger = logging.getLogger(__name__)

DEMO_SOURCES = [
    SourceIn(name="APP1", parent_type=ParentType.API),
    SourceIn(name="APP2", parent_type=ParentType.WEB),
    SourceIn(name="SIS3", parent_type=ParentType.SISTEMA),
]

# Asignaciones de la pizarra.
DEMO_BINDINGS = [
    ("APP1", "C3"),
    ("APP2", "C2"),
    ("SIS3", "C1"),
]


def build_demo_logs() -> List[LogRecord]:
    """Seis logs de ejemplo: un OK y un ERROR por cada fuente.

    Las fechas se escalonan hacia atrás para que la tabla del visor no muestre
    todo con el mismo timestamp y el orden se lea con claridad.
    """

    now = datetime.now(timezone.utc)

    def at(minutes: int) -> datetime:
        return now - timedelta(minutes=minutes)

    return [
        LogRecord(
            id=new_ulid(),
            source_id="APP1",
            parent_type=ParentType.API,
            entrada="POST /orders",
            resultado="Orden creada correctamente",
            metodo="POST",
            fecha=at(25),
            steps=[
                LogStep(orden=1, tipo=StepType.ENTRADA,
                        contenido="Solicitud recibida para crear orden", duration_ms=120),
                LogStep(orden=2, tipo=StepType.SALIDA,
                        contenido="Orden registrada en base de datos", duration_ms=240),
            ],
        ),
        LogRecord(
            id=new_ulid(),
            source_id="APP1",
            parent_type=ParentType.API,
            entrada="POST /orders",
            resultado="Error al crear orden",
            metodo="POST",
            fecha=at(20),
            steps=[
                LogStep(orden=1, tipo=StepType.ENTRADA,
                        contenido="Solicitud recibida para crear orden", duration_ms=100),
                LogStep(orden=2, tipo=StepType.ERROR,
                        contenido="DB timeout 3000ms", duration_ms=3000),
            ],
        ),
        LogRecord(
            id=new_ulid(),
            source_id="APP2",
            parent_type=ParentType.WEB,
            entrada="GET /users",
            resultado="Usuarios consultados correctamente",
            metodo="GET",
            fecha=at(15),
            steps=[
                LogStep(orden=1, tipo=StepType.ENTRADA,
                        contenido="Solicitud recibida desde interfaz web", duration_ms=80),
                LogStep(orden=2, tipo=StepType.SALIDA,
                        contenido="Listado de usuarios enviado", duration_ms=150),
            ],
        ),
        LogRecord(
            id=new_ulid(),
            source_id="APP2",
            parent_type=ParentType.WEB,
            entrada="GET /dashboard",
            resultado="Error cargando dashboard",
            metodo="GET",
            fecha=at(10),
            steps=[
                LogStep(orden=1, tipo=StepType.ENTRADA,
                        contenido="Solicitud de dashboard recibida", duration_ms=90),
                LogStep(orden=2, tipo=StepType.ERROR,
                        contenido="Servicio externo no respondio", duration_ms=1800),
            ],
        ),
        LogRecord(
            id=new_ulid(),
            source_id="SIS3",
            parent_type=ParentType.SISTEMA,
            entrada="SYSTEM healthcheck",
            resultado="Sistema operativo correctamente",
            metodo="JOB",
            fecha=at(5),
            steps=[
                LogStep(orden=1, tipo=StepType.ENTRADA,
                        contenido="Inicio de verificacion automatica", duration_ms=50),
                LogStep(orden=2, tipo=StepType.SALIDA,
                        contenido="Verificacion completada sin errores", duration_ms=100),
            ],
        ),
        LogRecord(
            id=new_ulid(),
            source_id="SIS3",
            parent_type=ParentType.SISTEMA,
            entrada="SYSTEM backup",
            resultado="Error ejecutando respaldo",
            metodo="JOB",
            fecha=at(1),
            steps=[
                LogStep(orden=1, tipo=StepType.ENTRADA,
                        contenido="Inicio de tarea de respaldo", duration_ms=70),
                LogStep(orden=2, tipo=StepType.ERROR,
                        contenido="Espacio insuficiente en disco", duration_ms=2200),
            ],
        ),
    ]


async def _ensure_connections() -> None:
    settings = get_settings()

    for spec in settings.demo_connections():
        connection_id = str(spec["id"])

        if await repo.get_connection(connection_id) is not None:
            print(f"  = {connection_id} ya existía ({spec['engine']})")
            continue

        await repo.create_connection(
            ConnectionIn(
                name=str(spec["name"]),
                engine=str(spec["engine"]),
                host=str(spec["host"]),
                port=int(spec["port"]),  # type: ignore[arg-type]
                user=str(spec["user"]),
                password=str(spec["password"]),
                database=str(spec["database"]),
            ),
            connection_id=connection_id,
        )
        print(f"  + {connection_id} {spec['name']} -> {spec['host']}:{spec['port']}")


async def _ensure_sources() -> None:
    for source in DEMO_SOURCES:
        if await repo.get_source(source.name) is not None:
            print(f"  = {source.name} ya existía")
            continue
        await repo.create_source(source)
        print(f"  + {source.name} ({source.parent_type.value})")


async def _ensure_bindings() -> List[str]:
    """Asigna cada fuente a su conexión. Devuelve las fuentes efectivamente ligadas.

    Un motor caído no aborta el seed: se informa y se sigue con el resto, para
    que la demo pueda arrancar aunque SQL Server todavía esté inicializando.
    """

    bound: List[str] = []

    for source_id, connection_id in DEMO_BINDINGS:
        if await repo.current_binding(source_id) == connection_id:
            print(f"  = {source_id} -> {connection_id} (ya asignado)")
            bound.append(source_id)
            continue

        try:
            await storage_router.switch(source_id, connection_id)
        except SwitchAborted as exc:
            print(f"  ! {source_id} -> {connection_id} FALLÓ: {exc}")
            continue

        print(f"  + {source_id} -> {connection_id}")
        bound.append(source_id)

    return bound


async def _insert_demo_logs(bound: List[str]) -> int:
    insertados = 0

    for record in build_demo_logs():
        if record.source_id not in bound:
            continue
        try:
            connection_id = await storage_router.save(record)
        except Exception as exc:  # noqa: BLE001 - informamos y seguimos
            print(f"  ! log de {record.source_id} falló: {type(exc).__name__}: {exc}")
            continue
        insertados += 1
        print(
            f"  + {record.source_id} {record.metodo} {record.entrada} "
            f"[{record.estado.value}, {record.tiempo_ms}ms] -> {connection_id}"
        )

    return insertados


async def seed_demo_data(metadata_only: bool = False) -> int:
    settings = get_settings()

    await init_metadata_db(settings.sqlite_path)
    await storage_router.rebuild()

    try:
        print("Conexiones:")
        await _ensure_connections()

        print("Fuentes:")
        await _ensure_sources()

        print("Asignaciones:")
        bound = await _ensure_bindings()

        if metadata_only:
            print("\n--metadata-only: se omiten los logs de ejemplo.")
        else:
            print("Logs de ejemplo:")
            insertados = await _insert_demo_logs(bound)
            print(f"\n{insertados} log(s) insertado(s).")

        if not bound:
            print(
                "\nNinguna fuente quedó asignada: revisá que los motores estén "
                "levantados (`docker compose ps`)."
            )
            return 1

        return 0
    finally:
        await storage_router.close_all()
        await close_metadata_db()


def main() -> int:
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="Carga los datos de demo de LogMon.")
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Crea conexiones, fuentes y asignaciones, pero no inserta logs.",
    )
    args = parser.parse_args()

    return asyncio.run(seed_demo_data(metadata_only=args.metadata_only))


if __name__ == "__main__":
    raise SystemExit(main())
