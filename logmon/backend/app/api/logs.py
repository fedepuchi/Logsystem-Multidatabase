from fastapi import APIRouter, HTTPException
from app.models import LogRecord
from app.storage.base import LogFilters
from app.storage.router import storage_router

router = APIRouter(
    prefix="/api/logs",
    tags=["Logs"]
)

@router.post("")
async def create_log(log: LogRecord):

    await storage_router.save(log)

    return {
        "message": "Log guardado correctamente"
    }

@router.get("")
async def get_logs(
    source: str | None = None,
    estado: str | None = None,
    metodo: str | None = None,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None
):
    filters = LogFilters(
    source=source,
    estado=estado,
    metodo=metodo,
    fecha_inicio=fecha_inicio,
    fecha_fin=fecha_fin
)
    return await storage_router.query(filters)

@router.get("/{id}")
async def get_log(
    id: str,
    conn: str
):
    log = await storage_router.get(
    connection_id=conn,
    log_id=id
)
    raise HTTPException(
    status_code=404,
    detail="Log no encontrado"
)

@router.post("/demo")
async def demo():
    await storage_router.create_demo_logs()

    return {
        "message":"Datos creados"
    }

