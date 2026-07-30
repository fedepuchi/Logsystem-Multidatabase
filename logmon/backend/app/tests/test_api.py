"""Tests de la API REST, extremo a extremo sobre la app real.

Usan adapters en memoria, así que corren siempre y cubren el contrato HTTP
completo: códigos de estado, validación, forma de las respuestas y el merge
multi-motor que consume el frontend.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest


def conexion(nombre: str, engine: str = "postgres", host: str = "db") -> Dict[str, Any]:
    return {
        "name": nombre,
        "engine": engine,
        "host": host,
        "port": 5432,
        "user": "loguser",
        "password": "logpass",
        "database": "logdb",
    }


def log(source: str = "APP1", metodo: str = "POST", error: bool = False) -> Dict[str, Any]:
    pasos = [{"orden": 1, "tipo": "ENTRADA", "contenido": "payload", "duration_ms": 100}]
    pasos.append(
        {"orden": 2, "tipo": "ERROR", "contenido": "DB timeout", "duration_ms": 300}
        if error
        else {"orden": 2, "tipo": "SALIDA", "contenido": "201 Created", "duration_ms": 50}
    )
    return {
        "source_id": source,
        "parent_type": "API",
        "entrada": f"{metodo} /orders",
        "resultado": "procesado",
        "metodo": metodo,
        "steps": pasos,
    }


async def _preparar(client, *, conexiones=("C1", "C2"), fuente="APP1") -> None:
    for indice, _ in enumerate(conexiones, start=1):
        await client.post("/api/connections", json=conexion(f"Conexión {indice}"))
    await client.post("/api/sources", json={"name": fuente, "parent_type": "API"})


# --------------------------------------------------------------------------
# Conexiones
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_crear_conexion_devuelve_201_y_numera_desde_c1(api_client) -> None:
    client, _, _ = api_client

    primera = await client.post("/api/connections", json=conexion("C1 MariaDB", "mariadb"))
    segunda = await client.post("/api/connections", json=conexion("C2 Postgres"))

    assert primera.status_code == 201
    assert primera.json()["id"] == "C1"
    assert segunda.json()["id"] == "C2"


@pytest.mark.anyio
async def test_la_password_nunca_sale_en_las_respuestas(api_client) -> None:
    client, _, _ = api_client

    creada = await client.post("/api/connections", json=conexion("C1"))
    detalle = await client.get("/api/connections/C1")
    listado = await client.get("/api/connections")

    assert "password" not in creada.json()
    assert "password" not in detalle.json()
    assert all("password" not in item for item in listado.json())


@pytest.mark.anyio
async def test_nombre_duplicado_devuelve_409(api_client) -> None:
    client, _, _ = api_client

    await client.post("/api/connections", json=conexion("C1 MariaDB"))
    repetida = await client.post("/api/connections", json=conexion("c1 mariadb"))

    assert repetida.status_code == 409


@pytest.mark.anyio
@pytest.mark.parametrize(
    "campo,valor",
    [("engine", "cassandra"), ("port", 0), ("port", 70000)],
)
async def test_payload_invalido_devuelve_422(api_client, campo, valor) -> None:
    client, _, _ = api_client

    payload = conexion("C1")
    payload[campo] = valor

    assert (await client.post("/api/connections", json=payload)).status_code == 422


@pytest.mark.anyio
async def test_conexion_inexistente_devuelve_404(api_client) -> None:
    client, _, _ = api_client

    assert (await client.get("/api/connections/C9")).status_code == 404
    assert (await client.delete("/api/connections/C9")).status_code == 404
    assert (await client.post("/api/connections/C9/test")).status_code == 404


@pytest.mark.anyio
async def test_test_de_conexion_reporta_exito_y_fallo_con_200(api_client) -> None:
    client, _, store = api_client

    await client.post("/api/connections", json=conexion("C1"))
    ok = await client.post("/api/connections/C1/test")

    assert ok.status_code == 200
    assert ok.json()["success"] is True

    # Un motor caído es un resultado, no un error de la API.
    store.failing.add("C1")
    caido = await client.post("/api/connections/C1/test")

    assert caido.status_code == 200
    assert caido.json()["success"] is False
    assert "ConnectionRefusedError" in caido.json()["message"]


@pytest.mark.anyio
async def test_editar_conexion_descarta_el_pool_cacheado(api_client) -> None:
    client, router, _ = api_client

    await client.post("/api/connections", json=conexion("C1"))
    await client.post("/api/connections/C1/test")  # fuerza la apertura del adapter
    viejo = router.registry.peek("C1")
    assert viejo is not None

    respuesta = await client.put("/api/connections/C1", json=conexion("C1 renombrada"))

    assert respuesta.status_code == 200
    assert respuesta.json()["name"] == "C1 renombrada"
    assert router.registry.peek("C1") is None
    assert viejo.closed is True


@pytest.mark.anyio
async def test_no_se_puede_borrar_una_conexion_con_historial(api_client) -> None:
    client, _, _ = api_client
    await _preparar(client)

    await client.post("/api/sources/APP1/switch", json={"connection_id": "C1"})
    en_uso = await client.delete("/api/connections/C1")
    libre = await client.delete("/api/connections/C2")

    assert en_uso.status_code == 409
    assert libre.status_code == 204


# --------------------------------------------------------------------------
# Fuentes y switch
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_crear_fuente_nace_sin_conexion(api_client) -> None:
    client, _, _ = api_client

    creada = await client.post("/api/sources", json={"name": "APP1", "parent_type": "API"})

    assert creada.status_code == 201
    assert creada.json()["connection_id"] is None

    repetida = await client.post("/api/sources", json={"name": "APP1", "parent_type": "WEB"})
    assert repetida.status_code == 409


@pytest.mark.anyio
async def test_switch_a_conexion_o_fuente_inexistente_devuelve_404(api_client) -> None:
    client, _, _ = api_client
    await _preparar(client)

    sin_conexion = await client.post(
        "/api/sources/APP1/switch", json={"connection_id": "C9"}
    )
    sin_fuente = await client.post(
        "/api/sources/NOPE/switch", json={"connection_id": "C1"}
    )

    assert sin_conexion.status_code == 404
    assert sin_fuente.status_code == 404


@pytest.mark.anyio
async def test_switch_a_un_motor_caido_devuelve_409_y_no_mueve_nada(api_client) -> None:
    client, _, store = api_client
    await _preparar(client)

    await client.post("/api/sources/APP1/switch", json={"connection_id": "C1"})
    store.failing.add("C2")

    abortado = await client.post("/api/sources/APP1/switch", json={"connection_id": "C2"})
    fuente = await client.get("/api/sources/APP1")

    assert abortado.status_code == 409
    assert "sigue escribiendo en su destino anterior" in abortado.json()["detail"]
    assert fuente.json()["connection_id"] == "C1"

    # Y la ingesta sigue entrando en el destino viejo.
    creado = await client.post("/api/logs", json=log())
    assert creado.json()["connection_id"] == "C1"


@pytest.mark.anyio
async def test_history_expone_el_recorrido_y_la_auditoria(api_client) -> None:
    client, _, store = api_client
    await _preparar(client)

    await client.post("/api/sources/APP1/switch", json={"connection_id": "C1"})
    store.failing.add("C2")
    await client.post("/api/sources/APP1/switch", json={"connection_id": "C2"})
    store.failing.discard("C2")
    await client.post("/api/sources/APP1/switch", json={"connection_id": "C2"})

    historial = (await client.get("/api/sources/APP1/history")).json()
    estados = [(a["status"], a["to_connection_id"]) for a in historial["audit"]]

    assert historial["connections"] == ["C1", "C2"]
    assert ("OK", "C1") in estados
    assert ("ABORTED", "C2") in estados
    assert ("OK", "C2") in estados


@pytest.mark.anyio
async def test_borrar_fuente_con_historial_requiere_force(api_client) -> None:
    client, _, _ = api_client
    await _preparar(client)
    await client.post("/api/sources/APP1/switch", json={"connection_id": "C1"})

    sin_force = await client.delete("/api/sources/APP1")
    con_force = await client.delete("/api/sources/APP1?force=true")

    assert sin_force.status_code == 409
    assert con_force.status_code == 204


# --------------------------------------------------------------------------
# Ingesta
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ingesta_sin_binding_devuelve_400(api_client) -> None:
    client, _, _ = api_client
    await _preparar(client)

    respuesta = await client.post("/api/logs", json=log())

    assert respuesta.status_code == 400
    assert "no tiene una conexión asignada" in respuesta.json()["detail"]


@pytest.mark.anyio
async def test_el_servidor_genera_el_ulid_y_deriva_estado_y_tiempo(api_client) -> None:
    client, _, _ = api_client
    await _preparar(client)
    await client.post("/api/sources/APP1/switch", json={"connection_id": "C1"})

    ok = (await client.post("/api/logs", json=log())).json()
    con_error = (await client.post("/api/logs", json=log(error=True))).json()

    assert len(ok["id"]) == 26  # ULID
    assert ok["id"] != con_error["id"]
    assert ok["connection_id"] == "C1"

    # Regla de la pizarra: tiempo_ms = suma de los pasos, estado = ERROR si hay
    # algún paso ERROR. El cliente no puede imponerlos.
    assert ok["estado"] == "OK" and ok["tiempo_ms"] == 150
    assert con_error["estado"] == "ERROR" and con_error["tiempo_ms"] == 400


@pytest.mark.anyio
async def test_el_id_enviado_por_el_cliente_se_ignora(api_client) -> None:
    client, _, _ = api_client
    await _preparar(client)
    await client.post("/api/sources/APP1/switch", json={"connection_id": "C1"})

    payload = log()
    payload["id"] = "ID-FALSIFICADO"

    creado = (await client.post("/api/logs", json=payload)).json()

    assert creado["id"] != "ID-FALSIFICADO"


@pytest.mark.anyio
async def test_demo_sin_bindings_devuelve_400(api_client) -> None:
    client, _, _ = api_client

    respuesta = await client.post("/api/logs/demo")

    assert respuesta.status_code == 400
    assert "make seed" in respuesta.json()["detail"]


@pytest.mark.anyio
async def test_demo_reparte_los_logs_entre_las_fuentes_asignadas(api_client) -> None:
    client, _, _ = api_client

    for indice in range(1, 4):
        await client.post("/api/connections", json=conexion(f"C{indice}"))
    for nombre, tipo in (("APP1", "API"), ("APP2", "WEB"), ("SIS3", "SISTEMA")):
        await client.post("/api/sources", json={"name": nombre, "parent_type": tipo})
    await client.post("/api/sources/APP1/switch", json={"connection_id": "C3"})
    await client.post("/api/sources/APP2/switch", json={"connection_id": "C2"})
    await client.post("/api/sources/SIS3/switch", json={"connection_id": "C1"})

    respuesta = await client.post("/api/logs/demo")
    filas = (await client.get("/api/logs", params={"limit": 100})).json()

    assert respuesta.status_code == 201
    assert respuesta.json()["result"]["creados"] == 6
    assert len(filas) == 6
    assert {f["connection_id"] for f in filas} == {"C1", "C2", "C3"}
    assert sum(1 for f in filas if f["estado"] == "ERROR") == 3


# --------------------------------------------------------------------------
# Visor
# --------------------------------------------------------------------------


@pytest.fixture
async def visor(api_client):
    """APP1 con 3 logs en C1 y 2 en C2 tras un switch. Devuelve (client, ids)."""

    client, _, _ = api_client
    await _preparar(client)

    await client.post("/api/sources/APP1/switch", json={"connection_id": "C1"})
    en_c1 = [
        (await client.post("/api/logs", json=log(error=(i == 0)))).json()["id"]
        for i in range(3)
    ]

    await client.post("/api/sources/APP1/switch", json={"connection_id": "C2"})
    en_c2 = [
        (await client.post("/api/logs", json=log(metodo="GET"))).json()["id"]
        for _ in range(2)
    ]

    return client, en_c1, en_c2


@pytest.mark.anyio
async def test_el_visor_mergea_los_dos_motores_y_etiqueta_el_origen(visor) -> None:
    client, en_c1, en_c2 = visor

    filas = (await client.get("/api/logs", params={"source": "APP1"})).json()

    assert len(filas) == 5
    assert {f["id"] for f in filas if f["connection_id"] == "C1"} == set(en_c1)
    assert {f["id"] for f in filas if f["connection_id"] == "C2"} == set(en_c2)


@pytest.mark.anyio
async def test_el_visor_ordena_descendente_por_fecha(visor) -> None:
    client, _, _ = visor

    filas = (await client.get("/api/logs", params={"source": "APP1"})).json()
    claves = [(f["fecha"], f["id"]) for f in filas]

    assert claves == sorted(claves, reverse=True)


@pytest.mark.anyio
async def test_filtros_del_visor(visor) -> None:
    client, _, _ = visor

    async def filtrar(**params):
        return (await client.get("/api/logs", params={"source": "APP1", **params})).json()

    assert len(await filtrar(estado="ERROR")) == 1
    assert len(await filtrar(estado="OK")) == 4
    assert len(await filtrar(metodo="GET")) == 2
    assert len(await filtrar(metodo="POST")) == 3


@pytest.mark.anyio
async def test_paginacion_global_sobre_el_merge(visor) -> None:
    client, _, _ = visor

    async def pagina(**params):
        return (await client.get("/api/logs", params={"source": "APP1", **params})).json()

    todas = await pagina(limit=100)
    primera = await pagina(limit=3, offset=0)
    segunda = await pagina(limit=3, offset=3)

    assert [f["id"] for f in primera + segunda] == [f["id"] for f in todas]
    assert len(primera) == 3
    assert len(segunda) == 2


@pytest.mark.anyio
async def test_rango_de_fechas_invertido_devuelve_422(api_client) -> None:
    client, _, _ = api_client

    respuesta = await client.get(
        "/api/logs",
        params={"fecha_inicio": "2026-07-30T12:00:00Z", "fecha_fin": "2026-07-29T12:00:00Z"},
    )

    assert respuesta.status_code == 422


@pytest.mark.anyio
async def test_detalle_se_pide_al_motor_de_origen(visor) -> None:
    client, en_c1, _ = visor

    correcto = await client.get(f"/api/logs/{en_c1[0]}", params={"conn": "C1"})
    equivocado = await client.get(f"/api/logs/{en_c1[0]}", params={"conn": "C2"})
    sin_conn = await client.get(f"/api/logs/{en_c1[0]}")

    assert correcto.status_code == 200
    assert len(correcto.json()["steps"]) == 2
    assert [s["tipo"] for s in correcto.json()["steps"]] == ["ENTRADA", "ERROR"]
    assert equivocado.status_code == 404
    assert sin_conn.status_code == 422  # conn es obligatorio


@pytest.mark.anyio
async def test_un_motor_caido_degrada_el_visor_pero_no_lo_tumba(visor, api_client) -> None:
    client, _, en_c2 = visor
    _, _, store = api_client

    store.failing.add("C1")
    filas = (await client.get("/api/logs", params={"source": "APP1"})).json()

    assert {f["id"] for f in filas} == set(en_c2)


# --------------------------------------------------------------------------
# Rutas
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_health(api_client) -> None:
    client, _, _ = api_client

    respuesta = await client.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_ruta_de_api_inexistente_devuelve_404_no_el_index(api_client) -> None:
    client, _, _ = api_client

    respuesta = await client.get("/api/no-existe")

    assert respuesta.status_code == 404
    assert "text/html" not in respuesta.headers.get("content-type", "")
