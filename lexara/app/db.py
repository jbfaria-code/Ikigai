"""SQLite persistence.

Every helper opens its own short-lived connection so that background review
workers can write without sharing a connection with the request thread.
WAL mode keeps concurrent readers from blocking on those writes.
"""
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

_init_lock = threading.Lock()
_initialised = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    client      TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    filename     TEXT NOT NULL,
    stored_path  TEXT NOT NULL,
    kind         TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    pages        INTEGER NOT NULL DEFAULT 0,
    words        INTEGER NOT NULL DEFAULT 0,
    text         TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'ready',
    error        TEXT DEFAULT '',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents(workspace_id);

CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal     INTEGER NOT NULL,
    page        INTEGER NOT NULL DEFAULT 0,
    text        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

CREATE TABLE IF NOT EXISTS review_tables (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tables_workspace ON review_tables(workspace_id);

CREATE TABLE IF NOT EXISTS review_columns (
    id         TEXT PRIMARY KEY,
    table_id   TEXT NOT NULL REFERENCES review_tables(id) ON DELETE CASCADE,
    ordinal    INTEGER NOT NULL,
    header     TEXT NOT NULL,
    prompt     TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'text',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_columns_table ON review_columns(table_id);

CREATE TABLE IF NOT EXISTS review_rows (
    id          TEXT PRIMARY KEY,
    table_id    TEXT NOT NULL REFERENCES review_tables(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal     INTEGER NOT NULL,
    UNIQUE(table_id, document_id)
);
CREATE INDEX IF NOT EXISTS idx_rows_table ON review_rows(table_id);

CREATE TABLE IF NOT EXISTS review_cells (
    id          TEXT PRIMARY KEY,
    table_id    TEXT NOT NULL REFERENCES review_tables(id) ON DELETE CASCADE,
    column_id   TEXT NOT NULL REFERENCES review_columns(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'empty',
    value       TEXT NOT NULL DEFAULT '',
    reasoning   TEXT NOT NULL DEFAULT '',
    quote       TEXT NOT NULL DEFAULT '',
    page        INTEGER NOT NULL DEFAULT 0,
    confidence  TEXT NOT NULL DEFAULT '',
    edited      INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL,
    UNIQUE(column_id, document_id)
);
CREATE INDEX IF NOT EXISTS idx_cells_table ON review_cells(table_id);

CREATE TABLE IF NOT EXISTS threads (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    title        TEXT NOT NULL DEFAULT 'New thread',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_threads_workspace ON threads(workspace_id);

CREATE TABLE IF NOT EXISTS messages (
    id         TEXT PRIMARY KEY,
    thread_id  TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    citations  TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);

CREATE TABLE IF NOT EXISTS playbook_runs (
    id           TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    document_id  TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    playbook_key TEXT NOT NULL,
    playbook_name TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'running',
    result       TEXT NOT NULL DEFAULT '{}',
    error        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_workspace ON playbook_runs(workspace_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def connect() -> sqlite3.Connection:
    init()
    conn = sqlite3.connect(config.DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def cursor(commit: bool = True):
    conn = connect()
    try:
        yield conn
        if commit:
            conn.commit()
    finally:
        conn.close()


def init() -> None:
    """Create the data directory and schema once per process."""
    global _initialised
    if _initialised:
        return
    with _init_lock:
        if _initialised:
            return
        config.ensure_dirs()
        conn = sqlite3.connect(config.DB_PATH, timeout=30, check_same_thread=False)
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()
        _initialised = True


def reset_for_tests() -> None:
    """Force the next connect() to re-create the schema (used by the suite)."""
    global _initialised
    _initialised = False


def query(sql: str, params=()) -> list[dict]:
    with cursor(commit=False) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def query_one(sql: str, params=()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params=()) -> None:
    with cursor() as conn:
        conn.execute(sql, params)


def execute_many(sql: str, seq) -> None:
    with cursor() as conn:
        conn.executemany(sql, seq)


def loads(raw: str, fallback):
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback
