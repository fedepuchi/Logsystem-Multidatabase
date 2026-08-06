from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

class SecretKeyError(RuntimeError):
    """LOGMON_SECRET_KEY falta o no es una clave Fernet válida."""

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
    if not value:
        return ""

    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        # Fila guardada antes del cifrado: se devuelve tal cual para no dejar
        # inservible una metadata que ya existía.
        return value
