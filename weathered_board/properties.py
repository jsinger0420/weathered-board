"""Blender properties for a weathered board.

The same property group is attached to the Scene (settings for the next
board added) and to each board Object (its own settings, so it can be
regenerated later). A few options (live update, pattern preview) are only
read from the Scene's copy.

Live update: changing a board's setting queues that board, and a short
timer rebuilds everything queued once the changes pause. Dragging a slider
therefore rebuilds a few times, not on every pixel of movement.
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
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


LIVE_UPDATE_DELAY = 0.35  # seconds of quiet before a queued board rebuilds

_suspended = False  # set while copying settings, so a copy is not 12 rebuilds
_pending: set[str] = set()  # names of board objects waiting to rebuild


def _flush_pending():
    from . import operators  # late import: operators imports this module

    names = list(_pending)
    _pending.clear()
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is not None and obj.weathered_board.is_board:
            operators.rebuild(obj)
    return None  # run once


def _changed(self, context):
    """A setting changed: queue the board for a rebuild if live update is on."""
    if _suspended:
        return
    obj = self.id_data
    if not isinstance(obj, bpy.types.Object) or not self.is_board:
        return
    scene = context.scene if context and context.scene else bpy.context.scene
    if scene is None or not scene.weathered_board.live_update:
        return
    _pending.add(obj.name)
    if not bpy.app.timers.is_registered(_flush_pending):
        bpy.app.timers.register(_flush_pending, first_interval=LIVE_UPDATE_DELAY)


def _printer_update(self, context):
    self.resolution, self.min_feature = PRINTER_DEFAULTS[self.printer]
    _changed(self, context)


def _show_pattern_update(self, context):
    """Switch every 3D viewport between the pattern colours and normal shading."""
    screen = context.screen if context else None
    if screen is None:
        return
    for area in screen.areas:
        if area.type != "VIEW_3D":
            continue
        for space in area.spaces:
            if space.type == "VIEW_3D":
                shading = space.shading
                if self.show_pattern:
                    if shading.type not in {"SOLID"}:
                        shading.type = "SOLID"
                    shading.color_type = "VERTEX"
                else:
                    shading.color_type = "MATERIAL"


def _round(name):
    return FloatProperty(
        name=name.replace("_", " ").title(),
        description="Rounding: 0 = sharp, 1 = fully rounded",
        default=0.15, min=0.0, max=1.0, subtype="FACTOR", update=_changed,
    )


def _weather(face, default=True):
    return BoolProperty(name=face.replace("_", " ").title(), default=default, update=_changed)


class WBOARD_Settings(bpy.types.PropertyGroup):
    is_board: BoolProperty(default=False, options={"HIDDEN"})

    # Size and scale
    units: EnumProperty(name="Units", items=UNIT_ITEMS, default="IN", update=_changed)
    length: FloatProperty(name="Length", default=96.0, min=0.001, update=_changed)
    width: FloatProperty(name="Width", default=5.5, min=0.001, update=_changed)
    thickness: FloatProperty(name="Thickness", default=1.5, min=0.001, update=_changed)
    scale_n: FloatProperty(
        name="Scale 1:", description="Reduction ratio, e.g. 48 for 1:48",
        default=48.0, min=1.0, update=_changed,
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
    depth: FloatProperty(name="Depth (mm)", default=3.0, min=0.0, update=_changed)
    edge_margin: FloatProperty(name="Edge Margin (mm)", default=0.0, min=0.0, update=_changed)
    ring_spacing_min: FloatProperty(name="Ring Spacing Min (mm)", default=3.0, min=0.01, update=_changed)
    ring_spacing_max: FloatProperty(name="Ring Spacing Max (mm)", default=6.0, min=0.01, update=_changed)
    ridge_sharpness: FloatProperty(name="Ridge Sharpness", default=0.6, min=0.0, max=1.0, subtype="FACTOR", update=_changed)
    grain_waviness: FloatProperty(name="Grain Waviness", default=0.4, min=0.0, max=1.0, subtype="FACTOR", update=_changed)
    end_spacing: FloatProperty(name="End Ring Spacing (mm)", default=4.0, min=0.01, update=_changed)
    end_center: EnumProperty(name="End Centre", items=END_CENTER_ITEMS, default="RANDOM", update=_changed)
    end_wobble: FloatProperty(name="End Wobble", default=0.1, min=0.0, max=1.0, subtype="FACTOR", update=_changed)
    use_end_depth: BoolProperty(name="Separate End Depth", default=False, update=_changed)
    end_depth: FloatProperty(name="End Depth (mm)", default=3.0, min=0.0, update=_changed)
    knots_min: IntProperty(name="Knots Min", default=0, min=0, update=_changed)
    knots_max: IntProperty(name="Knots Max", default=2, min=0, update=_changed)
    checks: FloatProperty(name="Checks", default=0.3, min=0.0, max=1.0, subtype="FACTOR", update=_changed)
    patchiness: FloatProperty(name="Patchiness", default=0.5, min=0.0, max=1.0, subtype="FACTOR", update=_changed)

    # Printing
    printer: EnumProperty(name="Printer", items=PRINTER_ITEMS, default="RESIN", update=_printer_update)
    resolution: FloatProperty(name="Resolution (mm)", default=0.05, min=0.005, precision=3, update=_changed)
    min_feature: FloatProperty(name="Smallest Feature (mm)", default=0.1, min=0.01, precision=3, update=_changed)
    detail_boost: FloatProperty(
        name="Detail Boost",
        description="Exaggerate ring spacing and carving depth by this factor",
        default=1.0, min=1.0, update=_changed,
    )
    auto_detail: BoolProperty(
        name="Auto Detail Boost",
        description="Raise the boost as needed so the rings are big enough to "
                    "carve and print at this scale",
        default=True, update=_changed,
    )

    # Randomness
    seed: IntProperty(name="Seed", default=0, min=0, update=_changed)
    lock_seed: BoolProperty(
        name="Lock Seed",
        description="Use the seed above for new boards instead of a random one",
        default=False,
    )
    count: IntProperty(name="Count", default=1, min=1, max=100)

    # Read from the Scene's copy only
    live_update: BoolProperty(
        name="Live Update",
        description="Rebuild the selected board automatically when its settings change",
        default=True,
    )
    show_pattern: BoolProperty(
        name="Show Grain Pattern",
        description="Colour the board by its ring pattern in the viewport "
                    "(grey = faces that won't be weathered)",
        default=False, update=_show_pattern_update,
    )
    last_error: StringProperty(default="", options={"HIDDEN"})

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
            auto_detail=self.auto_detail,
            seed=self.seed,
        )

    def copy_from(self, other: "WBOARD_Settings") -> None:
        global _suspended
        _suspended = True
        try:
            for key in self.__annotations__:
                if key not in ("show_pattern", "last_error"):
                    setattr(self, key, getattr(other, key))
        finally:
            _suspended = False


def register():
    bpy.types.Scene.weathered_board = bpy.props.PointerProperty(type=WBOARD_Settings)
    bpy.types.Object.weathered_board = bpy.props.PointerProperty(type=WBOARD_Settings)


def unregister():
    del bpy.types.Object.weathered_board
    del bpy.types.Scene.weathered_board
