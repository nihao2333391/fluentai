"""Model library persistence and automation associations."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from app.database import Database
from app.domain import ModelAutomationAssociate, ModelCreate, ModelRead, ModelUpdate
from app.repositories.common import dump_json, load_json, utc_now
from app.repositories.errors import RepositoryConflictError, RepositoryNotFoundError


class ModelRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list(self) -> list[ModelRead]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM models ORDER BY updated_at DESC, id DESC"
            ).fetchall()
            return [self._row_to_model(connection, row) for row in rows]

    def get(self, model_id: int) -> ModelRead:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
            if row is None:
                raise RepositoryNotFoundError(f"Model {model_id} was not found.")
            return self._row_to_model(connection, row)

    def create(self, payload: ModelCreate) -> ModelRead:
        path = self._validated_file(payload.file_path)
        stat = path.stat()
        now = utc_now()
        try:
            with self.database.connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO models(
                        name, file_path, file_size, file_mtime, description, tags_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload.name,
                        str(path),
                        stat.st_size,
                        datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                        payload.description,
                        dump_json(payload.tags),
                        now,
                        now,
                    ),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("Model insert did not return an id.")
                model_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflictError(f"Model file {str(path)!r} already exists.") from exc
        return self.get(model_id)

    def update(self, model_id: int, payload: ModelUpdate) -> ModelRead:
        path = self._validated_file(payload.file_path)
        stat = path.stat()
        try:
            with self.database.connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE models
                    SET name = ?, file_path = ?, file_size = ?, file_mtime = ?,
                        description = ?, tags_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload.name,
                        str(path),
                        stat.st_size,
                        datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                        payload.description,
                        dump_json(payload.tags),
                        utc_now(),
                        model_id,
                    ),
                )
                if cursor.rowcount == 0:
                    raise RepositoryNotFoundError(f"Model {model_id} was not found.")
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflictError(f"Model file {str(path)!r} already exists.") from exc
        return self.get(model_id)

    def delete(self, model_id: int) -> None:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM models WHERE id = ?", (model_id,))
            if cursor.rowcount == 0:
                raise RepositoryNotFoundError(f"Model {model_id} was not found.")

    def associate(self, model_id: int, payload: ModelAutomationAssociate) -> ModelRead:
        now = utc_now()
        with self.database.connect() as connection:
            if (
                connection.execute("SELECT 1 FROM models WHERE id = ?", (model_id,)).fetchone()
                is None
            ):
                raise RepositoryNotFoundError(f"Model {model_id} was not found.")
            if (
                connection.execute(
                    "SELECT 1 FROM automations WHERE id = ?", (payload.automation_id,)
                ).fetchone()
                is None
            ):
                raise RepositoryNotFoundError(f"Automation {payload.automation_id} was not found.")

            if payload.is_default:
                connection.execute(
                    "UPDATE model_automations SET is_default = 0 WHERE model_id = ?",
                    (model_id,),
                )
            connection.execute(
                """
                INSERT INTO model_automations(model_id, automation_id, is_default, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(model_id, automation_id)
                DO UPDATE SET is_default = excluded.is_default
                """,
                (model_id, payload.automation_id, int(payload.is_default), now),
            )
        return self.get(model_id)

    @staticmethod
    def _validated_file(file_path: str) -> Path:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Model file does not exist: {path}")
        return path

    @staticmethod
    def _row_to_model(connection: sqlite3.Connection, row: sqlite3.Row) -> ModelRead:
        associations = connection.execute(
            """
            SELECT automation_id, is_default
            FROM model_automations
            WHERE model_id = ?
            ORDER BY automation_id
            """,
            (int(row["id"]),),
        ).fetchall()
        default_automation_id = next(
            (int(item["automation_id"]) for item in associations if int(item["is_default"]) == 1),
            None,
        )
        return ModelRead(
            id=int(row["id"]),
            name=str(row["name"]),
            file_path=str(row["file_path"]),
            file_size=int(row["file_size"]),
            file_mtime=cast(str | None, row["file_mtime"]),
            description=str(row["description"]),
            tags=cast(list[str], load_json(cast(str, row["tags_json"]), [])),
            automation_ids=[int(item["automation_id"]) for item in associations],
            default_automation_id=default_automation_id,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
