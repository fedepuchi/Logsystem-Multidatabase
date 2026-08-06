"""Separación admin/ingesta y API keys por fuente.

El resto de la suite corre en modo abierto (sin ADMIN_API_KEY), que es como
levanta la demo. Acá se enciende la autenticación para verificar lo único que
importa del modelo: que cada credencial sirva sólo para su superficie y que una
key escriba únicamente logs de su fuente.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.tests.test_api import conexion, log

ADMIN = {"X-Admin-Key": "clave-admin-de-prueba"}


@pytest.mark.anyio
async def test_cada_credencial_sirve_solo_para_su_superficie(api_client, monkeypatch) -> None:
    client, _, _ = api_client

    # get_settings está cacheada: encender la auth exige limpiarla.
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN["X-Admin-Key"])
    get_settings.cache_clear()

    try:
        # Administración: dos fuentes ligadas al mismo motor.
        assert (await client.get("/api/connections")).status_code == 401
        await client.post("/api/connections", json=conexion("C1"), headers=ADMIN)
        for fuente, tipo in (("APP1", "API"), ("APP2", "WEB")):
            await client.post(
                "/api/sources", json={"name": fuente, "parent_type": tipo}, headers=ADMIN
            )
            await client.post(
                f"/api/sources/{fuente}/switch",
                json={"connection_id": "C1"},
                headers=ADMIN,
            )

        # El secreto viaja una única vez, al emitir la key.
        creada = (
            await client.post(
                "/api/sources/APP1/keys", json={"name": "prod"}, headers=ADMIN
            )
        ).json()
        key = {"X-API-Key": creada["api_key"]}
        listado = (await client.get("/api/sources/APP1/keys", headers=ADMIN)).json()

        assert creada["api_key"].startswith("lmk_")
        assert "api_key" not in listado[0]
        assert listado[0]["preview"] == creada["preview"]

        # La key de APP1 ingesta como APP1, y sólo como APP1.
        assert (await client.post("/api/logs", json=log(), headers=key)).status_code == 201
        assert (
            await client.post("/api/logs", json=log(source="APP2"), headers=key)
        ).status_code == 403

        # Las credenciales no se cruzan: ni admin ingesta, ni la key administra.
        assert (await client.post("/api/logs", json=log(), headers=ADMIN)).status_code == 403
        assert (await client.get("/api/connections", headers=key)).status_code == 403

        # Revocar deja la key afuera sin borrar su rastro.
        assert (
            await client.delete(f"/api/sources/APP1/keys/{creada['id']}", headers=ADMIN)
        ).status_code == 204
        assert (await client.post("/api/logs", json=log(), headers=key)).status_code == 401

        revocada = (await client.get("/api/sources/APP1/keys", headers=ADMIN)).json()[0]
        assert revocada["revoked_at"] is not None
        assert revocada["last_used_at"] is not None
    finally:
        get_settings.cache_clear()
