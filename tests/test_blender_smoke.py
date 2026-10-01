"""The add-on inside Blender: adding, rebuilding, the panel, checks, export, tooltips.

Covers live update, Check Printability and STL export too. Runs only where
bpy is importable: inside Blender (blender --background --python-expr ...)
or with the ``bpy`` module from PyPI installed.
"""

import sys
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def addon():
    """Register the add-on for one test and unregister it afterwards."""
    import weathered_board

    weathered_board.register()
    yield weathered_board
    weathered_board.unregister()


def test_add_board(addon):
    """Add Weathered Board creates one board object with a seed and a real mesh."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    before = len(bpy.data.objects)
    assert bpy.ops.wboard.add() == {"FINISHED"}
    assert len(bpy.data.objects) == before + 1
    obj = bpy.context.active_object
    assert obj.weathered_board.is_board
    assert obj.weathered_board.seed > 0
    assert len(obj.data.polygons) > 0


def test_regenerate_and_new_seed(addon):
    """Regenerate keeps the board's seed; New Seed replaces it."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wboard.add()
    obj = bpy.context.active_object
    seed = obj.weathered_board.seed
    assert bpy.ops.wboard.regenerate() == {"FINISHED"}
    assert obj.weathered_board.seed == seed
    assert bpy.ops.wboard.new_seed() == {"FINISHED"}
    assert obj.weathered_board.seed != seed


def test_export_stl_in_mm(addon, tmp_path):
    """Export STL writes a non-empty file (larger than the 84-byte STL header)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wboard.add()
    path = tmp_path / "board.stl"
    assert bpy.ops.wboard.export_stl(filepath=str(path)) == {"FINISHED"}
    assert path.stat().st_size > 84


def test_board_has_pattern_colours(addon):
    """New boards carry the pattern preview as their active colour attribute."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wboard.add()
    mesh = bpy.context.active_object.data
    attr = mesh.color_attributes.get("WB_Pattern")
    assert attr is not None
    assert mesh.color_attributes.active_color.name == "WB_Pattern"


def test_live_update_rebuilds_a_changed_board(addon):
    """Changing a board's setting queues a rebuild that applies the change.

    Halving the length must halve the board's size once the queue is
    flushed.
    """
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
    """With live update off, changing a setting queues nothing."""
    from weathered_board import properties

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.weathered_board.live_update = False
    bpy.ops.wboard.add()
    obj = bpy.context.active_object
    obj.weathered_board.length = 48.0
    assert obj.name not in properties._pending


def test_errors_are_kept_on_the_board(addon):
    """A failed rebuild keeps its error message on the board.

    The panel shows it there; live updates have no other way to report
    errors.
    """
    from weathered_board import operators

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.weathered_board.live_update = False
    bpy.ops.wboard.add()
    obj = bpy.context.active_object
    obj.weathered_board.depth = 1000.0  # deeper than the board allows
    assert operators.rebuild(obj)
    assert "Depth" in obj.weathered_board.last_error


def test_add_menu_entry(addon):
    """Weathered Board appears in the 3D Viewport's Add > Mesh menu."""
    from weathered_board import ui_panel

    assert ui_panel.draw_add_menu in bpy.types.VIEW3D_MT_mesh_add._dyn_ui_initialize()


def test_panel_print_info_draws(addon):
    """The panel's size readout gives the printed size for the default 1x6 at 1:48."""
    from unittest import mock

    from weathered_board import ui_panel

    layout = mock.MagicMock()
    ui_panel._draw_print_info(layout, bpy.context.scene.weathered_board)
    labels = [c.kwargs.get("text", "") for c in layout.column.return_value.label.call_args_list]
    assert any(t.startswith("Printed: 50.80 x 2.91 x 0.79 mm") for t in labels)


