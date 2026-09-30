"""Carving: turn ring phases into inward displacement.

Build plan steps 4-5. See docs/DESIGN.md, "Combining into a displacement".
"""

from __future__ import annotations

import numpy as np

from .params import BoardParams


def erosion_profile(phi: np.ndarray, sharpness: float) -> np.ndarray:
    """E(phi): 1 across the soft earlywood, 0 at the latewood ridge."""
    raise NotImplementedError("Erosion profile: build plan step 4.")


def displace(vertices: np.ndarray, normals: np.ndarray, face_weights: np.ndarray,
             params: BoardParams, rng: np.random.Generator) -> np.ndarray:
    """Return carved vertex positions, never outside the original box."""
    raise NotImplementedError("Carving: build plan step 4.")
