"""La contraseña de una conexión no puede quedar legible en la metadata."""

from __future__ import annotations

import pytest

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
