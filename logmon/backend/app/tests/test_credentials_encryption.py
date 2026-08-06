"""La contraseña de una conexión no puede quedar legible en la metadata."""

from __future__ import annotations

import pytest

from app.crypto import PasswordDecryptError, decrypt_password, encrypt_password
from app.metadata import db as metadata_db
from app.metadata import repo
from app.models import ConnectionIn

CLAVE = "clave-super-secreta-para-la-prueba"


@pytest.mark.anyio
async def test_la_password_se_guarda_cifrada(tmp_path) -> None:
    ruta = tmp_path / "meta.db"
    await metadata_db.init_metadata_db(str(ruta))

    try:
        await repo.create_connection(
            ConnectionIn(
                name="C9 Postgres",
                engine="postgres",
                host="localhost",
                port=5432,
                user="loguser",
                password=CLAVE,
                database="logdb",
            ),
            connection_id="C9",
        )

        # El adapter sí la necesita en claro.
        conexion = await repo.get_connection_for_adapter("C9")
        assert conexion is not None
        assert conexion["password"] == CLAVE

        # El archivo de la metadata, no.
        assert CLAVE.encode() not in ruta.read_bytes()
    finally:
        await metadata_db.close_metadata_db()


def test_una_password_en_texto_plano_no_pasa_por_descifrada() -> None:
    """Antes se devolvía tal cual, y el cifrado quedaba opcional de hecho.

    Si un valor sin cifrar se acepta en silencio, nada obliga a que las filas
    estén cifradas: el test que comprueba que la clave no aparece en el archivo
    seguiría pasando mientras alguien escriba directo en la base.
    """

    with pytest.raises(PasswordDecryptError):
        decrypt_password("esto-nunca-se-cifro")


def test_cambiar_la_clave_falla_con_un_mensaje_y_no_devuelve_el_cifrado(monkeypatch) -> None:
    """El caso que más costaba diagnosticar.

    Devolver el texto cifrado hacía que el motor rechazara la conexión con un
    error de credenciales, sin ninguna pista de que la causa real era que
    LOGMON_SECRET_KEY había cambiado.
    """

    from cryptography.fernet import Fernet

    from app.config import get_settings
    from app.crypto import _fernet

    cifrada = encrypt_password(CLAVE)

    # Las dos cachés: _fernet guarda la instancia y get_settings el valor leído
    # del entorno. Limpiar sólo la primera deja la clave vieja en pie.
    monkeypatch.setenv("LOGMON_SECRET_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    _fernet.cache_clear()

    try:
        with pytest.raises(PasswordDecryptError) as excinfo:
            decrypt_password(cifrada)

        mensaje = str(excinfo.value)
        assert "LOGMON_SECRET_KEY" in mensaje
        # Lo que no puede pasar: que el cifrado se filtre como si fuera la clave.
        assert cifrada not in mensaje
    finally:
        get_settings.cache_clear()
        _fernet.cache_clear()


def test_la_password_vacia_sigue_siendo_valida() -> None:
    """Hay motores que no piden contraseña; eso no es un error de descifrado."""

    assert decrypt_password("") == ""
