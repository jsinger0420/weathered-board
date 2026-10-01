"""Rounded box with per-edge radii (build plan step 1)."""

import math

import numpy as np
import pytest
from meshcheck import (
    euler_ok,
    is_closed_and_consistent,
    min_triangle_area,
    signed_volume,
    triangle_normals,
)

from core.geometry import FACE_NAMES, MAX_VERTICES, RoundedBoard, rounded_box
from core.params import EDGES, FACES, BoardParams, ParamError

# A short, chunky test board in full-size mm (fast to build, all radii matter).
L, W, T = 120.0, 50.0, 20.0
RES = 0.5  # with scale 1 this is the full-size grid spacing in mm


def make(rounds=None, length=L, width=W, thickness=T, res=RES):
    """Settings for a 120 x 50 x 20 mm test board at full scale.

    ``rounds`` is one rounding for every edge, or a dict of edge roundings.
    """
    p = BoardParams(length=length, width=width, thickness=thickness, scale=1.0, resolution=res)
    if rounds is not None:
        if isinstance(rounds, (int, float)):
            rounds = {e: float(rounds) for e in EDGES}
        p.edge_round.update(rounds)
    return p


def assert_valid(mesh, p):
    """Assert ``mesh`` is a sound rounded board for ``p``.

    Closed with consistent winding, a single surface, facing outward, inside
    the original box, with no degenerate or folded triangles, unit normals,
    and every vertex on the surface.
    """
    v, t = mesh.vertices, mesh.triangles
    assert is_closed_and_consistent(t), "mesh is not closed or has flipped winding"
    assert euler_ok(v, t), "mesh is not a single closed surface"
    assert signed_volume(v, t) > 0, "triangles wound inward"
    half = 0.5 * np.array(p.size)
    assert (np.abs(v) <= half + 1e-9).all(), "vertex outside the original box"
    assert min_triangle_area(v, t) > 1e-10, "degenerate triangle"
    assert_faces_outward(mesh, p)
    assert np.allclose(np.linalg.norm(mesh.normals, axis=1), 1.0)
    assert (np.abs(RoundedBoard(p).sdf(v)) < 1e-6).all(), "vertex off the surface"


def assert_faces_outward(mesh, p):
    """Assert no triangle is folded over.

    Every triangle must face away from the interior point its vertices were
    projected from (the inner box shrunk by the rounding bands). The rounded
    parts are a projection out from those points, so a triangle facing back
    toward them would be a fold.
    """
    board = RoundedBoard(p)
    half = board.half
    band = np.maximum(board.bands(), 1e-6 * half[:, None])
    v, t = mesh.vertices, mesh.triangles
    centroid = v[t].mean(axis=1)
    inner = np.clip(centroid, -half + band[:, 0], half - band[:, 1])
    tn = triangle_normals(v, t)
    facing = np.einsum("ij,ij->i", tn, centroid - inner)
    flat = np.linalg.norm(centroid - inner, axis=1) < 1e-9
    assert (facing[~flat] > 0).all(), "folded triangle"


# --------------------------------------------------------------------------
# Validity across many rounding combinations
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value", [0.0, 0.15, 0.5, 1.0])
def test_uniform_rounding_is_valid(value):
    """Every edge at the same rounding, from sharp to fully round, gives a sound mesh."""
    p = make(value)
    assert_valid(rounded_box(p), p)


@pytest.mark.parametrize("seed", range(12))
def test_random_mixed_rounding_is_valid(seed):
    """Random mixes of sharp, light and heavy rounding give a sound mesh."""
    rng = np.random.default_rng(seed)
    # Mix of sharp, light and heavy rounding, edge by edge.
    choices = np.array([0.0, 0.05, 0.15, 0.4, 0.75, 1.0])
    rounds = {e: float(rng.choice(choices)) for e in EDGES}
    p = make(rounds)
    assert_valid(rounded_box(p), p)


@pytest.mark.parametrize("size", [(120, 50, 20), (120, 20, 50), (40, 40, 40), (300, 140, 19)])
def test_other_proportions_are_valid(size):
    """Random rounding on long, tall, cube-shaped and wide boards gives a sound mesh."""
    rng = np.random.default_rng(7)
    rounds = {e: float(rng.uniform(0, 1)) for e in EDGES}
    p = make(rounds, *size)
    assert_valid(rounded_box(p), p)


