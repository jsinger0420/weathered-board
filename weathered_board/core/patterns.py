"""Ring patterns for the whole board, and a colour preview of them.

``board_patterns`` evaluates both ring fields on every vertex: the virtual
log (used by the long faces) and the end semicircles (used by the ends),
plus the knots, checks and patchy wear. Which one applies where is decided
later by the face weights, exactly as the carving will, so the preview
shows what will be carved.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .ends import EndRings
from .features import Checks, Knots, Patches
from .geometry import FACE_NAMES, BoxMesh
from .grain import VirtualLog
from .params import END_FACES, BoardParams
from .rng import streams

LIGHT_WOOD = np.array([0.86, 0.71, 0.50])  # earlywood
DARK_WOOD = np.array([0.42, 0.27, 0.15])  # latewood
UNSELECTED = np.array([0.62, 0.62, 0.64])  # faces that will not be weathered
KNOT_WOOD = np.array([0.30, 0.18, 0.09])  # knot cores
CRACK = np.array([0.12, 0.08, 0.05])  # checks


@dataclass
class Patterns:
    log: VirtualLog
    ends: EndRings
    long_phase: np.ndarray  # (N,) ring phase from the virtual log
    end_phase: np.ndarray  # (N,) ring phase from the end semicircles
    knots: Knots | None = None
    checks: Checks | None = None
    knot_core: np.ndarray | None = None  # (N,) 1 inside a knot
    long_check: np.ndarray | None = None  # (N,) 0..1 crack strength, long faces
    end_check: np.ndarray | None = None  # (N,) 0..1 crack strength, ends
    patch: np.ndarray | None = None  # (N,) share of full depth the wear reaches

    def phase_for_face(self, face: str) -> np.ndarray:
        return self.end_phase if face in END_FACES else self.long_phase

    def check_for_face(self, face: str) -> np.ndarray:
        return self.end_check if face in END_FACES else self.long_check


def board_patterns(params: BoardParams, mesh: BoxMesh) -> Patterns:
    rng = streams(params.seed)
    v = mesh.vertices
    log = VirtualLog(params, rng["grain"])
    ends = EndRings(params, rng["ends"])
    knots = Knots(params, rng["knots"], log)

    def rings_at(points):
        return log.rings(points, knots.bend(points))

    rings = rings_at(v)
    mean_spacing = 0.5 * sum(log.spacing)
    checks = Checks(params, rng["checks"], rings_at, ends, mean_spacing)
    patches = Patches(params, rng["patch"])
    return Patterns(
        log, ends, np.mod(rings, 1.0), ends.phase(v),
        knots=knots, checks=checks,
        knot_core=knots.core(v),
        long_check=checks.long_checks(v, rings),
        end_check=checks.end_checks(v),
        patch=patches(v),
    )


def latewood(phase: np.ndarray) -> np.ndarray:
    """0 across the soft earlywood, 1 in the hard latewood band near phase 1."""
    t = np.clip((phase - 0.78) / (0.92 - 0.78), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def preview_colors(params: BoardParams, mesh: BoxMesh, patterns: Patterns) -> np.ndarray:
    """(N, 3) linear RGB: light earlywood, dark latewood rings, and grey on
    faces that won't be weathered. Across a rounded edge the colours blend
    by face weight, as the carving will."""
    w = mesh.face_weights
    total = np.maximum(w.sum(axis=1), 1e-12)
    dark = np.zeros(len(w))
    knot = np.zeros(len(w))
    crack = np.zeros(len(w))
    unselected = np.zeros(len(w))
    for col, face in enumerate(FACE_NAMES):
        share = w[:, col] / total
        if params.faces.get(face, False):
            dark += share * latewood(patterns.phase_for_face(face))
            if patterns.check_for_face(face) is not None:
                crack += share * patterns.check_for_face(face)
            if face not in END_FACES and patterns.knot_core is not None:
                knot += share * patterns.knot_core
        else:
            unselected += share
    wood = LIGHT_WOOD + dark[:, None] * (DARK_WOOD - LIGHT_WOOD)
    wood = wood + knot[:, None] * (KNOT_WOOD - wood)
    wood = wood + np.clip(crack, 0, 1)[:, None] * (CRACK - wood)
    return wood + unselected[:, None] * (UNSELECTED - wood)
