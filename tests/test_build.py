import numpy as np
import pytest
from meshcheck import is_closed_and_consistent, signed_volume

from core import build_board
from core.params import BoardParams


@pytest.fixture
def params():
    # 1x6 board, 8 ft, at 1:48, coarse resolution to keep the test fast.
    return BoardParams(length=2438.4, width=139.7, thickness=19.05, scale=48, resolution=0.2)


def test_mesh_is_watertight(params):
    _, tris = build_board(params)
    assert is_closed_and_consistent(tris)


def test_normals_point_outward(params):
    verts, tris = build_board(params)
    assert signed_volume(verts, tris) > 0


def test_scaled_size(params):
    verts, _ = build_board(params)
    size = verts.max(axis=0) - verts.min(axis=0)
    expected = np.array(params.size) / params.scale
    assert np.allclose(size, expected, rtol=1e-3)


def test_default_board_is_weathered_at_1_48(params):
    from core import build

    params.resolution = 0.05  # resin default
    r = build(params)
    # Auto boost lets the rings carve to the quarter-thickness wear cap;
    # checks (cracks) may cut deeper, up to 35% of the thickness.
    assert r.depth.max() >= 0.9 * params.thickness / 4 / 48
    assert r.depth.max() <= 0.35 * params.thickness / 48 + 1e-9
