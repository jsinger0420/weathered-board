"""Vectorized mesh checks shared by the tests."""

import numpy as np


def is_closed_and_consistent(tris: np.ndarray) -> bool:
    """Every directed edge appears once and its reverse appears once."""
    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]).astype(np.int64)
    n = int(e.max()) + 1
    fwd = e[:, 0] * n + e[:, 1]
    rev = e[:, 1] * n + e[:, 0]
    if len(np.unique(fwd)) != len(fwd):
        return False  # an edge used twice in the same direction
    return bool(np.isin(rev, fwd).all())


def euler_ok(verts: np.ndarray, tris: np.ndarray) -> bool:
    """Closed genus-0 triangle mesh: F = 2V - 4, and every vertex is used."""
    used = np.unique(tris)
    return len(tris) == 2 * len(verts) - 4 and len(used) == len(verts)


def signed_volume(verts: np.ndarray, tris: np.ndarray) -> float:
    v = verts[tris]
    return float(np.einsum("ij,ij->i", v[:, 0], np.cross(v[:, 1], v[:, 2])).sum() / 6.0)


def triangle_normals(verts: np.ndarray, tris: np.ndarray) -> np.ndarray:
    v = verts[tris]
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    return n / np.linalg.norm(n, axis=1, keepdims=True)


def min_triangle_area(verts: np.ndarray, tris: np.ndarray) -> float:
    v = verts[tris]
    return float(0.5 * np.linalg.norm(np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]), axis=1).min())
