"""The public API in api.py, used by other add-ons such as Tie Strip Generator."""

import importlib
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from meshcheck import is_closed_and_consistent, signed_volume

PKG_DIR = Path(__file__).resolve().parents[1] / "weathered_board"


def load_api():
    """Import api.py as part of a package, without running its bpy-importing __init__.

    In Blender the module is ``bl_ext.<repo>.weathered_board.api``; here a
    bare package object stands in for ``weathered_board``.
    """
    name = "_wb_api_test_pkg"
    if name not in sys.modules:
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules[name] = pkg
    return importlib.import_module(name + ".api")


api = load_api()

# HO tie: 8'6" x 9" x 7" at 1:87.1.
HO = dict(length_mm=102 * 25.4, width_mm=9 * 25.4, thickness_mm=7 * 25.4, scale=87.1)


def test_api_version_is_two_ints():
    """API_VERSION is a (major, minor) tuple of integers, currently 1.x."""
    v = api.API_VERSION
    assert isinstance(v, tuple) and len(v) == 2
    assert all(isinstance(n, int) and not isinstance(n, bool) for n in v)
    assert v[0] == 1


def test_list_presets_builtins_first():
    """Without Blender, list_presets gives the built-ins, marked as such."""
    presets = api.list_presets()
    assert [p.name for p in presets][:3] == ["Barn Siding", "Dock Plank", "Fence Board"]
    assert all(p.builtin and p.description for p in presets)


def test_get_preset_values_uses_preset_keys():
    """A preset's values cover exactly the preset settings, and are a copy."""
    values = api.get_preset_values("Dock Plank")
    assert set(values) == set(api.PRESET_KEYS)
    values["depth"] = 99.0
    assert api.get_preset_values("Dock Plank")["depth"] != 99.0


@pytest.mark.parametrize("name", [p.name for p in api.BUILTIN_PRESETS])
def test_every_builtin_preset_builds(name):
    """Each built-in preset builds through build_board at an overridden size."""
    board = api.build_board(preset=name, length_mm=300.0, width_mm=100.0,
                            thickness_mm=30.0, scale=24.0, resolution=0.1)
    assert board.vertices.shape[1] == 3 and board.vertices.dtype == np.float64
    assert board.triangles.shape[1] == 3 and board.triangles.dtype == np.int32
    assert is_closed_and_consistent(board.triangles)
    assert signed_volume(board.vertices, board.triangles) > 0  # wound outward
    size = board.vertices.max(axis=0) - board.vertices.min(axis=0)
    assert size == pytest.approx([300 / 24, 100 / 24, 30 / 24], rel=0.02)
    assert set(board.face_depth) == set(api.FACES)


def test_unknown_preset_raises_board_error():
    """An unknown preset name is a BoardError, which is also a ValueError."""
    with pytest.raises(api.BoardError, match="No Such Look"):
        api.build_board(preset="No Such Look", **HO)
    with pytest.raises(ValueError):
        api.get_preset_values("No Such Look")


def test_bad_settings_raise_board_error():
    """Unknown settings, wrong kinds and impossible boards are all BoardError."""
    with pytest.raises(api.BoardError, match="seed"):
        api.build_board(values={"seed": 3}, **HO)
    with pytest.raises(api.BoardError):
        api.build_board(values={"depth": "deep"}, **HO)
    with pytest.raises(api.BoardError):
        api.build_board(printer="LASER", **HO)
    with pytest.raises(api.BoardError, match="quarter"):
        api.build_board(values={"depth": 60.0}, **HO)  # ParamError, wrapped


def test_same_seed_same_mesh_different_seed_differs():
    """Building twice with one seed gives identical arrays; another seed doesn't."""
    a = api.build_board(seed=7, **HO)
    b = api.build_board(seed=7, **HO)
    c = api.build_board(seed=8, **HO)
    assert np.array_equal(a.vertices, b.vertices)
    assert np.array_equal(a.triangles, b.triangles)
    assert a.face_depth == b.face_depth
    assert not np.array_equal(a.vertices, c.vertices)


def test_seed_wraps_into_range():
    """Seeds are kept in 0 .. 2**31 - 1, so 2**31 + 5 builds like 5."""
    a = api.build_board(seed=5, **HO)
    b = api.build_board(seed=2**31 + 5, **HO)
    assert np.array_equal(a.vertices, b.vertices)


def test_bottom_flat_by_default():
    """weather_bottom=False leaves the bottom flat; True carves it.

    The bottom's entry isn't exactly 0: where a rounded edge meets a
    weathered side, the easing between faces reaches a few microns onto
    the bottom. That stays far below anything a printer can show.
    """
    flat = api.build_board(preset="Barn Siding", **HO)
    assert flat.face_depth["bottom"] < 0.01  # printed mm
    assert flat.face_depth["bottom"] < 0.02 * flat.face_depth["top"]
    carved = api.build_board(preset="Barn Siding", weather_bottom=True, **HO)
    assert carved.face_depth["bottom"] > 0


def test_weather_bottom_none_keeps_preset_choice():
    """None takes weather_bottom from the values (the default look leaves it off)."""
    mesh = api.build_board(values={"weather_bottom": True}, weather_bottom=None, **HO)
    assert mesh.face_depth["bottom"] > 0


def test_ho_tie_printed_size():
    """An HO tie, 8'6" x 9" x 7" at 1:87.1, prints about 29.75 x 2.62 x 2.04 mm."""
    board = api.build_board(**HO)
    lo, hi = board.vertices.min(axis=0), board.vertices.max(axis=0)
    assert hi - lo == pytest.approx([29.75, 2.62, 2.04], abs=0.02)
    assert (hi + lo) == pytest.approx([0, 0, 0], abs=0.02)  # centred on the origin


def test_values_override_preset_and_size_overrides_values():
    """values beats the preset; the size arguments beat both."""
    plain = api.build_board(preset="Fence Board", **HO)
    shallow = api.build_board(preset="Fence Board", values={"depth": 1.0, "length": 1.0}, **HO)
    assert shallow.carve_depth_mm < plain.carve_depth_mm
    size = shallow.vertices.max(axis=0) - shallow.vertices.min(axis=0)
    assert size[0] == pytest.approx(29.75, abs=0.02)


def test_printer_sets_resolution_and_boost_is_reported():
    """FDM's coarser defaults need a bigger boost at HO scale, and it is reported."""
    resin = api.build_board(printer="RESIN", **HO)
    fdm = api.build_board(printer="FDM", **HO)
    assert fdm.boost > resin.boost >= 1.0
    assert len(fdm.vertices) < len(resin.vertices)
    assert resin.carve_depth_mm <= 0.25 * HO["thickness_mm"] / HO["scale"] + 1e-9


def test_result_is_read_only():
    """The returned mesh can't be changed by accident."""
    board = api.build_board(**HO)
    with pytest.raises(ValueError):
        board.vertices[0, 0] = 1.0
    with pytest.raises(AttributeError):
        board.boost = 2.0


def test_api_does_not_import_bpy():
    """Importing and using the API from plain Python never needs Blender."""
    assert "bpy" not in sys.modules
