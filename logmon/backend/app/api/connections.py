from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_storage_router
from app.metadata import repo
from app.models import ConnectionIn
from app.storage.router import StorageRouter

router = APIRouter(prefix="/api/connections", tags=["Connections"])


def _public_connection(connection: Dict[str, Any]) -> Dict[str, Any]:
    """Elimina la contraseña antes de devolver la conexión al frontend."""

    return {key: value for key, value in connection.items() if key != "password"}


async def _get_connection_or_404(connection_id: str) -> Dict[str, Any]:
    connection = await repo.get_connection(connection_id)

    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conexión no encontrada",
        )

    return connection


def _require_name(connection: ConnectionIn) -> str:
    name = connection.name.strip()

    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El nombre de la conexión es obligatorio",
        )

    return name


@router.get("")
async def list_connections() -> List[Dict[str, Any]]:
    return [_public_connection(connection) for connection in await repo.list_connections()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_connection(connection: ConnectionIn) -> Dict[str, Any]:
    name = _require_name(connection)

    if await repo.connection_name_exists(name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una conexión con ese nombre",
        )

    created = await repo.create_connection(connection)
    return _public_connection(created)


@router.get("/{connection_id}")
async def get_connection(connection_id: str) -> Dict[str, Any]:
    return _public_connection(await _get_connection_or_404(connection_id))


@router.put("/{connection_id}")
async def update_connection(
    connection_id: str,
    connection: ConnectionIn,
    storage_router: StorageRouter = Depends(get_storage_router),
) -> Dict[str, Any]:
    await _get_connection_or_404(connection_id)
    name = _require_name(connection)

    if await repo.connection_name_exists(name, exclude_id=connection_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una conexión con ese nombre",
        )

    updated = await repo.update_connection(connection_id, connection)

    # El pool cacheado quedó con las credenciales viejas: se descarta para que
    # la próxima escritura lo reabra con los datos nuevos.
    await storage_router.registry.forget(connection_id)

    return _public_connection(updated)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: str,
    storage_router: StorageRouter = Depends(get_storage_router),
) -> Response:
    await _get_connection_or_404(connection_id)

    if await repo.connection_has_bindings(connection_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "La conexión tiene logs asociados en el historial de alguna fuente "
                "y no puede eliminarse sin perder su rastro en el visor"
            ),
        )

    await storage_router.registry.forget(connection_id)
    await repo.delete_connection(connection_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{connection_id}/test")
async def test_connection(
    connection_id: str,
    storage_router: StorageRouter = Depends(get_storage_router),
) -> Dict[str, Any]:
    """Abre el adapter y hace ping. Siempre responde 200 con un flag success.

    Un motor caído no es un error de la API: es justo el resultado que el
    usuario quiere ver en el formulario de conexión.
    """

    await _get_connection_or_404(connection_id)

    try:
        adapter = await storage_router.registry.get(connection_id)
        alive = await adapter.ping()
    except Exception as exc:  # noqa: BLE001 - el fallo es el resultado
        return {"success": False, "message": f"{type(exc).__name__}: {exc}"}

    if not alive:
        return {"success": False, "message": "El motor respondió, pero el ping devolvió False"}

    return {"success": True, "message": f"Conexión {connection_id} OK"}
