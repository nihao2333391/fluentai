from pathlib import Path

from app.database import Database
from app.domain import MeshingAutomationCreate, MeshingPresetDocument, MeshingPresetItem
from app.repositories.errors import RepositoryConflictError
from app.repositories.meshing_automations import MeshingAutomationRepository


def _create_payload(name: str) -> MeshingAutomationCreate:
    return MeshingAutomationCreate(
        name=name,
        description="Venturi family preset",
        model_family="Venturi",
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

    created = repository.create(_create_payload("Venturi mesh"))
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

    repository.delete(created.id)
    assert repository.list() == []
