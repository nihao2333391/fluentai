from pathlib import Path

from app.database import Database
from app.domain import (
    MeshingAutomationCreate,
    MeshingAutomationUpdate,
    MeshingPresetDocument,
    MeshingPresetItem,
    PartCategoryCreate,
    PartCategoryRename,
)
from app.repositories.categories import PartCategoryRepository
from app.repositories.errors import RepositoryConflictError
from app.repositories.meshing_automations import MeshingAutomationRepository


def _create_payload(name: str, category_id: str = "uncategorized") -> MeshingAutomationCreate:
    return MeshingAutomationCreate(
        name=name,
        description="Venturi family preset",
        model_family="Venturi",
        category_id=category_id,
        preset=MeshingPresetDocument(
            workflow_type="watertight",
            items=[
                MeshingPresetItem(
                    task_path=["import_geometry"],
                    argument_path=["length_unit"],
                    value="m",
                )
            ],
        ),
    )


def test_meshing_automation_crud_and_unique_name(tmp_path: Path) -> None:
    database = Database(tmp_path / "meshing.db")
    database.initialize()
    repository = MeshingAutomationRepository(database)
    category = PartCategoryRepository(database).create(PartCategoryCreate(name="Venturi"))

    created = repository.create(_create_payload("Venturi mesh", category.id))
    assert created.id > 0
    assert created.preset.workflow_type == "watertight"

    fetched = repository.get(created.id)
    assert fetched.model_family == "Venturi"

    try:
        repository.create(_create_payload("venturi mesh"))
    except RepositoryConflictError:
        pass
    else:
        raise AssertionError("Duplicate Meshing automation name was accepted")

    next_category = PartCategoryRepository(database).create(
        PartCategoryCreate(name="Venturi Mk II")
    )
    update_payload = _create_payload("Venturi mesh updated", next_category.id).model_copy(
        update={"description": "Updated preset", "model_family": "untrusted manual value"}
    )
    updated = repository.update(created.id, MeshingAutomationUpdate(**update_payload.model_dump()))
    assert updated.id == created.id
    assert updated.name == "Venturi mesh updated"
    assert updated.description == "Updated preset"
    assert updated.model_family == "Venturi Mk II"
    assert updated.category_id == next_category.id
    assert updated.updated_at >= created.updated_at

    renamed = PartCategoryRepository(database).rename(
        next_category.id, PartCategoryRename(name="文丘里管")
    )
    assert renamed.name == "文丘里管"
    assert renamed.template_count == 1
    renamed_template = repository.get(created.id)
    assert renamed_template.category_id == next_category.id
    assert renamed_template.model_family == "文丘里管"
    assert renamed_template.status == updated.status

    repository.delete(created.id)
    assert repository.list() == []
