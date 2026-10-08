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


def _stl_triangles(path):
    """Number of triangles in a binary STL file (from its header)."""
    import struct

    with open(path, "rb") as f:
        f.seek(80)
        return struct.unpack("<I", f.read(4))[0]


def test_simplify_exports_a_lighter_mesh(addon, tmp_path):
    """Simplify Mesh exports about Max Triangles, and the check still passes."""
    obj = _small_board()
    full = len(obj.data.polygons)
    obj.weathered_board.max_triangles = 2000
    obj.weathered_board.simplify = True
    assert obj.modifiers.get("WB Simplify") is not None
    assert len(obj.data.polygons) == full  # full detail is kept underneath
    path = tmp_path / "board.stl"
    bpy.ops.wboard.export_stl(filepath=str(path))
    assert 1800 <= _stl_triangles(path) <= 2200 < full
    bpy.ops.wboard.check()
    report = obj.weathered_board.check_report
    assert "(simplified)" in report and "ERROR" not in report


def test_simplify_off_restores_full_detail_without_a_rebuild(addon):
    """Turning Simplify off just removes the modifier; the mesh is untouched."""
    obj = _small_board()
    mesh = obj.data
    obj.weathered_board.simplify = True
    obj.weathered_board.simplify = False
    assert obj.modifiers.get("WB Simplify") is None
    assert obj.data == mesh


def test_simplify_survives_a_rebuild(addon):
    """Rebuilding a simplified board keeps it simplified to the same target."""
    from weathered_board import operators

    obj = _small_board()
    obj.weathered_board.max_triangles = 3000
    obj.weathered_board.simplify = True
    operators.rebuild(obj)
    mod = obj.modifiers.get("WB Simplify")
    assert mod is not None
    assert mod.ratio * len(obj.data.polygons) == pytest.approx(3000)


@pytest.fixture
def preset_dir(addon, tmp_path):
    """Keep saved presets in a temporary folder for one test."""
    from weathered_board import preset_store

    preset_store.folder_override = str(tmp_path / "presets")
    yield tmp_path / "presets"
    preset_store.folder_override = None


def test_preset_defaults_match_the_panel(addon):
    """core.presets.DEFAULT_VALUES agrees with every property's default in Blender."""
    from weathered_board.core.presets import DEFAULT_VALUES

    rna = bpy.types.Scene.bl_rna.properties["weathered_board"].fixed_type.properties
    for key, value in DEFAULT_VALUES.items():
        default = rna[key].default
        assert default == pytest.approx(value) if isinstance(value, float) else default == value, key


def test_apply_builtin_preset_to_new_board_settings(addon):
    """A built-in preset applied with nothing selected sets the next board's look and size."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene.weathered_board
    assert bpy.ops.wboard.apply_preset(name="Barn Siding") == {"FINISHED"}
    assert s.width == 11.5 and s.depth == 4.5 and s.use_end_depth
    assert s.preset == "Barn Siding"
    assert s.scale_n == 48.0  # scale untouched


def test_apply_preset_keeps_size_when_asked(addon):
    """With Presets Set Size off, only the look changes."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene.weathered_board
    s.preset_size = False
    s.length = 50.0
    bpy.ops.wboard.apply_preset(name="Fence Board")
    assert s.length == 50.0 and s.thickness == 1.5
    assert s.depth == 2.5


def test_apply_preset_rebuilds_selected_boards(addon):
    """Applying a preset to selected boards restyles and rebuilds each once."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene.weathered_board
    s.count = 2
    s.length = 24.0
    s.resolution = 0.1
    bpy.ops.wboard.add()
    boards = [o for o in bpy.data.objects if o.weathered_board.is_board]
    for o in boards:
        o.select_set(True)
    widths = [o.dimensions.y for o in boards]
    s.preset_size = True
    assert bpy.ops.wboard.apply_preset(name="Barn Siding") == {"FINISHED"}
    for o, before in zip(boards, widths):
        assert o.weathered_board.width == 11.5
        assert o.weathered_board.preset == "Barn Siding"
        assert o.dimensions.y > 1.5 * before  # rebuilt at the new width
    assert not __import__("weathered_board.properties").properties._pending


def test_save_apply_and_remove_your_own_preset(preset_dir):
    """A saved preset appears as a file, applies back, and can be deleted."""
    from weathered_board import preset_store

    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene.weathered_board
    s.depth = 1.25
    s.round_a_top = 0.9
    assert bpy.ops.wboard.save_preset(name="My Look") == {"FINISHED"}
    assert (preset_dir / "My Look.json").exists()
    assert preset_store.saved_names() == ["My Look"]

    s.depth = 3.0
    s.round_a_top = 0.15
    assert bpy.ops.wboard.apply_preset(name="My Look") == {"FINISHED"}
    assert s.depth == pytest.approx(1.25) and s.round_a_top == pytest.approx(0.9)

    assert bpy.ops.wboard.remove_preset(name="My Look") == {"FINISHED"}
    assert preset_store.saved_names() == []
    assert s.preset == ""


def test_builtin_names_are_reserved(preset_dir):
    """You can't save over or remove a built-in preset."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with pytest.raises(RuntimeError):
        bpy.ops.wboard.save_preset(name="dock plank")
    with pytest.raises(RuntimeError):
        bpy.ops.wboard.remove_preset(name="Dock Plank")