# --------------------------------------------------------------------------
# Each edge gets its own radius
# --------------------------------------------------------------------------

def edge_geometry(edge, half):
    """For an edge: (along axis, (axis_a, sign_a), (axis_b, sign_b))."""
    fa, fb = EDGES[edge]
    (ka, sa), (kb, sb) = FACES[fa], FACES[fb]
    along = 3 - ka - kb
    return along, (ka, sa), (kb, sb)


def arc_radii(mesh, p, edge):
    """Distances from an edge's arc centre to the vertices on its rounded part.

    Only vertices away from the corners are used. Returns (distances,
    expected radius).
    """
    half = 0.5 * np.array(p.size)
    r = p.edge_radius(edge)
    along, (ka, sa), (kb, sb) = edge_geometry(edge, half)
    v = mesh.vertices
    # Stay clear of the corners, where the radius blends to the corner value.
    rmax = max(p.edge_radius(e) for e in EDGES)
    away = np.abs(v[:, along]) < half[along] - 2.2 * rmax - 1e-6
    ca, cb = sa * (half[ka] - r), sb * (half[kb] - r)
    in_arc = (sa * v[:, ka] > half[ka] - r + 1e-9) & (sb * v[:, kb] > half[kb] - r + 1e-9)
    sel = away & in_arc
    d = np.hypot(v[sel, ka] - ca, v[sel, kb] - cb)
    return d, r


@pytest.mark.parametrize("edge", list(EDGES))
def test_each_edge_has_its_own_radius(edge):
    """Raising one edge's rounding changes only that edge.

    Every edge's arc must be an exact circle of its own radius.
    """
    # Big cube so every edge, including the short end edges, has a middle
    # stretch clear of the corner blending.
    rounds = {e: 0.1 for e in EDGES}
    rounds[edge] = 0.3
    p = make(rounds, length=200, width=200, thickness=200, res=2.0)
    mesh = rounded_box(p)
    for e in EDGES:
        along, _, _ = edge_geometry(e, 0.5 * np.array(p.size))
        d, r = arc_radii(mesh, p, e)
        assert len(d) > 0, f"no arc vertices found on {e}"
        assert np.allclose(d, r, atol=1e-9), f"{e}: expected radius {r}"


def test_sharp_edges_stay_sharp():
    """All edges at 0 give an exact box: sharp corners and full volume."""
    p = make(0.0)
    v = rounded_box(p).vertices
    half = 0.5 * np.array(p.size)
    corners = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]) * half
    for c in corners:
        assert np.isclose(np.linalg.norm(v - c, axis=1).min(), 0.0)
    assert np.isclose(signed_volume(v, rounded_box(p).triangles), L * W * T)


def test_fully_rounded_long_edges_make_a_cylinder():
    """A square board with its long edges fully rounded is a round dowel along its middle."""
    rounds = {e: 0.0 for e in EDGES}
    for e in ("top_front", "top_back", "bottom_front", "bottom_back"):
        rounds[e] = 1.0
    p = make(rounds, length=200, width=30, thickness=30, res=0.5)
    v = rounded_box(p).vertices
    mid = np.abs(v[:, 0]) < 60
    assert np.allclose(np.hypot(v[mid, 1], v[mid, 2]), 15.0, atol=1e-9)


def test_uniform_radius_volume_matches_formula():
    """With one radius on every edge, the volume matches the exact formula.

    The formula is for a router-shaped box; the mesh must agree within 0.2%.
    """
    # Router-style corners: three equal quarter-cylinders intersect, so each
    # corner keeps (2 - sqrt 2) r^3 of its r^3 cube (one eighth of a
    # Steinmetz tricylinder), and each edge keeps a quarter disc per length.
    r = 6.0
    p = make(res=0.25)
    for e in EDGES:
        p.edge_round[e] = r / p.max_radius(e)
    assert all(np.isclose(p.edge_radius(e), r) for e in EDGES)
    a, b, c = L - 2 * r, W - 2 * r, T - 2 * r
    expected = (a * b * c + 2 * r * (a * b + b * c + c * a)
                + math.pi * r * r * (a + b + c) + 8 * (2 - math.sqrt(2)) * r**3)
    mesh = rounded_box(p)
    assert signed_volume(mesh.vertices, mesh.triangles) == pytest.approx(expected, rel=2e-3)


