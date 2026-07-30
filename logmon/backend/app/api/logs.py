from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_storage_router
from app.ids import new_ulid
from app.models import Estado, LogCreate, LogRecord, LogSummary
from app.storage.base import LogFilters
from app.storage.router import StorageRouter, UnboundSourceError

router = APIRouter(prefix="/api/logs", tags=["Logs"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_log(
    log: LogCreate,
    storage_router: StorageRouter = Depends(get_storage_router),
) -> Dict[str, Any]:
    """Ingesta. El ULID lo genera el servidor y se devuelve al cliente."""

    record = log.to_record(new_ulid())

    try:
        connection_id = await storage_router.save(record)
    except UnboundSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {
        "message": "Log guardado correctamente",
        "id": record.id,
        "connection_id": connection_id,
        "estado": record.estado.value,
        "tiempo_ms": record.tiempo_ms,
    }


@router.get("")
async def get_logs(
    source: Optional[str] = None,
    estado: Optional[Estado] = None,
    metodo: Optional[str] = None,
    fecha_inicio: Optional[datetime] = None,
    fecha_fin: Optional[datetime] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    storage_router: StorageRouter = Depends(get_storage_router),
) -> List[LogSummary]:
    """Listado con merge multi-DB.

    Cada fila viene etiquetada con el ``connection_id`` del motor donde vive,
    así que tras un switch se ven juntos los logs viejos y los nuevos.
    """

    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="fecha_inicio no puede ser posterior a fecha_fin",
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

    return await storage_router.query(filters)


# Esta ruta debe declararse antes de /{log_id}: de lo contrario FastAPI
# interpretaría "demo" como un id.
@router.post("/demo", status_code=status.HTTP_201_CREATED)
async def create_demo_logs(
    storage_router: StorageRouter = Depends(get_storage_router),
) -> Dict[str, Any]:
    try:
        result = await storage_router.create_demo_logs()
    except UnboundSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"message": "Datos creados", "result": result}


@router.get("/{log_id}")
async def get_log(
    log_id: str,
    conn: str = Query(..., min_length=1, description="connection_id del motor de origen"),
    storage_router: StorageRouter = Depends(get_storage_router),
) -> LogRecord:
    log = await storage_router.get(connection_id=conn, log_id=log_id)

    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log no encontrado",
        )

    return log
