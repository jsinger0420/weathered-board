"""Base mesh: a rounded box with its own radius on each of the 12 edges.

See docs/DESIGN.md, "Base mesh with rounded edges".

The shape is defined the way a router shapes a board: every edge is rounded
along its full length with its own radius, and where edges meet at a corner
their roundings simply intersect. Mathematically the board is the
intersection of three extruded 2D rounded rectangles, one per pair of axes,
each with its own radius in each of its four corners. That makes every edge
an exact quarter-circle and the whole board convex.

Meshing:

1. Each axis gets one sorted list of grid coordinates, refined near both
   ends where rounding happens. Every face grid uses these shared lists, so
   vertices on the 12 seams coincide exactly and merge cleanly.
2. Grid points already on the rounded board (the flat parts) stay put. The
   rest move inward along a smoothly varying direction until they reach the
   surface (a bisection search along each ray). Because the board is convex
   and the directions vary smoothly, neighbouring points land next to each
   other and triangles never fold.

Everything is in full-size millimetres and fully vectorized in numpy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .params import EDGES, FACES, BoardParams, ParamError

MAX_VERTICES = 4_000_000
MIN_BAND_SEGMENTS = 8
BISECTION_STEPS = 60

FACE_NAMES = tuple(FACES)
_FACE_BY_AXIS_SIDE = {(axis, sign): name for name, (axis, sign) in FACES.items()}
_EDGE_BY_FACES = {frozenset(pair): name for name, pair in EDGES.items()}


@dataclass
class BoxMesh:
    vertices: np.ndarray  # (N, 3) float64, full-size mm
    triangles: np.ndarray  # (M, 3) int32, wound outward
    normals: np.ndarray  # (N, 3) float64, unit
    face_weights: np.ndarray  # (N, 6) float64, columns in FACE_NAMES order


# --------------------------------------------------------------------------
# The solid: signed distance
# --------------------------------------------------------------------------

def _edge_name(axis_a: int, sign_a: int, axis_b: int, sign_b: int) -> str:
    fa = _FACE_BY_AXIS_SIDE[(axis_a, sign_a)]
    fb = _FACE_BY_AXIS_SIDE[(axis_b, sign_b)]
    return _EDGE_BY_FACES[frozenset((fa, fb))]


class RoundedBoard:
    """Signed distance (negative inside) for the router-shaped board."""

    # The three cross-sections, as (axis u, axis v); each holds the 4 edges
    # that run along the remaining axis.
    PLANES = ((1, 2), (0, 2), (0, 1))

    def __init__(self, params: BoardParams):
        self.half = 0.5 * np.array(params.size, dtype=float)
        # radius[plane][su][sv], su/sv: 0 = negative side, 1 = positive side
        self.radius = np.zeros((3, 2, 2))
        for n, (u, v) in enumerate(self.PLANES):
            for iu, su in enumerate((-1, 1)):
                for iv, sv in enumerate((-1, 1)):
                    self.radius[n, iu, iv] = params.edge_radius(_edge_name(u, su, v, sv))

    def plane_sdf(self, p: np.ndarray, n: int) -> np.ndarray:
        """2D rounded-rectangle distance in one cross-section, extruded."""
        u, v = self.PLANES[n]
        r = self.radius[n, (p[:, u] >= 0).astype(int), (p[:, v] >= 0).astype(int)]
        qu = np.abs(p[:, u]) - self.half[u] + r
        qv = np.abs(p[:, v]) - self.half[v] + r
        outside = np.hypot(np.maximum(qu, 0.0), np.maximum(qv, 0.0))
        return outside + np.minimum(np.maximum(qu, qv), 0.0) - r

    def sdf(self, p: np.ndarray) -> np.ndarray:
        return np.maximum(np.maximum(self.plane_sdf(p, 0), self.plane_sdf(p, 1)), self.plane_sdf(p, 2))

    def bands(self) -> np.ndarray:
        """(3, 2): for each axis and side, the widest radius on any edge of
        that face. Rounding only happens within this distance of the face."""
        band = np.zeros((3, 2))
        for n, (u, v) in enumerate(self.PLANES):
            band[u, 0] = max(band[u, 0], self.radius[n, 0, :].max())
            band[u, 1] = max(band[u, 1], self.radius[n, 1, :].max())
            band[v, 0] = max(band[v, 0], self.radius[n, :, 0].max())
            band[v, 1] = max(band[v, 1], self.radius[n, :, 1].max())
        return band


# --------------------------------------------------------------------------
# Grids
# --------------------------------------------------------------------------

def _axis_coords(h: float, band_lo: float, band_hi: float, spacing: float) -> np.ndarray:
    """Sorted grid coordinates along one axis, refined in both rounding bands."""
    pieces = []

    def run(a: float, b: float, step: float) -> None:
        if b - a <= 1e-12:
            return
        n = max(1, int(np.ceil((b - a) / step - 1e-9)))
        pieces.append(np.linspace(a, b, n + 1))

    lo_end = -h + band_lo
    hi_start = max(h - band_hi, lo_end)
    if band_lo > 0:
        run(-h, lo_end, min(spacing, band_lo / MIN_BAND_SEGMENTS))
    run(lo_end, hi_start, spacing)
    if band_hi > 0:
        run(hi_start, h, min(spacing, band_hi / MIN_BAND_SEGMENTS))
    coords = np.unique(np.concatenate(pieces)) if pieces else np.array([-h, h])
    coords[0], coords[-1] = -h, h
    return coords + 0.0  # turn any -0.0 into 0.0 so seams merge


def _face_grid(axis: int, sign: int, half: np.ndarray, coords: list[np.ndarray]):
    """Grid points and outward-wound triangles for one flat face."""
    i, j = (axis + 1) % 3, (axis + 2) % 3  # e_i x e_j = e_axis
    ci, cj = coords[i], coords[j]
    ni, nj = len(ci), len(cj)
    gi, gj = np.meshgrid(ci, cj, indexing="ij")
    pts = np.empty((ni * nj, 3))
    pts[:, axis] = sign * half[axis]
    pts[:, i] = gi.ravel()
    pts[:, j] = gj.ravel()

    idx = np.arange(ni * nj).reshape(ni, nj)
    v00, v10 = idx[:-1, :-1].ravel(), idx[1:, :-1].ravel()
    v11, v01 = idx[1:, 1:].ravel(), idx[:-1, 1:].ravel()
    if sign > 0:
        tris = np.concatenate([np.stack([v00, v10, v11], 1), np.stack([v00, v11, v01], 1)])
    else:
        tris = np.concatenate([np.stack([v00, v11, v10], 1), np.stack([v00, v01, v11], 1)])
    return pts, tris


def grid_coords(params: BoardParams) -> list[np.ndarray]:
    board = RoundedBoard(params)
    band = board.bands()
    spacing = params.resolution * params.scale
    return [_axis_coords(board.half[k], band[k, 0], band[k, 1], spacing) for k in range(3)]


def estimate_vertices(params: BoardParams) -> int:
    nx, ny, nz = (len(c) for c in grid_coords(params))
    return 2 * (nx * ny + ny * nz + nz * nx)


# --------------------------------------------------------------------------
# Moving grid points onto the surface
# --------------------------------------------------------------------------

def _project(board: RoundedBoard, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Move box-surface points inward onto the rounded board.

    Each point that lies outside the board travels toward a point c inside
    it: p clamped to the inner box shrunk by each face's band. That inner
    box is inside the board (every radius on a face is at most its band),
    so the ray from p to c always crosses the surface exactly once.
    Returns (points, moved mask).
    """
    half = board.half
    tol = 1e-9 * max(half.max(), 1.0)
    moved = board.sdf(pts) > tol
    if not moved.any():
        return pts.copy(), moved

    band = np.maximum(board.bands(), 1e-6 * half[:, None])  # keep directions defined
    p = pts[moved]
    c = np.clip(p, -half + band[:, 0], half - band[:, 1])
    ray = c - p  # from p (outside) to c (inside)

    t_out = np.zeros(len(p))  # sdf >= 0 here
    t_in = np.ones(len(p))  # sdf <= 0 here (at c)
    for _ in range(BISECTION_STEPS):
        t = 0.5 * (t_out + t_in)
        inside = board.sdf(p + t[:, None] * ray) <= 0.0
        t_in = np.where(inside, t, t_in)
        t_out = np.where(inside, t_out, t)

    out = pts.copy()
    out[moved] = p + (0.5 * (t_out + t_in))[:, None] * ray
    return out, moved


