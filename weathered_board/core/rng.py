"""Seeded random streams, one per part of the board.

Each part (grain, ends, knots, ...) draws from its own generator spawned
from the board's seed. Changing how many numbers one part draws therefore
never changes the others: a new knot setting leaves the grain alone.

Only ever append to STREAMS; reordering it would change every board made
from an existing seed.
"""

from __future__ import annotations

import numpy as np

STREAMS = ("grain", "ends", "knots", "checks", "patch")


def streams(seed: int) -> dict[str, np.random.Generator]:
    """One independent, repeatable random generator per name in STREAMS.

    The same ``seed`` always gives the same generators.
    """
    children = np.random.SeedSequence(int(seed)).spawn(len(STREAMS))
    return {name: np.random.default_rng(child) for name, child in zip(STREAMS, children)}
