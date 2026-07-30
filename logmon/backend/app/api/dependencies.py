from importlib import import_module
from typing import Any

from fastapi import HTTPException, status


def get_storage_router() -> Any:
    """
    Obtiene el router de almacenamiento sin impedir
    que FastAPI arranque.

    El módulo app.storage.router pertenece a la capa
    de almacenamiento.
    """

    try:
        module = import_module("app.storage.router")

    except ModuleNotFoundError as exc:
        if exc.name != "app.storage.router":
            raise

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "El router de almacenamiento todavía "
                "no está disponible."
            ),
        ) from exc

    storage_router = getattr(
        module,
        "storage_router",
        None,
    )

    if storage_router is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "app.storage.router no exporta "
                "storage_router."
            ),
        )

    return storage_router