"""Carving: turn ring phases into inward displacement.

See docs/DESIGN.md, "Turning rings into ridges" and "Combining into a
displacement". In weathered wood the soft earlywood wears away and the
hard latewood stands proud, so each face's ring phase becomes a depth:
zero on the latewood ridge, up to ``depth`` in the earlywood valleys.
Knot cores wear less, cracks cut deeper, and patchy wear scales the depth.

The carving is done in two parts that each cannot fold the mesh (a smooth
recession of the whole surface, then the ridges raised back up), followed
by a repair pass that eases back any carving that would still turn a
triangle over. See ``carve``.

All lengths are full-size millimetres.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import FACE_NAMES, BoxMesh, RoundedBoard
from .params import END_FACES, FACES, BoardParams
from .patterns import Patterns

RIDGE_CENTRE = 0.88  # ring phase of the latewood ridge (matches the preview)
VALLEY_SCOOP = 0.2  # share of the depth that curves the valley floor
MIN_SAMPLES_PER_RING = 2.0  # below this the ridges are flattened out
FULL_SAMPLES_PER_RING = 4.0  # at or above this they are carved in full
MIN_SAMPLES_PER_WALL = 4.0  # vertices across a ridge wall before it looks stepped
SHRINK_MARGIN = 3.0  # carving rays aim at least this many depths inside the board
NORMAL_SMOOTHING_STEPS = 12  # passes that ease ridge directions across corner creases
MAX_REPAIR_PASSES = 40  # halvings of ridge height at turned-over triangles
FADE_SLOPE = 3.0  # depth changes no faster than 1 mm per FADE_SLOPE mm
KNOT_HARDNESS = 0.85  # how much less a knot's core wears than the wood around it
CHECK_DEPTH = 1.6  # checks cut this many times the face's depth (within their cap)
MAX_CHECK_FRACTION = 0.35  # checks never deeper than this share of the thickness


@dataclass
class Carving:
    """The carved board, in full-size millimetres.

    ``depth`` is the cut at each vertex, measured straight into the faces (the
    largest move along any one axis), and is 0 on latewood ridges.
    """

    vertices: np.ndarray  # (N, 3) carved positions, full-size mm
    depth: np.ndarray  # (N,) cut at each vertex, measured straight into the faces, mm


def ridge_half_width(sharpness: float) -> float:
    """Half-width of the latewood ridge as a fraction of a ring.

    Sharpness 0 gives a smooth wave spanning the whole ring; sharpness 1 a
    narrow ridge between wide, flat-bottomed valleys.
    """
    return 0.5 - 0.44 * float(np.clip(sharpness, 0.0, 1.0))


def erosion_profile(phase: np.ndarray, sharpness: float, half_width: float | None = None) -> np.ndarray:
    """E(phase) in [0, 1]: 0 on the latewood ridge, 1 deepest in the earlywood.

    The ridge's sides rise over ``ridge_half_width`` of a ring; beyond that
    the valley floor keeps sinking gently toward the middle of the
    earlywood, so valleys are scooped rather than flat-bottomed. Periodic
    in phase (E(0) = E(1)), so there is no seam where one year's rings end
    and the next begin. ``half_width`` overrides the one from sharpness
    (used to widen ridges the mesh is too coarse to carve crisply).
    """
    hw = ridge_half_width(sharpness) if half_width is None else min(half_width, 0.5)
    d = np.abs(np.mod(phase - RIDGE_CENTRE + 0.5, 1.0) - 0.5)  # distance to ridge, 0..0.5
    sides = 0.5 - 0.5 * np.cos(np.pi * np.clip(d / hw, 0.0, 1.0))
    bowl = 0.5 - 0.5 * np.cos(np.pi * d / 0.5)
    return (1.0 - VALLEY_SCOOP) * sides + VALLEY_SCOOP * bowl


def samples_per_ring(ring_spacing: float, params: BoardParams) -> float:
    """How many mesh vertices fall across one ring, for a full-size spacing."""
    return ring_spacing * params.boost() / (params.resolution * params.scale)


def detail_factor(ring_spacing: float, params: BoardParams) -> float:
    """1 when the mesh is fine enough to carve each ring, easing to 0 when it is too coarse.

    A coarse mesh cannot show ridges; carving them anyway would only give
    random-looking jagged noise, so the carving fades out instead. The
    ridges stay on the original surface either way, so the board keeps its
    size.
    """
    k = samples_per_ring(ring_spacing, params)
    t = (k - MIN_SAMPLES_PER_RING) / (FULL_SAMPLES_PER_RING - MIN_SAMPLES_PER_RING)
    return float(np.clip(t, 0.0, 1.0))


def effective_half_width(ring_spacing: float, params: BoardParams) -> float:
    """The ridge half-width actually carved, widened if the mesh is too coarse.

    Starts from the one asked for by ridge_sharpness. A ridge wall that
    falls on fewer than MIN_SAMPLES_PER_WALL vertices comes out as a jagged
    staircase wherever rings cross the grid at an angle (as the end
    semicircles always do); widening it keeps the ridge smooth.
    """
    k = samples_per_ring(ring_spacing, params)
    return max(ridge_half_width(params.ridge_sharpness), MIN_SAMPLES_PER_WALL / max(k, 1e-9))


def _smoothstep(t: np.ndarray) -> np.ndarray:
    """Smooth 0-to-1 ramp with zero slope at both ends (see features._smoothstep)."""
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _border_taper(p: np.ndarray, half: np.ndarray, axis: int, margin: float, depth: float) -> np.ndarray:
    """Depth factor near a face's border: 0 at the border, 1 inside the margin.

    It reaches 1 at ``margin`` mm inside the border, or at FADE_SLOPE x
    depth if that is wider, so the fade is never too steep.
    """
    if margin <= 0:
        return np.ones(len(p))
    i, j = (axis + 1) % 3, (axis + 2) % 3
    dist = np.minimum(half[i] - np.abs(p[:, i]), half[j] - np.abs(p[:, j]))
    return _smoothstep(dist / max(margin, FADE_SLOPE * depth))


def _neighbour_fade(p: np.ndarray, half: np.ndarray, face: str, depth: np.ndarray,
                    face_depth: dict[str, float]) -> np.ndarray:
    """Ease a face's depth down to a shallower neighbour's before their edge.

    Where a weathered face meets an unweathered one (or a shallower one,
    such as a long face beside an end with its own depth), the depth would
    otherwise change from one to the other across the edge's rounding,
    which can be a fraction of a millimetre wide: too steep to carve
    without folding the mesh. Instead it eases down over FADE_SLOPE times
    the difference, so both sides reach the edge at the same depth.
    """
    axis, _ = FACES[face]
    out = depth
    for name, (n_axis, n_sign) in FACES.items():
        if n_axis == axis:
            continue
        drop = face_depth[face] - face_depth[name]
        if drop <= 0:
            continue
        dist = half[n_axis] - n_sign * p[:, n_axis]  # distance to that border
        floor = face_depth[name]
        out = np.minimum(out, floor + (depth - floor) * _smoothstep(dist / (FADE_SLOPE * drop)))
    return out


def face_depths(params: BoardParams, mesh: BoxMesh, patterns: Patterns):
    """Depths each face asks for at each vertex, before blending.

    Returns (nominal, actual), both (N, 6): nominal is the face's full
    depth (with the border taper), actual is that times the erosion
    profile, so it is 0 on latewood ridges.
    """
    half = 0.5 * np.array(params.size)
    long_detail = detail_factor(min(params.ring_spacing), params)
    end_detail = detail_factor(params.end_spacing, params)
    long_hw = effective_half_width(min(params.ring_spacing), params)
    end_hw = effective_half_width(params.end_spacing, params)

    # Each face's full depth, as carved (0 if not weathered). A mesh too
    # coarse for the rings carves nothing rather than noise.
    face_depth = {
        f: (params.carve_depth(end=True) * end_detail if f in END_FACES else params.carve_depth() * long_detail)
        if params.faces.get(f, False) else 0.0
        for f in FACE_NAMES
    }
    p = mesh.vertices
    nominal = np.zeros((len(p), len(FACE_NAMES)))
    actual = np.zeros_like(nominal)
    for col, face in enumerate(FACE_NAMES):
        if face_depth[face] <= 0:
            continue
        is_end = face in END_FACES
        erosion = erosion_profile(patterns.phase_for_face(face), params.ridge_sharpness,
                                  end_hw if is_end else long_hw)
        if not is_end and patterns.knot_core is not None:
            # A knot's dense core barely wears, so it stands proud.
            erosion = erosion * (1.0 - KNOT_HARDNESS * patterns.knot_core)
        depth = face_depth[face] * _border_taper(p, half, FACES[face][0], params.edge_margin, face_depth[face])
        depth = _neighbour_fade(p, half, face, depth, face_depth)
        fade = depth / face_depth[face]  # 1 away from borders, easing to 0 at them
        if patterns.patch is not None:
            depth = depth * patterns.patch
        nominal[:, col] = depth
        actual[:, col] = depth * erosion
        check = patterns.check_for_face(face)
        if check is not None:
            # Cracks cut deeper than the wear around them, up to 35% of the
            # thickness (they are narrow, so even cracks on opposite faces
            # leave 30% of the wood between them), and fade out at borders.
            crack_depth = min(CHECK_DEPTH * face_depth[face], MAX_CHECK_FRACTION * params.thickness)
            actual[:, col] = np.maximum(actual[:, col], crack_depth * fade * check)
    return nominal, actual


def smoothed_normals(mesh: BoxMesh, steps: int = NORMAL_SMOOTHING_STEPS) -> np.ndarray:
    """Normals eased across creases, for raising the ridges.

    Where two edge roundings meet at a corner the surface turns sharply
    along a crease, and neighbouring normals point very differently.
    Raising ridges along them would pull neighbouring vertices apart in
    different directions and can turn triangles over. Each pass replaces a
    rounded vertex's normal with the average of the triangles around it;
    flat-face vertices keep their exact face normal.
    """
    n = mesh.normals.copy()
    rounded = mesh.rounded
    # Only rounded vertices change, and they only read their own triangles.
    tris = mesh.triangles[rounded[mesh.triangles].any(axis=1)]
    if len(tris) == 0:
        return n
    count = np.bincount(tris.ravel(), minlength=len(n)).astype(float)
    for _ in range(steps):
        tri_sum = n[tris].sum(axis=1)  # (M, 3)
        acc = np.zeros_like(n)
        for axis in range(3):
            for corner in range(3):
                acc[:, axis] += np.bincount(tris[:, corner], weights=tri_sum[:, axis], minlength=len(n))
        acc /= np.maximum(count, 1.0)[:, None]
        acc /= np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-12)
        n[rounded] = acc[rounded]
    return n


def carve(params: BoardParams, mesh: BoxMesh, patterns: Patterns) -> Carving:
    """Carve the ring pattern into the board, in two parts.

    1. Recession. The whole surface sinks by the faces' full depth Dn,
       which is smooth (it only changes across edges and border tapers).
       Each vertex moves toward its own point c inside the board, the
       vertex clamped to an inner box shrunk by at least twice the deepest
       cut, by Dn along its dominant axis and proportionally along the
       others: -Dn (p - c) / max|p - c|. On a flat face this is a straight
       cut; near an edge the faces and the edge recede together, so the
       carving runs out over the edge with no raised lip. Each vertex
       moves along its own ray toward c by less than its distance from c,
       so no triangle can turn over.

    2. Ridges. The latewood is built back up along the surface normal by
       Dn - D, where D is the depth the erosion profile asks for (0 on a
       ridge, Dn deepest in the earlywood). Raising a surface along its
       normal by a varying amount is a height map, which cannot fold.

    Every vertex ends up no further out than where it started, so the
    carved board never exceeds its original size, and ridge tops sit on
    the original surface.
    """
    nominal, actual = face_depths(params, mesh, patterns)
    w = mesh.face_weights
    total = np.maximum(w.sum(axis=1), 1e-12)
    d_nominal = (w * nominal).sum(axis=1) / total
    d_actual = (w * actual).sum(axis=1) / total
    p = mesh.vertices
    if d_nominal.max() <= 0:
        return Carving(p.copy(), np.zeros(len(p)))

    board = RoundedBoard(params)
    half = board.half
    deepest = max(params.carve_depth(), params.carve_depth(end=True))
    inset = np.minimum(np.maximum(board.bands(), SHRINK_MARGIN * deepest), half[:, None])
    c = np.clip(p, -half + inset[:, 0], half - inset[:, 1])
    ray = p - c
    reach = np.maximum(np.abs(ray).max(axis=1), 1e-12)

    recession = -(d_nominal / reach)[:, None] * ray
    lift = (d_nominal - d_actual)[:, None] * smoothed_normals(mesh)
    lift = _limit_lift(p + recession, lift, half)
    recession, lift = _repair_folds(mesh, recession, lift)
    # Guard against round-off pushing a ridge top a hair past the original.
    carved = np.clip(p + recession + lift, -half, half)
    # Depth as the cut measured straight into the faces: the largest move
    # along any one axis. (At an edge the corner also recedes diagonally,
    # as a box shrunk evenly on every face does.)
    depth = np.abs(p - carved).max(axis=1)
    return Carving(carved, depth)


def _limit_lift(receded: np.ndarray, lift: np.ndarray, half: np.ndarray) -> np.ndarray:
    """Shorten any ridge lift that would poke past the original board.

    On a rounded edge the smoothed normal can point a little more outward
    than the recession came in, so a full-height ridge could end up just
    outside the original surface. Scaling the lift (rather than clamping
    the vertex afterwards) keeps the vertex on its own path, so it cannot
    fold anything."""
    room = half - np.abs(receded)  # >= 0: distance to the box on each axis
    toward = np.where(np.sign(lift) == np.sign(receded), np.abs(lift), 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(toward > 1e-15, room / toward, np.inf)
    scale = np.clip(ratio.min(axis=1), 0.0, 1.0)
    return lift * scale[:, None]


def _triangle_orientation(verts: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Un-normalized triangle normals."""
    v = verts[tris]
    return np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])


