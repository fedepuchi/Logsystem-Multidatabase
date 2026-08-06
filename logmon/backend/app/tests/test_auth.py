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


@pytest.mark.anyio
async def test_el_lote_exige_credencial_y_valida_la_fuente(api_client, monkeypatch) -> None:
    """El lote no puede ser la puerta de atrás de la ingesta individual.

    Este caso existe porque no existía: `POST /api/logs` validaba credencial y
    fuente, y `POST /api/logs/batch` no validaba nada, así que bastaba con
    mandar los logs de a uno dentro de un lote para escribir en cualquier
    fuente sin ninguna clave.
    """

    client, _, _ = api_client

    monkeypatch.setenv("ADMIN_API_KEY", ADMIN["X-Admin-Key"])
    get_settings.cache_clear()

    try:
        await client.post("/api/connections", json=conexion("C1"), headers=ADMIN)
        for fuente in ("APP1", "APP2"):
            await client.post(
                "/api/sources", json={"name": fuente, "parent_type": "API"}, headers=ADMIN
            )
            await client.post(
                f"/api/sources/{fuente}/switch",
                json={"connection_id": "C1"},
                headers=ADMIN,
            )

        # Sin credencial no se entra, igual que en la ingesta individual.
        assert (await client.post("/api/logs/batch", json=[log()])).status_code == 401

        # La clave de administración tampoco habilita la ingesta.
        assert (
            await client.post("/api/logs/batch", json=[log()], headers=ADMIN)
        ).status_code == 403

        creada = (
            await client.post(
                "/api/sources/APP1/keys", json={"name": "lotes"}, headers=ADMIN
            )
        ).json()
        key = {"X-API-Key": creada["api_key"]}

        # Un lote propio entra completo.
        propio = await client.post("/api/logs/batch", json=[log(), log()], headers=key)
        assert propio.status_code == 200
        assert propio.json()["saved"] == 2

        # Mezclado: el ajeno se rechaza solo y el propio sigue entrando.
        mezclado = await client.post(
            "/api/logs/batch",
            json=[log(source="APP1"), log(source="APP2")],
            headers=key,
        )
        cuerpo = mezclado.json()
        items = cuerpo["items"]

        assert cuerpo["saved"] == 1 and cuerpo["failed"] == 1
        assert items[0]["success"] is True
        assert items[1]["success"] is False
        assert "APP1" in items[1]["error"] and "APP2" in items[1]["error"]
    finally:
        get_settings.cache_clear()


@pytest.mark.anyio
async def test_stats_exige_administracion(api_client, monkeypatch) -> None:
    """`/api/stats` agrega los mismos datos que el visor y tiene que pedir lo mismo."""

    client, _, _ = api_client

    monkeypatch.setenv("ADMIN_API_KEY", ADMIN["X-Admin-Key"])
    get_settings.cache_clear()

    try:
        assert (await client.get("/api/stats")).status_code == 401
        assert (await client.get("/api/stats", headers=ADMIN)).status_code == 200
    finally:
        get_settings.cache_clear()
