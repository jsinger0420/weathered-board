"""Long-face grain: the "virtual log" ring field.

Build plan step 3. See docs/DESIGN.md, "The virtual log".
"""

from __future__ import annotations

import numpy as np

from .params import BoardParams


def ring_phase(points: np.ndarray, params: BoardParams, rng: np.random.Generator) -> np.ndarray:
    """Ring phase in [0, 1) for each point on the long faces."""
    raise NotImplementedError("Virtual log ring field: build plan step 3.")
