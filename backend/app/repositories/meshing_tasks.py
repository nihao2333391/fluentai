"""Persistence for template applications and their Fluent execution state."""

from __future__ import annotations

import builtins
import json
import sqlite3
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from app.database import Database
from app.domain import (
    MeshingLiveSessionSnapshot,
    MeshingTaskArtifactRead,
    MeshingTaskEventRead,
    MeshingTaskHistoryRead,
    MeshingTaskRead,
)
from app.repositories.common import dump_json, utc_now
from app.repositories.errors import RepositoryNotFoundError


class MeshingTaskRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        task_id: str,
        automation_id: int | None,
        automation_name: str,
        template_revision: int,
        template_snapshot: dict[str, Any],
        models: list[dict[str, Any]],
        session_id: str,
    ) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO meshing_tasks(
                    id, automation_id, template_revision, template_snapshot_json,
                    model_snapshot_json, session_id, status, phase, message,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'queued', 'queued', ?, ?, ?)""",
                (
                    task_id,
                    automation_id,
                    template_revision,
                    dump_json({"name": automation_name, **template_snapshot}),
                    dump_json(models),
                    session_id,
                    "等待 Fluent 连接。",
                    now,
                    now,
                ),
            )
            self._add_event(
                connection, task_id, "task_created", "queued", "queued", "任务已创建并进入队列。"
            )

    def sync(self, snapshot: MeshingLiveSessionSnapshot) -> None:
        status = self._status(snapshot)
        surface = self._stage_status(snapshot, "create_surface_mesh")
        volume = self._stage_status(snapshot, "create_volume_mesh")
        now = utc_now()
        completed_at = now if status in {"completed", "failed", "stopped", "interrupted"} else None
        with self.database.connect() as connection:
            previous = connection.execute(
                "SELECT status, phase, message FROM meshing_tasks WHERE id=?",
                (snapshot.task_id,),
            ).fetchone()
            if previous is None:
                return
            connection.execute(
                """UPDATE meshing_tasks
                   SET status=?, surface_mesh_status=?, volume_mesh_status=?,
                       phase=?, message=?, updated_at=?,
                       completed_at=COALESCE(?, completed_at)
                   WHERE id=?""",
                (
                    status,
                    surface,
                    volume,
                    snapshot.phase,
                    snapshot.message,
                    now,
                    completed_at,
                    snapshot.task_id,
                ),
            )
            if (
                previous["status"] != status
                or previous["phase"] != snapshot.phase
                or previous["message"] != snapshot.message
            ):
                self._add_event(
                    connection,
                    snapshot.task_id,
                    "state_changed",
                    status,
                    snapshot.phase,
                    snapshot.message,
                )

    def list(
        self, limit: int = 100, include_deleted: bool = False
    ) -> builtins.list[MeshingTaskRead]:
        deleted_filter = "" if include_deleted else "WHERE task.deleted_at IS NULL"
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""SELECT task.*,
                    (SELECT COUNT(*) FROM meshing_task_artifacts artifact
                     WHERE artifact.task_id = task.id) AS artifact_count
                    FROM meshing_tasks task {deleted_filter}
                    ORDER BY task.created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [self._to_read(row) for row in rows]

    def get(self, task_id: str, include_deleted: bool = False) -> MeshingTaskRead:
        deleted_filter = "" if include_deleted else "AND deleted_at IS NULL"
        with self.database.connect() as connection:
            row = connection.execute(
                f"""SELECT task.*,
                    (SELECT COUNT(*) FROM meshing_task_artifacts artifact
                     WHERE artifact.task_id = task.id) AS artifact_count
                    FROM meshing_tasks task WHERE task.id=? {deleted_filter}""",
                (task_id,),
            ).fetchone()
        if row is None:
            raise RepositoryNotFoundError(f"Meshing task {task_id} was not found.")
        return self._to_read(row)

    def history(self, task_id: str, include_deleted: bool = False) -> MeshingTaskHistoryRead:
        task = self.get(task_id, include_deleted=include_deleted)
        with self.database.connect() as connection:
            artifact_rows = connection.execute(
                "SELECT * FROM meshing_task_artifacts WHERE task_id=? ORDER BY created_at, id",
                (task_id,),
            ).fetchall()
            event_rows = connection.execute(
                "SELECT * FROM meshing_task_events WHERE task_id=? ORDER BY created_at, id",
                (task_id,),
            ).fetchall()
        return MeshingTaskHistoryRead(
            task=task,
            artifacts=[self._artifact_read(row) for row in artifact_rows],
            events=[self._event_read(row) for row in event_rows],
        )

    def artifacts(self, task_id: str) -> builtins.list[MeshingTaskArtifactRead]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM meshing_task_artifacts WHERE task_id=? ORDER BY created_at, id",
                (task_id,),
            ).fetchall()
        return [self._artifact_read(row) for row in rows]

    def register_archive(
        self,
        task_id: str,
        archive_id: str,
        files: builtins.list[tuple[str, str]],
    ) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE meshing_result_archives SET task_id=? WHERE id=?",
                (task_id, archive_id),
            )
            for kind, raw_path in files:
                path = Path(raw_path)
                exists = path.is_file()
                connection.execute(
                    """INSERT OR IGNORE INTO meshing_task_artifacts(
                        id, task_id, archive_id, kind, file_path, file_size,
                        status, created_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}')""",
                    (
                        str(uuid4()),
                        task_id,
                        archive_id,
                        kind,
                        raw_path,
                        path.stat().st_size if exists else None,
                        "retained" if exists else "missing",
                        now,
                    ),
                )
            self._add_event(
                connection,
                task_id,
                "artifact_archived",
                "completed",
                "archived",
                "网格、参数记录和说明文件已归档。",
                {"archive_id": archive_id},
            )

    def add_event(
        self,
        task_id: str,
        event_type: str,
        status: str,
        phase: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.database.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM meshing_tasks WHERE id=?", (task_id,)
            ).fetchone()
            if exists is None:
                return
            self._add_event(connection, task_id, event_type, status, phase, message, payload)

    def mark_artifact_status(self, artifact_id: str, status: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE meshing_task_artifacts SET status=? WHERE id=?",
                (status, artifact_id),
            )

    def soft_delete(self, task_id: str, message: str) -> MeshingTaskRead:
        now = utc_now()
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE meshing_tasks SET deleted_at=?, updated_at=? "
                "WHERE id=? AND deleted_at IS NULL",
                (now, now, task_id),
            )
            if cursor.rowcount == 0:
                raise RepositoryNotFoundError(f"Meshing task {task_id} was not found.")
            self._add_event(connection, task_id, "task_deleted", "deleted", "deleted", message)
        return self.get(task_id, include_deleted=True)

    def backfill_legacy_archives(self) -> None:
        """Attach existing archive files to durable history tasks, idempotently."""
        with self.database.connect() as connection:
            archives = connection.execute(
                """SELECT archive.*, automation.name AS automation_name,
                          model.name AS model_name, model.file_path AS model_path
                   FROM meshing_result_archives archive
                   LEFT JOIN meshing_automations automation ON automation.id=archive.automation_id
                   LEFT JOIN models model ON model.id=archive.model_id
                   WHERE archive.task_id IS NULL ORDER BY archive.created_at, archive.id"""
            ).fetchall()
            grouped: dict[str, list[sqlite3.Row]] = {}
            for archive in archives:
                grouped.setdefault(str(archive["session_id"]), []).append(archive)
            for session_id, rows in grouped.items():
                existing = connection.execute(
                    "SELECT id FROM meshing_tasks WHERE session_id=?", (session_id,)
                ).fetchone()
                task_id = str(existing["id"]) if existing else f"legacy-{session_id}"
                if existing is None:
                    models = []
                    automation_id = rows[0]["automation_id"]
                    automation_name = rows[0]["automation_name"] or "历史归档"
                    created_at = str(rows[0]["created_at"])
                    for archive in rows:
                        record = self._load_legacy_record(str(archive["record_json_path"]))
                        models.append(
                            {
                                "id": archive["model_id"],
                                "name": (
                                    record.get("model_name") or archive["model_name"] or "历史模型"
                                ),
                                "file_path": (
                                    record.get("model_path") or archive["model_path"] or ""
                                ),
                            }
                        )
                    connection.execute(
                        """INSERT INTO meshing_tasks(
                            id, automation_id, template_revision, template_snapshot_json,
                            model_snapshot_json, session_id, status, surface_mesh_status,
                            volume_mesh_status, phase, message, created_at, updated_at, completed_at
                        ) VALUES (?, ?, 0, ?, ?, ?, 'completed', 'completed', 'completed',
                                  'completed', ?, ?, ?, ?)""",
                        (
                            task_id,
                            automation_id,
                            dump_json({"name": automation_name, "legacy_snapshot_missing": True}),
                            dump_json(models),
                            session_id,
                            "由旧网格归档重建历史索引；原任务和模板快照不可用。",
                            created_at,
                            created_at,
                            created_at,
                        ),
                    )
                    self._add_event(
                        connection,
                        task_id,
                        "legacy_archive_indexed",
                        "completed",
                        "completed",
                        "由既有网格归档重建历史任务索引。",
                    )
                for archive in rows:
                    archive_id = str(archive["id"])
                    connection.execute(
                        "UPDATE meshing_result_archives SET task_id=? WHERE id=?",
                        (task_id, archive_id),
                    )
                    paths = [
                        ("mesh", str(archive["mesh_path"])),
                        ("record_json", str(archive["record_json_path"])),
                        ("record_markdown", str(archive["record_markdown_path"])),
                    ]
                    for kind, raw_path in paths:
                        path = Path(raw_path)
                        exists = path.is_file()
                        connection.execute(
                            """INSERT OR IGNORE INTO meshing_task_artifacts(
                                id, task_id, archive_id, kind, file_path, file_size,
                                status, created_at, metadata_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}')""",
                            (
                                str(uuid4()),
                                task_id,
                                archive_id,
                                kind,
                                raw_path,
                                path.stat().st_size if exists else None,
                                "retained" if exists else "missing",
                                str(archive["created_at"]),
                            ),
                        )

    @staticmethod
    def _load_legacy_record(path: str) -> dict[str, Any]:
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def mark_running_interrupted(self) -> None:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT id, status FROM meshing_tasks WHERE deleted_at IS NULL AND
                   status IN ('queued', 'preparing', 'waiting_surface', 'waiting_volume')"""
            ).fetchall()
            for row in rows:
                task_id = str(row["id"])
                if str(row["status"]) == "queued":
                    message = "应用重启时任务仍在排队，尚未启动执行。可重新提交任务。"
                    event_type = "queue_discarded"
                else:
                    message = "应用重启时，Fluent 执行尚未结束。请检查 Fluent 后重新创建任务。"
                    event_type = "execution_interrupted"
                now = utc_now()
                connection.execute(
                    """UPDATE meshing_tasks
                       SET status='interrupted', phase='interrupted', message=?,
                           updated_at=?, completed_at=? WHERE id=?""",
                    (message, now, now, task_id),
                )
                self._add_event(
                    connection,
                    task_id,
                    event_type,
                    "interrupted",
                    "interrupted",
                    message,
                )

    @staticmethod
    def _status(snapshot: MeshingLiveSessionSnapshot) -> str:
        if snapshot.status == "queued":
            return "queued"
        if snapshot.status == "completed":
            return "completed"
        if snapshot.status == "failed":
            return "failed"
        if snapshot.status == "stopped":
            return "stopped"
        if snapshot.phase == "surface_ready":
            return "waiting_surface"
        if snapshot.phase == "volume_ready":
            return "waiting_volume"
        return "preparing"

    @staticmethod
    def _to_read(row: sqlite3.Row) -> MeshingTaskRead:
        template = json.loads(cast(str, row["template_snapshot_json"]))
        models = json.loads(cast(str, row["model_snapshot_json"]))
        return MeshingTaskRead(
            id=str(row["id"]),
            automation_id=cast(int | None, row["automation_id"]),
            automation_name=str(template.get("name", "已删除模板")),
            template_revision=int(row["template_revision"]),
            model_names=[str(model.get("name", "未知模型")) for model in models],
            session_id=cast(str | None, row["session_id"]),
            status=cast(Any, row["status"]),
            surface_mesh_status=cast(Any, row["surface_mesh_status"]),
            volume_mesh_status=cast(Any, row["volume_mesh_status"]),
            phase=str(row["phase"]),
            message=str(row["message"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            completed_at=cast(str | None, row["completed_at"]),
            deleted_at=cast(str | None, row["deleted_at"]),
            artifact_count=int(row["artifact_count"]),
        )

    @staticmethod
    def _artifact_read(row: sqlite3.Row) -> MeshingTaskArtifactRead:
        return MeshingTaskArtifactRead(
            id=str(row["id"]),
            task_id=str(row["task_id"]),
            archive_id=cast(str | None, row["archive_id"]),
            kind=cast(Any, row["kind"]),
            file_path=str(row["file_path"]),
            file_size=cast(int | None, row["file_size"]),
            status=cast(Any, row["status"]),
            created_at=str(row["created_at"]),
            metadata=json.loads(cast(str, row["metadata_json"])),
        )

    @staticmethod
    def _event_read(row: sqlite3.Row) -> MeshingTaskEventRead:
        return MeshingTaskEventRead(
            id=str(row["id"]),
            task_id=str(row["task_id"]),
            event_type=str(row["event_type"]),
            status=str(row["status"]),
            phase=str(row["phase"]),
            message=str(row["message"]),
            payload=json.loads(cast(str, row["payload_json"])),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _add_event(
        connection: sqlite3.Connection,
        task_id: str,
        event_type: str,
        status: str,
        phase: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        connection.execute(
            """INSERT INTO meshing_task_events(
                id, task_id, event_type, status, phase, message, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()),
                task_id,
                event_type,
                status,
                phase,
                message,
                dump_json(payload or {}),
                utc_now(),
            ),
        )

    @staticmethod
    def _stage_status(snapshot: MeshingLiveSessionSnapshot, task_name: str) -> str:
        step = next(
            (item for item in snapshot.steps if item.task_path == [task_name]),
            None,
        )
        if step is not None and step.status == "failed":
            return "failed"
        if step is not None and step.status == "completed":
            return "completed"
        if snapshot.status == "completed":
            return "completed"
        if task_name == "create_surface_mesh":
            if snapshot.phase == "surface_ready":
                return "ready"
            if snapshot.phase == "generating_surface":
                return "running"
            if snapshot.phase in {"preparing_volume", "volume_ready", "generating_volume"}:
                return "completed"
        else:
            if snapshot.phase == "volume_ready":
                return "ready"
            if snapshot.phase == "generating_volume":
                return "running"
        return "pending"
