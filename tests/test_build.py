from collections import Counter

import numpy as np
import pytest

from core import build_board
from core.params import BoardParams


def closed_and_consistent(tris):
    """Every edge used by exactly two triangles, once in each direction."""
    directed = Counter()
    for a, b, c in tris:
        for e in ((a, b), (b, c), (c, a)):
            directed[e] += 1
    for (a, b), n in directed.items():
        if n != 1 or directed.get((b, a)) != 1:
            return False
    return True


def signed_volume(verts, tris):
    v = verts[tris]
    return np.einsum("ij,ij->i", v[:, 0], np.cross(v[:, 1], v[:, 2])).sum() / 6.0


@pytest.fixture
def params():
    return BoardParams(length=2438.4, width=139.7, thickness=19.05, scale=48)


def test_mesh_is_watertight(params):
    _, tris = build_board(params)
    assert closed_and_consistent(tris)


def test_normals_point_outward(params):
    verts, tris = build_board(params)
    assert signed_volume(verts, tris) > 0


def test_scaled_size(params):
    verts, _ = build_board(params)
    size = verts.max(axis=0) - verts.min(axis=0)
    expected = np.array(params.size) / params.scale
    assert np.allclose(size, expected, rtol=1e-3)