def _small_board():
    """Add a quick-to-build board (2 ft) and return it."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene.weathered_board
    s.live_update = False
    s.length = 24.0
    bpy.ops.wboard.add()
    return bpy.context.active_object


def test_check_printability_stores_a_report(addon):
    """A fresh board passes Check Printability with a full report.

    The report must cover the object checks: watertight, self-intersections
    and printed size.
    """
    obj = _small_board()
    assert bpy.ops.wboard.check() == {"FINISHED"}
    report = obj.weathered_board.check_report
    levels = [line.split("\t")[0] for line in report.splitlines()]
    assert "Watertight" in report and "No self-intersections" in report and "Printed size" in report
    assert "ERROR" not in levels


def test_check_notices_a_scaled_board(addon):
    """Scaling a board after building it is caught by the printed-size check."""
    obj = _small_board()
    obj.scale = (1.1, 1.0, 1.0)
    bpy.context.view_layer.update()
    bpy.ops.wboard.check()
    assert "Size differs from settings" in obj.weathered_board.check_report


def test_check_notices_a_hole(addon):
    """Deleting a face leaves open edges, which the check reports as an error."""
    import bmesh as bm_mod

    obj = _small_board()
    bm = bm_mod.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    bm_mod.ops.delete(bm, geom=[bm.faces[0]], context="FACES_ONLY")
    bm.to_mesh(obj.data)
    bm.free()
    # Run without a window, Blender turns the operator's error report into
    # an exception; in the app it shows as an error message instead.
    with pytest.raises(RuntimeError, match="have problems"):
        bpy.ops.wboard.check()
    assert "Open edges" in obj.weathered_board.check_report


def test_rebuilding_clears_the_report(addon):
    """A rebuild clears the last check's results, since they no longer apply."""
    from weathered_board import operators

    obj = _small_board()
    bpy.ops.wboard.check()
    assert obj.weathered_board.check_report
    operators.rebuild(obj)
    assert obj.weathered_board.check_report == ""


def test_export_one_file_per_board(addon, tmp_path):
    """One File per Board writes a separately named file for each board.

    The selection is put back as it was afterwards.
    """
    _small_board()
    first = bpy.context.active_object
    bpy.ops.wboard.add()
    second = bpy.context.active_object
    first.select_set(True)
    second.select_set(True)
    path = tmp_path / "boards.stl"
    assert bpy.ops.wboard.export_stl(filepath=str(path), one_file_per_board=True) == {"FINISHED"}
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == sorted([f"boards_{first.name}.stl", f"boards_{second.name}.stl"])
    # The selection is put back as it was.
    assert first.select_get() and second.select_get()


def _visible_props(rna):
    """Settings of a Blender type that show in the UI (not hidden, not ``rna_type``)."""
    return [p for p in rna.properties if p.identifier != "rna_type" and not p.is_hidden]


def test_every_setting_has_a_tooltip(addon):
    """Every visible setting, and every drop-down option, has a helpful tooltip.

    Setting tooltips must be at least 20 characters long.
    """
    from weathered_board.properties import WBOARD_Settings

    missing = []
    for p in _visible_props(WBOARD_Settings.bl_rna):
        if len(p.description.strip()) < 20:
            missing.append(p.identifier)
        if p.type == "ENUM":
            missing += [f"{p.identifier}.{i.identifier}" for i in p.enum_items if not i.description.strip()]
    assert not missing, f"settings without a helpful tooltip: {missing}"


def test_every_button_has_a_tooltip(addon):
    """Every operator has a real tooltip (its docstring) and every setting it shows has one too.

    Settings from Blender's file browser are skipped.
    """
    from weathered_board import operators

    missing = []
    for cls in operators.classes:
        if len((cls.__doc__ or "").strip()) < 20:
            missing.append(cls.bl_idname)
        op = getattr(bpy.ops.wboard, cls.bl_idname.split(".")[1])
        for p in _visible_props(op.get_rna_type()):
            if p.identifier in ("filepath", "check_existing", "filter_glob"):
                continue  # from Blender's file browser
            if not p.description.strip():
                missing.append(f"{cls.bl_idname}.{p.identifier}")
            if p.type == "ENUM":
                missing += [f"{cls.bl_idname}.{p.identifier}.{i.identifier}"
                            for i in p.enum_items if not i.description.strip()]
    assert not missing, f"buttons without a tooltip: {missing}"


def test_edge_group_buttons_have_their_own_tooltips(addon):
    """Each edge-group button has its own tooltip naming its edges.

    All / Long / End A / End B are one operator with a different group set.
    """
    from weathered_board.operators import WBOARD_OT_set_edges

    class Props:
        """Stands in for the button's operator properties, set to the Long group."""

        group = "LONG"
    assert "length of the board" in WBOARD_OT_set_edges.description(bpy.context, Props)
