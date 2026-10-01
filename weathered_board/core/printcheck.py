"""Printability checks that need only the built board and its settings.

The Blender side adds checks on the actual object (open edges,
self-intersections, its real exported size) on top of these.
All sizes in the findings are printed millimetres.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .params import FACES, BoardParams
from .weather import detail_factor

OK, INFO, WARNING, ERROR = "OK", "INFO", "WARNING", "ERROR"
MAX_TRIANGLES = 2_000_000  # some slicers slow down a lot above this
MIN_WALL_FEATURES = 2.0  # thinnest wall, in smallest printable features
MIN_CUT_FEATURES = 0.5  # shallowest carving worth printing, in smallest features


@dataclass
class Finding:
    level: str  # OK, INFO, WARNING or ERROR
    title: str
    detail: str = ""


def is_watertight(triangles: np.ndarray) -> bool:
    """Every edge shared by exactly two triangles, once in each direction."""
    t = triangles.astype(np.int64)
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    n = int(e.max()) + 1 if len(e) else 0
    fwd = e[:, 0] * n + e[:, 1]
    rev = e[:, 1] * n + e[:, 0]
    return len(np.unique(fwd)) == len(fwd) and bool(np.isin(rev, fwd).all())


def check_board(params: BoardParams, triangles: np.ndarray, face_depth: dict[str, float]) -> list[Finding]:
    """Checks on a built board. ``face_depth`` is the deepest cut on each
    face, in printed mm."""
    out: list[Finding] = []
    scale = params.scale

    # Watertight
    if is_watertight(triangles):
        out.append(Finding(OK, "Watertight", "Closed surface, consistent normals"))
    else:
        out.append(Finding(ERROR, "Not watertight", "The mesh has open or doubled edges"))

    weathered = [f for f in FACES if params.faces.get(f, False)]
    boost = params.boost()

    # Ring detail
    if weathered and params.depth > 0:
        finest = min(params.ring_spacing[0], params.end_spacing)
        printed = finest * boost / scale
        needed = params.needed_boost()
        if detail_factor(finest, params) < 1.0:
            out.append(Finding(
                ERROR if detail_factor(finest, params) == 0 else WARNING,
                "Rings too fine for the mesh",
                f"Rings {printed:.3f} mm apart; carving fades. "
                f"Use Auto Detail Boost or set Detail Boost to {needed:.1f}",
            ))
        elif printed < params.min_feature:
            out.append(Finding(
                WARNING, "Rings finer than the printer",
                f"Rings {printed:.3f} mm apart, smallest feature {params.min_feature} mm. "
                f"Set Detail Boost to {needed:.1f}",
            ))
        else:
            out.append(Finding(OK, "Ring detail", f"Rings {printed:.2f} mm apart (boost {boost:.1f}x)"))

        deepest = max((face_depth.get(f, 0.0) for f in weathered), default=0.0)
        if deepest < MIN_CUT_FEATURES * params.min_feature:
            out.append(Finding(
                WARNING, "Carving very shallow",
                f"Deepest cut {deepest:.3f} mm; under half the smallest feature "
                f"({params.min_feature} mm) may not show. Raise Depth or Detail Boost",
            ))
        else:
            out.append(Finding(OK, "Carving depth", f"Deepest cut {deepest:.3f} mm"))

    # Thinnest wall between opposite faces (a safe lower bound: the deepest
    # cuts on the two faces, as if they lined up).
    thinnest, where = np.inf, ""
    for axis, name in enumerate(("length", "width", "thickness")):
        minus = next(f for f, (a, s) in FACES.items() if a == axis and s < 0)
        plus = next(f for f, (a, s) in FACES.items() if a == axis and s > 0)
        wall = params.size[axis] / scale - face_depth.get(minus, 0.0) - face_depth.get(plus, 0.0)
        if wall < thinnest:
            thinnest, where = wall, name
    need = MIN_WALL_FEATURES * params.min_feature
    if thinnest < need:
        out.append(Finding(ERROR, "Wall too thin",
                           f"{thinnest:.3f} mm across the {where} at worst; needs {need:.2f} mm"))
    else:
        out.append(Finding(OK, "Wall thickness", f"At least {thinnest:.2f} mm across the {where}"))

    # Base
    if params.faces.get("bottom", False):
        out.append(Finding(INFO, "Bottom is weathered", "It will need supports or a raft to print"))
    else:
        out.append(Finding(OK, "Flat base", "Bottom is flat and prints directly on the bed"))

    # Size
    n = len(triangles)
    if n > MAX_TRIANGLES:
        out.append(Finding(WARNING, "Heavy mesh", f"{n:,} triangles; some slicers slow down. Raise Resolution"))
    else:
        out.append(Finding(OK, "Mesh size", f"{n:,} triangles"))
    return out
