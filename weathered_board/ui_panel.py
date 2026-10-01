"""Sidebar panel in the 3D Viewport (N panel, "Weathered Board" tab).

With a board selected the panel edits that board's own settings;
otherwise it edits the settings used for the next board added.
"""

import bpy

from .core.geometry import MAX_VERTICES, estimate_vertices
from .core.params import EDGE_GROUPS, MAX_DEPTH_FRACTION, ParamError
from .core.weather import detail_factor


def _settings(context):
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
    bl_label = "Weathered Board"
    bl_idname = "WBOARD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Weathered Board"

    def draw(self, context):
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
    bl_label = "Edge Rounding"
    bl_parent_id = "WBOARD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Weathered Board"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
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
    bl_label = "Weathering"
    bl_parent_id = "WBOARD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Weathered Board"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
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
    bl_label = "Printing"
    bl_parent_id = "WBOARD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Weathered Board"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        s, _ = _settings(context)
        layout.prop(s, "printer")
        col = layout.column(align=True)
        col.prop(s, "resolution")
        col.prop(s, "min_feature")
        col.prop(s, "auto_detail")
        col.prop(s, "detail_boost", text="Detail Boost (min)" if s.auto_detail else "Detail Boost")
        layout.operator("wboard.export_stl", icon="EXPORT")


def draw_add_menu(self, _context):
    """Entry in the 3D Viewport's Add > Mesh menu (Shift+A)."""
    self.layout.operator("wboard.add", text="Weathered Board", icon="MESH_CUBE")


classes = (
    WBOARD_PT_main,
    WBOARD_PT_edges,
    WBOARD_PT_weathering,
    WBOARD_PT_printing,
)
