from app.domain import MeshingPresetDocument, MeshingPresetItem, MeshingPresetValue
from app.meshing.schema_index import MESHING_SCHEMA_INDEX


def _preset(
    task_path: list[str],
    argument_path: list[str],
    value: MeshingPresetValue,
    compound_child_name: str | None = None,
) -> MeshingPresetDocument:
    return MeshingPresetDocument(
        workflow_type="watertight",
        items=[
            MeshingPresetItem(
                task_path=task_path,
                argument_path=argument_path,
                value=value,
                compound_child_name=compound_child_name,
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


def test_compound_child_and_nested_meshing_arguments_validate() -> None:
    local_sizing = MESHING_SCHEMA_INDEX.validate(
        _preset(
            ["add_local_sizing"],
            ["boi_face_label_list"],
            ["wall-big"],
            compound_child_name="wall-big",
        )
    )
    assert local_sizing.valid is True

    nested = MESHING_SCHEMA_INDEX.validate(
        _preset(
            ["create_volume_mesh"],
            ["volume_fill_controls", "hex_max_cell_length"],
            0.0032,
        )
    )
    assert nested.valid is True

    manual_label = MESHING_SCHEMA_INDEX.validate(
        _preset(
            ["add_local_sizing"],
            ["boi_face_label_list"],
            ["manual-wall-label"],
            compound_child_name="wall-by-label",
        )
    )
    assert manual_label.valid is True


def test_compound_child_name_is_rejected_for_simple_tasks() -> None:
    report = MESHING_SCHEMA_INDEX.validate(
        _preset(
            ["import_geometry"],
            ["length_unit"],
            "m",
            compound_child_name="not-a-compound-child",
        )
    )
    assert report.valid is False
    assert "does not support compound child presets" in report.errors[0]


def test_same_compound_argument_is_allowed_for_different_children() -> None:
    preset = MeshingPresetDocument(
        workflow_type="watertight",
        items=[
            MeshingPresetItem(
                task_path=["add_local_sizing"],
                argument_path=["boi_size"],
                value=0.001,
                compound_child_name="wall-big",
            ),
            MeshingPresetItem(
                task_path=["add_local_sizing"],
                argument_path=["boi_size"],
                value=0.0005,
                compound_child_name="wall-small",
            ),
        ],
    )
    report = MESHING_SCHEMA_INDEX.validate(preset)
    assert report.valid is True