def vertex_normals(verts: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Area-weighted vertex normals of a triangle mesh (unit length)."""
    v = verts[tris]
    face_n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])  # length = 2 * area
    acc = np.zeros_like(verts)
    for axis in range(3):
        for corner in range(3):
            acc[:, axis] += np.bincount(tris[:, corner], weights=face_n[:, axis], minlength=len(verts))
    return acc / np.linalg.norm(acc, axis=1, keepdims=True)


def _normals_and_weights(box_pts, verts, tris, moved, half):
    """Normals and face weights.

    Points that did not move lie on flat faces (or on a sharp edge or
    corner): their normal is the sum of the axes of the faces they touch,
    and they belong fully to each of those faces. Points on the rounded
    surface take the mesh normal, and belong to each face by the squared
    normal component toward it, so weights slide smoothly across an edge.
    """
    normals = vertex_normals(verts, tris)
    sgn = np.where(box_pts >= 0, 1.0, -1.0)
    on_face = np.abs(np.abs(box_pts) - half) <= 1e-9 * max(half.max(), 1.0)
    flat = ~moved
    n = on_face[flat] * sgn[flat]
    normals[flat] = n / np.linalg.norm(n, axis=1, keepdims=True)

    weights = np.zeros((len(verts), len(FACE_NAMES)))
    for col, name in enumerate(FACE_NAMES):
        axis, sign = FACES[name]
        weights[:, col] = np.clip(sign * normals[:, axis], 0.0, 1.0) ** 2
        touches = on_face[flat, axis] & (sgn[flat, axis] == sign)
        weights[flat, col] = touches.astype(float)
    return normals, weights


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def rounded_box(params: BoardParams) -> BoxMesh:
    """Closed rounded box in full-size millimetres, centred on the origin."""
    board = RoundedBoard(params)
    half = board.half
    band = board.bands()
    spacing = params.resolution * params.scale
    coords = [_axis_coords(half[k], band[k, 0], band[k, 1], spacing) for k in range(3)]

    n_est = 2 * (len(coords[0]) * len(coords[1]) + len(coords[1]) * len(coords[2])
                 + len(coords[2]) * len(coords[0]))
    if n_est > MAX_VERTICES:
        raise ParamError(
            f"About {n_est:,} vertices at {params.resolution} mm resolution; "
            f"the limit is {MAX_VERTICES:,}. Use a coarser resolution."
        )

    all_pts, all_tris, offset = [], [], 0
    for name in FACE_NAMES:
        axis, sign = FACES[name]
        pts, tris = _face_grid(axis, sign, half, coords)
        all_pts.append(pts)
        all_tris.append(tris + offset)
        offset += len(pts)
    pts = np.concatenate(all_pts)
    tris = np.concatenate(all_tris)

    # Merge the duplicate points along the 12 seams (exactly equal by
    # construction, since every face grid uses the same axis coordinates).
    pts, inverse = np.unique(pts, axis=0, return_inverse=True)
    tris = inverse.reshape(-1)[tris].astype(np.int32)

    verts, moved = _project(board, pts)
    normals, weights = _normals_and_weights(pts, verts, tris, moved, half)
    return BoxMesh(verts, tris, normals, weights)
