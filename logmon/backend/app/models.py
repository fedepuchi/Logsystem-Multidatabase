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


class ConnectionIn(BaseModel):
    name: str
    engine: str
    host: str
    port: int
    user: str
    password: str
    database: str


class SourceIn(BaseModel):
    name: str
    parent_type: ParentType


class SwitchIn(BaseModel):
    connection_id: str