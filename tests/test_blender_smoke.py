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
