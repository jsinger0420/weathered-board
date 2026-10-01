"""Knots, checks (cracks) and patchy wear.

See docs/DESIGN.md, "Extra features". Each draws from its own random
stream (core/rng.py), so changing one never reshuffles the others or the
grain. All lengths are full-size millimetres.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .ends import EndRings
from .grain import VirtualLog
from .noise import Noise, scaled
from .params import BoardParams


def _smoothstep(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _unit(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v)


# --------------------------------------------------------------------------
# Knots
# --------------------------------------------------------------------------

KNOT_RADIUS = (0.04, 0.12)  # knot radius as a share of the board width
KNOT_BEND = 1.2  # how far rings are pushed aside, in knot radii
KNOT_REACH = 2.5  # how far from the knot the grain bends, in knot radii


@dataclass
class Knot:
    base: np.ndarray  # where the branch leaves the pith
    axis: np.ndarray  # unit direction of the branch, out from the pith
    radius: float


class Knots:
    """Branches growing out of the pith line and through the board.

    Where a branch crosses a face it shows as an oval. The grain bends
    around it (the distance from the pith is pushed out near the branch),
    and its dense core resists wear, so it stands proud of the worn
    earlywood around it, as knots do on old boards.
    """

    def __init__(self, params: BoardParams, rng: np.random.Generator, log: VirtualLog):
        self.knots: list[Knot] = []
        lo, hi = params.knots
        count = int(rng.integers(lo, max(lo, hi) + 1))
        grid = params.resolution * params.scale
        half = 0.5 * np.array(params.size)
        for _ in range(count):
            x = rng.uniform(-0.4, 0.4) * params.length
            base = log.pith_at(x)
            # Aim through a point inside the board, angled a little along it
            # (branches grow upward and outward from the trunk).
            target = np.array([x, rng.uniform(-0.6, 0.6) * half[1], rng.uniform(-0.6, 0.6) * half[2]])
            axis = _unit(target - base)
            axis = _unit(axis + np.array([rng.normal(0.0, 0.15), 0.0, 0.0]))
            radius = max(rng.uniform(*KNOT_RADIUS) * params.width, 4.0 * grid)
            self.knots.append(Knot(base, axis, radius))
        self.soft = 2.0 * grid  # width of the knot's soft rim

    def _distance(self, knot: Knot, points: np.ndarray) -> np.ndarray:
        q = points - knot.base
        along = q @ knot.axis
        d = np.linalg.norm(q - along[:, None] * knot.axis, axis=1)
        return np.where(along > 0, d, np.inf)

    def bend(self, points: np.ndarray) -> np.ndarray:
        """Extra distance from the pith near each knot, so rings flow around it."""
        out = np.zeros(len(points))
        for k in self.knots:
            d = self._distance(k, points)
            out += KNOT_BEND * k.radius * np.exp(-(d / (KNOT_REACH * k.radius)) ** 2)
        return out

    def core(self, points: np.ndarray) -> np.ndarray:
        """1 inside a knot, 0 outside, with a soft rim."""
        out = np.zeros(len(points))
        for k in self.knots:
            d = self._distance(k, points)
            soft = max(self.soft, 0.25 * k.radius)
            out = np.maximum(out, _smoothstep((k.radius + 0.5 * soft - d) / soft))
        return out


# --------------------------------------------------------------------------
# Checks (cracks)
# --------------------------------------------------------------------------

CHECK_WIDTH_RINGS = 0.25  # crack width as a share of the mean ring spacing
CHECKS_PER_METRE = 6.0  # long-face checks per metre of board at checks = 1
END_CHECKS = 4.0  # radial checks per end at checks = 1
LONG_FACE_WEIGHTS = {"top": "width", "bottom": "width", "front": "thickness", "back": "thickness"}


@dataclass
class LongCheck:
    axis: int  # axis of the face it is on (1 for front/back, 2 for top/bottom)
    sign: int  # which side of that axis
    across: float  # position across the face (z on front/back, y on top/bottom)
    x: float  # middle of the crack along the board
    length: float
    wander: np.ndarray  # (2, 3): amplitude, wavelength, phase of two gentle waves


@dataclass
class EndCheck:
    end: str  # end_a or end_b
    origin: np.ndarray  # (y, z) of the ring centre
    direction: np.ndarray  # unit (y, z), out from the centre
    start: float  # distance from the centre where it begins
    length: float


class Checks:
    """Narrow cracks. On the long faces they split along the fibres: nearly
    straight lines along the board with a slight wander, tapering at both
    tips and cutting across the curving ridges. On the ends they run
    straight out from the ring centre, opening toward the outside as end
    checks do."""

    def __init__(self, params: BoardParams, rng: np.random.Generator,
                 rings_at, ends: EndRings, mean_spacing: float):
        grid = params.resolution * params.scale
        self.width = max(CHECK_WIDTH_RINGS * mean_spacing, 4.0 * grid)
        self.mean_spacing = mean_spacing
        half = 0.5 * np.array(params.size)
        amount = params.checks

        self.long: list[LongCheck] = []
        n_long = int(rng.poisson(amount * CHECKS_PER_METRE * params.length / 1000.0)) if amount > 0 else 0
        # Only on long faces that are being weathered, more on wider faces.
        faces = [f for f in LONG_FACE_WEIGHTS if params.faces.get(f, False)]
        if not faces:
            n_long = 0
        weights = np.array([getattr(params, LONG_FACE_WEIGHTS[f]) for f in faces]) if faces else None
        for _ in range(n_long):
            face = faces[rng.choice(len(faces), p=weights / weights.sum())]
            axis, sign = (2, 1 if face == "top" else -1) if face in ("top", "bottom") else (1, 1 if face == "back" else -1)
            other = 3 - axis
            across = rng.uniform(-0.7, 0.7) * half[other]
            x = rng.uniform(-0.45, 0.45) * params.length
            length = rng.uniform(0.15, 0.5) * params.length
            wander = np.stack([
                rng.uniform(0.005, 0.02, 2) * params.width,  # amplitude
                rng.uniform(150.0, 600.0, 2),  # wavelength along the board
                rng.uniform(0.0, 2 * np.pi, 2),  # phase
            ], axis=0)
            self.long.append(LongCheck(axis, sign, across, x, length, wander))
        self.half = half

        self.end: list[EndCheck] = []
        inward = {"TOP": (0.0, -1.0), "BOTTOM": (0.0, 1.0), "FRONT": (1.0, 0.0), "BACK": (-1.0, 0.0)}
        size_across = min(params.width, 2.0 * params.thickness)
        for end, centre in ends.centres.items():
            n_end = int(rng.poisson(amount * END_CHECKS)) if amount > 0 else 0
            base_angle = np.arctan2(inward[centre.edge][1], inward[centre.edge][0])
            for _ in range(n_end):
                a = base_angle + rng.uniform(-1.3, 1.3)
                self.end.append(EndCheck(
                    end, np.array([centre.y, centre.z]), np.array([np.cos(a), np.sin(a)]),
                    rng.uniform(0.0, 0.25) * size_across, rng.uniform(0.3, 0.9) * size_across))

    def long_checks(self, points: np.ndarray, rings: np.ndarray | None = None) -> np.ndarray:
        """0..1 crack strength on the long faces."""
        out = np.zeros(len(points))
        x = points[:, 0]
        for c in self.long:
            other = 3 - c.axis
            amp, wavelength, phase = c.wander
            line = c.across + (amp * np.sin(2 * np.pi * x[:, None] / wavelength + phase)).sum(axis=1)
            profile = _smoothstep(1.0 - np.abs(points[:, other] - line) / (0.5 * self.width))
            t = np.abs(x - c.x) / (0.5 * c.length)
            taper = np.clip(1.0 - t * t, 0.0, 1.0)  # thins out to both tips
            # Only on its own face (not the opposite one at the same position).
            off_face = np.abs(c.sign * points[:, c.axis] - self.half[c.axis])
            on_face = _smoothstep(1.0 - off_face / (2.0 * self.width))
            out = np.maximum(out, profile * taper * on_face)
        return out

    def end_checks(self, points: np.ndarray) -> np.ndarray:
        """0..1 crack strength on the ends."""
        out = np.zeros(len(points))
        for c in self.end:
            on_end = points[:, 0] < 0 if c.end == "end_a" else points[:, 0] >= 0
            v = points[:, 1:] - c.origin
            along = v @ c.direction
            perp = np.abs(v[:, 0] * c.direction[1] - v[:, 1] * c.direction[0])
            profile = _smoothstep(1.0 - perp / (0.5 * self.width))
            t = (along - c.start) / c.length
            # Opens toward the outside: shallow where it starts, deepest at its far end.
            taper = _smoothstep(t / 0.6) * _smoothstep((1.15 - t) / 0.15)
            out = np.maximum(out, np.where(on_end, profile * taper, 0.0))
        return out


# --------------------------------------------------------------------------
# Patchy wear
# --------------------------------------------------------------------------

PATCH_SCALE = (300.0, 0.5, 0.5)  # mm along; the cross-board sizes are shares of width


class Patches:
    """Low-frequency variation in wear: 1 = full depth, down to
    1 - patchiness where the board was sheltered."""

    def __init__(self, params: BoardParams, rng: np.random.Generator):
        self.noise = Noise(rng)
        self.amount = params.patchiness
        self.scale = (PATCH_SCALE[0], PATCH_SCALE[1] * params.width, PATCH_SCALE[2] * params.width)

    def __call__(self, points: np.ndarray) -> np.ndarray:
        if self.amount <= 0:
            return np.ones(len(points))
        n = self.noise.fbm(scaled(points, self.scale), octaves=3)
        shelter = np.clip(0.5 + 1.2 * n, 0.0, 1.0)
        return 1.0 - self.amount * shelter
