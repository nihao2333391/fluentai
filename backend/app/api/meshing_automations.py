"""Authenticated Fluent Meshing automation and schema endpoints."""

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import DatabaseDependency
from app.domain import (
    MeshingAutomationCreate,
    MeshingAutomationRead,
    MeshingAutomationUpdate,
    MeshingPresetDocument,
    MeshingPresetValidationReport,
    MeshingSchemaSummary,
)
from app.meshing.schema_index import MESHING_SCHEMA_INDEX
from app.repositories.meshing_automations import MeshingAutomationRepository

router = APIRouter(tags=["meshing"])


def _validate_preset(preset: MeshingPresetDocument) -> MeshingPresetValidationReport:
    report = MESHING_SCHEMA_INDEX.validate(preset)
    if not report.valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "Meshing preset validation failed.", "errors": report.errors},
        )
    return report


@router.get("/meshing/schemas", response_model=list[MeshingSchemaSummary])
def list_meshing_schemas() -> list[MeshingSchemaSummary]:
    return MESHING_SCHEMA_INDEX.summaries()


@router.post("/meshing/presets/validate", response_model=MeshingPresetValidationReport)
def validate_meshing_preset(preset: MeshingPresetDocument) -> MeshingPresetValidationReport:
    return MESHING_SCHEMA_INDEX.validate(preset)


@router.get("/meshing-automations", response_model=list[MeshingAutomationRead])
def list_meshing_automations(database: DatabaseDependency) -> list[MeshingAutomationRead]:
    return MeshingAutomationRepository(database).list()


@router.post(
    "/meshing-automations",
    response_model=MeshingAutomationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_meshing_automation(
    payload: MeshingAutomationCreate,
    database: DatabaseDependency,
) -> MeshingAutomationRead:
    _validate_preset(payload.preset)
    return MeshingAutomationRepository(database).create(payload)


@router.get("/meshing-automations/{automation_id}", response_model=MeshingAutomationRead)
def get_meshing_automation(
    automation_id: int,
    database: DatabaseDependency,
) -> MeshingAutomationRead:
    return MeshingAutomationRepository(database).get(automation_id)


@router.put("/meshing-automations/{automation_id}", response_model=MeshingAutomationRead)
def update_meshing_automation(
    automation_id: int,
    payload: MeshingAutomationUpdate,
    database: DatabaseDependency,
) -> MeshingAutomationRead:
    _validate_preset(payload.preset)
    return MeshingAutomationRepository(database).update(automation_id, payload)


@router.delete("/meshing-automations/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meshing_automation(
    automation_id: int,
    database: DatabaseDependency,
) -> Response:
    MeshingAutomationRepository(database).delete(automation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/meshing-automations/{automation_id}/validate",
    response_model=MeshingPresetValidationReport,
)
def validate_saved_meshing_automation(
    automation_id: int,
    database: DatabaseDependency,
) -> MeshingPresetValidationReport:
    automation = MeshingAutomationRepository(database).get(automation_id)
    return MESHING_SCHEMA_INDEX.validate(automation.preset)