def test_preset_names_are_made_file_safe(preset_dir):
    """Characters Windows can't use in a file name are dropped."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wboard.save_preset(name='Old: "grey" 1/2')
    assert (preset_dir / "Old grey 12.json").exists()


def test_a_broken_preset_file_is_reported(preset_dir):
    """A damaged preset file gives an error, not a half-applied preset."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    preset_dir.mkdir(parents=True, exist_ok=True)
    (preset_dir / "Broken.json").write_text("{nope", encoding="utf-8")
    s = bpy.context.scene.weathered_board
    with pytest.raises(RuntimeError):
        bpy.ops.wboard.apply_preset(name="Broken")
    assert s.depth == 3.0


def test_preset_menu_and_buttons_have_tooltips(addon):
    """Built-in presets show their own description as the tooltip."""
    from weathered_board.core.presets import BUILTIN_PRESETS
    from weathered_board.operators import WBOARD_OT_apply_preset

    for preset in BUILTIN_PRESETS:
        props = type("P", (), {"name": preset.name})
        assert WBOARD_OT_apply_preset.description(None, props) == preset.description
    props = type("P", (), {"name": "Mine"})
    assert "Mine" in WBOARD_OT_apply_preset.description(None, props)


def test_preset_menu_and_panel_draw(preset_dir):
    """The presets menu lists built-ins and saved presets; the panel shows the current one."""
    from unittest import mock

    from weathered_board import preset_store, ui_panel

    bpy.ops.wm.read_factory_settings(use_empty=True)
    preset_store.save("Mine", {})
    menu = mock.MagicMock()
    ui_panel.WBOARD_MT_presets.draw(menu, bpy.context)
    texts = [c.kwargs.get("text") for c in menu.layout.operator.call_args_list]
    assert texts == ["Barn Siding", "Dock Plank", "Fence Board", "Mine"]

    bpy.ops.wboard.apply_preset(name="Dock Plank")
    panel = mock.MagicMock()
    ui_panel.WBOARD_PT_main.draw(panel, bpy.context)
    menus = panel.layout.row.return_value.menu.call_args_list
    assert menus[0].kwargs["text"] == "Dock Plank"


def test_api_lists_and_builds_saved_presets(preset_dir):
    """Inside Blender the public API sees saved presets, after the built-ins."""
    from weathered_board import api, preset_store

    preset_store.save("Mine", {"depth": 1.5, "weather_bottom": True})
    presets = api.list_presets()
    assert [p.builtin for p in presets] == [True] * 3 + [False]
    assert presets[-1].name == "Mine"
    assert api.get_preset_values("Mine")["depth"] == 1.5
    board = api.build_board(preset="Mine", weather_bottom=None, length_mm=300.0,
                            width_mm=100.0, thickness_mm=30.0, scale=24.0, resolution=0.1)
    assert board.face_depth["bottom"] > 0


def test_api_reports_a_broken_saved_preset(preset_dir):
    """A damaged saved preset is a BoardError from the API."""
    from weathered_board import api

    preset_dir.mkdir(parents=True, exist_ok=True)
    (preset_dir / "Broken.json").write_text("{nope", encoding="utf-8")
    with pytest.raises(api.BoardError):
        api.get_preset_values("Broken")


def test_api_leaves_the_scene_alone(addon):
    """build_board adds no objects or meshes to the file."""
    from weathered_board import api

    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects, meshes = len(bpy.data.objects), len(bpy.data.meshes)
    api.build_board(length_mm=300.0, width_mm=100.0, thickness_mm=30.0, scale=24.0)
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == (objects, meshes)
