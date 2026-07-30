"""Round-trip de serialización de Mongo y Redis, sin servidores.

Los adapters SQL guardan cada campo en su columna, pero Mongo embebe los pasos
en el documento y Redis los serializa a JSON dentro de un hash: ahí es donde se
pierden tipos (fechas naive, duration_ms nulo, enums). Estos casos corren
siempre, aunque no haya ningún motor levantado.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import Estado, LogRecord, LogStep, ParentType, StepType

pytest.importorskip("pymongo", reason="pymongo no instalado")
pytest.importorskip("redis", reason="redis-py no instalado")

from app.storage.adapters.mongo import MongoAdapter  # noqa: E402
from app.storage.adapters.redis import RedisAdapter  # noqa: E402


def _record(**overrides) -> LogRecord:
    base = dict(
        id="01J0000000000000000000000A",
        source_id="APP1",
        parent_type=ParentType.API,
        entrada="POST /orders",
        resultado="Orden creada — 100 % ok",  # acentos y símbolos a propósito
        metodo="POST",
        fecha=datetime(2026, 7, 30, 12, 34, 56, 789000, tzinfo=timezone.utc),
        steps=[
            LogStep(orden=1, tipo=StepType.ENTRADA, contenido="payload", duration_ms=120),
            LogStep(orden=2, tipo=StepType.ERROR, contenido="DB timeout", duration_ms=3000),
        ],
    )
    base.update(overrides)
    return LogRecord(**base)


def _assert_equivalent(original: LogRecord, restored: LogRecord) -> None:
    assert restored.id == original.id
    assert restored.source_id == original.source_id
    assert restored.parent_type == original.parent_type
    assert restored.entrada == original.entrada
    assert restored.resultado == original.resultado
    assert restored.metodo == original.metodo
    assert restored.estado == original.estado
    assert restored.tiempo_ms == original.tiempo_ms
    assert restored.fecha == original.fecha
    assert restored.fecha.tzinfo is not None

    assert len(restored.steps) == len(original.steps)
    for got, expected in zip(restored.steps, original.steps):
        assert got.orden == expected.orden
        assert got.tipo == expected.tipo
        assert got.contenido == expected.contenido
        assert got.duration_ms == expected.duration_ms


def test_mongo_round_trip() -> None:
    original = _record()
    restored = MongoAdapter._document_to_record(MongoAdapter._record_to_document(original))

    _assert_equivalent(original, restored)
    assert restored.estado == Estado.ERROR
    assert restored.tiempo_ms == 3120


def test_redis_round_trip() -> None:
    original = _record()
    restored = RedisAdapter._mapping_to_record(RedisAdapter._record_to_mapping(original))

    _assert_equivalent(original, restored)
    assert restored.estado == Estado.ERROR
    assert restored.tiempo_ms == 3120


def test_mongo_usa_el_id_como_clave_primaria() -> None:
    document = MongoAdapter._record_to_document(_record())
    assert document["_id"] == "01J0000000000000000000000A"
    assert "id" not in document


def test_redis_serializa_solo_strings() -> None:
    # El hash de Redis sólo acepta valores escalares: si algo quedara como dict
    # o lista, hset fallaría recién en runtime contra el servidor.
    mapping = RedisAdapter._record_to_mapping(_record())
    assert all(isinstance(value, str) for value in mapping.values()), mapping


def test_duration_ms_nulo_sobrevive_el_round_trip() -> None:
    original = _record(
        steps=[LogStep(orden=1, tipo=StepType.SALIDA, contenido="sin medición")]
    )

    _assert_equivalent(original, MongoAdapter._document_to_record(
        MongoAdapter._record_to_document(original)))
    _assert_equivalent(original, RedisAdapter._mapping_to_record(
        RedisAdapter._record_to_mapping(original)))

    assert original.tiempo_ms == 0
    assert original.estado == Estado.OK


def test_fecha_naive_se_normaliza_a_utc() -> None:
    original = _record(fecha=datetime(2026, 7, 30, 12, 0, 0))

    for restored in (
        MongoAdapter._document_to_record(MongoAdapter._record_to_document(original)),
        RedisAdapter._mapping_to_record(RedisAdapter._record_to_mapping(original)),
    ):
        assert restored.fecha.tzinfo is not None
        assert restored.fecha == datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)


def test_los_pasos_se_devuelven_ordenados() -> None:
    original = _record(
        steps=[
            LogStep(orden=3, tipo=StepType.SALIDA, contenido="c", duration_ms=1),
            LogStep(orden=1, tipo=StepType.ENTRADA, contenido="a", duration_ms=1),
            LogStep(orden=2, tipo=StepType.SALIDA, contenido="b", duration_ms=1),
        ]
    )

    restored = MongoAdapter._document_to_record(MongoAdapter._record_to_document(original))
    assert [s.orden for s in restored.steps] == [1, 2, 3]
    assert [s.contenido for s in restored.steps] == ["a", "b", "c"]