def _repair_folds(mesh: BoxMesh, recession: np.ndarray, lift: np.ndarray):
    """Ease the carving back just enough that no triangle turns over.

    First, ridges are lowered: the lift at the corners of any turned-over
    triangle is halved, repeatedly. If a triangle is still turned over
    after that, the whole carving at its corners is eased back the same
    way. The uncarved board never folds, so this always ends with a clean
    mesh. In practice it touches a handful of vertices at corners, where
    edges of different roundings meet, the end rings meet the long grain,
    or a weathered face meets an unweathered one; real boards are worn
    smooth at corners anyway. After the first full check only triangles
    around changed vertices are looked at again.
    """
    tris = mesh.triangles
    p = mesh.vertices
    before = _triangle_orientation(p, tris)
    recession, lift = recession.copy(), lift.copy()
    candidates = np.arange(len(tris))

    def flipped_vertices():
        """Vertices of triangles that are currently turned over, or None if none are.

        Also narrows the triangles to recheck next time to those around these
        vertices, since only they can change.
        """
        nonlocal candidates
        t = tris[candidates]
        after = _triangle_orientation(p + recession + lift, t)
        bad = np.einsum("ij,ij->i", before[candidates], after) <= 0
        if not bad.any():
            return None
        verts = np.unique(t[bad])
        changed = np.zeros(len(p), dtype=bool)
        changed[verts] = True
        candidates = np.flatnonzero(changed[tris].any(axis=1))
        return verts

    for _ in range(MAX_REPAIR_PASSES):
        bad = flipped_vertices()
        if bad is None:
            return recession, lift
        lift[bad] *= 0.5
    for _ in range(MAX_REPAIR_PASSES):
        bad = flipped_vertices()
        if bad is None:
            return recession, lift
        recession[bad] *= 0.5
        lift[bad] *= 0.5
    bad = flipped_vertices()
    if bad is not None:
        recession[bad] = 0.0
        lift[bad] = 0.0
    return recession, lift
