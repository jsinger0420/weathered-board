"""End faces: evenly spaced, stylized semicircles.

See docs/DESIGN.md, "End faces: stylized semicircles". Each end has its
own centre point on one of its four edges, and its rings are circles of
evenly growing radius around that point. Because the centre sits on an
edge, the rings show as half-circles (cut off by the face where they
grow larger than it).

All lengths are full-size millimetres.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .noise import Noise
from .params import BoardParams

END_EDGES = ("TOP", "BOTTOM", "FRONT", "BACK")
# With a random centre, most ends get theirs on the long top/bottom edge so
# the half-rings span the board's width, as on a flat-sawn board.
RANDOM_EDGE_WEIGHTS = (0.4, 0.4, 0.1, 0.1)


@dataclass
class EndCentre:
    """Where one end's semicircular rings are centred.

    ``edge`` is the edge of the end face the centre sits on (TOP, BOTTOM,
    FRONT or BACK); ``y`` and ``z`` are its position in full-size mm.
    """

    edge: str  # TOP, BOTTOM, FRONT or BACK
    y: float
    z: float


class EndRings:
    """The semicircular ring pattern on both ends of a board.

    Each end gets its own centre on one of its edges, so the two ends of a
    board differ. ``phase`` gives the ring phase at any point; ``distance``
    is the plain distance from the ring centre, used for the radial cracks.
    """

    def __init__(self, params: BoardParams, rng: np.random.Generator):
        """Pick each end's ring centre and set up the spacing and wobble.

        The ring spacing is ``end_spacing`` times the detail boost. With
        ``end_center`` RANDOM, each end draws its own edge (usually top or
        bottom); either way the centre falls somewhere in the middle half of
        that edge. ``rng`` is the board's "ends" random stream.
        """
        half = 0.5 * np.array(params.size, dtype=float)
        hy, hz = half[1], half[2]
        self.spacing = params.end_spacing * params.boost()
        self.wobble = params.end_wobble

        self.centres: dict[str, EndCentre] = {}
        for end in ("end_a", "end_b"):
            edge = params.end_center
            if edge == "RANDOM":
                edge = END_EDGES[rng.choice(len(END_EDGES), p=RANDOM_EDGE_WEIGHTS)]
            # A point in the middle 50% of that edge.
            along = rng.uniform(-0.5, 0.5)
            if edge in ("TOP", "BOTTOM"):
                y, z = along * hy, (hz if edge == "TOP" else -hz)
            else:
                y, z = (-hy if edge == "FRONT" else hy), along * hz
            self.centres[end] = EndCentre(edge, y, z)

        self.noise = Noise(rng)

    def distance(self, points: np.ndarray) -> np.ndarray:
        """Distance from each point to its end's ring centre, within the end's plane.

        Points with x < 0 use end A's centre, others end B's.
        """
        a, b = self.centres["end_a"], self.centres["end_b"]
        use_b = points[:, 0] >= 0
        cy = np.where(use_b, b.y, a.y)
        cz = np.where(use_b, b.z, a.z)
        return np.hypot(points[:, 1] - cy, points[:, 2] - cz)

    def phase(self, points: np.ndarray) -> np.ndarray:
        """Ring phase in [0, 1); with no wobble, exactly frac(d / spacing)."""
        points = np.asarray(points, dtype=np.float64)
        rings = self.distance(points) / self.spacing
        if self.wobble > 0:
            # Up to half a ring of hand-made unevenness at wobble = 1.
            rings = rings + 0.5 * self.wobble * self.noise.fbm(points / (1.5 * self.spacing), octaves=2)
        return np.mod(rings, 1.0)
