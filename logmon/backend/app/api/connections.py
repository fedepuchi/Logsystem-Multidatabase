from uuid import uuid4

from fastapi import (
    APIRouter,
    HTTPException,
    Response,
    status,
)

from app.api.state import CONNECTIONS, SOURCES
from app.models import ConnectionIn


router = APIRouter(
    prefix="/api/connections",
    tags=["Connections"],
)


def _public_connection(
    connection: dict,
) -> dict:
    """
    Elimina la contraseña antes de devolver
    la conexión al frontend.
    """

    return {
        key: value
        for key, value in connection.items()
        if key != "password"
    }


def _get_connection_or_404(
    connection_id: str,
) -> dict:
    connection = CONNECTIONS.get(connection_id)

    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conexión no encontrada",
        )

    return connection


@router.get("")
async def list_connections() -> list[dict]:
    return [
        _public_connection(connection)
        for connection in CONNECTIONS.values()
    ]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_connection(
    connection: ConnectionIn,
) -> dict:
    normalized_name = connection.name.strip()

    if not normalized_name:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "El nombre de la conexión "
                "es obligatorio"
            ),
        )

    repeated_name = any(
        current["name"].casefold()
        == normalized_name.casefold()
        for current in CONNECTIONS.values()
    )

    if repeated_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Ya existe una conexión "
                "con ese nombre"
            ),
        )

    connection_id = (
        f"C{uuid4().hex[:8].upper()}"
    )

    created = {
        "id": connection_id,
        "name": normalized_name,
        "engine": (
            connection.engine
            .strip()
            .lower()
        ),
        "host": connection.host.strip(),
        "port": connection.port,
        "user": connection.user.strip(),
        "password": connection.password,
        "database": connection.database.strip(),
    }

    CONNECTIONS[connection_id] = created

    return _public_connection(created)


@router.get("/{connection_id}")
async def get_connection(
    connection_id: str,
) -> dict:
    connection = _get_connection_or_404(
        connection_id
    )

    return _public_connection(connection)


@router.put("/{connection_id}")
async def update_connection(
    connection_id: str,
    connection: ConnectionIn,
) -> dict:
    _get_connection_or_404(connection_id)

    normalized_name = connection.name.strip()

    repeated_name = any(
        current_id != connection_id
        and current["name"].casefold()
        == normalized_name.casefold()
        for current_id, current
        in CONNECTIONS.items()
    )

    if repeated_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Ya existe una conexión "
                "con ese nombre"
            ),
        )

    updated = {
        "id": connection_id,
        "name": normalized_name,
        "engine": (
            connection.engine
            .strip()
            .lower()
        ),
        "host": connection.host.strip(),
        "port": connection.port,
        "user": connection.user.strip(),
        "password": connection.password,
        "database": connection.database.strip(),
    }

    CONNECTIONS[connection_id] = updated

    return _public_connection(updated)


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_connection(
    connection_id: str,
) -> Response:
    _get_connection_or_404(connection_id)

    connection_in_use = any(
        source.get("connection_id")
        == connection_id
        for source in SOURCES.values()
    )

    if connection_in_use:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "La conexión está asignada "
                "a una fuente y no puede eliminarse"
            ),
        )

    del CONNECTIONS[connection_id]

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )


@router.post("/{connection_id}/test")
async def test_connection(
    connection_id: str,
) -> dict:
    _get_connection_or_404(connection_id)


    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "La prueba real de conexión queda "
            "pendiente de integrar con el registry "
            "de adapters de la capa storage."
        ),
    )