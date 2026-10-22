"""Model library and automation association endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import DatabaseDependency, FluentServiceDependency
from app.domain import (
    ModelAutomationAssociate,
    ModelCreate,
    ModelOpenReport,
    ModelRead,
    ModelUpdate,
    OpenModelRequest,
)
from app.repositories.models import ModelRepository

router = APIRouter(tags=["models"])
ALLOWED_SUFFIXES = {".cas", ".h5", ".msh"}


def _validate_model_suffix(file_path: str) -> None:
    if Path(file_path).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Model file must use .cas, .cas.h5, .msh, or .msh.h5.",
        )


@router.get("", response_model=list[ModelRead])
def list_models(database: DatabaseDependency) -> list[ModelRead]:
    return ModelRepository(database).list()


@router.post("", response_model=ModelRead, status_code=status.HTTP_201_CREATED)
def create_model(payload: ModelCreate, database: DatabaseDependency) -> ModelRead:
    _validate_model_suffix(payload.file_path)
    return ModelRepository(database).create(payload)


@router.get("/{model_id}", response_model=ModelRead)
def get_model(model_id: int, database: DatabaseDependency) -> ModelRead:
    return ModelRepository(database).get(model_id)


@router.put("/{model_id}", response_model=ModelRead)
def update_model(
    model_id: int,
    payload: ModelUpdate,
    database: DatabaseDependency,
) -> ModelRead:
    _validate_model_suffix(payload.file_path)
    return ModelRepository(database).update(model_id, payload)


@router.post("/{model_id}/open", response_model=ModelOpenReport)
def open_model(
    model_id: int,
    payload: OpenModelRequest,
    fluent: FluentServiceDependency,
) -> ModelOpenReport:
    return fluent.open_model(model_id, payload)


@router.post("/{model_id}/refresh", response_model=ModelRead)
def refresh_model(model_id: int, database: DatabaseDependency) -> ModelRead:
    return ModelRepository(database).refresh(model_id)


@router.post("/{model_id}/associate", response_model=ModelRead)
def associate_model(
    model_id: int,
    payload: ModelAutomationAssociate,
    database: DatabaseDependency,
) -> ModelRead:
    return ModelRepository(database).associate(model_id, payload)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(model_id: int, database: DatabaseDependency) -> Response:
    ModelRepository(database).delete(model_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
