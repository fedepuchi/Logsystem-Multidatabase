from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

class SecretKeyError(RuntimeError):
    """LOGMON_SECRET_KEY falta o no es una clave Fernet válida."""


class PasswordDecryptError(RuntimeError):
    """Una contraseña guardada no se puede descifrar con la clave actual."""

@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = get_settings().logmon_secret_key.strip()

    if not key:
        raise SecretKeyError(
            "LOGMON_SECRET_KEY está vacía: sin ella no se pueden guardar ni leer las "
            "contraseñas de las conexiones. Generá una con "
            "python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'."
        )

    try:
        return Fernet(key.encode())
    except (TypeError, ValueError) as exc:
        raise SecretKeyError("LOGMON_SECRET_KEY no es una clave Fernet válida.") from exc


def validate_secret_key() -> None:
    """Falla al arrancar y no en el primer guardado."""

    _fernet.cache_clear()
    _fernet()


def encrypt_password(value: str) -> str:
    return _fernet().encrypt((value or "").encode()).decode()


def decrypt_password(value: str) -> str:
    """Descifra una contraseña de conexión.

    Falla en vez de devolver el valor tal cual. Devolverlo escondía dos
    problemas distintos: una fila en texto plano seguía funcionando para
    siempre —con lo que el cifrado quedaba opcional de hecho— y, si alguien
    cambiaba LOGMON_SECRET_KEY, se entregaba el **texto cifrado** como si fuera
    la contraseña, que después el motor rechazaba con un error de credenciales
    imposible de relacionar con la causa real.

    La contraseña vacía es válida: hay motores que no la piden.
    """

    if not value:
        return ""

    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise PasswordDecryptError(
            "No se pudo descifrar la contraseña de la conexión. Suele ser una "
            "de dos cosas: LOGMON_SECRET_KEY cambió desde que se guardó, o la "
            "fila quedó en texto plano. Volvé a cargar la conexión con la "
            "clave actual."
        ) from exc
