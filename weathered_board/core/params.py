"""Board settings as plain Python values, independent of Blender.

Everything here is in full-size millimetres unless a name says otherwise.
The Blender layer converts its properties into a ``BoardParams`` and hands
it to ``core.build_board``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MM_PER_INCH = 25.4

# Face name -> (axis index, sign). X = length, Y = width, Z = thickness.
FACES: dict[str, tuple[int, int]] = {
    "top": (2, +1),
    "bottom": (2, -1),
    "front": (1, -1),
    "back": (1, +1),
    "end_a": (0, -1),
    "end_b": (0, +1),
}
LONG_FACES = ("top", "bottom", "front", "back")
END_FACES = ("end_a", "end_b")

# Edge name -> the two faces it joins.
EDGES: dict[str, tuple[str, str]] = {
    "top_front": ("top", "front"),
    "top_back": ("top", "back"),
    "bottom_front": ("bottom", "front"),
    "bottom_back": ("bottom", "back"),
    "a_top": ("end_a", "top"),
    "a_bottom": ("end_a", "bottom"),
    "a_front": ("end_a", "front"),
    "a_back": ("end_a", "back"),
    "b_top": ("end_b", "top"),
    "b_bottom": ("end_b", "bottom"),
    "b_front": ("end_b", "front"),
    "b_back": ("end_b", "back"),
}
EDGE_GROUPS: dict[str, tuple[str, ...]] = {
    "ALL": tuple(EDGES),
    "LONG": ("top_front", "top_back", "bottom_front", "bottom_back"),
    "END_A": ("a_top", "a_bottom", "a_front", "a_back"),
    "END_B": ("b_top", "b_bottom", "b_front", "b_back"),
}

PRINTER_DEFAULTS = {
    # printer: (resolution mm, min_feature mm) in printed size
    "RESIN": (0.05, 0.1),
    "FDM": (0.1, 0.4),
}


MIN_RING_VERTICES = 4  # vertices across one ring for it to carve cleanly
MAX_DEPTH_FRACTION = 0.25  # carving never deeper than this share of the thickness


class ParamError(ValueError):
    """Raised when settings describe a board that cannot be built."""


@dataclass
class BoardParams:
    # Full-size dimensions in millimetres.
    length: float
    width: float
    thickness: float
    scale: float = 1.0  # N in 1:N

    faces: dict[str, bool] = field(
        default_factory=lambda: {f: f != "bottom" for f in FACES}
    )
    # 0-1 fraction of the largest radius each edge can take.
    edge_round: dict[str, float] = field(
        default_factory=lambda: {e: 0.15 for e in EDGES}
    )

    depth: float = 3.0
    edge_margin: float = 0.0
    ring_spacing: tuple[float, float] = (3.0, 6.0)
    ridge_sharpness: float = 0.6
    grain_waviness: float = 0.4
    end_spacing: float = 4.0
    end_center: str = "RANDOM"  # RANDOM, TOP, BOTTOM, FRONT, BACK
    end_wobble: float = 0.1
    end_depth: float | None = None
    knots: tuple[int, int] = (0, 2)
    checks: float = 0.3
    patchiness: float = 0.5

    printer: str = "RESIN"
    resolution: float = 0.05  # printed mm between vertices
    min_feature: float = 0.1  # printed mm
    detail_boost: float = 1.0
    auto_detail: bool = True  # raise the boost as needed so rings can print

    seed: int = 0

    # ---- derived values -------------------------------------------------

    def needed_boost(self) -> float:
        """Smallest boost that lets the finest rings print: each ring at
        least MIN_RING_VERTICES vertices and 2 smallest-features wide."""
        finest = min(self.ring_spacing[0], self.end_spacing)
        printed_needed = max(MIN_RING_VERTICES * self.resolution, 2.0 * self.min_feature)
        return max(1.0, printed_needed * self.scale / finest)

    def boost(self) -> float:
        """The boost actually applied to ring spacing and carving depth."""
        if self.auto_detail:
            return max(self.detail_boost, self.needed_boost())
        return self.detail_boost

    def carve_depth(self, end: bool = False) -> float:
        """Full-size carving depth after the boost, never past a quarter of
        the thickness (so opposite faces can't meet)."""
        base = self.end_depth if (end and self.end_depth is not None) else self.depth
        return min(base * self.boost(), MAX_DEPTH_FRACTION * self.thickness)

    @property
    def size(self) -> tuple[float, float, float]:
        return (self.length, self.width, self.thickness)

    def max_radius(self, edge: str) -> float:
        """Largest radius an edge can take: half the smaller of the two
        dimensions across its cross-section."""
        f1, f2 = EDGES[edge]
        a1, a2 = FACES[f1][0], FACES[f2][0]
        return 0.5 * min(self.size[a1], self.size[a2])

    def edge_radius(self, edge: str) -> float:
        """Radius of an edge in full-size millimetres."""
        return self.edge_round[edge] * self.max_radius(edge)

    # ---- validation -----------------------------------------------------

    def validate(self) -> None:
        if min(self.size) <= 0:
            raise ParamError("Length, width and thickness must be positive.")
        if self.scale < 1:
            raise ParamError("Scale must be 1:1 or smaller (N >= 1).")
        for edge, value in self.edge_round.items():
            if edge not in EDGES:
                raise ParamError(f"Unknown edge '{edge}'.")
            if not 0.0 <= value <= 1.0:
                raise ParamError(f"Rounding for edge '{edge}' must be 0-1.")
        if self.depth < 0:
            raise ParamError("Depth cannot be negative.")
        if self.depth > 0.25 * self.thickness:
            raise ParamError(
                "Depth is more than a quarter of the thickness; "
                "opposite faces could meet."
            )
        if self.edge_margin * 2 > min(self.width, self.thickness):
            raise ParamError("Edge margin is wider than half a face.")
        lo, hi = self.ring_spacing
        if not 0 < lo <= hi:
            raise ParamError("Ring spacing range must be positive, min <= max.")
        if self.end_spacing <= 0:
            raise ParamError("End spacing must be positive.")
        if self.resolution <= 0:
            raise ParamError("Resolution must be positive.")
        if self.detail_boost < 1:
            raise ParamError("Detail boost must be 1 or more.")


def to_mm(value: float, units: str) -> float:
    """Convert a full-size input value to millimetres."""
    return value * MM_PER_INCH if units == "IN" else value
