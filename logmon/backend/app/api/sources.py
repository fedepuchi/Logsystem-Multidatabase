from fastapi import APIRouter, HTTPException
from app.models import SourceIn, SwitchIn

router = APIRouter(
    prefix="/api/sources",
    tags=["Sources"]
)

sources = [
    {
        "name":"APP1",
        "parent_type":"API",
        "connection_id":"C1"
    }
]

@router.post("/{source}/switch")
async def switch_source(
    source: str,
    switch: SwitchIn
):

    for current in sources:

        if current["name"] == source:

            current["connection_id"] = switch.connection_id

            return {
                "message":"Cambio realizado",
                "source": current
            }

    raise HTTPException(
        status_code=404,
        detail="Fuente no encontrada"
    )

@router.get("")
async def list_sources():
    return sources 

@router.post("")
async def create_source(source: SourceIn):

    nueva = {
        "name": source.name,
        "parent_type": source.parent_type,
        "connection_id": None
    }

    sources.append(nueva)

    return nueva

@router.get("/{source}")
async def get_source(source: str):

    for current in sources:
        if current["name"] == source:
            return current

    raise HTTPException(
        status_code=404,
        detail="Fuente no encontrada"
    )

@router.delete("/{source}")
async def delete_source(source: str):

    for i, current in enumerate(sources):
        if current["name"] == source:
            sources.pop(i)
            return {"message": "Fuente eliminada"}

    raise HTTPException(
        status_code=404,
        detail="Fuente no encontrada"
    )



