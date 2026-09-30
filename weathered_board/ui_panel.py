"""Sidebar panel in the 3D Viewport (N panel, "Weathered Board" tab).

With a board selected the panel edits that board's own settings;
otherwise it edits the settings used for the next board added.
"""

import bpy

from .core.params import EDGE_GROUPS


def _settings(context):
    obj = context.active_object
    if obj is not None and obj.weathered_board.is_board:
        return obj.weathered_board, True
    return context.scene.weathered_board, False


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

        box = layout.box()
        box.label(text="Size (full size)")
        box.prop(s, "units")
        col = box.column(align=True)
        col.prop(s, "length")
        col.prop(s, "width")
        col.prop(s, "thickness")
        box.prop(s, "scale_n")

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
        col.prop(s, "detail_boost")
        layout.operator("wboard.export_stl", icon="EXPORT")


classes = (
    WBOARD_PT_main,
    WBOARD_PT_edges,
    WBOARD_PT_weathering,
    WBOARD_PT_printing,
)
