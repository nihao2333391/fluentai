from app.domain import MeshingPresetDocument, MeshingPresetItem, MeshingPresetValue
from app.meshing.schema_index import MESHING_SCHEMA_INDEX


def _preset(
    task_path: list[str], argument_path: list[str], value: MeshingPresetValue
) -> MeshingPresetDocument:
    return MeshingPresetDocument(
        workflow_type="watertight",
        items=[
            MeshingPresetItem(
                task_path=task_path,
                argument_path=argument_path,
                value=value,
            )
        ],
    )


def test_known_meshing_argument_validates() -> None:
    report = MESHING_SCHEMA_INDEX.validate(
        _preset(["import_geometry"], ["file_name"], r"D:\geometry\FFF.dsco")
    )
    assert report.valid is True
    assert report.schema_id == "fluent-meshing-25.2-watertight"
    assert report.item_count == 1


def test_unknown_and_read_only_meshing_arguments_are_rejected() -> None:
    unknown = MESHING_SCHEMA_INDEX.validate(_preset(["missing_task"], ["file_name"], "value"))
    assert unknown.valid is False
    assert "Unknown Meshing task path" in unknown.errors[0]

    read_only = MESHING_SCHEMA_INDEX.validate(
        _preset(["update_boundaries"], ["boundary_allowed_type_list"], [])
    )
    assert read_only.valid is False
    assert "read-only" in read_only.errors[0]


def test_wrong_meshing_value_type_is_rejected() -> None:
    report = MESHING_SCHEMA_INDEX.validate(_preset(["import_geometry"], ["length_unit"], 123))
    assert report.valid is False
    assert "must be one of" in report.errors[0]
