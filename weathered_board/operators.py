"""Operators: add, regenerate, reseed, set edge groups, export STL."""

import bpy
import numpy as np
from bpy.props import EnumProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ExportHelper

from . import mesh_io
from .core import ParamError, build
from .core.params import EDGE_GROUPS

SEED_MAX = 2**31 - 1


def _random_seed() -> int:
    return int(np.random.default_rng().integers(1, SEED_MAX))


def _active_board(context):
    obj = context.active_object
    if obj is not None and obj.weathered_board.is_board:
        return obj
    return None


def rebuild(obj) -> str:
    """Rebuild a board's mesh from its own settings.

    Returns an error message, or "" on success. The message is also kept
    on the board so the panel can show it (live updates have no operator
    to report through).
    """
    settings = obj.weathered_board
    try:
        result = build(settings.to_params())
    except (ParamError, NotImplementedError) as err:
        settings.last_error = str(err)
        return str(err)
    mesh_io.replace_mesh(obj, result.vertices, result.triangles, result.preview)
    settings.last_error = ""
    return ""


class WBOARD_OT_add(bpy.types.Operator):
    """Add weathered boards using the settings in the panel"""

    bl_idname = "wboard.add"
    bl_label = "Add Weathered Board"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        template = context.scene.weathered_board
        mesh_io.set_scene_millimetres(context.scene)
        base_seed = template.seed if template.lock_seed else _random_seed()
        gap = 0.0
        for i in range(template.count):
            seed = (base_seed + i) % SEED_MAX
            params = template.to_params()
            params.seed = seed
            try:
                result = build(params)
            except (ParamError, NotImplementedError) as err:
                self.report({"ERROR"}, str(err))
                return {"CANCELLED"}
            verts = result.vertices
            obj = mesh_io.new_board_object(context, "WeatheredBoard", verts, result.triangles, result.preview)
            obj.weathered_board.copy_from(template)
            obj.weathered_board.seed = seed
            obj.weathered_board.is_board = True
            # Lay boards out side by side along Y.
            width = float(np.ptp(verts[:, 1]))
            obj.location = context.scene.cursor.location.copy()
            obj.location.y += gap
            gap += width * 1.5
            obj.select_set(True)
            context.view_layer.objects.active = obj
        return {"FINISHED"}


class WBOARD_OT_regenerate(bpy.types.Operator):
    """Rebuild the selected board from its settings, keeping its seed"""

    bl_idname = "wboard.regenerate"
    bl_label = "Regenerate"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_board(context) is not None

    def execute(self, context):
        error = rebuild(_active_board(context))
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}
        return {"FINISHED"}


class WBOARD_OT_new_seed(bpy.types.Operator):
    """Roll a new seed for the selected board and rebuild it"""

    bl_idname = "wboard.new_seed"
    bl_label = "New Seed"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_board(context) is not None

    def execute(self, context):
        obj = _active_board(context)
        from . import properties
        properties._suspended = True  # rebuild once below, not via live update
        try:
            obj.weathered_board.seed = _random_seed()
        finally:
            properties._suspended = False
        error = rebuild(obj)
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}
        return {"FINISHED"}


class WBOARD_OT_set_edges(bpy.types.Operator):
    """Set the rounding of a group of edges at once"""

    bl_idname = "wboard.set_edges"
    bl_label = "Set Edge Rounding"
    bl_options = {"REGISTER", "UNDO"}

    group: EnumProperty(
        name="Edges",
        items=[
            ("ALL", "All Edges", ""),
            ("LONG", "Long Edges", ""),
            ("END_A", "End A Edges", ""),
            ("END_B", "End B Edges", ""),
        ],
    )
    value: FloatProperty(name="Rounding", default=0.15, min=0.0, max=1.0, subtype="FACTOR")
    target: StringProperty(default="SCENE", options={"HIDDEN"})

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = _active_board(context)
        settings = obj.weathered_board if (self.target == "OBJECT" and obj) else context.scene.weathered_board
        from . import properties
        properties._suspended = True  # one rebuild for the group, not four
        try:
            for edge in EDGE_GROUPS[self.group]:
                setattr(settings, f"round_{edge}", self.value)
        finally:
            properties._suspended = False
        if self.target == "OBJECT" and obj is not None and context.scene.weathered_board.live_update:
            rebuild(obj)
        return {"FINISHED"}


class WBOARD_OT_export_stl(bpy.types.Operator, ExportHelper):
    """Export the selected boards as STL in millimetres"""

    bl_idname = "wboard.export_stl"
    bl_label = "Export STL"
    filename_ext = ".stl"
    filter_glob: StringProperty(default="*.stl", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return any(o.weathered_board.is_board for o in context.selected_objects)

    def execute(self, context):
        mesh_io.set_scene_millimetres(context.scene)
        bpy.ops.wm.stl_export(
            filepath=self.filepath,
            export_selected_objects=True,
            global_scale=1.0,
            apply_modifiers=True,
        )
        self.report({"INFO"}, f"Exported {self.filepath}")
        return {"FINISHED"}


classes = (
    WBOARD_OT_add,
    WBOARD_OT_regenerate,
    WBOARD_OT_new_seed,
    WBOARD_OT_set_edges,
    WBOARD_OT_export_stl,
)
