"""Sidebar panel in the 3D Viewport (N panel, "Weathered Board" tab).

With a board selected the panel edits that board's own settings;
otherwise it edits the settings used for the next board added.
"""

import bpy

from .core.geometry import MAX_VERTICES, estimate_vertices
from .core.params import EDGE_GROUPS, MAX_DEPTH_FRACTION, ParamError
from .core.weather import detail_factor


def _settings(context):
    """The settings the panel should show and edit, and whether they are a board's.

    With a weathered board active this is that board's own settings, so edits
    change (and with live update, rebuild) it. Otherwise it is the scene's
    settings, used for the next board added.
    """
    obj = context.active_object
    if obj is not None and obj.weathered_board.is_board:
        return obj.weathered_board, True
    return context.scene.weathered_board, False


def _draw_print_info(layout, s):
    """Printed size and how heavy the mesh will be, before building it."""
    try:
        params = s.to_params()
        params.validate()
        verts = estimate_vertices(params)
    except ParamError as err:
        layout.label(text=str(err), icon="ERROR")
        return
    size = " x ".join(f"{d / params.scale:.2f}" for d in params.size)
    col = layout.column(align=True)
    col.label(text=f"Printed: {size} mm")
    if verts > MAX_VERTICES:
        col.label(text=f"~{verts:,} vertices: too many, raise Resolution", icon="ERROR")
    else:
        col.label(text=f"~{verts:,} vertices", icon="MESH_DATA")
    if s.simplify:
        col.label(text=f"Simplified to ~{s.max_triangles:,} triangles", icon="MOD_DECIM")
    _draw_detail_info(col, params)


def _draw_detail_info(col, params):
    """How the rings and carving will come out at this scale."""
    if not any(params.faces.values()) or params.depth <= 0:
        return
    boost = params.boost()
    finest = min(params.ring_spacing[0], params.end_spacing)
    ring_mm = finest * boost / params.scale
    cut_mm = params.carve_depth() / params.scale
    if boost > 1.0:
        how = "auto" if params.auto_detail and boost > params.detail_boost else "manual"
        col.label(text=f"Detail boost {boost:.1f}x ({how})", icon="ZOOM_IN")
    col.label(text=f"Rings {ring_mm:.2f} mm apart, cut up to {cut_mm:.3f} mm")
    if params.carve_depth() < params.depth * boost - 1e-9:
        col.label(text=f"Depth capped at {MAX_DEPTH_FRACTION:.0%} of thickness", icon="INFO")
    if detail_factor(finest, params) < 1.0:
        col.label(text="Rings too fine for this Resolution:", icon="ERROR")
        col.label(text="carving fades. Use Auto Detail Boost.")


class WBOARD_PT_main(bpy.types.Panel):
    """The Weathered Board tab: add boards, size and scale, faces to weather and seed."""

    bl_label = "Weathered Board"
    bl_idname = "WBOARD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Weathered Board"

    def draw(self, context):
        """Draw the main section.

        From the top: the board being edited, Add / Regenerate / New Seed, the
        Live Update and Show Grain Pattern switches, any build error, size and
        scale with the printed size and expected vertex count, faces to
        weather, and the seed.
        """
        layout = self.layout
        s, on_board = _settings(context)
        layout.label(text="Selected board" if on_board else "New board settings",
                     icon="MESH_CUBE" if on_board else "ADD")

        row = layout.row(align=True)
        row.operator("wboard.add", icon="ADD")
        if on_board:
            row = layout.row(align=True)
            row.operator("wboard.regenerate", icon="FILE_REFRESH")
            row.operator("wboard.new_seed", icon="MOD_NOISE")

        scene_s = context.scene.weathered_board
        row = layout.row(align=True)
        row.prop(scene_s, "live_update", toggle=True, icon="AUTO")
        row.prop(scene_s, "show_pattern", toggle=True, icon="TEXTURE")

        if on_board and s.last_error:
            layout.label(text=s.last_error, icon="ERROR")

        box = layout.box()
        box.label(text="Size (full size)")
        box.prop(s, "units")
        col = box.column(align=True)
        col.prop(s, "length")
        col.prop(s, "width")
        col.prop(s, "thickness")
        box.prop(s, "scale_n")
        _draw_print_info(box, s)

        box = layout.box()
        box.label(text="Faces to weather")
        grid = box.grid_flow(columns=2, align=True)
        for face in ("top", "bottom", "front", "back", "end_a", "end_b"):
            grid.prop(s, f"weather_{face}")

        box = layout.box()
        box.label(text="Randomness")
        row = box.row(align=True)
        row.prop(s, "seed")
        if not on_board:
            row.prop(s, "lock_seed", text="", icon="LOCKED" if s.lock_seed else "UNLOCKED")
            box.prop(s, "count")


