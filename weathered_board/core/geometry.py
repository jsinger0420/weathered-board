"""Base mesh: a rounded box with its own radius on each of the 12 edges.

Build plan step 1 replaces ``box_mesh`` with the rounded-box builder
described in docs/DESIGN.md ("Base mesh with rounded edges"). Until then a
plain closed box stands in, so the Blender side can be wired up and tested
end to end.
"""

from __future__ import annotations

import numpy as np

from .params import BoardParams


def box_mesh(size: tuple[float, float, float]) -> tuple[np.ndarray, np.ndarray]:
    """Closed box centred on the origin, triangles wound outward.

    Returns (vertices float64 (N, 3), triangles int32 (M, 3)).
    """
    hx, hy, hz = (0.5 * s for s in size)
    verts = np.array(
        [
            [-hx, -hy, -hz], [hx, -hy, -hz], [hx, hy, -hz], [-hx, hy, -hz],
            [-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz],
        ],
        dtype=np.float64,
    )
    quads = [
        (0, 3, 2, 1),  # bottom (-Z)
        (4, 5, 6, 7),  # top (+Z)
        (0, 1, 5, 4),  # front (-Y)
        (2, 3, 7, 6),  # back (+Y)
        (0, 4, 7, 3),  # end_a (-X)
        (1, 2, 6, 5),  # end_b (+X)
    ]
    tris = []
    for a, b, c, d in quads:
        tris.append((a, b, c))
        tris.append((a, c, d))
    return verts, np.array(tris, dtype=np.int32)


def rounded_box(params: BoardParams):
    """Rounded box with per-edge radii, normals and face weights.

    Not implemented yet (build plan step 1). Will return
    (vertices, triangles, normals, face_weights).
    """
    raise NotImplementedError("Rounded box builder: build plan step 1.")
