"""Registers the add-on and adds a board. Runs only where bpy is importable:
inside Blender (blender --background --python-expr ...) or with the
``bpy`` module from PyPI installed."""

import sys
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def addon():
    import weathered_board

    weathered_board.register()
    yield weathered_board
    weathered_board.unregister()


def test_add_board(addon):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    before = len(bpy.data.objects)
    assert bpy.ops.wboard.add() == {"FINISHED"}
    assert len(bpy.data.objects) == before + 1
    obj = bpy.context.active_object
    assert obj.weathered_board.is_board
    assert obj.weathered_board.seed > 0
    assert len(obj.data.polygons) > 0


def test_regenerate_and_new_seed(addon):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wboard.add()
    obj = bpy.context.active_object
    seed = obj.weathered_board.seed
    assert bpy.ops.wboard.regenerate() == {"FINISHED"}
    assert obj.weathered_board.seed == seed
    assert bpy.ops.wboard.new_seed() == {"FINISHED"}
    assert obj.weathered_board.seed != seed


def test_export_stl_in_mm(addon, tmp_path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wboard.add()
    path = tmp_path / "board.stl"
    assert bpy.ops.wboard.export_stl(filepath=str(path)) == {"FINISHED"}
    assert path.stat().st_size > 84


def test_board_has_pattern_colours(addon):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wboard.add()
    mesh = bpy.context.active_object.data
    attr = mesh.color_attributes.get("WB_Pattern")
    assert attr is not None
    assert mesh.color_attributes.active_color.name == "WB_Pattern"


def test_live_update_rebuilds_a_changed_board(addon):
    from weathered_board import properties

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.weathered_board.live_update = True
    bpy.ops.wboard.add()
    obj = bpy.context.active_object
    before = obj.dimensions.x
    obj.weathered_board.length = 48.0  # half of the default 96 in
    assert obj.name in properties._pending
    properties._flush_pending()  # what the timer would run
    bpy.context.view_layer.update()
    assert obj.dimensions.x == pytest.approx(before / 2, rel=1e-3)


def test_live_update_off_leaves_the_board_alone(addon):
    from weathered_board import properties

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.weathered_board.live_update = False
    bpy.ops.wboard.add()
    obj = bpy.context.active_object
    obj.weathered_board.length = 48.0
    assert obj.name not in properties._pending


def test_errors_are_kept_on_the_board(addon):
    from weathered_board import operators

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.weathered_board.live_update = False
    bpy.ops.wboard.add()
    obj = bpy.context.active_object
    obj.weathered_board.depth = 1000.0  # deeper than the board allows
    assert operators.rebuild(obj)
    assert "Depth" in obj.weathered_board.last_error


def test_add_menu_entry(addon):
    from weathered_board import ui_panel

    assert ui_panel.draw_add_menu in bpy.types.VIEW3D_MT_mesh_add._dyn_ui_initialize()


def test_panel_print_info_draws(addon):
    from unittest import mock

    from weathered_board import ui_panel

    layout = mock.MagicMock()
    ui_panel._draw_print_info(layout, bpy.context.scene.weathered_board)
    labels = [c.kwargs.get("text", "") for c in layout.column.return_value.label.call_args_list]
    assert any(t.startswith("Printed: 50.80 x 2.91 x 0.79 mm") for t in labels)
