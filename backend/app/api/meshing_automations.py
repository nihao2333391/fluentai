"""Authenticated Fluent Meshing automation and schema endpoints."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import DatabaseDependency, MeshingServiceDependency
from app.domain import (
    ApplyMeshingAutomationRequest,
    FluentConnectionConfig,
    FluentStatus,
    MeshingAutomationCreate,
    MeshingAutomationRead,
    MeshingAutomationUpdate,
    MeshingPresetDocument,
    MeshingPresetValidationReport,
    MeshingReadReport,
    MeshingReadRequest,
    MeshingSchemaSummary,
    MeshingWorkflowReport,
    MeshingWriteReport,
    MeshingWriteRequest,
)
from app.meshing.schema_index import MESHING_SCHEMA_INDEX
from app.repositories.meshing_automations import MeshingAutomationRepository

router = APIRouter(tags=["meshing"])


@router.get("/meshing/status", response_model=FluentStatus)
def get_meshing_status(meshing: MeshingServiceDependency) -> FluentStatus:
    return meshing.status()


@router.post("/meshing/connect", response_model=FluentStatus)
def connect_meshing(
    payload: FluentConnectionConfig,
    meshing: MeshingServiceDependency,
) -> FluentStatus:
    return meshing.connect(payload)


@router.post("/meshing/disconnect", response_model=FluentStatus)
def disconnect_meshing(meshing: MeshingServiceDependency) -> FluentStatus:
    return meshing.disconnect()


@router.post("/meshing/read", response_model=MeshingReadReport)
def read_meshing_arguments(
    payload: MeshingReadRequest,
    meshing: MeshingServiceDependency,
) -> MeshingReadReport:
    return meshing.read_arguments(payload)


@router.post("/meshing/write", response_model=MeshingWriteReport)
def write_meshing_arguments(
    payload: MeshingWriteRequest,
    meshing: MeshingServiceDependency,
) -> MeshingWriteReport:
    return meshing.write_arguments(payload)


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


@router.get("/meshing/schemas/{workflow_type}")
def get_meshing_schema(
    workflow_type: Literal["watertight", "fault-tolerant"],
) -> dict[str, Any]:
    schema = MESHING_SCHEMA_INDEX.schemas.get(workflow_type)
    if schema is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown Meshing workflow type: {workflow_type}",
        )
    return schema


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


@router.post(
    "/meshing-automations/{automation_id}/apply",
    response_model=MeshingWorkflowReport,
)
def apply_meshing_automation(
    automation_id: int,
    payload: ApplyMeshingAutomationRequest,
    meshing: MeshingServiceDependency,
) -> MeshingWorkflowReport:
    return meshing.apply_automation(automation_id, payload)
