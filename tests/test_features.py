"""Knots, checks and patchy wear (build plan step 5)."""

import numpy as np
import pytest
from meshcheck import is_closed_and_consistent, triangle_normals

from core.geometry import FACE_NAMES, rounded_box
from core.grain import VirtualLog
from core.params import EDGES, BoardParams
from core.patterns import board_patterns, preview_colors
from core.rng import streams
from core.weather import MAX_CHECK_FRACTION, carve

L, W, T = 400.0, 100.0, 25.0


def params(**kw):
    """Settings for a 400 x 100 x 25 mm test board with every feature off.

    Tests turn on the features they need.
    """
    base = dict(length=L, width=W, thickness=T, scale=1.0, resolution=0.8, seed=3, depth=2.0,
                auto_detail=False, knots=(0, 0), checks=0.0, patchiness=0.0)
    base.update(kw)
    p = BoardParams(**base)
    p.edge_round.update({e: 0.15 for e in EDGES})
    return p


def patterns(p):
    """Build the rounded box for ``p`` and its patterns. Returns (mesh, patterns)."""
    mesh = rounded_box(p)
    return mesh, board_patterns(p, mesh)


def face_only(mesh, face):
    """Vertices fully on one face."""
    w = mesh.face_weights
    return (w[:, FACE_NAMES.index(face)] == 1.0) & (w.sum(axis=1) == 1.0)


# --------------------------------------------------------------------------
# Knots
# --------------------------------------------------------------------------

@pytest.mark.parametrize("lo,hi", [(0, 0), (1, 1), (2, 4)])
def test_knot_count_stays_in_range(lo, hi):
    """Each board gets between Knots Min and Knots Max knots."""
    for seed in range(5):
        _, pt = patterns(params(seed=seed, knots=(lo, hi)))
        assert lo <= len(pt.knots.knots) <= hi


@pytest.mark.parametrize("seed", range(5))
def test_every_knot_shows_on_the_board(seed):
    """A knot always crosses the board, so its core shows on some vertex."""
    _, pt = patterns(params(seed=seed, knots=(1, 1)))
    assert pt.knot_core.max() > 0.9


def test_knot_core_stands_proud():
    """A knot's core is cut less than half as deep as the wood around it.

    Knots are hard and resist wear, so they should stand proud.
    """
    for seed in range(6):
        p = params(seed=seed, knots=(1, 1), faces={f: True for f in FACE_NAMES})
        mesh, pt = patterns(p)
        carving = carve(p, mesh, pt)
        core = pt.knot_core > 0.99
        if core.sum() < 20:
            continue
        ring = (pt.knot_core < 0.01) & (pt.knot_core > -1)
        assert carving.depth[core].mean() < 0.5 * carving.depth[ring].mean()
        return
    pytest.fail("no knot large enough to compare")


def test_grain_bends_around_knots():
    """The grain bends around knots and is untouched far from them.

    Near a knot the ring phase shifts; far from every knot it must match a
    board without knots exactly.
    """
    mesh, plain = patterns(params(knots=(0, 0)))
    _, knotty = patterns(params(knots=(2, 2)))
    near = knotty.knot_core > 0.0
    bent = np.abs(np.mod(knotty.long_phase - plain.long_phase + 0.5, 1) - 0.5)
    assert bent[near].mean() > 0.05
    # Far from every knot the grain is unchanged.
    far = knotty.knots.bend(mesh.vertices) < 1e-9
    diff = np.abs(np.mod(knotty.long_phase[far] - plain.long_phase[far] + 0.5, 1) - 0.5)
    assert diff.max() < 1e-6


def test_knots_do_not_reshuffle_anything_else():
    """Adding knots leaves the ends, patchy wear and pith unchanged.

    Each part draws from its own random stream, so knots must not reshuffle
    the others.
    """
    mesh, a = patterns(params(knots=(0, 0), patchiness=0.5, checks=0.5))
    _, b = patterns(params(knots=(3, 3), patchiness=0.5, checks=0.5))
    assert np.array_equal(a.end_phase, b.end_phase)
    assert np.array_equal(a.patch, b.patch)
    assert np.array_equal(a.log.pith_point, b.log.pith_point)


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def test_no_checks_when_off():
    """Checks set to 0 makes no cracks at all."""
    _, pt = patterns(params(checks=0.0))
    assert not pt.checks.long and not pt.checks.end
    assert pt.long_check.max() == 0 and pt.end_check.max() == 0


def test_checks_only_on_weathered_long_faces():
    """Long-face cracks only go on long faces that are being weathered."""
    for seed in range(8):
        p = params(seed=seed, checks=1.0, faces={f: f in ("top", "end_a", "end_b") for f in FACE_NAMES})
        _, pt = patterns(p)
        for c in pt.checks.long:
            assert (c.axis, c.sign) == (2, 1), "check on a face that is not weathered"


def test_long_checks_stay_on_their_own_face():
    """Each long-face crack shows on its own face, not the opposite one."""
    p = params(checks=1.0, seed=2, faces={f: True for f in FACE_NAMES})
    mesh, pt = patterns(p)
    assert pt.checks.long
    names = {(2, 1): ("top", "bottom"), (2, -1): ("bottom", "top"), (1, 1): ("back", "front"), (1, -1): ("front", "back")}
    all_checks = pt.checks.long
    for c in all_checks:
        own, opposite = (face_only(mesh, f) for f in names[(c.axis, c.sign)])
        pt.checks.long = [c]  # look at this crack alone
        assert pt.checks.long_checks(mesh.vertices[own]).max() > 0.5
        assert pt.checks.long_checks(mesh.vertices[opposite]).max() == 0.0
    pt.checks.long = all_checks


