"""Authenticated Fluent Meshing automation and schema endpoints."""

import logging
import traceback
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import DatabaseDependency, MeshingServiceDependency
from app.domain import (
    ApplyMeshingAutomationRequest,
    FluentConnectionConfig,
    FluentStatus,
    MeshingArchiveCreate,
    MeshingArchiveRecord,
    MeshingAutomationCreate,
    MeshingAutomationRead,
    MeshingAutomationUpdate,
    MeshingLiveSessionSnapshot,
    MeshingLiveSessionStart,
    MeshingLiveStepReport,
    MeshingLiveStepRequest,
    MeshingLiveWriteRequest,
    MeshingPresetDocument,
    MeshingPresetValidationReport,
    MeshingReadReport,
    MeshingReadRequest,
    MeshingReferenceInspection,
    MeshingSchemaSummary,
    MeshingTaskDeleteReport,
    MeshingTaskDeleteRequest,
    MeshingTaskHistoryRead,
    MeshingTaskRead,
    MeshingWorkflowReport,
    MeshingWriteReport,
    MeshingWriteRequest,
)
from app.meshing.schema_index import MESHING_SCHEMA_INDEX
from app.meshing.workflow_contract import get_watertight_workflow_contract
from app.repositories.categories import PartCategoryRepository
from app.repositories.meshing_automations import MeshingAutomationRepository
from app.services.meshing_service import MeshingAdapterBusyError

router = APIRouter(tags=["meshing"])
logger = logging.getLogger(__name__)


@router.get("/meshing/tasks", response_model=list[MeshingTaskRead])
def list_meshing_tasks(
    meshing: MeshingServiceDependency,
    include_deleted: bool = False,
) -> list[MeshingTaskRead]:
    return meshing.list_meshing_tasks(include_deleted=include_deleted)


@router.get("/meshing/tasks/{task_id}/history", response_model=MeshingTaskHistoryRead)
def get_meshing_task_history(
    task_id: str,
    meshing: MeshingServiceDependency,
    include_deleted: bool = False,
) -> MeshingTaskHistoryRead:
    return meshing.meshing_task_history(task_id, include_deleted=include_deleted)


@router.delete("/meshing/tasks/{task_id}", response_model=MeshingTaskDeleteReport)
def delete_meshing_task(
    task_id: str,
    payload: MeshingTaskDeleteRequest,
    meshing: MeshingServiceDependency,
) -> MeshingTaskDeleteReport:
    try:
        return meshing.delete_meshing_task(task_id, cleanup_artifacts=payload.cleanup_artifacts)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/meshing/status", response_model=FluentStatus)
def get_meshing_status(meshing: MeshingServiceDependency) -> FluentStatus:
    return meshing.status()


@router.post("/meshing/connect", response_model=FluentStatus)
def connect_meshing(
    payload: FluentConnectionConfig,
    meshing: MeshingServiceDependency,
) -> FluentStatus:
    try:
        return meshing.connect(payload)
    except (FileNotFoundError, MeshingAdapterBusyError):
        raise
    except Exception as exc:
        reason = str(exc)
        if payload.password:
            reason = reason.replace(payload.password, "[已隐藏]")
        diagnostic = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        if payload.password:
            diagnostic = diagnostic.replace(payload.password, "[已隐藏]")
        logger.error("Fluent Meshing connection failed:\n%s", diagnostic)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Fluent Meshing 连接失败（{type(exc).__name__}）：{reason}",
        ) from exc


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


