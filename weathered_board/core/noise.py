"""Vectorized fractal 3D noise in numpy (no per-point Python calls).

Build plan step 3. Blender's mathutils.noise is not used: it evaluates one
point at a time, far too slow for dense meshes.
"""

from __future__ import annotations

import numpy as np


def fbm(points: np.ndarray, rng_offset: np.ndarray, octaves: int = 4,
        frequency: float = 1.0, lacunarity: float = 2.0, gain: float = 0.5) -> np.ndarray:
    """Fractal noise in roughly [-1, 1] for each point (N, 3)."""
    raise NotImplementedError("Fractal noise: build plan step 3.")
