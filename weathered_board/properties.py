"""Blender properties for a weathered board.

The same property group is attached to the Scene (settings for the next
board added) and to each board Object (its own settings, so it can be
regenerated later).
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
)

from .core.params import BoardParams, EDGES, FACES, PRINTER_DEFAULTS, to_mm

UNIT_ITEMS = [
    ("IN", "Inches", "Full-size dimensions in inches"),
    ("MM", "Millimetres", "Full-size dimensions in millimetres"),
]
PRINTER_ITEMS = [
    ("RESIN", "Resin", "Resin printer: 0.05 mm resolution, 0.1 mm smallest feature"),
    ("FDM", "FDM", "Filament printer: 0.1 mm resolution, 0.4 mm smallest feature"),
]
END_CENTER_ITEMS = [
    ("RANDOM", "Random", "Each end picks its own edge"),
    ("TOP", "Top", ""),
    ("BOTTOM", "Bottom", ""),
    ("FRONT", "Front", ""),
    ("BACK", "Back", ""),
]


def _printer_update(self, _context):
    self.resolution, self.min_feature = PRINTER_DEFAULTS[self.printer]


def _round(name):
    return FloatProperty(
        name=name.replace("_", " ").title(),
        description="Rounding: 0 = sharp, 1 = fully rounded",
        default=0.15, min=0.0, max=1.0, subtype="FACTOR",
    )


def _weather(face, default=True):
    return BoolProperty(name=face.replace("_", " ").title(), default=default)


class WBOARD_Settings(bpy.types.PropertyGroup):
    is_board: BoolProperty(default=False, options={"HIDDEN"})

    # Size and scale
    units: EnumProperty(name="Units", items=UNIT_ITEMS, default="IN")
    length: FloatProperty(name="Length", default=96.0, min=0.001)
    width: FloatProperty(name="Width", default=5.5, min=0.001)
    thickness: FloatProperty(name="Thickness", default=1.5, min=0.001)
    scale_n: FloatProperty(
        name="Scale 1:", description="Reduction ratio, e.g. 48 for 1:48",
        default=48.0, min=1.0,
    )

    # Faces to weather (bottom off by default: flat base prints best)
    weather_top: _weather("top")
    weather_bottom: _weather("bottom", default=False)
    weather_front: _weather("front")
    weather_back: _weather("back")
    weather_end_a: _weather("end_a")
    weather_end_b: _weather("end_b")

    # Edge rounding, one per edge
    round_top_front: _round("top_front")
    round_top_back: _round("top_back")
    round_bottom_front: _round("bottom_front")
    round_bottom_back: _round("bottom_back")
    round_a_top: _round("a_top")
    round_a_bottom: _round("a_bottom")
    round_a_front: _round("a_front")
    round_a_back: _round("a_back")
    round_b_top: _round("b_top")
    round_b_bottom: _round("b_bottom")
    round_b_front: _round("b_front")
    round_b_back: _round("b_back")

    # Weathering (full-size mm)
    depth: FloatProperty(name="Depth (mm)", default=3.0, min=0.0)
    edge_margin: FloatProperty(name="Edge Margin (mm)", default=0.0, min=0.0)
    ring_spacing_min: FloatProperty(name="Ring Spacing Min (mm)", default=3.0, min=0.01)
    ring_spacing_max: FloatProperty(name="Ring Spacing Max (mm)", default=6.0, min=0.01)
    ridge_sharpness: FloatProperty(name="Ridge Sharpness", default=0.6, min=0.0, max=1.0, subtype="FACTOR")
    grain_waviness: FloatProperty(name="Grain Waviness", default=0.4, min=0.0, max=1.0, subtype="FACTOR")
    end_spacing: FloatProperty(name="End Ring Spacing (mm)", default=4.0, min=0.01)
    end_center: EnumProperty(name="End Centre", items=END_CENTER_ITEMS, default="RANDOM")
    end_wobble: FloatProperty(name="End Wobble", default=0.1, min=0.0, max=1.0, subtype="FACTOR")
    use_end_depth: BoolProperty(name="Separate End Depth", default=False)
    end_depth: FloatProperty(name="End Depth (mm)", default=3.0, min=0.0)
    knots_min: IntProperty(name="Knots Min", default=0, min=0)
    knots_max: IntProperty(name="Knots Max", default=2, min=0)
    checks: FloatProperty(name="Checks", default=0.3, min=0.0, max=1.0, subtype="FACTOR")
    patchiness: FloatProperty(name="Patchiness", default=0.5, min=0.0, max=1.0, subtype="FACTOR")

    # Printing
    printer: EnumProperty(name="Printer", items=PRINTER_ITEMS, default="RESIN", update=_printer_update)
    resolution: FloatProperty(name="Resolution (mm)", default=0.05, min=0.005, precision=3)
    min_feature: FloatProperty(name="Smallest Feature (mm)", default=0.1, min=0.01, precision=3)
    detail_boost: FloatProperty(name="Detail Boost", default=1.0, min=1.0)

    # Randomness
    seed: IntProperty(name="Seed", default=0, min=0)
    lock_seed: BoolProperty(
        name="Lock Seed",
        description="Use the seed above for new boards instead of a random one",
        default=False,
    )
    count: IntProperty(name="Count", default=1, min=1, max=100)

    def to_params(self) -> BoardParams:
        """Convert to the plain values the core works with."""
        mm = lambda v: to_mm(v, self.units)  # noqa: E731
        return BoardParams(
            length=mm(self.length),
            width=mm(self.width),
            thickness=mm(self.thickness),
            scale=self.scale_n,
            faces={f: getattr(self, f"weather_{f}") for f in FACES},
            edge_round={e: getattr(self, f"round_{e}") for e in EDGES},
            depth=self.depth,
            edge_margin=self.edge_margin,
            ring_spacing=(self.ring_spacing_min, self.ring_spacing_max),
            ridge_sharpness=self.ridge_sharpness,
            grain_waviness=self.grain_waviness,
            end_spacing=self.end_spacing,
            end_center=self.end_center,
            end_wobble=self.end_wobble,
            end_depth=self.end_depth if self.use_end_depth else None,
            knots=(self.knots_min, max(self.knots_min, self.knots_max)),
            checks=self.checks,
            patchiness=self.patchiness,
            printer=self.printer,
            resolution=self.resolution,
            min_feature=self.min_feature,
            detail_boost=self.detail_boost,
            seed=self.seed,
        )

    def copy_from(self, other: "WBOARD_Settings") -> None:
        for key in self.__annotations__:
            setattr(self, key, getattr(other, key))


def register():
    bpy.types.Scene.weathered_board = bpy.props.PointerProperty(type=WBOARD_Settings)
    bpy.types.Object.weathered_board = bpy.props.PointerProperty(type=WBOARD_Settings)


def unregister():
    del bpy.types.Object.weathered_board
    del bpy.types.Scene.weathered_board
