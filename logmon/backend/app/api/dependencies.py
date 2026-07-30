from app.storage.router import StorageRouter, storage_router


def get_storage_router() -> StorageRouter:
    """Router de almacenamiento compartido por todo el proceso.

    Es un singleton a propósito: los locks por fuente y el mapa de destinos
    activos viven en memoria, así que el backend debe correr con un único
    worker (WEB_CONCURRENCY=1).
    """

    return storage_router
