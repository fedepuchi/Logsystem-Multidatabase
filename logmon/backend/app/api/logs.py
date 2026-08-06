from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import ValidationError

from app.api.auth import ensure_source_matches, require_admin, require_ingest_source
from app.api.dependencies import get_storage_router
from app.config import get_settings
from app.ids import new_ulid
from app.models import Estado, LogCreate, LogRecord, LogSummary
from app.storage.base import LogFilters, StatsFilters
from app.storage.router import StorageRouter, UnboundSourceError

# Único router con las dos superficies: POST "" es ingesta (API key de fuente) y
# el resto —visor y demo— es administración. Por eso la dependencia va por ruta
# y no colgada del router entero.
router = APIRouter(prefix="/api/logs", tags=["Logs"])


@router.post("/api/logs", status_code=status.HTTP_201_CREATED)
async def create_log(
    log: LogCreate,
    storage_router: StorageRouter = Depends(get_storage_router),
    ingest_source: Optional[str] = Depends(require_ingest_source),
) -> Dict[str, Any]:
    """Ingesta individual. El ULID lo genera el servidor."""

    ensure_source_matches(ingest_source, log.source_id)

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


@router.post("/api/logs/batch", status_code=status.HTTP_200_OK)
async def create_logs_batch(
    payloads: List[Any] = Body(...),
    storage_router: StorageRouter = Depends(get_storage_router),
) -> Dict[str, Any]:
    """Ingesta parcial por lotes.

    Cada elemento se valida por separado para que un payload inválido no haga
    que FastAPI rechace el lote completo con 422. Los válidos se envían al
    router, que toma una sola vez el lock de cada fuente.
    """

    settings = get_settings()
    if not payloads:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El lote debe contener al menos un log",
        )
    if len(payloads) > settings.logmon_batch_max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"El lote contiene {len(payloads)} elementos; "
                f"el máximo permitido es {settings.logmon_batch_max_size}"
            ),
        )

    output: List[Optional[Dict[str, Any]]] = [None] * len(payloads)
    valid_indexes: List[int] = []
    records: List[LogRecord] = []

    for index, raw_payload in enumerate(payloads):
        try:
            log = LogCreate.model_validate(raw_payload)
        except ValidationError as exc:
            output[index] = {
                "index": index,
                "success": False,
                "id": None,
                "source_id": (
                    raw_payload.get("source_id")
                    if isinstance(raw_payload, dict)
                    else None
                ),
                "connection_id": None,
                "error": str(exc),
            }
            continue

        record = log.to_record(new_ulid())
        valid_indexes.append(index)
        records.append(record)

    if records:
        saved_results = await storage_router.save_many(records)
        for input_index, record, saved in zip(valid_indexes, records, saved_results):
            output[input_index] = {
                "index": input_index,
                "success": saved.success,
                "id": record.id,
                "source_id": record.source_id,
                "connection_id": saved.connection_id,
                "estado": record.estado.value,
                "tiempo_ms": record.tiempo_ms,
                "error": saved.error,
            }

    final_items = [
        item
        if item is not None
        else {
            "index": index,
            "success": False,
            "id": None,
            "source_id": None,
            "connection_id": None,
            "error": "Resultado no generado",
        }
        for index, item in enumerate(output)
    ]
    saved_count = sum(1 for item in final_items if item["success"])

    return {
        "received": len(payloads),
        "saved": saved_count,
        "failed": len(payloads) - saved_count,
        "items": final_items,
    }


@router.get("", dependencies=[Depends(require_admin)])
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


@router.get("/api/stats")
async def get_stats(
    source: Optional[str] = None,
    fecha_inicio: Optional[datetime] = None,
    fecha_fin: Optional[datetime] = None,
    bucket_minutes: int = Query(default=60, ge=1, le=1440),
    storage_router: StorageRouter = Depends(get_storage_router),
) -> Dict[str, Any]:
    """Totales, tasa de error y volumen por franja, calculados en el backend."""

    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="fecha_inicio no puede ser posterior a fecha_fin",
        )

    return await storage_router.stats(
        StatsFilters(
            source_id=source,
            fecha_desde=fecha_inicio,
            fecha_hasta=fecha_fin,
            bucket_minutes=bucket_minutes,
        )
    )

# Esta ruta debe declararse antes de /{log_id}: de lo contrario FastAPI
# interpretaría "demo" como un id.
@router.post(
    "/demo",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
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


@router.get("/{log_id}", dependencies=[Depends(require_admin)])
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