@router.get("/meshing/workflows/watertight/schema")
def get_watertight_workflow_ui_schema() -> dict[str, Any]:
    return get_watertight_workflow_contract()


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
    "/meshing/reference-models/{model_id}/inspect",
    response_model=MeshingReferenceInspection,
)
def inspect_meshing_reference_model(
    model_id: int, meshing: MeshingServiceDependency
) -> MeshingReferenceInspection:
    try:
        return meshing.inspect_reference_model(model_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
    PartCategoryRepository(database).get(payload.category_id)
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
    PartCategoryRepository(database).get(payload.category_id)
    return MeshingAutomationRepository(database).update(automation_id, payload)


@router.post("/meshing-automations/{automation_id}/publish", response_model=MeshingAutomationRead)
def publish_meshing_automation(
    automation_id: int, database: DatabaseDependency
) -> MeshingAutomationRead:
    automation = MeshingAutomationRepository(database).get(automation_id)
    _validate_preset(automation.preset)
    return MeshingAutomationRepository(database).publish(automation_id)


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
    automation = MeshingAutomationRepository(meshing.database).get(automation_id)
    if automation.status != "active" or automation.published_revision is None:
        raise HTTPException(status_code=422, detail="请先发布模板，再应用到模型。")
    return meshing.apply_automation(automation_id, payload)


@router.post("/meshing/live-sessions", response_model=MeshingLiveSessionSnapshot)
def start_live_meshing_session(
    payload: MeshingLiveSessionStart,
    meshing: MeshingServiceDependency,
) -> MeshingLiveSessionSnapshot:
    try:
        automation = MeshingAutomationRepository(meshing.database).get(payload.automation_id)
        if automation.status != "active" or automation.published_revision is None:
            raise HTTPException(status_code=422, detail="请先发布模板，再应用到模型。")
        return meshing.start_live_session(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/meshing/live-sessions/{session_id}", response_model=MeshingLiveSessionSnapshot)
def get_live_meshing_session(
    session_id: str,
    meshing: MeshingServiceDependency,
) -> MeshingLiveSessionSnapshot:
    try:
        return meshing.get_live_session(session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/meshing/live-sessions/{session_id}/archive",
    response_model=MeshingArchiveRecord,
)
def archive_live_meshing_result(
    session_id: str,
    payload: MeshingArchiveCreate,
    meshing: MeshingServiceDependency,
) -> MeshingArchiveRecord:
    try:
        return meshing.archive_live_result(session_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/meshing/live-sessions/{session_id}/archives",
    response_model=list[MeshingArchiveRecord],
)
def list_live_meshing_archives(
    session_id: str, meshing: MeshingServiceDependency
) -> list[MeshingArchiveRecord]:
    return meshing.list_live_archives(session_id)


@router.post(
    "/meshing/live-sessions/{session_id}/enter",
    response_model=MeshingLiveStepReport,
)
def enter_live_meshing_step(
    session_id: str,
    payload: MeshingLiveStepRequest,
    meshing: MeshingServiceDependency,
) -> MeshingLiveStepReport:
    try:
        return meshing.enter_live_step(session_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/meshing/live-sessions/{session_id}/steps/{step_index}",
    response_model=MeshingLiveStepReport,
)
def read_live_meshing_step(
    session_id: str,
    step_index: int,
    meshing: MeshingServiceDependency,
) -> MeshingLiveStepReport:
    try:
        return meshing.read_live_step(session_id, step_index)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/meshing/live-sessions/{session_id}/write",
    response_model=MeshingLiveStepReport,
)
def write_live_meshing_values(
    session_id: str,
    payload: MeshingLiveWriteRequest,
    meshing: MeshingServiceDependency,
) -> MeshingLiveStepReport:
    try:
        return meshing.write_live_step(session_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/meshing/live-sessions/{session_id}/execute",
    response_model=MeshingLiveStepReport,
)
def execute_live_meshing_step(
    session_id: str,
    payload: MeshingLiveStepRequest,
    meshing: MeshingServiceDependency,
) -> MeshingLiveStepReport:
    try:
        return meshing.execute_live_step(session_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/meshing/live-sessions/{session_id}/retry-prepare",
    response_model=MeshingLiveSessionSnapshot,
)
def retry_live_meshing_preparation(
    session_id: str, meshing: MeshingServiceDependency
) -> MeshingLiveSessionSnapshot:
    try:
        return meshing.retry_live_preparation(session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/meshing/live-sessions/{session_id}/next-model",
    response_model=MeshingLiveSessionSnapshot,
)
def next_live_meshing_model(
    session_id: str,
    meshing: MeshingServiceDependency,
) -> MeshingLiveSessionSnapshot:
    try:
        return meshing.next_live_model(session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/meshing/live-sessions/{session_id}/retry-model",
    response_model=MeshingLiveSessionSnapshot,
)
def retry_live_meshing_model(
    session_id: str,
    meshing: MeshingServiceDependency,
) -> MeshingLiveSessionSnapshot:
    try:
        return meshing.retry_live_model(session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/meshing/live-sessions/{session_id}/stop",
    response_model=MeshingLiveSessionSnapshot,
)
def stop_live_meshing_session(
    session_id: str,
    meshing: MeshingServiceDependency,
) -> MeshingLiveSessionSnapshot:
    try:
        return meshing.stop_live_session(session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
