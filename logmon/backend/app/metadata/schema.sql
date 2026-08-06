PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS connections (
    id          TEXT    PRIMARY KEY,
    name        TEXT    NOT NULL,
    engine      TEXT    NOT NULL CHECK (engine IN ('mariadb', 'postgres', 'sqlserver', 'mongo', 'redis')),
    host        TEXT    NOT NULL,
    port        INTEGER NOT NULL,
    "user"      TEXT    NOT NULL,
    password    TEXT    NOT NULL,  -- cifrada (token Fernet), nunca en claro
    "database"  TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS sources (
    id          TEXT    PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    parent_type TEXT    NOT NULL CHECK (parent_type IN ('API', 'WEB', 'SISTEMA')),
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- API keys de ingesta. Una fuente puede tener varias (rotación sin ventana de
-- corte) y de cada una se guarda sólo el SHA-256: el texto plano se devuelve
-- una única vez, al crearla. Revocar no borra la fila, la marca: así el panel
-- sigue mostrando quién ingestó y hasta cuándo.
CREATE TABLE IF NOT EXISTS source_api_keys (
    id           TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    preview      TEXT NOT NULL,
    key_hash     TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_used_at TEXT NULL,
    revoked_at   TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_api_keys_source ON source_api_keys (source_id, created_at DESC);

CREATE TABLE IF NOT EXISTS source_bindings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     TEXT    NOT NULL REFERENCES sources(id)     ON DELETE CASCADE,
    connection_id TEXT    NOT NULL REFERENCES connections(id) ON DELETE RESTRICT,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_bindings_source ON source_bindings (source_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_bindings_conn   ON source_bindings (connection_id);

CREATE TABLE IF NOT EXISTS switch_audit (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id          TEXT    NOT NULL,
    from_connection_id TEXT    NULL,
    to_connection_id   TEXT    NOT NULL,
    status             TEXT    NOT NULL CHECK (status IN ('OK', 'ABORTED')),
    detail             TEXT    NULL,
    created_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_source ON switch_audit (source_id, created_at DESC);
