from __future__ import annotations
 
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Protocol, runtime_checkable
 
from app.models import Estado, LogRecord
 
 
@dataclass
class LogFilters:
    source_id: Optional[str] = None
    estado: Optional[Estado] = None
    metodo: Optional[str] = None
    fecha_desde: Optional[datetime] = None
    fecha_hasta: Optional[datetime] = None
    limit: int = 100
    offset: int = 0
 
 
@runtime_checkable
class LogRepository(Protocol):
    async def ensure_schema(self) -> None: ...
 
    async def ping(self) -> bool: ...
 
    async def save(self, record: LogRecord) -> None: ...
 
    async def query(self, filters: LogFilters) -> List[LogRecord]: ...
 
    async def get(self, log_id: str) -> Optional[LogRecord]: ...
 
    async def close(self) -> None: ...
 