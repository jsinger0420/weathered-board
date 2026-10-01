"""Pure-numpy board builder. Never imports bpy, so it can be tested with
plain Python (see tests/)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .geometry import FACE_NAMES, rounded_box
from .params import BoardParams, ParamError  # noqa: F401  (re-exported)
from .patterns import board_patterns, preview_colors
from .weather import carve


@dataclass
class BoardResult:
    vertices: np.ndarray  # (N, 3) printed millimetres
    triangles: np.ndarray  # (M, 3) int32
    preview: np.ndarray  # (N, 3) linear RGB colour preview of the ring patterns
    depth: np.ndarray  # (N,) carving depth at each vertex, printed millimetres
    face_depth: dict[str, float] = field(default_factory=dict)  # deepest cut per face, printed mm


def build(params: BoardParams) -> BoardResult:
    """Build a board: rounded box, ring patterns, carving and the colour
    preview of the patterns."""
    params.validate()
    mesh = rounded_box(params)
    patterns = board_patterns(params, mesh)
    carving = carve(params, mesh, patterns)
    colors = preview_colors(params, mesh, patterns)
    depth = carving.depth / params.scale
    face_depth = {}
    for col, face in enumerate(FACE_NAMES):
        mostly = mesh.face_weights[:, col] > 0.5
        face_depth[face] = float(depth[mostly].max()) if mostly.any() else 0.0
    return BoardResult(carving.vertices / params.scale, mesh.triangles, colors, depth, face_depth)


def check(params: BoardParams, result: BoardResult | None = None):
    """Printability findings for a board (builds it if no result is given)."""
    from .printcheck import check_board

    result = result or build(params)
    return check_board(params, result.triangles, result.face_depth)


def build_board(params: BoardParams) -> tuple[np.ndarray, np.ndarray]:
    """Vertices (printed mm) and triangles only."""
    result = build(params)
    return result.vertices, result.triangles
