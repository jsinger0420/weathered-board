"""Vectorized 3D gradient (Perlin) noise and fractal sums of it, in numpy.

Every function works on whole arrays of points at once. Blender's own
mathutils.noise is not used because it evaluates one point per call, far
too slow for meshes of several hundred thousand vertices.

A ``Noise`` object owns its permutation table, so two objects built from
different random generators give unrelated fields, and the same generator
state always gives the same field.
"""

from __future__ import annotations

import numpy as np

# The 12 edge directions of a cube: Perlin's improved-noise gradients.
_GRADIENTS = np.array(
    [
        [1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0],
        [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
        [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1],
    ],
    dtype=np.float64,
)


def _fade(t: np.ndarray) -> np.ndarray:
    """Perlin's quintic fade curve, 6t^5 - 15t^4 + 10t^3.

    It runs from 0 to 1 with zero slope and curvature at both ends, so the
    noise has no visible seams along the lattice lines.
    """
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


class Noise:
    """Seeded 3D gradient noise, roughly in [-1, 1], zero at lattice points."""

    def __init__(self, rng: np.random.Generator):
        """Shuffle a permutation table from ``rng`` and pick a random offset.

        The offset keeps the lattice points, where the noise is always 0, away
        from round-number coordinates such as the board's faces.
        """
        perm = rng.permutation(256)
        self._perm = np.concatenate([perm, perm]).astype(np.int64)
        self._offset = rng.uniform(0.0, 256.0, size=3)

    def __call__(self, points: np.ndarray) -> np.ndarray:
        """Noise value at each point of ``points`` (N, 3), roughly in [-1, 1].

        Smooth, with features about 1 unit across; callers divide their
        coordinates by a feature size first (see ``scaled``).
        """
        p = np.asarray(points, dtype=np.float64) + self._offset
        cell = np.floor(p)
        f = p - cell
        i = cell.astype(np.int64) & 255
        u = _fade(f)
        perm = self._perm

        def corner(dx: int, dy: int, dz: int) -> np.ndarray:
            """Dot product of one lattice corner's gradient with each point's offset from it."""
            h = perm[perm[perm[i[:, 0] + dx] + i[:, 1] + dy] + i[:, 2] + dz] % 12
            g = _GRADIENTS[h]
            return g[:, 0] * (f[:, 0] - dx) + g[:, 1] * (f[:, 1] - dy) + g[:, 2] * (f[:, 2] - dz)

        c000, c100 = corner(0, 0, 0), corner(1, 0, 0)
        c010, c110 = corner(0, 1, 0), corner(1, 1, 0)
        c001, c101 = corner(0, 0, 1), corner(1, 0, 1)
        c011, c111 = corner(0, 1, 1), corner(1, 1, 1)
        x00 = c000 + u[:, 0] * (c100 - c000)
        x10 = c010 + u[:, 0] * (c110 - c010)
        x01 = c001 + u[:, 0] * (c101 - c001)
        x11 = c011 + u[:, 0] * (c111 - c011)
        y0 = x00 + u[:, 1] * (x10 - x00)
        y1 = x01 + u[:, 1] * (x11 - x01)
        return y0 + u[:, 2] * (y1 - y0)

    def fbm(self, points: np.ndarray, octaves: int = 4, lacunarity: float = 2.0,
            gain: float = 0.5) -> np.ndarray:
        """Fractal sum of octaves, normalized to roughly [-1, 1]."""
        p = np.asarray(points, dtype=np.float64)
        total = np.zeros(len(p))
        amp, norm, freq = 1.0, 0.0, 1.0
        for octave in range(octaves):
            # Shift each octave so their lattices don't line up.
            total += amp * self(p * freq + 17.31 * octave)
            norm += amp
            amp *= gain
            freq *= lacunarity
        return total / norm


def scaled(points: np.ndarray, scale: tuple[float, float, float]) -> np.ndarray:
    """Divide each axis by a feature size, so noise varies once per size.

    Grain features are long along the board and short across it, so the
    callers pass something like (150, 10, 10) millimetres.
    """
    return np.asarray(points, dtype=np.float64) / np.asarray(scale, dtype=np.float64)
