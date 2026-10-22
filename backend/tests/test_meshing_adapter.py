from app.domain import MeshingPresetDocument, MeshingPresetItem
from app.meshing.pyfluent_adapter import _validate_names, _values_equal


def test_meshing_values_compare_fluent_sequence_containers() -> None:
    assert _values_equal(["wall-big"], ("wall-big",)) is True
    assert _values_equal(0.001, "0.001") is True
    assert _values_equal(True, "true") is False


def test_meshing_name_validation_reports_exact_missing_names() -> None:
    preset = MeshingPresetDocument(
        workflow_type="watertight",
        items=[
            MeshingPresetItem(
                task_path=["add_boundary_layer"],
                argument_path=["bl_label_list"],
                value=["wall-big", "wall-missing"],
                compound_child_name="boundary-layer-1",
            )
        ],
    )
    checks, missing = _validate_names(preset, {"wall-big", "wall-small"})
    assert [check.found for check in checks] == [True, False]
    assert missing == ["label:wall-missing"]
