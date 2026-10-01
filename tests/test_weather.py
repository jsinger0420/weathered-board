"""Carving (build plan step 4)."""

import numpy as np
import pytest
from meshcheck import is_closed_and_consistent, signed_volume, triangle_normals

from core.geometry import FACE_NAMES, rounded_box
from core.params import EDGES, BoardParams
from core.patterns import board_patterns
from core.weather import (
    carve,
    detail_factor,
    effective_half_width,
    erosion_profile,
    ridge_half_width,
    RIDGE_CENTRE,
)

L, W, T = 120.0, 50.0, 20.0


def params(rounds=0.15, **kw):
    """Settings for a 120 x 50 x 20 mm test board with rings only.

    No knots, cracks or patchy wear, and no auto boost.
    """
    # Rings only: knots, checks and patchy wear are tested in test_features.py.
    base = dict(length=L, width=W, thickness=T, scale=1.0, resolution=0.4, seed=5, depth=2.0,
                auto_detail=False, knots=(0, 0), checks=0.0, patchiness=0.0)
    base.update(kw)
    p = BoardParams(**base)
    if isinstance(rounds, dict):
        p.edge_round.update(rounds)
    else:
        p.edge_round.update({e: float(rounds) for e in EDGES})
    return p


def run(p):
    """Build, pattern and carve ``p``. Returns (uncarved mesh, carving)."""
    mesh = rounded_box(p)
    return mesh, carve(p, mesh, board_patterns(p, mesh))


# --------------------------------------------------------------------------
# Erosion profile
# --------------------------------------------------------------------------

@pytest.mark.parametrize("sharpness", [0.0, 0.3, 0.6, 1.0])
def test_profile_shape(sharpness):
    """The erosion profile has the right shape.

    It stays within 0-1, is 0 on the ridge and 1 deepest in the valley,
    joins up from one year to the next, and is smooth.
    """
    ph = np.linspace(0, 1, 2001)
    e = erosion_profile(ph, sharpness)
    assert e.min() >= 0 and e.max() <= 1 + 1e-12
    assert erosion_profile(np.array([RIDGE_CENTRE]), sharpness)[0] == pytest.approx(0)
    assert e.max() == pytest.approx(1, abs=1e-3)
    # Periodic: no seam between one year and the next.
    assert erosion_profile(np.array([0.0]), sharpness)[0] == pytest.approx(
        erosion_profile(np.array([1.0 - 1e-12]), sharpness)[0], abs=1e-9)
    assert np.abs(np.diff(e)).max() < 0.05  # smooth


def test_sharper_ridges_leave_wider_valleys():
    """Raising Ridge Sharpness widens the deep part of each groove."""
    ph = np.linspace(0, 1, 2001)
    deep = [(erosion_profile(ph, s) > 0.9).mean() for s in (0.0, 0.5, 1.0)]
    assert deep[0] < deep[1] < deep[2]


def test_coarse_meshes_widen_ridges_then_fade_them():
    """Coarser meshes widen the ridges, then stop carving them.

    A fine mesh carves ridges as set; a coarser one widens them; one too
    coarse for the rings carves nothing.
    """
    fine = params(resolution=0.1)
    assert effective_half_width(4.0, fine) == pytest.approx(ridge_half_width(fine.ridge_sharpness))
    medium = params(resolution=0.5)
    assert effective_half_width(4.0, medium) > ridge_half_width(medium.ridge_sharpness)
    assert detail_factor(4.0, params(resolution=0.5)) == 1.0
    assert detail_factor(4.0, params(resolution=3.0)) == 0.0


# --------------------------------------------------------------------------
# The carved mesh
# --------------------------------------------------------------------------

def assert_carving_valid(mesh, carving, p):
    """Assert the carved board is sound.

    Closed, inside its original size, no turned-over triangles, and smaller
    in volume than before.
    """
    v, t = carving.vertices, mesh.triangles
    assert is_closed_and_consistent(t)
    half = 0.5 * np.array(p.size)
    assert (np.abs(v) <= half + 1e-9).all(), "carving went outside the original board"
    # No triangle turned over: each still faces the way it did before.
    before = triangle_normals(mesh.vertices, t)
    after = triangle_normals(v, t)
    assert (np.einsum("ij,ij->i", before, after) > 0).all(), "folded triangle"
    assert signed_volume(v, t) < signed_volume(mesh.vertices, t)


@pytest.mark.parametrize("rounds", [0.0, 0.05, 0.15, 0.5, 1.0])
def test_carving_is_valid_for_any_rounding(rounds):
    """Carving is sound for every edge rounding from sharp to fully round."""
    p = params(rounds, faces={f: True for f in FACE_NAMES})
    mesh, carving = run(p)
    assert_carving_valid(mesh, carving, p)


