from fastapi import APIRouter, HTTPException

from app.models import ConnectionIn

router = APIRouter(
    prefix="/api/connections",
    tags=["Connections"]
)

# Temporal mientras se implementa metadata/repo.py
connections = []

@router.get("")
async def list_connections():
    return connections

@router.post("")
async def create_connection(connection: ConnectionIn):

    nueva = {
        "id": f"C{len(connections)+1}",
        "name": connection.name,
        "engine": connection.engine,
        "host": connection.host,
        "port": connection.port,
        "user": connection.user,
        "database": connection.database
    }

    connections.append(nueva)

    return nueva

@router.get("/{connection_id}")
async def get_connection(connection_id: str):

    for connection in connections:
        if connection["id"] == connection_id:
            return connection

    raise HTTPException(
        status_code=404,
        detail="Conexión no encontrada"
    )

@router.put("/{connection_id}")
async def update_connection(
    connection_id: str,
    connection: ConnectionIn
):

    for index, current in enumerate(connections):

        if current["id"] == connection_id:

            connections[index] = {
                "id": connection_id,
                "name": connection.name,
                "engine": connection.engine,
                "host": connection.host,
                "port": connection.port,
                "user": connection.user,
                "database": connection.database
            }

            return connections[index]

    raise HTTPException(
        status_code=404,
        detail="Conexión no encontrada"
    )

@router.delete("/{connection_id}")
async def delete_connection(connection_id: str):

    for index, current in enumerate(connections):

        if current["id"] == connection_id:

            connections.pop(index)

            return {
                "message": "Conexión eliminada"
            }

    raise HTTPException(
        status_code=404,
        detail="Conexión no encontrada"
    )

@router.post("/{connection_id}/test")
async def test_connection(connection_id: str):

    for connection in connections:

        if connection["id"] == connection_id:

            # Aquí luego irá:
            #
            # adapter = registry.get(connection_id)
            # ok = await adapter.ping()

            return {
                "success": True,
                "message": "Conexión simulada correctamente"
            }

    raise HTTPException(
        status_code=404,
        detail="Conexión no encontrada"
    )


