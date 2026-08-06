from __future__ import annotations

from functools import lru_cache
from typing import Dict, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración central del backend leída desde variables de entorno."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    log_level: str = "info"

    # Metadata.
    sqlite_path: str = "./data/logmon.db"

    # Frontend y CORS.
    static_dir: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:8000"

    # Jorge — API: lotes y retención.
    # Variables de entorno:
    # LOGMON_BATCH_MAX_SIZE, LOGMON_RETENTION_DAYS y
    # LOGMON_RETENTION_INTERVAL_SECONDS.
    logmon_batch_max_size: int = Field(default=500, ge=1, le=5000)
    logmon_retention_days: int = Field(default=30, ge=1, le=3650)
    logmon_retention_interval_seconds: int = Field(default=3600, ge=60)
    # Clave de la superficie de administración (header X-Admin-Key). Vacía
    # apaga la autenticación entera —modo abierto de la demo— y app.main se
    # niega a arrancar así si APP_ENV no es development. La ingesta no usa esta
    # clave: cada fuente tiene sus propias API keys en la metadata.
    admin_api_key: str = ""

    mariadb_host: str = "localhost"
    mariadb_port: int = 3306
    mariadb_user: str = "loguser"
    mariadb_password: str = "logpass"
    mariadb_database: str = "logdb"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "loguser"
    postgres_password: str = "logpass"
    postgres_db: str = "logdb"

    sqlserver_host: str = "localhost"
    sqlserver_port: int = 1433
    sqlserver_user: str = "sa"
    mssql_sa_password: str = "Alec2026!SecureSQL"
    sqlserver_database: str = "logdb"

    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_user: str = ""
    mongo_password: str = ""
    mongo_database: str = "logdb"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_user: str = ""
    redis_password: str = ""
    redis_db: str = "0"

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def demo_connections(self) -> List[Dict[str, object]]:
        return [
            {
                "id": "C1",
                "name": "C1 MariaDB",
                "engine": "mariadb",
                "host": self.mariadb_host,
                "port": self.mariadb_port,
                "user": self.mariadb_user,
                "password": self.mariadb_password,
                "database": self.mariadb_database,
            },
            {
                "id": "C2",
                "name": "C2 PostgreSQL",
                "engine": "postgres",
                "host": self.postgres_host,
                "port": self.postgres_port,
                "user": self.postgres_user,
                "password": self.postgres_password,
                "database": self.postgres_db,
            },
            {
                "id": "C3",
                "name": "C3 SQL Server",
                "engine": "sqlserver",
                "host": self.sqlserver_host,
                "port": self.sqlserver_port,
                "user": self.sqlserver_user,
                "password": self.mssql_sa_password,
                "database": self.sqlserver_database,
            },
            {
                "id": "C4",
                "name": "C4 MongoDB",
                "engine": "mongo",
                "host": self.mongo_host,
                "port": self.mongo_port,
                "user": self.mongo_user,
                "password": self.mongo_password,
                "database": self.mongo_database,
            },
            {
                "id": "C5",
                "name": "C5 Redis",
                "engine": "redis",
                "host": self.redis_host,
                "port": self.redis_port,
                "user": self.redis_user,
                "password": self.redis_password,
                "database": self.redis_db,
            },
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
