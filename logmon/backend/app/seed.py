from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from models import ConnectionIn, LogRecord, LogStep, ParentType, SourceIn, StepType

try:
    from ids import new_ulid
except ImportError:
    def new_ulid() -> str:
        return uuid.uuid4().hex[:26].upper()


DEMO_CONNECTIONS = [
    {
        "connection_id": "C1",
        "data": ConnectionIn(
            name="C1 MariaDB",
            engine="mariadb",
            host="mariadb",
            port=3306,
            user="logmon",
            password="logmon",
            database="logmon",
        ),
    },
    {
        "connection_id": "C2",
        "data": ConnectionIn(
            name="C2 PostgreSQL",
            engine="postgres",
            host="postgres",
            port=5432,
            user="logmon",
            password="logmon",
            database="logmon",
        ),
    },
    {
        "connection_id": "C3",
        "data": ConnectionIn(
            name="C3 SQL Server",
            engine="sqlserver",
            host="sqlserver",
            port=1433,
            user="sa",
            password="YourStrong!Passw0rd",
            database="logmon",
        ),
    },
    {
        "connection_id": "C4",
        "data": ConnectionIn(
            name="C4 MongoDB",
            engine="mongo",
            host="mongo",
            port=27017,
            user="logmon",
            password="logmon",
            database="logmon",
        ),
    },
    {
        "connection_id": "C5",
        "data": ConnectionIn(
            name="C5 Redis",
            engine="redis",
            host="redis",
            port=6379,
            user="",
            password="logmon",
            database="0",
        ),
    },
]


DEMO_SOURCES = [
    {
        "source_id": "APP1",
        "data": SourceIn(
            name="APP1",
            parent_type=ParentType.API,
        ),
    },
    {
        "source_id": "APP2",
        "data": SourceIn(
            name="APP2",
            parent_type=ParentType.WEB,
        ),
    },
    {
        "source_id": "SIS3",
        "data": SourceIn(
            name="SIS3",
            parent_type=ParentType.SISTEMA,
        ),
    },
]


DEMO_BINDINGS = [
    {
        "source_id": "APP1",
        "connection_id": "C3",
    },
    {
        "source_id": "APP2",
        "connection_id": "C2",
    },
    {
        "source_id": "SIS3",
        "connection_id": "C1",
    },
]


def build_demo_logs():
    now = datetime.now(timezone.utc)

    return [
    LogRecord(
        id=new_ulid(),
        source_id="APP1",
        parent_type=ParentType.API,
        entrada="POST /orders",
        resultado="Orden creada correctamente",
        metodo="POST",
        fecha=now,
        steps=[
            LogStep(
                orden=1,
                tipo=StepType.ENTRADA,
                contenido="Solicitud recibida para crear orden",
                duration_ms=120,
            ),
            LogStep(
                orden=2,
                tipo=StepType.SALIDA,
                contenido="Orden registrada en base de datos",
                duration_ms=240,
            ),
        ],
    ),
    LogRecord(
        id=new_ulid(),
        source_id="APP1",
        parent_type=ParentType.API,
        entrada="POST /orders",
        resultado="Error al crear orden",
        metodo="POST",
        fecha=now,
        steps=[
            LogStep(
                orden=1,
                tipo=StepType.ENTRADA,
                contenido="Solicitud recibida para crear orden",
                duration_ms=100,
            ),
            LogStep(
                orden=2,
                tipo=StepType.ERROR,
                contenido="DB timeout 3000ms",
                duration_ms=3000,
            ),
        ],
    ),
    LogRecord(
        id=new_ulid(),
        source_id="APP2",
        parent_type=ParentType.WEB,
        entrada="GET /users",
        resultado="Usuarios consultados correctamente",
        metodo="GET",
        fecha=now,
        steps=[
            LogStep(
                orden=1,
                tipo=StepType.ENTRADA,
                contenido="Solicitud recibida desde interfaz web",
                duration_ms=80,
            ),
            LogStep(
                orden=2,
                tipo=StepType.SALIDA,
                contenido="Listado de usuarios enviado",
                duration_ms=150,
            ),
        ],
    ),
    LogRecord(
        id=new_ulid(),
        source_id="APP2",
        parent_type=ParentType.WEB,
        entrada="GET /dashboard",
        resultado="Error cargando dashboard",
        metodo="GET",
        fecha=now,
        steps=[
            LogStep(
                orden=1,
                tipo=StepType.ENTRADA,
                contenido="Solicitud de dashboard recibida",
                duration_ms=90,
            ),
            LogStep(
                orden=2,
                tipo=StepType.ERROR,
                contenido="Servicio externo no respondio",
                duration_ms=1800,
            ),
        ],
    ),
    LogRecord(
        id=new_ulid(),
        source_id="SIS3",
        parent_type=ParentType.SISTEMA,
        entrada="SYSTEM healthcheck",
        resultado="Sistema operativo correctamente",
        metodo="JOB",
        fecha=now,
        steps=[
            LogStep(
                orden=1,
                tipo=StepType.ENTRADA,
                contenido="Inicio de verificacion automatica",
                duration_ms=50,
            ),
            LogStep(
                orden=2,
                tipo=StepType.SALIDA,
                contenido="Verificacion completada sin errores",
                duration_ms=100,
            ),
        ],
    ),
    LogRecord(
        id=new_ulid(),
        source_id="SIS3",
        parent_type=ParentType.SISTEMA,
        entrada="SYSTEM backup",
        resultado="Error ejecutando respaldo",
        metodo="JOB",
        fecha=now,
        steps=[
            LogStep(
                orden=1,
                tipo=StepType.ENTRADA,
                contenido="Inicio de tarea de respaldo",
                duration_ms=70,
            ),
            LogStep(
                orden=2,
                tipo=StepType.ERROR,
                contenido="Espacio insuficiente en disco",
                duration_ms=2200,
            ),
        ],
    ),
]


async def seed_demo_data() -> None:
    demo_logs = build_demo_logs()

    print("Conexiones demo:")
    for connection in DEMO_CONNECTIONS:
        data = connection["data"]
        print(connection["connection_id"], data.name, data.engine)

    print("Fuentes demo:")
    for source in DEMO_SOURCES:
        data = source["data"]
        print(source["source_id"], data.name, data.parent_type.value)

    print("Asignaciones demo:")
    for binding in DEMO_BINDINGS:
        print(binding["source_id"], "->", binding["connection_id"])

    print("Logs demo:")
    for log in demo_logs:
        print(log.source_id, log.metodo, log.entrada, log.estado.value, log.tiempo_ms)


if __name__ == "__main__":
    asyncio.run(seed_demo_data())