# --------------------------------------------------------------------------
# Normals and face weights
# --------------------------------------------------------------------------

def test_normals_point_outward_and_flat_faces_are_exact():
    """Normals point outward everywhere and are exact on flat faces.

    On a flat face a vertex's normal must be exactly that face's axis.
    """
    rng = np.random.default_rng(3)
    p = make({e: float(rng.uniform(0.1, 1)) for e in EDGES})
    mesh = rounded_box(p)
    v, n = mesh.vertices, mesh.normals
    # Outward everywhere: away from the board's centre line in each axis.
    board = RoundedBoard(p)
    inner = np.clip(v, -board.half + board.bands()[:, 0], board.half - board.bands()[:, 1])
    out = np.einsum("ij,ij->i", n, v - inner)
    assert (out[np.linalg.norm(v - inner, axis=1) > 1e-9] > 0).all()
    # Flat-face vertices have exactly the face's axis as normal.
    top = np.isclose(v[:, 2], T / 2) & (np.abs(v[:, 0]) < 10) & (np.abs(v[:, 1]) < 5)
    assert np.allclose(n[top], [0, 0, 1])


def test_face_weights_on_flat_faces():
    """A vertex in the middle of the top belongs to the top alone."""
    p = make(0.3)
    mesh = rounded_box(p)
    centre_top = np.argmin(np.linalg.norm(mesh.vertices - [0, 0, T / 2], axis=1))
    w = mesh.face_weights[centre_top]
    assert w[FACE_NAMES.index("top")] == 1.0
    assert w.sum() == 1.0


def test_face_weights_blend_across_a_rounded_edge():
    """Across a rounded edge, a vertex's weights for its two faces add up to 1."""
    p = make(0.5)
    mesh = rounded_box(p)
    w = mesh.face_weights
    top, front = FACE_NAMES.index("top"), FACE_NAMES.index("front")
    rounded = mesh.vertices[:, 0] ** 2 < 1  # mid-length strip
    on_edge = rounded & (w[:, top] > 0) & (w[:, front] > 0)
    assert on_edge.any()
    assert np.allclose(w[on_edge, top] + w[on_edge, front], 1.0)


def test_sharp_seam_belongs_to_both_faces():
    """On a sharp edge, seam vertices belong fully to both faces."""
    p = make(0.0)
    mesh = rounded_box(p)
    v, w = mesh.vertices, mesh.face_weights
    top, front = FACE_NAMES.index("top"), FACE_NAMES.index("front")
    seam = np.isclose(v[:, 2], T / 2) & np.isclose(v[:, 1], -W / 2)
    assert seam.any()
    assert (w[seam, top] == 1).all() and (w[seam, front] == 1).all()


# --------------------------------------------------------------------------
# Resolution and limits
# --------------------------------------------------------------------------

def test_every_rounded_band_gets_at_least_eight_segments():
    """Each rounded edge gets enough vertices to look round, even on a coarse mesh."""
    p = make({e: 0.05 for e in EDGES}, res=5.0)  # coarse grid, thin bands
    v = rounded_box(p).vertices
    r = p.edge_radius("top_front")
    mid = np.abs(v[:, 0]) < 1e-9
    band = mid & (v[:, 1] < -W / 2 + r - 1e-9) & (v[:, 2] > T / 2 - r + 1e-9)
    assert band.sum() >= 7  # 8 segments per side -> 7 interior arc points + more


def test_too_many_vertices_is_refused():
    """A mesh over the vertex limit is refused with a message, before building it."""
    p = make(0.2, length=3000, width=300, thickness=50, res=0.05)
    with pytest.raises(ParamError, match="vertices"):
        rounded_box(p)
    assert MAX_VERTICES > 0


def test_build_is_deterministic():
    """Building twice with the same settings gives identical meshes."""
    p = make(0.37)
    a, b = rounded_box(p), rounded_box(p)
    assert np.array_equal(a.vertices, b.vertices)
    assert np.array_equal(a.triangles, b.triangles)
