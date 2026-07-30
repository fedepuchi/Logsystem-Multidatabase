PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS connections (
    id          TEXT    PRIMARY KEY,
    name        TEXT    NOT NULL,
    engine      TEXT    NOT NULL CHECK (engine IN ('mariadb', 'postgres', 'sqlserver', 'mongo', 'redis')),
    host        TEXT    NOT NULL,
    port        INTEGER NOT NULL,
    "user"      TEXT    NOT NULL,
    password    TEXT    NOT NULL,
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
