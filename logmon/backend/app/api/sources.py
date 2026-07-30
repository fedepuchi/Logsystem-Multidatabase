from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)

from app.api.dependencies import (
    get_storage_router,
)
from app.api.state import (
    CONNECTIONS,
    SOURCES,
)
from app.models import SourceIn, SwitchIn


router = APIRouter(
    prefix="/api/sources",
    tags=["Sources"],
)


def _get_source_or_404(
    source_name: str,
) -> dict:
    source = SOURCES.get(source_name)

    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fuente no encontrada",
        )

    return source


@router.get("")
async def list_sources() -> list[dict]:
    return list(SOURCES.values())


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_source(
    source: SourceIn,
) -> dict:
    source_name = source.name.strip()

    if not source_name:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "El nombre de la fuente "
                "es obligatorio"
            ),
        )

    if source_name in SOURCES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Ya existe una fuente "
                "con ese nombre"
            ),
        )

    created = {
        "name": source_name,
        "parent_type": source.parent_type,
        "connection_id": None,
    }

    SOURCES[source_name] = created

    return created


@router.get("/{source_name}")
async def get_source(
    source_name: str,
) -> dict:
    return _get_source_or_404(source_name)


@router.post("/{source_name}/switch")
async def switch_source(
    source_name: str,
    switch: SwitchIn,
    storage_router=Depends(
        get_storage_router
    ),
) -> dict:
    source = _get_source_or_404(
        source_name
    )

    if switch.connection_id not in CONNECTIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conexión no encontrada",
        )

    bind_source = getattr(
        storage_router,
        "bind_source",
        None,
    )

    if not callable(bind_source):
        raise HTTPException(
            status_code=(
                status.HTTP_501_NOT_IMPLEMENTED
            ),
            detail=(
                "storage_router debe implementar "
                "bind_source(source_id, connection_id)"
            ),
        )

    try:
        result = bind_source(
            source_name,
            switch.connection_id,
        )

        if hasattr(result, "__await__"):
            await result

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    source["connection_id"] = (
        switch.connection_id
    )

    return {
        "message": "Cambio realizado",
        "source": source,
    }


@router.delete(
    "/{source_name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_source(
    source_name: str,
) -> Response:
    _get_source_or_404(source_name)

    del SOURCES[source_name]

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )