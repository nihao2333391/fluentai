"""Synchronization log persistence."""

import sqlite3
from typing import Literal, cast

from app.database import Database
from app.domain import SyncLogCreate, SyncLogRead
from app.repositories.common import dump_json, load_json, utc_now

LogDirection = Literal["read", "write", "sync", "apply", "pull"]
LogStatus = Literal["success", "failed"]


class SyncLogRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, payload: SyncLogCreate) -> SyncLogRead:
        now = utc_now()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO sync_logs(
                    direction, target, automation_id, meshing_automation_id,
                    model_id, payload_json, status, message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.direction,
                    payload.target,
                    payload.automation_id,
                    payload.meshing_automation_id,
                    payload.model_id,
                    dump_json(payload.payload),
                    payload.status,
                    payload.message,
                    now,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("Sync log insert did not return an id.")
            log_id = int(cursor.lastrowid)
            row = connection.execute("SELECT * FROM sync_logs WHERE id = ?", (log_id,)).fetchone()
        if row is None:
            raise RuntimeError("Created sync log could not be read back.")
        return self._row_to_model(row)

    def list(
        self,
        limit: int = 100,
        *,
        direction: LogDirection | None = None,
        status: LogStatus | None = None,
        automation_id: int | None = None,
        meshing_automation_id: int | None = None,
        model_id: int | None = None,
        search: str | None = None,
    ) -> list[SyncLogRead]:
        clauses: list[str] = []
        values: list[object] = []
        if direction is not None:
            clauses.append("direction = ?")
            values.append(direction)
        if status is not None:
            clauses.append("status = ?")
            values.append(status)
        if automation_id is not None:
            clauses.append("automation_id = ?")
            values.append(automation_id)
        if meshing_automation_id is not None:
            clauses.append("meshing_automation_id = ?")
            values.append(meshing_automation_id)
        if model_id is not None:
            clauses.append("model_id = ?")
            values.append(model_id)
        if search:
            clauses.append("(target LIKE ? OR message LIKE ? OR payload_json LIKE ?)")
            pattern = f"%{search}%"
            values.extend([pattern, pattern, pattern])
        where = f"WHERE {' AND '.join(clauses)} " if clauses else ""
        values.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM sync_logs {where}ORDER BY created_at DESC, id DESC LIMIT ?",
                values,
            ).fetchall()
        return [self._row_to_model(row) for row in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> SyncLogRead:
        return SyncLogRead(
            id=int(row["id"]),
            direction=cast(LogDirection, row["direction"]),
            target=str(row["target"]),
            automation_id=cast(int | None, row["automation_id"]),
            meshing_automation_id=cast(int | None, row["meshing_automation_id"]),
            model_id=cast(int | None, row["model_id"]),
            payload=cast(dict[str, object], load_json(cast(str, row["payload_json"]), {})),
            status=cast(LogStatus, row["status"]),
            message=str(row["message"]),
            created_at=str(row["created_at"]),
        )