@pytest.mark.parametrize("seed", range(6))
def test_carving_is_valid_for_mixed_rounding(seed):
    """Carving is sound with deep, sharp ridges, mixed rounding and random faces."""
    rng = np.random.default_rng(seed)
    rounds = {e: float(rng.choice([0.0, 0.1, 0.3, 0.8, 1.0])) for e in EDGES}
    p = params(rounds, seed=seed, depth=4.5, ridge_sharpness=1.0,
               faces={f: bool(rng.random() < 0.7) for f in FACE_NAMES})
    mesh, carving = run(p)
    assert_carving_valid(mesh, carving, p)


def test_depth_reaches_but_never_exceeds_the_setting():
    """The deepest cut comes within 10% of Depth and never passes it."""
    p = params()
    _, carving = run(p)
    assert carving.depth.max() <= p.depth + 1e-9
    assert carving.depth.max() > 0.9 * p.depth


def test_latewood_ridges_stay_on_the_original_surface():
    """Ridge tops stay on the original surface, so the board keeps its full size."""
    p = params(rounds=0.0)
    mesh, carving = run(p)
    top = mesh.face_weights[:, FACE_NAMES.index("top")] == 1.0
    assert carving.depth[top].min() < 0.02 * p.depth
    # So the board still measures its full size across the ridge tops.
    size = carving.vertices.max(axis=0) - carving.vertices.min(axis=0)
    assert np.allclose(size, p.size, atol=0.02 * p.depth)


def test_unselected_faces_stay_flat():
    """An unweathered face is left exactly as it was."""
    p = params(faces={f: f != "bottom" for f in FACE_NAMES})
    mesh, carving = run(p)
    bottom = mesh.face_weights[:, FACE_NAMES.index("bottom")] == 1.0
    assert np.array_equal(carving.vertices[bottom], mesh.vertices[bottom])
    assert carving.depth[~bottom].max() > 0


def test_no_faces_selected_means_no_carving():
    """With no faces selected nothing moves."""
    p = params(faces={f: False for f in FACE_NAMES})
    mesh, carving = run(p)
    assert np.array_equal(carving.vertices, mesh.vertices)


def test_zero_depth_means_no_carving():
    """A depth of 0 moves nothing."""
    p = params(depth=0.0)
    mesh, carving = run(p)
    assert np.array_equal(carving.vertices, mesh.vertices)


def test_separate_end_depth():
    """A separate End Depth carves the ends deeper without changing the long faces."""
    p = params(rounds=0.0, depth=1.0, end_depth=3.0)
    mesh, carving = run(p)
    ends = (mesh.face_weights[:, FACE_NAMES.index("end_a")] == 1.0) | \
           (mesh.face_weights[:, FACE_NAMES.index("end_b")] == 1.0)
    only_end = ends & (mesh.face_weights.sum(axis=1) == 1.0)
    assert carving.depth[only_end].max() > 2.5
    long_only = (mesh.face_weights[:, FACE_NAMES.index("top")] == 1.0) & (mesh.face_weights.sum(axis=1) == 1.0)
    assert carving.depth[long_only].max() <= 1.0 + 1e-9


def test_edge_margin_leaves_a_smooth_border():
    """An Edge Margin leaves an unworn border on each face.

    Full depth is still reached inside the border.
    """
    margin = 5.0
    p = params(rounds=0.0, edge_margin=margin)
    mesh, carving = run(p)
    v = mesh.vertices
    top = mesh.face_weights[:, FACE_NAMES.index("top")] == 1.0
    near_border = top & ((np.abs(v[:, 0]) > L / 2 - 0.5) | (np.abs(v[:, 1]) > W / 2 - 0.5))
    assert carving.depth[near_border].max() < 0.05 * p.depth
    inside = top & (np.abs(v[:, 0]) < L / 2 - margin) & (np.abs(v[:, 1]) < W / 2 - margin)
    assert carving.depth[inside].max() > 0.9 * p.depth


def test_grooves_run_out_over_a_rounded_edge():
    """Grooves carry on over a rounded edge, with no raised, uncut lip."""
    p = params(rounds=0.3, depth=3.0)
    mesh, carving = run(p)
    on_edge = mesh.rounded & (np.abs(mesh.vertices[:, 0]) < L / 4)
    assert carving.depth[on_edge].max() > 0.8 * p.depth


def test_too_coarse_a_mesh_carves_nothing():
    """A mesh too coarse to show the rings carves nothing rather than noise."""
    p = params(resolution=3.0, ring_spacing=(3.0, 4.0), end_spacing=4.0)
    mesh, carving = run(p)
    assert carving.depth.max() < 1e-12


def test_carving_is_repeatable_and_follows_the_seed():
    """Carving repeats exactly for the same seed and differs for another."""
    a = run(params(seed=9))[1].vertices
    b = run(params(seed=9))[1].vertices
    c = run(params(seed=10))[1].vertices
    assert np.array_equal(a, b)
    assert not np.allclose(a, c)
