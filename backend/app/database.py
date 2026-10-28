"""SQLite connection and schema migration management."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
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
    (
        4,
        """
        CREATE TABLE meshing_result_archives (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            automation_id INTEGER REFERENCES meshing_automations(id) ON DELETE SET NULL,
            model_id INTEGER REFERENCES models(id) ON DELETE SET NULL,
            mesh_path TEXT NOT NULL,
            record_json_path TEXT NOT NULL,
            record_markdown_path TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX meshing_result_archives_session
            ON meshing_result_archives(session_id, created_at DESC);
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

    def backup_directory(self) -> Path:
        return self.path.parent / "backups"

    def list_backups(self) -> list[dict[str, object]]:
        directory = self.backup_directory()
        if not directory.exists():
            return []
        backups: list[dict[str, object]] = []
        for path in sorted(directory.glob("fluent-ai-*.db"), reverse=True):
            stat = path.stat()
            backups.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                }
            )
        return backups

    def create_backup(self, label: str = "manual") -> dict[str, object]:
        if not self.path.is_file():
            raise FileNotFoundError(f"Database does not exist: {self.path}")
        directory = self.backup_directory()
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        safe_label = "".join(char for char in label if char.isalnum() or char in "-_") or "manual"
        destination = directory / f"fluent-ai-{stamp}-{safe_label}.db"
        source_connection = sqlite3.connect(self.path, timeout=5.0)
        destination_connection = sqlite3.connect(destination, timeout=5.0)
        try:
            source_connection.backup(destination_connection)
            destination_connection.commit()
            integrity = destination_connection.execute("PRAGMA integrity_check").fetchone()
        finally:
            destination_connection.close()
            source_connection.close()
        if not integrity or str(integrity[0]) != "ok":
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"Backup integrity check failed: {destination}")
        self._prune_backups(keep=10)
        stat = destination.stat()
        return {
            "name": destination.name,
            "path": str(destination),
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        }

    def ensure_daily_backup(self) -> dict[str, object] | None:
        directory = self.backup_directory()
        if directory.exists():
            newest = max(
                (path.stat().st_mtime for path in directory.glob("fluent-ai-*.db")),
                default=0,
            )
            if datetime.now(UTC).timestamp() - newest < 86_400:
                return None
        return self.create_backup("daily")

    def restore_backup(self, backup_name: str) -> tuple[dict[str, object], dict[str, object]]:
        directory = self.backup_directory().resolve()
        backup_path = (directory / backup_name).resolve()
        if backup_path.parent != directory or backup_path.suffix.lower() != ".db":
            raise ValueError("Invalid database backup name.")
        if not backup_path.is_file():
            raise FileNotFoundError(f"Database backup does not exist: {backup_name}")

        safety_backup = self.create_backup("pre-restore")
        source_connection = sqlite3.connect(backup_path, timeout=5.0)
        destination_connection = sqlite3.connect(self.path, timeout=5.0)
        try:
            integrity = source_connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or str(integrity[0]) != "ok":
                raise RuntimeError(f"Backup integrity check failed: {backup_name}")
            source_connection.backup(destination_connection)
            destination_connection.commit()
        finally:
            destination_connection.close()
            source_connection.close()
        self.initialize()
        return safety_backup, {
            "name": backup_path.name,
            "path": str(backup_path),
            "size": backup_path.stat().st_size,
            "created_at": datetime.fromtimestamp(backup_path.stat().st_mtime, UTC).isoformat(),
        }

    def _prune_backups(self, keep: int) -> None:
        backups = sorted(
            self.backup_directory().glob("fluent-ai-*.db"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for stale in backups[keep:]:
            stale.unlink(missing_ok=True)
