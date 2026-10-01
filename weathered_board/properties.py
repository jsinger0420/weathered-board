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
    ("IN", "Inches", "Length, width and thickness are entered in inches"),
    ("MM", "Millimetres", "Length, width and thickness are entered in millimetres"),
]
PRINTER_ITEMS = [
    ("RESIN", "Resin", "Resin printer: sets Resolution to 0.05 mm and Smallest Feature to 0.1 mm"),
    ("FDM", "FDM", "Filament printer: sets Resolution to 0.1 mm and Smallest Feature to 0.4 mm"),
]
END_CENTER_ITEMS = [
    ("RANDOM", "Random", "Each end picks its own edge, usually the top or bottom, so the arcs span the width"),
    ("TOP", "Top", "Centre the end rings on the top edge of each end"),
    ("BOTTOM", "Bottom", "Centre the end rings on the bottom edge of each end"),
    ("FRONT", "Front", "Centre the end rings on the front edge of each end"),
    ("BACK", "Back", "Centre the end rings on the back edge of each end"),
]

# Plain-language names for faces, used in tooltips.
FACE_HELP = {
    "top": "the top face (the wide face facing up)",
    "bottom": "the bottom face. Left flat, it sits cleanly on the print bed without supports",
    "front": "the front edge face (the narrow long side facing you)",
    "back": "the back edge face (the narrow long side facing away)",
    "end_a": "end A (the left end, toward -X)",
    "end_b": "end B (the right end, toward +X)",
}
EDGE_HELP = {
    "top_front": "where the top meets the front, along the board",
    "top_back": "where the top meets the back, along the board",
    "bottom_front": "where the bottom meets the front, along the board",
    "bottom_back": "where the bottom meets the back, along the board",
    "a_top": "where end A meets the top",
    "a_bottom": "where end A meets the bottom",
    "a_front": "where end A meets the front",
    "a_back": "where end A meets the back",
    "b_top": "where end B meets the top",
    "b_bottom": "where end B meets the bottom",
    "b_front": "where end B meets the front",
    "b_back": "where end B meets the back",
}


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
        description=f"Rounding of the edge {EDGE_HELP[name]}. "
                    "0 = sharp corner, 1 = as round as the board allows "
                    "(a radius of half the thinner side it joins)",
        default=0.15, min=0.0, max=1.0, subtype="FACTOR", update=_changed,
    )


def _weather(face, default=True):
    return BoolProperty(
        name=face.replace("_", " ").title(),
        description=f"Carve weathering into {FACE_HELP[face]}. "
                    "Unticked faces stay perfectly flat",
        default=default, update=_changed,
    )


