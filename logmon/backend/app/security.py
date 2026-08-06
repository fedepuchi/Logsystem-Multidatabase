"""Generación, hashing y comparación de credenciales.

Hay dos credenciales distintas en el sistema y nunca se cruzan:

* la **clave de administración** (``ADMIN_API_KEY``), que vive en el entorno y
  habilita el panel: conexiones, fuentes, switch y visor;
* las **API keys por fuente**, que viven en la metadata y sólo habilitan la
  ingesta (``POST /api/logs``) de la fuente que las emitió.

De las keys por fuente se guarda únicamente el SHA-256: el texto plano se
muestra una sola vez, al crearlas. Un hash sin salt y sin KDF alcanza porque la
key no es una contraseña elegida por una persona sino 256 bits de
``secrets.token_urlsafe``: no hay diccionario que atacar, y el hash directo es
lo que permite resolver la key presentada con un único SELECT indexado.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# Prefijo visible de las keys de fuente. Sirve para reconocerlas de un vistazo
# en un log o en un .env, y para que el preview guardado no sea ambiguo.
KEY_PREFIX = "lmk_"

# Cuántos caracteres del principio se guardan en claro para identificar la key
# en el panel sin poder reconstruirla.
PREVIEW_LENGTH = 12


def generate_api_key() -> str:
    """Devuelve una API key nueva en texto plano. No se persiste nunca así."""

    return f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def key_preview(api_key: str) -> str:
    """Primeros caracteres de la key, para mostrarla en el listado."""

    return api_key[:PREVIEW_LENGTH]


def secrets_equal(left: str, right: str) -> bool:
    """Comparación en tiempo constante (la clave de admin sí se compara literal)."""

    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
