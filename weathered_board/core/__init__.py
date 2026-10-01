"""Pure-numpy board builder. Never imports bpy, so it can be tested with
plain Python (see tests/)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import rounded_box
from .params import BoardParams, ParamError  # noqa: F401  (re-exported)
from .patterns import board_patterns, preview_colors


@dataclass
class BoardResult:
    vertices: np.ndarray  # (N, 3) printed millimetres
    triangles: np.ndarray  # (M, 3) int32
    preview: np.ndarray  # (N, 3) linear RGB colour preview of the ring patterns


def build(params: BoardParams) -> BoardResult:
    """Build a board: rounded box, ring patterns and their colour preview.

    Weathering (carving) is added by later build plan steps in
    docs/DESIGN.md; until then the board's shape is the rounded box.
    """
    params.validate()
    mesh = rounded_box(params)
    patterns = board_patterns(params, mesh)
    colors = preview_colors(params, mesh, patterns)
    return BoardResult(mesh.vertices / params.scale, mesh.triangles, colors)


def build_board(params: BoardParams) -> tuple[np.ndarray, np.ndarray]:
    """Vertices (printed mm) and triangles only."""
    result = build(params)
    return result.vertices, result.triangles
