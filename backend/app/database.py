"""SQLite connection and schema migration management."""

from __future__ import annotations

import sqlite3
import threading
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
    (
        5,
        """
        CREATE TABLE part_categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            is_system INTEGER NOT NULL DEFAULT 0 CHECK (is_system IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        INSERT INTO part_categories(id, name, description, is_system, created_at, updated_at)
        SELECT 'uncategorized', '未分类', '迁移前创建的网格预设', 1,
               strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
               strftime('%Y-%m-%dT%H:%M:%fZ', 'now');

        ALTER TABLE meshing_automations ADD COLUMN category_id TEXT
            REFERENCES part_categories(id) ON DELETE RESTRICT;
        UPDATE meshing_automations SET category_id = 'uncategorized';
        CREATE INDEX meshing_automations_category
            ON meshing_automations(category_id, updated_at DESC);

        CREATE TABLE meshing_template_revisions (
            id TEXT PRIMARY KEY,
            automation_id INTEGER NOT NULL REFERENCES meshing_automations(id) ON DELETE CASCADE,
            revision_number INTEGER NOT NULL CHECK (revision_number > 0),
            preset_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft', 'published')),
            created_at TEXT NOT NULL,
            UNIQUE(automation_id, revision_number)
        );
        INSERT INTO meshing_template_revisions(
            id, automation_id, revision_number, preset_json, status, created_at
        )
        SELECT 'legacy-' || id, id, 1, preset_json,
               CASE WHEN status = 'active' THEN 'published' ELSE 'draft' END,
               created_at
        FROM meshing_automations;
        ALTER TABLE meshing_automations ADD COLUMN revision INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE meshing_automations ADD COLUMN published_revision INTEGER;
        UPDATE meshing_automations SET published_revision =
            CASE WHEN status = 'active' THEN 1 ELSE NULL END;
        """,
    ),
    (
        6,
        """
        CREATE TABLE meshing_tasks (
            id TEXT PRIMARY KEY,
            automation_id INTEGER REFERENCES meshing_automations(id) ON DELETE SET NULL,
            template_revision INTEGER NOT NULL,
            template_snapshot_json TEXT NOT NULL,
            model_snapshot_json TEXT NOT NULL,
            session_id TEXT UNIQUE,
            status TEXT NOT NULL CHECK (
                status IN ('queued', 'preparing', 'waiting_surface', 'waiting_volume',
                           'completed', 'failed', 'stopped', 'interrupted')
            ),
            surface_mesh_status TEXT NOT NULL DEFAULT 'pending',
            volume_mesh_status TEXT NOT NULL DEFAULT 'pending',
            phase TEXT NOT NULL DEFAULT 'queued',
            message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE INDEX meshing_tasks_created ON meshing_tasks(created_at DESC);
        CREATE INDEX meshing_tasks_status ON meshing_tasks(status, created_at);
        """,
    ),
    (
        7,
        """
        ALTER TABLE meshing_tasks ADD COLUMN deleted_at TEXT;
        ALTER TABLE meshing_result_archives ADD COLUMN task_id TEXT
            REFERENCES meshing_tasks(id) ON DELETE SET NULL;

        CREATE TABLE meshing_task_artifacts (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES meshing_tasks(id) ON DELETE RESTRICT,
            archive_id TEXT REFERENCES meshing_result_archives(id) ON DELETE SET NULL,
            kind TEXT NOT NULL CHECK (kind IN (
                'mesh', 'record_json', 'record_markdown', 'log', 'report'
            )),
            file_path TEXT NOT NULL,
            file_size INTEGER,
            status TEXT NOT NULL CHECK (status IN ('retained', 'missing', 'deleted')),
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(task_id, file_path)
        );
        CREATE INDEX meshing_task_artifacts_task
            ON meshing_task_artifacts(task_id, created_at DESC);
        CREATE INDEX meshing_task_artifacts_path
            ON meshing_task_artifacts(file_path);

        CREATE TABLE meshing_task_events (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES meshing_tasks(id) ON DELETE RESTRICT,
            event_type TEXT NOT NULL,
            status TEXT NOT NULL,
            phase TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX meshing_task_events_task
            ON meshing_task_events(task_id, created_at, id);
        """,
    ),
    (
        8,
        """
        INSERT INTO part_categories(id, name, description, is_system, created_at, updated_at)
        SELECT lower(hex(randomblob(16))), '文丘里', '', 0,
               strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
               strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE NOT EXISTS (SELECT 1 FROM part_categories WHERE name = '文丘里')
          AND EXISTS (
              SELECT 1 FROM meshing_automations
              WHERE model_family = '文丘里'
                 OR (lower(name) = 'localsize' AND model_family = '')
          );

        UPDATE meshing_automations
        SET category_id = (SELECT id FROM part_categories WHERE name = '文丘里'),
            model_family = '文丘里'
        WHERE model_family = '文丘里'
           OR (lower(name) = 'localsize' AND model_family = '');
        """,
    ),
    (
        9,
        """
        INSERT INTO part_categories(id, name, description, is_system, created_at, updated_at)
        SELECT lower(hex(randomblob(16))), trim(a.model_family), '', 0,
               strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
               strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        FROM meshing_automations a
        WHERE trim(COALESCE(a.model_family, '')) <> ''
          AND NOT EXISTS (
              SELECT 1 FROM part_categories c WHERE c.name = trim(a.model_family)
          )
        GROUP BY trim(a.model_family);

        UPDATE meshing_automations
        SET category_id = (
            SELECT c.id FROM part_categories c WHERE c.name = trim(meshing_automations.model_family)
        )
        WHERE category_id = 'uncategorized'
          AND trim(COALESCE(model_family, '')) <> '';
        """,
    ),
    (
        10,
        """
        CREATE TABLE agent_templates (
            template_id INTEGER PRIMARY KEY REFERENCES meshing_automations(id) ON DELETE CASCADE,
            agno_agent_id TEXT NOT NULL UNIQUE,
            agno_session_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE agent_runs (
            id TEXT PRIMARY KEY,
            template_id INTEGER NOT NULL REFERENCES meshing_automations(id) ON DELETE CASCADE,
            agno_session_id TEXT NOT NULL,
            agno_run_id TEXT,
            client_message_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('running', 'completed', 'failed', 'interrupted')
            ),
            user_message TEXT NOT NULL,
            assistant_message TEXT NOT NULL DEFAULT '',
            error TEXT,
            created_at TEXT NOT NULL,
            finished_at TEXT
        );
        CREATE UNIQUE INDEX agent_runs_client_message
            ON agent_runs(template_id, client_message_id);
        CREATE INDEX agent_runs_template ON agent_runs(template_id, created_at DESC);

        CREATE UNIQUE INDEX agent_runs_one_running_per_template
            ON agent_runs(template_id) WHERE status = 'running';

        CREATE TABLE agent_run_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX agent_run_events_run ON agent_run_events(run_id, id);

        UPDATE agent_runs SET status = 'interrupted',
            error = 'Agent run was interrupted when the application closed.',
            finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE status = 'running';
        """,
    ),
    (
        11,
        """
        ALTER TABLE agent_runs
            ADD COLUMN model_snapshot_json TEXT NOT NULL DEFAULT '{}';
        """,
    ),
    (
        12,
        """
        ALTER TABLE agent_runs ADD COLUMN run_kind TEXT NOT NULL DEFAULT 'chat';
        ALTER TABLE agent_runs ADD COLUMN trigger_key TEXT;
        ALTER TABLE agent_runs ADD COLUMN response_json TEXT NOT NULL DEFAULT '{}';
        CREATE UNIQUE INDEX agent_runs_proactive_trigger
            ON agent_runs(template_id, trigger_key)
            WHERE trigger_key IS NOT NULL;

        CREATE TABLE agent_knowledge_sources (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            source_files_json TEXT NOT NULL,
            allowed_tools_json TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL
        );
        CREATE TABLE agent_category_knowledge (
            category_id TEXT NOT NULL REFERENCES part_categories(id) ON DELETE CASCADE,
            knowledge_source_id TEXT NOT NULL REFERENCES agent_knowledge_sources(id)
                ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            PRIMARY KEY (category_id, knowledge_source_id)
        );

        INSERT INTO agent_knowledge_sources(
            id, display_name, source_files_json, allowed_tools_json, enabled, created_at
        ) VALUES (
            'venturi-boundary-layer-v2',
            '文丘里边界层规则',
            '["原有_层数推荐算法说明.md","Uniform_First_Height_计算封装说明.md"]',
            '["calculate_smooth_layers","calculate_uniform_first_height"]',
            1,
            strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        );
        INSERT INTO agent_category_knowledge(category_id, knowledge_source_id, created_at)
        SELECT id, 'venturi-boundary-layer-v2', strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        FROM part_categories
        WHERE lower(name) LIKE '%venturi%' OR name LIKE '%文丘里%';
        """,
    ),
)


