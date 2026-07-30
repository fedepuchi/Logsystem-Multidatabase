from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator # type: ignore


class ParentType(str, Enum):
    API = "API"
    WEB = "WEB"
    SISTEMA = "SISTEMA"


class StepType(str, Enum):
    ENTRADA = "ENTRADA"
    SALIDA = "SALIDA"
    ERROR = "ERROR"


class Estado(str, Enum):
    OK = "OK"
    ERROR = "ERROR"


class Engine(str, Enum):
    """Motores soportados. Coincide con el CHECK de connections.engine."""

    MARIADB = "mariadb"
    POSTGRES = "postgres"
    SQLSERVER = "sqlserver"
    MONGO = "mongo"
    REDIS = "redis"


class LogStep(BaseModel):
    orden: int
    tipo: StepType
    contenido: str
    duration_ms: Optional[int] = None


class LogRecord(BaseModel):
    id: str
    source_id: str
    parent_type: ParentType
    entrada: str
    resultado: str
    metodo: str
    tiempo_ms: int = 0
    estado: Estado = Estado.OK
    fecha: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    steps: List[LogStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def _derive_fields(self) -> "LogRecord":
        total = sum(s.duration_ms or 0 for s in self.steps)
        object.__setattr__(self, "tiempo_ms", total)
        has_error = any(s.tipo == StepType.ERROR for s in self.steps)
        object.__setattr__(self, "estado", Estado.ERROR if has_error else Estado.OK)
        return self


class LogCreate(BaseModel):
    """Payload de ingesta.

    No lleva ``id`` (lo genera el servidor con un ULID) ni ``tiempo_ms`` /
    ``estado``, que son derivados de los pasos según la regla de la pizarra.
    """

    source_id: str
    parent_type: ParentType
    entrada: str
    resultado: str
    metodo: str
    fecha: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    steps: List[LogStep] = Field(default_factory=list)

    def to_record(self, log_id: str) -> "LogRecord":
        return LogRecord(
            id=log_id,
            source_id=self.source_id,
            parent_type=self.parent_type,
            entrada=self.entrada,
            resultado=self.resultado,
            metodo=self.metodo,
            fecha=self.fecha,
            steps=self.steps,
        )


class LogSummary(BaseModel):
    id: str
    source_id: str
    parent_type: ParentType
    entrada: str
    resultado: str
    metodo: str
    tiempo_ms: int
    estado: Estado
    fecha: datetime
    connection_id: Optional[str] = None

    @classmethod
    def from_record(cls, record: LogRecord, connection_id: Optional[str] = None) -> "LogSummary":
        """Fila de la tabla del visor, etiquetada con el motor de origen."""

        return cls(
            id=record.id,
            source_id=record.source_id,
            parent_type=record.parent_type,
            entrada=record.entrada,
            resultado=record.resultado,
            metodo=record.metodo,
            tiempo_ms=record.tiempo_ms,
            estado=record.estado,
            fecha=record.fecha,
            connection_id=connection_id,
        )


class ConnectionIn(BaseModel):
    name: str
    engine: Engine
    host: str
    port: int = Field(ge=1, le=65535)
    user: str = ""
    password: str = ""
    database: str


class SourceIn(BaseModel):
    name: str
    parent_type: ParentType


class SwitchIn(BaseModel):
    connection_id: str