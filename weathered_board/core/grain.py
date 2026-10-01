"""Long-face grain: the "virtual log" ring field.

See docs/DESIGN.md, "The virtual log". The board is imagined as sawn from
a log whose centre line (the pith) runs roughly along the board, outside
it. A point's ring phase comes from its distance to that line: lines of
equal distance are the growth rings, and where a flat face slices through
them they show as long, curving grain lines (cathedral arches on the face
nearest the pith, near-parallel lines on the faces beside it). Knots push
the distance outward near each branch, so the grain flows around them.

All lengths are full-size millimetres.
"""

from __future__ import annotations

import math

import numpy as np

from .noise import Noise, scaled
from .params import BoardParams

WOBBLE_WAVELENGTH = 400.0  # mm along the board per pith wobble
DISTORTION_SCALE = (300.0, 25.0, 25.0)  # mm: ring wobble is long along the grain
DISTORTION_OCTAVES = 2


class VirtualLog:
    """The hidden log one board was sawn from. Built once per board."""

    def __init__(self, params: BoardParams, rng: np.random.Generator):
        """Invent the log this board was sawn from.

        Places the pith (70% of the time behind the top or bottom, for flat-sawn
        cathedral grain), tilts it up to 2 degrees, sets how much it wobbles and
        how much the rings are distorted (both from ``grain_waviness``), and
        tabulates the ring count against distance, with ring widths varying
        within ``ring_spacing`` times the detail boost. ``rng`` is the board's
        "grain" stream.
        """
        self.half = 0.5 * np.array(params.size, dtype=float)
        hy, hz = self.half[1], self.half[2]
        width = params.width
        boost = params.boost()

        # Where the pith sits around the board, seen from its end. Most
        # boards are flat-sawn, with the pith behind a wide face (top or
        # bottom), which is what gives cathedral arches on that face.
        if rng.random() < 0.7:
            angle = rng.choice([0.5 * math.pi, -0.5 * math.pi]) + rng.normal(0.0, math.radians(20))
        else:
            angle = rng.uniform(0.0, 2.0 * math.pi)
        direction = np.array([0.0, math.cos(angle), math.sin(angle)])
        # Distance from the board's centre to its cross-section boundary in
        # that direction, then a gap of 0.3-3 board widths beyond it.
        to_edge = min(
            hy / max(abs(direction[1]), 1e-12),
            hz / max(abs(direction[2]), 1e-12),
        )
        self.gap = rng.uniform(0.3, 3.0) * width
        self.pith_point = direction * (to_edge + self.gap)
        self.angle = angle

        # Slight tilt (up to about 2 degrees) so rings run out of the faces.
        tilt = math.tan(math.radians(2.0))
        ty, tz = rng.uniform(-tilt, tilt, size=2)
        d = np.array([1.0, ty, tz])
        self.pith_dir = d / np.linalg.norm(d)

        # Gentle wobble of the pith line along the board.
        self.wobble_noise = Noise(rng)
        self.wobble_amp = params.grain_waviness * 0.15 * width

        # Rings are not perfect circles: distort the distance a little.
        lo, hi = (s * boost for s in params.ring_spacing)
        self.spacing = (lo, hi)
        self.distort_noise = Noise(rng)
        self.distort_amp = params.grain_waviness * 2.0 * 0.5 * (lo + hi)

        # Ring widths vary from year to year within the spacing range. The
        # cumulative ring count N(R) is tabulated once, then interpolated.
        spacing_noise = Noise(rng)
        r_max = np.linalg.norm(self.pith_point) + np.linalg.norm(self.half) * 1.5 \
            + self.wobble_amp * 2 + self.distort_amp * 2 + hi
        step = lo / 20.0
        self._r_table = np.arange(0.0, r_max + step, step)
        mean = 0.5 * (lo + hi)
        u = spacing_noise.fbm(np.stack([self._r_table / (5.0 * mean),
                                        np.full_like(self._r_table, 0.37),
                                        np.full_like(self._r_table, 0.71)], axis=1), octaves=2)
        widths = lo + (hi - lo) * np.clip(0.5 + 0.9 * u, 0.0, 1.0)
        counts = np.concatenate([[0.0], np.cumsum(step / widths[:-1])])
        self._n_table = counts + rng.uniform(0.0, 1.0)  # random ring offset

    # ----------------------------------------------------------------------

    def pith_offset(self, x: np.ndarray) -> np.ndarray:
        """(N, 3) offset of the pith line's position at each x (wobble)."""
        t = x / WOBBLE_WAVELENGTH
        dy = self.wobble_noise(np.stack([t, np.full_like(t, 0.5), np.full_like(t, 0.5)], 1))
        dz = self.wobble_noise(np.stack([t, np.full_like(t, 7.5), np.full_like(t, 3.5)], 1))
        out = np.zeros((len(x), 3))
        out[:, 1] = self.wobble_amp * dy
        out[:, 2] = self.wobble_amp * dz
        return out

    def radius(self, points: np.ndarray) -> np.ndarray:
        """Distance of each point from the (wobbling) pith line.

        This is before ring distortion and knot bending.
        """
        q = points - self.pith_point - self.pith_offset(points[:, 0])
        along = q @ self.pith_dir
        return np.linalg.norm(q - along[:, None] * self.pith_dir, axis=1)

    def ring_count(self, r: np.ndarray) -> np.ndarray:
        """Number of rings from the pith out to distance r (fractional)."""
        return np.interp(r, self._r_table, self._n_table)

    def pith_at(self, x: float) -> np.ndarray:
        """Point on the (wobbling) pith line level with board position x."""
        t = x / self.pith_dir[0]
        return self.pith_point + t * self.pith_dir + self.pith_offset(np.array([float(x)]))[0]

    def rings(self, points: np.ndarray, bend: np.ndarray | None = None) -> np.ndarray:
        """Unwrapped ring count at each point.

        Whole rings from the pith plus the fraction into the current one.
        ``bend`` adds to the distance from the pith, which is how knots push
        rings aside.
        """
        points = np.asarray(points, dtype=np.float64)
        r = self.radius(points)
        r = r + self.distort_amp * self.distort_noise.fbm(scaled(points, DISTORTION_SCALE), octaves=DISTORTION_OCTAVES)
        if bend is not None:
            r = r + bend
        return self.ring_count(np.maximum(r, 0.0))

    def phase(self, points: np.ndarray, bend: np.ndarray | None = None) -> np.ndarray:
        """Ring phase in [0, 1) for each point.

        0 at the start of a year's soft earlywood, rising to 1 at its hard
        latewood edge.
        """
        return np.mod(self.rings(points, bend), 1.0)