class WBOARD_PT_edges(bpy.types.Panel):
    """Rounding for each of the 12 edges, with buttons to set a group at once."""

    bl_label = "Edge Rounding"
    bl_parent_id = "WBOARD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Weathered Board"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        """Draw the edge-group buttons, then one slider per edge.

        The sliders are grouped as long edges, end A and end B.
        """
        layout = self.layout
        s, on_board = _settings(context)
        row = layout.row(align=True)
        for group, label in (("ALL", "All"), ("LONG", "Long"), ("END_A", "End A"), ("END_B", "End B")):
            op = row.operator("wboard.set_edges", text=label)
            op.group = group
            op.target = "OBJECT" if on_board else "SCENE"
        for group, title in (("LONG", "Long edges"), ("END_A", "End A"), ("END_B", "End B")):
            col = layout.column(align=True)
            col.label(text=title)
            for edge in EDGE_GROUPS[group]:
                col.prop(s, f"round_{edge}")


class WBOARD_PT_weathering(bpy.types.Panel):
    """How the wear looks: depth, grain, end rings, knots, cracks and patchiness."""

    bl_label = "Weathering"
    bl_parent_id = "WBOARD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Weathered Board"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        """Draw the weathering settings in three groups.

        Overall wear, the long faces' grain, and the end rings.
        """
        layout = self.layout
        s, _ = _settings(context)
        col = layout.column(align=True)
        col.prop(s, "depth")
        col.prop(s, "edge_margin")
        col.prop(s, "patchiness")
        col.prop(s, "checks")

        col = layout.column(align=True)
        col.label(text="Long faces")
        col.prop(s, "ring_spacing_min")
        col.prop(s, "ring_spacing_max")
        col.prop(s, "ridge_sharpness")
        col.prop(s, "grain_waviness")
        row = col.row(align=True)
        row.prop(s, "knots_min")
        row.prop(s, "knots_max")

        col = layout.column(align=True)
        col.label(text="Ends")
        col.prop(s, "end_spacing")
        col.prop(s, "end_center")
        col.prop(s, "end_wobble")
        col.prop(s, "use_end_depth")
        sub = col.column()
        sub.enabled = s.use_end_depth
        sub.prop(s, "end_depth")


class WBOARD_PT_printing(bpy.types.Panel):
    """Printer settings, Check Printability with its results, and STL export."""

    bl_label = "Printing"
    bl_parent_id = "WBOARD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Weathered Board"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        """Draw the printer settings, the Check and Export buttons, and results.

        The last check's results appear if the board has any.
        """
        layout = self.layout
        s, _ = _settings(context)
        layout.prop(s, "printer")
        col = layout.column(align=True)
        col.prop(s, "resolution")
        col.prop(s, "min_feature")
        col.prop(s, "auto_detail")
        col.prop(s, "detail_boost", text="Detail Boost (min)" if s.auto_detail else "Detail Boost")
        col = layout.column(align=True)
        col.prop(s, "simplify")
        sub = col.column(align=True)
        sub.enabled = s.simplify
        sub.prop(s, "max_triangles")
        row = layout.row(align=True)
        row.operator("wboard.check", icon="CHECKMARK")
        row.operator("wboard.export_stl", icon="EXPORT")
        if s.check_report:
            _draw_report(layout.box(), s.check_report)


REPORT_ICONS = {"OK": "CHECKMARK", "INFO": "INFO", "WARNING": "ERROR", "ERROR": "CANCEL"}


def _draw_report(layout, report: str) -> None:
    """Draw the last Check Printability result.

    One line per finding, its detail underneath in small type.
    """
    layout.label(text="Last check")
    for line in report.splitlines():
        level, title, detail = (line.split("\t") + ["", "", ""])[:3]
        col = layout.column(align=True)
        col.label(text=title, icon=REPORT_ICONS.get(level, "DOT"))
        # The sidebar is narrow: one sentence per line.
        for sentence in (p.strip() for p in detail.split(". ") if p.strip()):
            sub = col.row()
            sub.scale_y = 0.75
            sub.label(text=sentence.rstrip("."))


def draw_add_menu(self, _context):
    """Entry in the 3D Viewport's Add > Mesh menu (Shift+A)."""
    self.layout.operator("wboard.add", text="Weathered Board", icon="MESH_CUBE")


classes = (
    WBOARD_PT_main,
    WBOARD_PT_edges,
    WBOARD_PT_weathering,
    WBOARD_PT_printing,
)
