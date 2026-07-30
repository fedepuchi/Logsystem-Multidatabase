from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from app.api.dependencies import (
    get_storage_router,
)
from app.models import Estado, LogRecord
from app.storage.base import LogFilters


router = APIRouter(
    prefix="/api/logs",
    tags=["Logs"],
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_log(
    log: LogRecord,
    storage_router=Depends(
        get_storage_router
    ),
) -> dict:
    try:
        await storage_router.save(log)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {
        "message": (
            "Log guardado correctamente"
        ),
        "id": log.id,
    }


@router.get("")
async def get_logs(
    source: str | None = None,
    estado: Estado | None = None,
    metodo: str | None = None,
    fecha_inicio: datetime | None = None,
    fecha_fin: datetime | None = None,
    limit: int = Query(
        default=100,
        ge=1,
        le=1000,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    storage_router=Depends(
        get_storage_router
    ),
) -> list[LogRecord]:
    if (
        fecha_inicio
        and fecha_fin
        and fecha_inicio > fecha_fin
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "fecha_inicio no puede ser "
                "posterior a fecha_fin"
            ),
        )

    filters = LogFilters(
        source_id=source,
        estado=estado,
        metodo=metodo,
        fecha_desde=fecha_inicio,
        fecha_hasta=fecha_fin,
        limit=limit,
        offset=offset,
    )

    return await storage_router.query(
        filters
    )


# Esta ruta debe declararse antes
# de /{log_id}.
#
# De lo contrario, FastAPI podría
# interpretar "demo" como un ID.

@router.post(
    "/demo",
    status_code=status.HTTP_201_CREATED,
)
async def create_demo_logs(
    storage_router=Depends(
        get_storage_router
    ),
) -> dict:
    create_demo = getattr(
        storage_router,
        "create_demo_logs",
        None,
    )

    if not callable(create_demo):
        raise HTTPException(
            status_code=(
                status.HTTP_501_NOT_IMPLEMENTED
            ),
            detail=(
                "storage_router debe implementar "
                "create_demo_logs()"
            ),
        )

    result = create_demo()

    if hasattr(result, "__await__"):
        result = await result

    return {
        "message": "Datos creados",
        "result": result,
    }


@router.get("/{log_id}")
async def get_log(
    log_id: str,
    conn: str = Query(
        ...,
        min_length=1,
    ),
    storage_router=Depends(
        get_storage_router
    ),
) -> LogRecord:
    log = await storage_router.get(
        connection_id=conn,
        log_id=log_id,
    )

    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log no encontrado",
        )

    return log