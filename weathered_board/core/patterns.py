"""Ring patterns for the whole board, and a colour preview of them.

``board_patterns`` evaluates both ring fields on every vertex: the virtual
log (used by the long faces) and the end semicircles (used by the ends).
Which one applies where is decided later by the face weights, exactly as
the carving will, so the preview shows what will be carved.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .ends import EndRings
from .geometry import FACE_NAMES, BoxMesh
from .grain import VirtualLog
from .params import END_FACES, BoardParams
from .rng import streams

LIGHT_WOOD = np.array([0.86, 0.71, 0.50])  # earlywood
DARK_WOOD = np.array([0.42, 0.27, 0.15])  # latewood
UNSELECTED = np.array([0.62, 0.62, 0.64])  # faces that will not be weathered


@dataclass
class Patterns:
    log: VirtualLog
    ends: EndRings
    long_phase: np.ndarray  # (N,) ring phase from the virtual log
    end_phase: np.ndarray  # (N,) ring phase from the end semicircles

    def phase_for_face(self, face: str) -> np.ndarray:
        return self.end_phase if face in END_FACES else self.long_phase


def board_patterns(params: BoardParams, mesh: BoxMesh) -> Patterns:
    rng = streams(params.seed)
    log = VirtualLog(params, rng["grain"])
    ends = EndRings(params, rng["ends"])
    return Patterns(log, ends, log.phase(mesh.vertices), ends.phase(mesh.vertices))


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
    unselected = np.zeros(len(w))
    for col, face in enumerate(FACE_NAMES):
        share = w[:, col] / total
        if params.faces.get(face, False):
            dark += share * latewood(patterns.phase_for_face(face))
        else:
            unselected += share
    wood = LIGHT_WOOD + dark[:, None] * (DARK_WOOD - LIGHT_WOOD)
    return wood + unselected[:, None] * (UNSELECTED - wood)
