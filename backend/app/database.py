"""SQLite connection and schema migration management."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE automations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            preset_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            file_path TEXT NOT NULL UNIQUE,
            file_size INTEGER NOT NULL DEFAULT 0,
            file_mtime TEXT,
            description TEXT NOT NULL DEFAULT '',
            tags_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE model_automations (
            model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
            automation_id INTEGER NOT NULL REFERENCES automations(id) ON DELETE CASCADE,
            is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
            created_at TEXT NOT NULL,
            PRIMARY KEY (model_id, automation_id)
        );

        CREATE UNIQUE INDEX model_automations_one_default
            ON model_automations(model_id)
            WHERE is_default = 1;

        CREATE TABLE app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
            progress INTEGER NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
            message TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT
        );

        CREATE TABLE sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT NOT NULL
                CHECK (direction IN ('read', 'write', 'sync', 'apply', 'pull')),
            target TEXT NOT NULL,
            automation_id INTEGER REFERENCES automations(id) ON DELETE SET NULL,
            model_id INTEGER REFERENCES models(id) ON DELETE SET NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL CHECK (status IN ('success', 'failed')),
            message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        INSERT INTO app_settings(key, value, updated_at) VALUES
            ('language', 'zh', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            ('ui_theme', 'system', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            ('fluent_connect_mode', 'launch', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            ('fluent_host', '127.0.0.1', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            ('fluent_port', '', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            ('fluent_path', '', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
        """,
    ),
    (
        2,
        """
        CREATE TABLE meshing_automations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            model_family TEXT NOT NULL DEFAULT '',
            reference_model_id INTEGER REFERENCES models(id) ON DELETE SET NULL,
            workflow_type TEXT NOT NULL
                CHECK (workflow_type IN ('watertight', 'fault-tolerant')),
            preset_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX meshing_automations_workflow_type
            ON meshing_automations(workflow_type, updated_at DESC);
        """,
    ),
    (
        3,
        """
        ALTER TABLE sync_logs
            ADD COLUMN meshing_automation_id INTEGER
            REFERENCES meshing_automations(id) ON DELETE SET NULL;

        CREATE INDEX sync_logs_meshing_automation
            ON sync_logs(meshing_automation_id, created_at DESC);
        """,
    ),
)


class Database:
    """Small SQLite wrapper using a connection per operation."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        """Apply pending schema migrations exactly once."""
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
            ).fetchone()
            current_version = int(row["version"]) if row else 0

            for version, sql in MIGRATIONS:
                if version <= current_version:
                    continue
                connection.executescript(sql)
                connection.execute(
                    """
                    INSERT INTO schema_migrations(version, applied_at)
                    VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    """,
                    (version,),
                )
