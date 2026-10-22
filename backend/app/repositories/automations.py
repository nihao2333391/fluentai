"""Automation persistence."""

import sqlite3
from typing import Literal, cast

from app.database import Database
from app.domain import AutomationCreate, AutomationRead, AutomationUpdate, PresetDocument
from app.repositories.common import dump_json, utc_now
from app.repositories.errors import RepositoryConflictError, RepositoryNotFoundError


class AutomationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list(self) -> list[AutomationRead]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM automations ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [self._row_to_model(row) for row in rows]

    def get(self, automation_id: int) -> AutomationRead:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM automations WHERE id = ?", (automation_id,)
            ).fetchone()
        if row is None:
            raise RepositoryNotFoundError(f"Automation {automation_id} was not found.")
        return self._row_to_model(row)

    def create(self, payload: AutomationCreate) -> AutomationRead:
        now = utc_now()
        try:
            with self.database.connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO automations(
                        name, description, preset_json, status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload.name,
                        payload.description,
                        dump_json(payload.preset.model_dump(mode="json")),
                        payload.status,
                        now,
                        now,
                    ),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("Automation insert did not return an id.")
                automation_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflictError(
                f"An automation named {payload.name!r} already exists."
            ) from exc
        return self.get(automation_id)

    def update(self, automation_id: int, payload: AutomationUpdate) -> AutomationRead:
        now = utc_now()
        try:
            with self.database.connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE automations
                    SET name = ?, description = ?, preset_json = ?, status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload.name,
                        payload.description,
                        dump_json(payload.preset.model_dump(mode="json")),
                        payload.status,
                        now,
                        automation_id,
                    ),
                )
                if cursor.rowcount == 0:
                    raise RepositoryNotFoundError(f"Automation {automation_id} was not found.")
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflictError(
                f"An automation named {payload.name!r} already exists."
            ) from exc
        return self.get(automation_id)

    def delete(self, automation_id: int) -> None:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM automations WHERE id = ?", (automation_id,))
            if cursor.rowcount == 0:
                raise RepositoryNotFoundError(f"Automation {automation_id} was not found.")

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> AutomationRead:
        preset = PresetDocument.model_validate_json(cast(str, row["preset_json"]))
        return AutomationRead(
            id=int(row["id"]),
            name=str(row["name"]),
            description=str(row["description"]),
            preset=preset,
            status=cast(Literal["draft", "active"], row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