class Database:
    """Small SQLite wrapper using a connection per operation.

    A long-lived keeper connection stays open so the WAL sidecar files are
    never deleted between short-lived connections. On Windows the last
    connection closing a WAL database removes its ``-wal``/``-shm`` files; a
    new connection racing that removal can observe the database as read-only
    (``SQLITE_READONLY``) when it later writes. Holding the keeper open for
    the lifetime of this object prevents the race.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._keeper: sqlite3.Connection | None = None
        self._keeper_lock = threading.Lock()
        # Serializes transactional blocks. Concurrent WAL writers on Windows
        # can hit transient SQLITE_READONLY errors when the OS briefly denies
        # access to the WAL sidecar files (antivirus scans are a common
        # trigger); one writer at a time avoids the race entirely.
        self._access_lock = threading.RLock()

    def _ensure_keeper(self) -> None:
        if self._keeper is not None:
            return
        with self._keeper_lock:
            if self._keeper is not None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            keeper = sqlite3.connect(self.path, timeout=5.0, check_same_thread=False)
            keeper.execute("PRAGMA busy_timeout = 5000")
            keeper.execute("PRAGMA journal_mode = WAL")
            self._keeper = keeper

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Run one transactional block with exclusive access to this database.

        The lock serializes writers process-wide; SQLite operations here are
        short-lived, so contention is negligible, and single-writer access
        sidesteps transient Windows WAL lock errors under concurrency.
        """
        with self._access_lock, self._single_connection() as connection:
            yield connection

    @contextmanager
    def _single_connection(self) -> Iterator[sqlite3.Connection]:
        self._ensure_keeper()
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
