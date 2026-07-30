"""Ningún log cae en el corte del switch.

La prueba de la pizarra: N escrituras concurrentes con un switch disparado a
mitad, y al final ``count(vieja) + count(nueva) == N``.
"""

from __future__ import annotations

import asyncio

import pytest

from app.storage.base import LogFilters
from app.tests.conftest import make_record

N = 60
CORTE = 10  # cuántas escrituras esperar antes de disparar el switch


@pytest.mark.anyio
async def test_switch_a_mitad_de_n_escrituras_no_pierde_ninguna(seeded_router) -> None:
    router, store = seeded_router
    store.save_latency = 0.001

    await router.switch("APP1", "C1")

    async def escribir(i: int) -> str:
        # Escalonadas para simular tráfico sostenido: si entran todas de golpe,
        # el switch queda detrás de las N en la cola FIFO del lock y nunca cae
        # realmente en el medio.
        await asyncio.sleep(i * 0.001)
        record = make_record("APP1", metodo="PUT")
        await router.save(record)
        return record.id

    async def cambiar() -> None:
        # Espera a que la base vieja tenga tráfico real antes de cambiar.
        for _ in range(500):
            if store.count("C1") >= CORTE:
                break
            await asyncio.sleep(0.001)
        await router.switch("APP1", "C2")

    ids = await asyncio.gather(*(escribir(i) for i in range(N)), cambiar())
    escritos = [log_id for log_id in ids[:N]]

    assert store.count("C1", "C2") == N
    assert store.count("C1") >= CORTE
    assert store.count("C2") >= 1, "el switch no llegó a caer en medio del tráfico"

    # Ni duplicados ni logs desaparecidos.
    guardados = {r.id for r in store.rows("C1")} | {r.id for r in store.rows("C2")}
    assert guardados == set(escritos)
    assert len(store.rows("C1")) + len(store.rows("C2")) == len(guardados)


@pytest.mark.anyio
async def test_el_visor_ve_las_n_filas_tras_el_switch(seeded_router) -> None:
    router, store = seeded_router
    store.save_latency = 0.001

    await router.switch("APP1", "C1")

    async def escribir(i: int) -> None:
        await asyncio.sleep(i * 0.001)
        await router.save(make_record("APP1"))

    async def cambiar() -> None:
        for _ in range(500):
            if store.count("C1") >= CORTE:
                break
            await asyncio.sleep(0.001)
        await router.switch("APP1", "C2")

    await asyncio.gather(*(escribir(i) for i in range(N)), cambiar())

    filas = await router.query(LogFilters(source_id="APP1", limit=1000))

    assert len(filas) == N
    assert {f.connection_id for f in filas} == {"C1", "C2"}
    assert len({f.id for f in filas}) == N


@pytest.mark.anyio
async def test_switches_concurrentes_sobre_la_misma_fuente_se_serializan(
    seeded_router,
) -> None:
    router, store = seeded_router

    await router.switch("APP1", "C1")

    await asyncio.gather(
        router.switch("APP1", "C2"),
        router.switch("APP1", "C4"),
        router.switch("APP1", "C5"),
    )

    # El lock por fuente garantiza que quede un único ganador coherente entre
    # el mapa en memoria y la metadata.
    from app.metadata import repo

    activo = await router.resolve("APP1")
    assert activo == await repo.current_binding("APP1")
    assert activo in {"C2", "C4", "C5"}


@pytest.mark.anyio
async def test_fuentes_distintas_no_se_bloquean_entre_si(seeded_router) -> None:
    router, store = seeded_router

    await router.switch("APP1", "C1")
    await router.switch("APP2", "C2")

    resultados = await asyncio.gather(
        *(router.save(make_record("APP1")) for _ in range(20)),
        *(router.save(make_record("APP2")) for _ in range(20)),
    )

    assert resultados.count("C1") == 20
    assert resultados.count("C2") == 20
    assert store.count("C1") == 20
    assert store.count("C2") == 20
