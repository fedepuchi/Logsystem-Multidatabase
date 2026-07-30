from __future__ import annotations

from ulid import ULID


def new_ulid() -> str:
    """Devuelve un ULID de 26 caracteres.

    Los ULID son únicos globalmente y ordenables por tiempo de creación, lo que
    permite mergear logs provenientes de varios motores tras un switch y
    desempatar de forma estable cuando dos registros comparten ``fecha``.
    """

    return str(ULID())
