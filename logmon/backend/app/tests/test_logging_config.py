"""LOG_LEVEL tiene que hacer algo.

Estaba declarado en config.py y no lo leía nadie, así que bajo uvicorn los
`logger.info` de la aplicación no salían por ningún lado: un switch fallido o un
motor caído no dejaban rastro.
"""

from __future__ import annotations

import logging

from app.main import nivel_de_log


def test_traduce_los_niveles_habituales() -> None:
    assert nivel_de_log("debug") == logging.DEBUG
    assert nivel_de_log("info") == logging.INFO
    assert nivel_de_log("warning") == logging.WARNING
    assert nivel_de_log("error") == logging.ERROR
    assert nivel_de_log("critical") == logging.CRITICAL


def test_no_distingue_mayusculas_ni_espacios() -> None:
    assert nivel_de_log("  DEBUG ") == logging.DEBUG
    assert nivel_de_log("Warning") == logging.WARNING


def test_un_valor_invalido_cae_en_info_y_no_revienta() -> None:
    """Un LOG_LEVEL mal escrito no puede impedir que la app arranque."""

    assert nivel_de_log("berrinche") == logging.INFO
    assert nivel_de_log("") == logging.INFO


def test_no_devuelve_atributos_sueltos_del_modulo_logging() -> None:
    """La trampa de resolverlo con getattr(logging, valor).

    `logging.Logger` o `logging.raiseExceptions` existen como atributos y no son
    niveles; con getattr, LOG_LEVEL=Logger habría devuelto una clase.
    """

    for trampa in ("Logger", "raiseExceptions", "getLogger"):
        assert nivel_de_log(trampa) == logging.INFO