def test_long_checks_run_along_the_board():
    """Long-face cracks are nearly straight and run a good way along the board.

    Their wander stays under 4% of the width and they are at least 15% of
    the board long.
    """
    p = params(checks=1.0, seed=4)
    _, pt = patterns(p)
    for c in pt.checks.long:
        amplitude = c.wander[0].sum()
        assert amplitude <= 0.04 * W  # gentle wander, nearly straight
        assert c.length >= 0.15 * L


def test_checks_cut_deeper_than_the_wear_but_within_their_cap():
    """Cracks cut deeper than the wear, but never past 35% of the thickness."""
    p = params(checks=1.0, seed=1, faces={f: True for f in FACE_NAMES})
    mesh, pt = patterns(p)
    carving = carve(p, mesh, pt)
    in_crack = (pt.long_check > 0.95) | (pt.end_check > 0.95)
    assert in_crack.any()
    assert carving.depth[in_crack].max() > p.depth * 1.3
    assert carving.depth.max() <= MAX_CHECK_FRACTION * T + 1e-6


def test_end_checks_only_on_their_own_end():
    """An end with no cracks of its own shows no crack from the other end."""
    p = params(checks=1.0, seed=5, faces={f: True for f in FACE_NAMES})
    mesh, pt = patterns(p)
    a = [c for c in pt.checks.end if c.end == "end_a"]
    b = [c for c in pt.checks.end if c.end == "end_b"]
    assert a or b
    if not b:
        assert pt.end_check[mesh.vertices[:, 0] > 0].max() == 0.0
    if not a:
        assert pt.end_check[mesh.vertices[:, 0] < 0].max() == 0.0


# --------------------------------------------------------------------------
# Patchy wear
# --------------------------------------------------------------------------

def test_patch_off_means_full_depth():
    """Patchiness 0 leaves the wear at full depth everywhere."""
    _, pt = patterns(params(patchiness=0.0))
    assert np.all(pt.patch == 1.0)


@pytest.mark.parametrize("amount", [0.3, 1.0])
def test_patch_range_and_smoothness(amount):
    """Patchy wear stays in range, really varies, and changes gently.

    It stays between 1 - patchiness and 1, and changes by under 10% of full
    depth per millimetre, gently enough to carve without folding.
    """
    mesh, pt = patterns(params(patchiness=amount))
    assert pt.patch.min() >= 1.0 - amount - 1e-12 and pt.patch.max() <= 1.0
    assert pt.patch.max() - pt.patch.min() > 0.3 * amount  # it actually varies
    # Smooth: it scales the recession, so it may change only gently,
    # here at most 10% of full depth per millimetre.
    e = mesh.triangles[:, [0, 1]]
    change = np.abs(np.diff(pt.patch[e], axis=1))[:, 0]
    length = np.linalg.norm(np.diff(mesh.vertices[e], axis=1)[:, 0], axis=1)
    assert (change / length).max() < 0.1


# --------------------------------------------------------------------------
# Everything together
# --------------------------------------------------------------------------

@pytest.mark.parametrize("seed", range(4))
def test_carving_with_all_features_is_valid(seed):
    """With every feature turned up, the carved board is still sound.

    Random rounding and faces too; the board must stay closed, inside its
    original size and free of folded triangles.
    """
    rng = np.random.default_rng(100 + seed)
    p = params(seed=seed, knots=(1, 3), checks=1.0, patchiness=0.8, depth=4.0, ridge_sharpness=0.9,
               faces={f: bool(rng.random() < 0.8) for f in FACE_NAMES})
    p.edge_round.update({e: float(rng.choice([0.0, 0.1, 0.5, 1.0])) for e in EDGES})
    mesh, pt = patterns(p)
    carving = carve(p, mesh, pt)
    assert is_closed_and_consistent(mesh.triangles)
    half = 0.5 * np.array(p.size)
    assert (np.abs(carving.vertices) <= half + 1e-9).all()
    before = triangle_normals(mesh.vertices, mesh.triangles)
    after = triangle_normals(carving.vertices, mesh.triangles)
    assert (np.einsum("ij,ij->i", before, after) > 0).all()


def test_preview_shows_knots_and_cracks_darker():
    """The colour preview draws knot cores and cracks darker than plain wood."""
    p = params(knots=(1, 1), checks=1.0, seed=2, faces={f: True for f in FACE_NAMES})
    mesh, pt = patterns(p)
    colors = preview_colors(p, mesh, pt)
    long_face = ~(face_only(mesh, "end_a") | face_only(mesh, "end_b"))
    plain = long_face & (pt.knot_core == 0) & (pt.long_check == 0)
    if (pt.knot_core > 0.99).any():
        assert colors[pt.knot_core > 0.99].sum(1).mean() < colors[plain].sum(1).mean()
    if (pt.long_check > 0.99).any():
        assert colors[pt.long_check > 0.99].sum(1).mean() < colors[plain].sum(1).mean()
