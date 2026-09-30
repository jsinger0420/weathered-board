"""Pure-numpy board builder. Never imports bpy, so it can be tested with
plain Python (see tests/)."""

from __future__ import annotations

import numpy as np

from .geometry import box_mesh
from .params import BoardParams, ParamError  # noqa: F401  (re-exported)


def build_board(params: BoardParams) -> tuple[np.ndarray, np.ndarray]:
    """Build a board and return (vertices, triangles) in printed millimetres.

    Currently returns the placeholder closed box; the rounded box and
    weathering are added by the build plan steps in docs/DESIGN.md.
    """
    params.validate()
    verts, tris = box_mesh(params.size)
    return verts / params.scale, tris
