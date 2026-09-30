"""End faces: evenly spaced, stylized semicircles.

Build plan step 3. See docs/DESIGN.md, "End faces: stylized semicircles".
"""

from __future__ import annotations

import numpy as np

from .params import BoardParams


def end_phase(points: np.ndarray, face: str, params: BoardParams, rng: np.random.Generator) -> np.ndarray:
    """Ring phase in [0, 1) for each point on one end face."""
    raise NotImplementedError("End semicircles: build plan step 3.")
