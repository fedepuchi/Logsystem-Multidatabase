from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.auth import require_admin
from app.api.dependencies import get_storage_router
from app.metadata import repo
from app.models import ApiKey, ApiKeyCreated, ApiKeyIn, SourceIn, SwitchIn
from app.security import generate_api_key, hash_api_key, key_preview
from app.storage.router import StorageRouter, SwitchAborted

# Todo lo de fuentes es administración, incluida la emisión de las API keys con
# las que después ingestan las aplicaciones.
router = APIRouter(
    prefix="/api/sources",
    tags=["Sources"],
    dependencies=[Depends(require_admin)],
)


async def _get_source_or_404(source_name: str) -> Dict[str, Any]:
    source = await repo.get_source(source_name)

    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fuente no encontrada",
        )

    return source


@router.get("")
async def list_sources() -> List[Dict[str, Any]]:
    return await repo.list_sources()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_source(source: SourceIn) -> Dict[str, Any]:
    source_name = source.name.strip()

    if not source_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El nombre de la fuente es obligatorio",
        )

    if await repo.get_source(source_name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una fuente con ese nombre",
        )

    return await repo.create_source(source)


@router.get("/{source_name}")
async def get_source(source_name: str) -> Dict[str, Any]:
    return await _get_source_or_404(source_name)


@router.get("/{source_name}/history")
async def get_source_history(source_name: str) -> Dict[str, Any]:
    """Conexiones por las que pasó la fuente + auditoría de sus switches.

    Es lo que respalda el visor multi-DB: sobre estas conexiones se hace el
    fan-out de lectura.
    """

    await _get_source_or_404(source_name)

    return {
        "source": source_name,
        "connections": await repo.binding_history(source_name),
        "audit": await repo.list_switch_audit(source_name),
    }


@router.post("/{source_name}/switch")
async def switch_source(
    source_name: str,
    switch: SwitchIn,
    storage_router: StorageRouter = Depends(get_storage_router),
) -> Dict[str, Any]:
    await _get_source_or_404(source_name)

    if await repo.get_connection(switch.connection_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conexión no encontrada",
        )

    try:
        result = await storage_router.switch(source_name, switch.connection_id)
    except SwitchAborted as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return {
        "message": (
            f"{source_name} ahora escribe en {result['to_connection_id']}"
        ),
        "source": await repo.get_source(source_name),
        "switch": result,
    }


@router.delete("/{source_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_name: str,
    force: bool = Query(
        default=False,
        description="Borra la fuente aunque tenga historial de bindings",
    ),
) -> Response:
    await _get_source_or_404(source_name)

    history = await repo.binding_history(source_name)
    if history and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"La fuente escribió en {', '.join(history)}. "
                "Borrarla oculta esos logs del visor; repetí con ?force=true si es lo que querés."
            ),
        )

    await repo.delete_source(source_name)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# API keys de ingesta
# --------------------------------------------------------------------------


@router.get("/{source_name}/keys")
async def list_source_keys(source_name: str) -> List[ApiKey]:
    """Keys emitidas para la fuente, vigentes y revocadas.

    El secreto no está: de cada key sólo se guardó el hash, así que acá viaja
    el preview (los primeros caracteres) que alcanza para identificarla.
    """

    await _get_source_or_404(source_name)

    return [ApiKey(**key) for key in await repo.list_api_keys(source_name)]


@router.post("/{source_name}/keys", status_code=status.HTTP_201_CREATED)
async def create_source_key(source_name: str, payload: ApiKeyIn) -> ApiKeyCreated:
    """Emite una key nueva para la fuente.

    Es la única respuesta donde el secreto viaja en texto plano: después ya no
    se puede recuperar, sólo revocar y emitir otra. Una fuente puede tener
    varias keys vivas a la vez, que es lo que permite rotarlas sin cortar la
    ingesta: se emite la nueva, se despliega, y recién ahí se revoca la vieja.
    """

    await _get_source_or_404(source_name)

    api_key = generate_api_key()
    created = await repo.create_api_key(
        source_id=source_name,
        name=payload.name.strip(),
        key_hash=hash_api_key(api_key),
        preview=key_preview(api_key),
    )

    return ApiKeyCreated(**created, api_key=api_key)


@router.delete("/{source_name}/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_source_key(source_name: str, key_id: str) -> Response:
    """Revoca la key. La fila queda para poder auditar hasta cuándo se usó."""

    await _get_source_or_404(source_name)

    key = await repo.get_api_key(key_id)

    # La comprobación de pertenencia evita que el id de una key de otra fuente
    # se revoque desde la URL equivocada, aunque hoy quien llega acá ya es admin.
    if key is None or key["source_id"] != source_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key no encontrada para esta fuente",
        )

    await repo.revoke_api_key(key_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
