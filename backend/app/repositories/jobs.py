"""Background job persistence."""

import sqlite3
from typing import Literal, cast
from uuid import uuid4

from app.database import Database
from app.domain import JobCreate, JobRead
from app.repositories.common import dump_json, load_json, utc_now
from app.repositories.errors import RepositoryNotFoundError

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class JobRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, payload: JobCreate) -> JobRead:
        job_id = str(uuid4())
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs(
                    id, job_type, status, progress, message, payload_json,
                    created_at, updated_at
                ) VALUES (?, ?, 'queued', 0, '', ?, ?, ?)
                """,
                (job_id, payload.job_type, dump_json(payload.payload), now, now),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> JobRead:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise RepositoryNotFoundError(f"Job {job_id} was not found.")
        return self._row_to_model(row)

    def list(self, limit: int = 50) -> list[JobRead]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_model(row) for row in rows]

    def is_cancelled(self, job_id: str) -> bool:
        return self.get(job_id).status == "cancelled"

    def cancel(self, job_id: str) -> JobRead:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = 'cancelled', message = 'Cancelled by user.',
                    updated_at = ?, finished_at = COALESCE(finished_at, ?)
                WHERE id = ? AND status IN ('queued', 'running')
                """,
                (now, now, job_id),
            )
        return self.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus,
        progress: int,
        message: str = "",
        result: dict[str, object] | None = None,
        error: str | None = None,
    ) -> JobRead:
        now = utc_now()
        started_at = now if status == "running" else None
        finished_at = now if status in {"succeeded", "failed", "cancelled"} else None
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, progress = ?, message = ?, result_json = ?, error = ?,
                    updated_at = ?, started_at = COALESCE(started_at, ?), finished_at = ?
                WHERE id = ? AND status <> 'cancelled'
                """,
                (
                    status,
                    max(0, min(100, progress)),
                    message,
                    dump_json(result) if result is not None else None,
                    error,
                    now,
                    started_at,
                    finished_at,
                    job_id,
                ),
            )
            if cursor.rowcount == 0:
                # A cancelled job is terminal and must not be overwritten by the worker.
                return self.get(job_id)
        return self.get(job_id)

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> JobRead:
        return JobRead(
            id=str(row["id"]),
            job_type=str(row["job_type"]),
            status=cast(JobStatus, row["status"]),
            progress=int(row["progress"]),
            message=str(row["message"]),
            payload=cast(dict[str, object], load_json(cast(str, row["payload_json"]), {})),
            result=cast(
                dict[str, object] | None,
                load_json(cast(str | None, row["result_json"]), None),
            ),
            error=cast(str | None, row["error"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            started_at=cast(str | None, row["started_at"]),
            finished_at=cast(str | None, row["finished_at"]),
        )
