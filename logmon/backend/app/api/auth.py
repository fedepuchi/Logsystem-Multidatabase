"""Separación entre administración e ingesta.

La API tiene dos superficies con públicos distintos:

* **Administración** — conexiones, fuentes, switch, visor y demo. La consume el
  panel y la maneja una persona. Se autentica con la clave de administración
  del entorno, en el header ``X-Admin-Key``.
* **Ingesta** — ``POST /api/logs``. La consumen las aplicaciones monitoreadas,
  que están desplegadas en cualquier lado y cuya credencial hay que poder rotar
  o revocar de a una. Se autentica con una API key emitida *para una fuente*,
  en el header ``X-API-Key``.

Los dos headers son distintos a propósito: una key de ingesta filtrada no puede
llegar a un endpoint de administración ni siquiera por accidente, y la clave de
admin no sirve para escribir logs a nombre de una fuente. Cuando se presenta la
credencial equivocada la respuesta es 403 con el motivo, no un 401 genérico:
sirve más para diagnosticar y no revela nada que quien ya tiene la credencial
no sepa.

Si ``ADMIN_API_KEY`` está vacía la autenticación queda apagada por completo
(modo abierto). Es lo que permite levantar la demo con ``make up`` sin
configurar nada, y ``app.main`` se niega a arrancar así fuera de
``APP_ENV=development``.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.config import get_settings
from app.metadata import repo
from app.security import hash_api_key, secrets_equal

ADMIN_HEADER = "X-Admin-Key"
INGEST_HEADER = "X-API-Key"

# auto_error=False: el 401 lo tiramos nosotros con un mensaje en castellano y
# después de distinguir "no mandaste credencial" de "mandaste la del otro rol".
_admin_key = APIKeyHeader(name=ADMIN_HEADER, auto_error=False)
_ingest_key = APIKeyHeader(name=INGEST_HEADER, auto_error=False)


def auth_enabled() -> bool:
    return bool(get_settings().admin_api_key.strip())


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def require_admin(
    admin_key: Optional[str] = Depends(_admin_key),
    ingest_key: Optional[str] = Depends(_ingest_key),
) -> None:
    """Exige la clave de administración. Se cuelga del router entero."""

    if not auth_enabled():
        return

    if not admin_key:
        if ingest_key:
            raise _forbidden(
                "Las API keys de fuente sólo habilitan la ingesta (POST /api/logs). "
                f"La administración usa el header {ADMIN_HEADER}."
            )
        raise _unauthorized(f"Falta el header {ADMIN_HEADER}")

    if not secrets_equal(admin_key, get_settings().admin_api_key.strip()):
        raise _unauthorized("Clave de administración inválida")


async def require_ingest_source(
    api_key: Optional[str] = Depends(_ingest_key),
    admin_key: Optional[str] = Depends(_admin_key),
) -> Optional[str]:
    """Resuelve la key de ingesta y devuelve la fuente a la que pertenece.

    Devuelve ``None`` en modo abierto, que es la señal para que la ruta no
    valide la fuente del payload.
    """

    if not auth_enabled():
        return None

    if not api_key:
        if admin_key:
            raise _forbidden(
                "La clave de administración no habilita la ingesta: cada fuente "
                f"escribe con su propia API key en el header {INGEST_HEADER}."
            )
        raise _unauthorized(f"Falta el header {INGEST_HEADER}")

    record = await repo.find_api_key_by_hash(hash_api_key(api_key))

    if record is None:
        raise _unauthorized("API key inválida")

    if record["revoked_at"] is not None:
        raise _unauthorized("API key revocada")

    await repo.touch_api_key(record["id"])

    return str(record["source_id"])


def ensure_source_matches(authorized_source: Optional[str], payload_source: str) -> None:
    """Una key sólo escribe logs de su fuente.

    Sin esto la separación por fuente sería decorativa: cualquier aplicación
    podría ensuciar el historial de otra con sólo cambiar ``source_id``.
    """

    if authorized_source is None or authorized_source == payload_source:
        return

    raise _forbidden(
        f"La API key pertenece a {authorized_source} y el log declara "
        f"source_id={payload_source}"
    )
