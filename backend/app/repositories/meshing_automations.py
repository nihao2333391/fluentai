"""Persistence for Fluent Meshing automation presets."""

import sqlite3
from typing import Literal, cast

from app.database import Database
from app.domain import (
    MeshingAutomationCreate,
    MeshingAutomationRead,
    MeshingAutomationUpdate,
    MeshingPresetDocument,
)
from app.repositories.common import dump_json, utc_now
from app.repositories.errors import RepositoryConflictError, RepositoryNotFoundError


class MeshingAutomationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list(self) -> list[MeshingAutomationRead]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM meshing_automations ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [self._row_to_model(row) for row in rows]

    def get(self, automation_id: int) -> MeshingAutomationRead:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM meshing_automations WHERE id = ?", (automation_id,)
            ).fetchone()
        if row is None:
            raise RepositoryNotFoundError(f"Meshing automation {automation_id} was not found.")
        return self._row_to_model(row)

    def create(self, payload: MeshingAutomationCreate) -> MeshingAutomationRead:
        now = utc_now()
        try:
            with self.database.connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO meshing_automations(
                        name, description, model_family, reference_model_id,
                        workflow_type, preset_json, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload.name,
                        payload.description,
                        payload.model_family,
                        payload.reference_model_id,
                        payload.preset.workflow_type,
                        dump_json(payload.preset.model_dump(mode="json")),
                        payload.status,
                        now,
                        now,
                    ),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("Meshing automation insert did not return an id.")
                automation_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflictError(
                f"A Meshing automation named {payload.name!r} already exists "
                "or its reference model is invalid."
            ) from exc
        return self.get(automation_id)

    def update(
        self,
        automation_id: int,
        payload: MeshingAutomationUpdate,
    ) -> MeshingAutomationRead:
        try:
            with self.database.connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE meshing_automations
                    SET name = ?, description = ?, model_family = ?, reference_model_id = ?,
                        workflow_type = ?, preset_json = ?, status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload.name,
                        payload.description,
                        payload.model_family,
                        payload.reference_model_id,
                        payload.preset.workflow_type,
                        dump_json(payload.preset.model_dump(mode="json")),
                        payload.status,
                        utc_now(),
                        automation_id,
                    ),
                )
                if cursor.rowcount == 0:
                    raise RepositoryNotFoundError(
                        f"Meshing automation {automation_id} was not found."
                    )
        except sqlite3.IntegrityError as exc:
            raise RepositoryConflictError(
                f"A Meshing automation named {payload.name!r} already exists "
                "or its reference model is invalid."
            ) from exc
        return self.get(automation_id)

    def delete(self, automation_id: int) -> None:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM meshing_automations WHERE id = ?", (automation_id,)
            )
            if cursor.rowcount == 0:
                raise RepositoryNotFoundError(f"Meshing automation {automation_id} was not found.")

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> MeshingAutomationRead:
        return MeshingAutomationRead(
            id=int(row["id"]),
            name=str(row["name"]),
            description=str(row["description"]),
            model_family=str(row["model_family"]),
            reference_model_id=cast(int | None, row["reference_model_id"]),
            preset=MeshingPresetDocument.model_validate_json(cast(str, row["preset_json"])),
            status=cast(Literal["draft", "active"], row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