class WBOARD_Settings(bpy.types.PropertyGroup):
    is_board: BoolProperty(default=False, options={"HIDDEN"})

    # Size and scale
    units: EnumProperty(
        name="Units", items=UNIT_ITEMS, default="IN", update=_changed,
        description="Units for Length, Width and Thickness. Weathering settings are always in millimetres",
    )
    length: FloatProperty(
        name="Length", default=96.0, min=0.001, update=_changed,
        description="Full-size length of the real board, before scaling (e.g. 96 for an 8 ft board)",
    )
    width: FloatProperty(
        name="Width", default=5.5, min=0.001, update=_changed,
        description="Full-size actual width, before scaling. Use the actual size, "
                    "not the nominal one: a nominal 1x6 is 5.5 in wide",
    )
    thickness: FloatProperty(
        name="Thickness", default=1.5, min=0.001, update=_changed,
        description="Full-size actual thickness, before scaling. A nominal 2x is "
                    "1.5 in thick, a nominal 1x is 0.75 in",
    )
    scale_n: FloatProperty(
        name="Scale 1:", default=48.0, min=1.0, update=_changed,
        description="Model scale as 1:N. The full-size board is divided by N, "
                    "e.g. 48 for O scale (1:48), 87 for HO (1:87), 1 for full size",
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
    depth: FloatProperty(
        name="Depth (mm)", default=3.0, min=0.0, update=_changed,
        description="How deep the worn grooves between the grain ridges go, in full-size mm. "
                    "Detail Boost multiplies it; it never goes past a quarter of the thickness",
    )
    edge_margin: FloatProperty(
        name="Edge Margin (mm)", default=0.0, min=0.0, update=_changed,
        description="Width of a smooth, unworn border around each weathered face, in full-size mm. "
                    "0 = the wear runs right out over the edges",
    )
    ring_spacing_min: FloatProperty(
        name="Ring Spacing Min (mm)", default=3.0, min=0.01, update=_changed,
        description="Narrowest growth ring on the long faces, in full-size mm. "
                    "Smaller = finer, denser grain lines",
    )
    ring_spacing_max: FloatProperty(
        name="Ring Spacing Max (mm)", default=6.0, min=0.01, update=_changed,
        description="Widest growth ring on the long faces, in full-size mm. Rings vary between "
                    "Min and Max, like fast and slow growth years",
    )
    ridge_sharpness: FloatProperty(
        name="Ridge Sharpness", default=0.6, min=0.0, max=1.0, subtype="FACTOR", update=_changed,
        description="Shape of the grain ridges. 0 = soft, rolling waves; "
                    "1 = narrow, crisp ridges between wide, scooped grooves",
    )
    grain_waviness: FloatProperty(
        name="Grain Waviness", default=0.4, min=0.0, max=1.0, subtype="FACTOR", update=_changed,
        description="How much the grain lines on the long faces wander. "
                    "0 = smooth, regular grain; 1 = wavy, irregular grain",
    )
    end_spacing: FloatProperty(
        name="End Ring Spacing (mm)", default=4.0, min=0.01, update=_changed,
        description="Distance between the semicircular rings on the board ends, in full-size mm",
    )
    end_center: EnumProperty(
        name="End Centre", items=END_CENTER_ITEMS, default="RANDOM", update=_changed,
        description="Which edge of each end the semicircular rings are centred on",
    )
    end_wobble: FloatProperty(
        name="End Wobble", default=0.1, min=0.0, max=1.0, subtype="FACTOR", update=_changed,
        description="Hand-made unevenness in the end rings. "
                    "0 = perfect, evenly spaced semicircles; 1 = up to half a ring of wobble",
    )
    use_end_depth: BoolProperty(
        name="Separate End Depth", default=False, update=_changed,
        description="Give the ends their own carving depth instead of using Depth. "
                    "End grain often weathers more deeply than the faces",
    )
    end_depth: FloatProperty(
        name="End Depth (mm)", default=3.0, min=0.0, update=_changed,
        description="Carving depth on the two ends, in full-size mm, when Separate End Depth is on",
    )
    knots_min: IntProperty(
        name="Knots Min", default=0, min=0, update=_changed,
        description="Fewest knots per board. Each board picks a number between Min and Max. "
                    "The grain flows around knots and their hard cores stand proud",
    )
    knots_max: IntProperty(
        name="Knots Max", default=2, min=0, update=_changed,
        description="Most knots per board. Set Min and Max to 0 for no knots",
    )
    checks: FloatProperty(
        name="Checks", default=0.3, min=0.0, max=1.0, subtype="FACTOR", update=_changed,
        description="Amount of cracks (checks): straight splits along the long faces and "
                    "radial cracks on the ends. 0 = none; 1 = about 6 per metre and 4 per end",
    )
    patchiness: FloatProperty(
        name="Patchiness", default=0.5, min=0.0, max=1.0, subtype="FACTOR", update=_changed,
        description="How unevenly the wear varies over the board. 0 = even wear everywhere; "
                    "1 = some sheltered areas barely worn at all",
    )

    # Printing
    printer: EnumProperty(
        name="Printer", items=PRINTER_ITEMS, default="RESIN", update=_printer_update,
        description="Type of 3D printer. Choosing one sets sensible Resolution and "
                    "Smallest Feature values, which you can then adjust",
    )
    resolution: FloatProperty(
        name="Resolution (mm)", default=0.05, min=0.005, precision=3, update=_changed,
        description="Spacing between mesh points on the printed board, in mm. Smaller = finer "
                    "detail but a heavier mesh and slower builds",
    )
    min_feature: FloatProperty(
        name="Smallest Feature (mm)", default=0.1, min=0.01, precision=3, update=_changed,
        description="Smallest detail your printer can reliably reproduce, in mm. Used by "
                    "Auto Detail Boost and Check Printability",
    )
    detail_boost: FloatProperty(
        name="Detail Boost", default=1.0, min=1.0, update=_changed,
        description="Exaggerate ring spacing and carving depth by this factor, so the grain "
                    "shows at small scales. With Auto Detail Boost on, this is the minimum",
    )
    auto_detail: BoolProperty(
        name="Auto Detail Boost", default=True, update=_changed,
        description="Raise the boost just enough that the rings are big enough to carve and "
                    "print at this scale. Off = use Detail Boost exactly",
    )

    # Randomness
    seed: IntProperty(
        name="Seed", default=0, min=0, update=_changed,
        description="Number that picks this board's random pattern. The same seed and settings "
                    "always give the same board; New Seed picks a fresh one",
    )
    lock_seed: BoolProperty(
        name="Lock Seed", default=False,
        description="Use the seed above for new boards instead of a random one, "
                    "to repeat a board you liked",
    )
    count: IntProperty(
        name="Count", default=1, min=1, max=100,
        description="How many boards Add Weathered Board creates at once, side by side, "
                    "each with its own pattern",
    )

    # Read from the Scene's copy only
    live_update: BoolProperty(
        name="Live Update", default=True,
        description="Rebuild the selected board automatically shortly after you change a "
                    "setting. Turn off to change several settings, then click Regenerate",
    )
    show_pattern: BoolProperty(
        name="Show Grain Pattern",
        description="Colour boards by their pattern in the viewport: light earlywood, dark "
                    "ridges, darker knots and cracks, grey for faces that won't be weathered",
        default=False, update=_show_pattern_update,
    )
    last_error: StringProperty(default="", options={"HIDDEN"})
    # Result of the last Check Printability: one finding per line,
    # "LEVEL\ttitle\tdetail". Cleared whenever the board is rebuilt.
    check_report: StringProperty(default="", options={"HIDDEN"})

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
                if key not in ("show_pattern", "last_error", "check_report"):
                    setattr(self, key, getattr(other, key))
        finally:
            _suspended = False


def register():
    bpy.types.Scene.weathered_board = bpy.props.PointerProperty(type=WBOARD_Settings)
    bpy.types.Object.weathered_board = bpy.props.PointerProperty(type=WBOARD_Settings)


def unregister():
    del bpy.types.Object.weathered_board
    del bpy.types.Scene.weathered_board
