"""La retención tiene que arrancar con la app y frenar con ella.

`cleanup_expired` y `retention_loop` estaban implementados, configurados y con
test propio... y nadie los iniciaba. La feature figuraba como entregada y no
borraba nada: los logs se acumulaban sin límite, incluida la memoria de Redis.

Lo que falta cubrir no es la lógica de borrado —eso ya lo prueba
`test_api_batch`— sino el **cableado**: que el lifespan cree la tarea con la
configuración correcta y que la detenga antes de cerrar los adapters.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import pytest

from app.config import get_settings


@pytest.mark.anyio
async def test_el_lifespan_arranca_y_detiene_la_retencion(tmp_path, monkeypatch) -> None:
    from cryptography.fernet import Fernet

    from app.main import app, lifespan
    from app.storage.router import storage_router

    monkeypatch.setenv("LOGMON_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "meta.db"))
    monkeypatch.setenv("LOGMON_RETENTION_DAYS", "7")
    monkeypatch.setenv("LOGMON_RETENTION_INTERVAL_SECONDS", "120")
    get_settings.cache_clear()

    visto: Dict[str, Any] = {
        "arranco": False,
        "dias": None,
        "intervalo": None,
        "freno_limpio": False,
    }

    async def falso_loop(
        retention_days: int,
        interval_seconds: int,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        visto["arranco"] = True
        visto["dias"] = retention_days
        visto["intervalo"] = interval_seconds
        assert stop_event is not None, "sin stop_event el shutdown tendría que cancelarla"
        await stop_event.wait()
        visto["freno_limpio"] = True

    monkeypatch.setattr(storage_router, "retention_loop", falso_loop)

    try:
        async with lifespan(app):
            # Un respiro para que el scheduler llegue a correr la tarea.
            await asyncio.sleep(0.05)

            assert visto["arranco"] is True, "el lifespan no arrancó la retención"
            assert visto["dias"] == 7
            assert visto["intervalo"] == 120
            assert visto["freno_limpio"] is False

        # Al salir del lifespan la tarea terminó sola por el stop_event, sin
        # necesidad de cancelarla.
        assert visto["freno_limpio"] is True
    finally:
        get_settings.cache_clear()


@pytest.mark.anyio
async def test_una_retencion_colgada_no_bloquea_el_shutdown(tmp_path, monkeypatch) -> None:
    """Si la tarea ignora el stop_event, el cierre la cancela y sigue.

    Sin el timeout, un borrado colgado contra un motor caído dejaría el proceso
    sin poder terminar.
    """

    from cryptography.fernet import Fernet

    from app import main as main_module
    from app.main import app, lifespan
    from app.storage.router import storage_router

    monkeypatch.setenv("LOGMON_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "meta.db"))
    get_settings.cache_clear()

    cancelada = {"si": False}

    async def loop_colgado(
        retention_days: int,
        interval_seconds: int,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        try:
            await asyncio.sleep(3600)  # nunca mira el stop_event
        except asyncio.CancelledError:
            cancelada["si"] = True
            raise

    monkeypatch.setattr(storage_router, "retention_loop", loop_colgado)
    # El timeout real es de 5s. Se baja acá para no demorar la suite; por eso
    # es una constante de módulo y no un literal dentro del lifespan.
    monkeypatch.setattr(main_module, "RETENTION_SHUTDOWN_TIMEOUT", 0.05)

    try:
        async with lifespan(app):
            await asyncio.sleep(0.05)

        assert cancelada["si"] is True
    finally:
        get_settings.cache_clear()
