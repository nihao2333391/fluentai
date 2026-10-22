"""Automation CRUD endpoints."""

from fastapi import APIRouter, Response, status

from app.api.deps import DatabaseDependency
from app.domain import AutomationCreate, AutomationRead, AutomationUpdate
from app.repositories.automations import AutomationRepository

router = APIRouter(tags=["automations"])


@router.get("", response_model=list[AutomationRead])
def list_automations(database: DatabaseDependency) -> list[AutomationRead]:
    return AutomationRepository(database).list()


@router.post("", response_model=AutomationRead, status_code=status.HTTP_201_CREATED)
def create_automation(
    payload: AutomationCreate,
    database: DatabaseDependency,
) -> AutomationRead:
    return AutomationRepository(database).create(payload)


@router.get("/{automation_id}", response_model=AutomationRead)
def get_automation(automation_id: int, database: DatabaseDependency) -> AutomationRead:
    return AutomationRepository(database).get(automation_id)


@router.put("/{automation_id}", response_model=AutomationRead)
def update_automation(
    automation_id: int,
    payload: AutomationUpdate,
    database: DatabaseDependency,
) -> AutomationRead:
    return AutomationRepository(database).update(automation_id, payload)


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation(automation_id: int, database: DatabaseDependency) -> Response:
    AutomationRepository(database).delete(automation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
