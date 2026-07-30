"""El switch redirige sin perder nada.

Corre siempre: usa adapters en memoria, así que prueba la lógica del router y
de la metadata sin depender de que los 5 motores estén levantados.
"""

from __future__ import annotations

import pytest

from app.metadata import repo
from app.storage.base import LogFilters
from app.storage.router import StorageRouter, SwitchAborted, UnboundSourceError
from app.tests.conftest import make_record


@pytest.mark.anyio
async def test_source_sin_binding_no_acepta_logs(seeded_router) -> None:
    router, _ = seeded_router

    with pytest.raises(UnboundSourceError):
        await router.save(make_record("APP1"))


@pytest.mark.anyio
async def test_switch_asigna_y_persiste_el_binding(seeded_router) -> None:
    router, _ = seeded_router

    result = await router.switch("APP1", "C1")

    assert result["from_connection_id"] is None
    assert result["to_connection_id"] == "C1"
    assert await repo.current_binding("APP1") == "C1"
    assert await router.resolve("APP1") == "C1"


@pytest.mark.anyio
async def test_los_logs_viejos_quedan_en_la_base_anterior(seeded_router) -> None:
    router, store = seeded_router

    await router.switch("APP1", "C1")
    viejos = [make_record("APP1") for _ in range(3)]
    for record in viejos:
        assert await router.save(record) == "C1"

    await router.switch("APP1", "C2")
    nuevos = [make_record("APP1") for _ in range(2)]
    for record in nuevos:
        assert await router.save(record) == "C2"

    # Los 3 primeros siguen intactos donde estaban...
    assert {r.id for r in store.rows("C1")} == {r.id for r in viejos}
    # ...y los nuevos cayeron sólo en el destino nuevo.
    assert {r.id for r in store.rows("C2")} == {r.id for r in nuevos}
    assert store.count("C1", "C2") == 5


@pytest.mark.anyio
async def test_el_visor_mergea_ambos_motores(seeded_router) -> None:
    router, _ = seeded_router

    await router.switch("APP1", "C1")
    en_c1 = [await _save(router, "APP1") for _ in range(3)]

    await router.switch("APP1", "C2")
    en_c2 = [await _save(router, "APP1") for _ in range(2)]

    filas = await router.query(LogFilters(source_id="APP1"))

    assert len(filas) == 5
    assert {f.connection_id for f in filas} == {"C1", "C2"}
    assert {f.id for f in filas if f.connection_id == "C1"} == set(en_c1)
    assert {f.id for f in filas if f.connection_id == "C2"} == set(en_c2)

    # Orden descendente por fecha, con el ULID como desempate.
    claves = [(f.fecha, f.id) for f in filas]
    assert claves == sorted(claves, reverse=True)


@pytest.mark.anyio
async def test_paginacion_global_sobre_el_merge(seeded_router) -> None:
    router, _ = seeded_router

    await router.switch("APP1", "C1")
    for _ in range(3):
        await _save(router, "APP1")
    await router.switch("APP1", "C2")
    for _ in range(3):
        await _save(router, "APP1")

    todas = await router.query(LogFilters(source_id="APP1", limit=100))
    pagina1 = await router.query(LogFilters(source_id="APP1", limit=4, offset=0))
    pagina2 = await router.query(LogFilters(source_id="APP1", limit=4, offset=4))

    assert len(todas) == 6
    assert len(pagina1) == 4
    assert len(pagina2) == 2
    assert [f.id for f in pagina1 + pagina2] == [f.id for f in todas]


@pytest.mark.anyio
async def test_switch_a_una_base_caida_se_aborta_sin_tocar_nada(seeded_router) -> None:
    router, store = seeded_router

    await router.switch("APP1", "C1")
    await _save(router, "APP1")

    store.failing.add("C3")

    with pytest.raises(SwitchAborted):
        await router.switch("APP1", "C3")

    # El binding no se movió ni en memoria ni en la metadata.
    assert await router.resolve("APP1") == "C1"
    assert await repo.current_binding("APP1") == "C1"

    # Y las escrituras siguen entrando en el destino anterior.
    assert await router.save(make_record("APP1")) == "C1"
    assert store.count("C1") == 2
    assert store.count("C3") == 0


@pytest.mark.anyio
async def test_el_aborto_queda_auditado(seeded_router) -> None:
    router, store = seeded_router

    await router.switch("APP1", "C1")
    store.failing.add("C4")

    with pytest.raises(SwitchAborted):
        await router.switch("APP1", "C4")

    auditoria = await repo.list_switch_audit("APP1")
    estados = [(a["status"], a["to_connection_id"]) for a in auditoria]

    assert ("ABORTED", "C4") in estados
    assert ("OK", "C1") in estados
    aborted = next(a for a in auditoria if a["status"] == "ABORTED")
    assert aborted["from_connection_id"] == "C1"
    assert "ConnectionRefusedError" in (aborted["detail"] or "")


@pytest.mark.anyio
async def test_historial_de_bindings_acumula_sin_duplicar(seeded_router) -> None:
    router, _ = seeded_router

    await router.switch("APP1", "C1")
    await router.switch("APP1", "C2")
    await router.switch("APP1", "C1")
    await router.switch("APP1", "C1")  # no-op: ya es el destino activo

    historial = await repo.binding_history("APP1")

    # binding_history devuelve conexiones distintas en orden de primera aparición.
    assert historial == ["C1", "C2"]
    assert await repo.current_binding("APP1") == "C1"


@pytest.mark.anyio
async def test_rebuild_reconstruye_el_mapa_desde_la_metadata(seeded_router) -> None:
    router, store = seeded_router

    await router.switch("APP1", "C1")
    await router.switch("APP2", "C2")

    # Simula un reinicio del proceso: router nuevo, misma metadata.
    reiniciado = StorageRouter()
    await reiniciado.rebuild()

    assert await reiniciado.resolve("APP1") == "C1"
    assert await reiniciado.resolve("APP2") == "C2"

    assert await reiniciado.save(make_record("APP1")) == "C1"
    assert store.count("C1") == 1


@pytest.mark.anyio
async def test_un_motor_caido_degrada_el_visor_pero_no_lo_tumba(seeded_router) -> None:
    router, store = seeded_router

    await router.switch("APP1", "C1")
    await _save(router, "APP1")
    await router.switch("APP1", "C2")
    en_c2 = [await _save(router, "APP1") for _ in range(2)]

    # C1 se cae después de haber recibido logs.
    store.failing.add("C1")

    filas = await router.query(LogFilters(source_id="APP1"))

    assert {f.id for f in filas} == set(en_c2)
    assert {f.connection_id for f in filas} == {"C2"}


async def _save(router, source_id: str) -> str:
    record = make_record(source_id)
    await router.save(record)
    return record.id
