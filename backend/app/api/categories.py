"""Part category endpoints."""

from fastapi import APIRouter, Response, status

from app.api.deps import DatabaseDependency
from app.domain import PartCategoryCreate, PartCategoryRead, PartCategoryRename
from app.repositories.categories import PartCategoryRepository

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[PartCategoryRead])
def list_categories(database: DatabaseDependency) -> list[PartCategoryRead]:
    return PartCategoryRepository(database).list()


@router.post("", response_model=PartCategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(payload: PartCategoryCreate, database: DatabaseDependency) -> PartCategoryRead:
    return PartCategoryRepository(database).create(payload)


@router.patch("/{category_id}", response_model=PartCategoryRead)
def rename_category(
    category_id: str, payload: PartCategoryRename, database: DatabaseDependency
) -> PartCategoryRead:
    return PartCategoryRepository(database).rename(category_id, payload)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: str, database: DatabaseDependency) -> Response:
    PartCategoryRepository(database).delete(category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
