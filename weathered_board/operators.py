"""Operators: add, regenerate, reseed, set edge groups, export STL."""

import os

import bmesh
import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ExportHelper
from mathutils.bvhtree import BVHTree

from . import mesh_io
from .core import ParamError, build, check
from .core.printcheck import ERROR, INFO, OK, WARNING, Finding
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
    settings.check_report = ""  # any earlier check no longer applies
    return ""


# --------------------------------------------------------------------------
# Printability
# --------------------------------------------------------------------------

SIZE_TOLERANCE = 0.005  # 0.5%


def object_findings(obj, params) -> list[Finding]:
    """Checks on the board as it actually is in the scene, which may have
    been edited, scaled or rotated since it was built."""
    out: list[Finding] = []
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.transform(obj.matrix_world)
        bm.verts.ensure_lookup_table()
        bad_edges = sum(1 for e in bm.edges if not e.is_manifold)
        if bad_edges:
            out.append(Finding(ERROR, "Open edges", f"{bad_edges} edges are not shared by exactly two faces"))
        else:
            out.append(Finding(OK, "Watertight", "Every edge joins exactly two faces"))

        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        tree = BVHTree.FromBMesh(bm)
        bm.faces.ensure_lookup_table()
        faces = bm.faces
        crossing = 0
        for a, b in tree.overlap(tree):
            # Triangles that only touch at a shared corner are not crossing.
            if {v.index for v in faces[a].verts} & {v.index for v in faces[b].verts}:
                continue
            crossing += 1
        if crossing:
            out.append(Finding(ERROR, "Self-intersections", f"{crossing} pairs of triangles cross each other"))
        else:
            out.append(Finding(OK, "No self-intersections"))

        co = np.array([v.co[:] for v in bm.verts]) if len(bm.verts) else np.zeros((1, 3))
        size = co.max(axis=0) - co.min(axis=0)
        expected = np.array(params.size) / params.scale
        text = " x ".join(f"{d:.2f}" for d in size)
        if np.allclose(np.sort(size), np.sort(expected), rtol=SIZE_TOLERANCE):
            out.append(Finding(OK, "Printed size", f"{text} mm"))
        else:
            want = " x ".join(f"{d:.2f}" for d in expected)
            out.append(Finding(WARNING, "Size differs from settings",
                               f"Prints {text} mm; settings give {want} mm (object scaled or edited?)"))
    finally:
        bm.free()
    return out


def run_checks(obj) -> list[Finding]:
    """All printability findings for one board."""
    params = obj.weathered_board.to_params()
    findings = object_findings(obj, params)
    # The core checks rebuild the board from its settings; the object
    # checks above already cover watertightness of what is in the scene.
    findings += [f for f in check(params) if f.title != "Watertight"]
    return findings


def store_report(obj, findings: list[Finding]) -> None:
    obj.weathered_board.check_report = "\n".join(
        f"{f.level}\t{f.title}\t{f.detail}" for f in findings)


def worst(findings: list[Finding]) -> str:
    for level in (ERROR, WARNING, INFO):
        if any(f.level == level for f in findings):
            return level
    return OK


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


class WBOARD_OT_check(bpy.types.Operator):
    """Check the selected boards for printing problems"""

    bl_idname = "wboard.check"
    bl_label = "Check Printability"

    @classmethod
    def poll(cls, context):
        return any(o.weathered_board.is_board for o in context.selected_objects)

    def execute(self, context):
        boards = [o for o in context.selected_objects if o.weathered_board.is_board]
        summary = {OK: 0, INFO: 0, WARNING: 0, ERROR: 0}
        for obj in boards:
            try:
                findings = run_checks(obj)
            except ParamError as err:
                findings = [Finding(ERROR, "Settings", str(err))]
            store_report(obj, findings)
            summary[worst(findings)] += 1
        n = len(boards)
        if summary[ERROR]:
            self.report({"ERROR"}, f"{summary[ERROR]} of {n} boards have problems; see the Printing panel")
        elif summary[WARNING]:
            self.report({"WARNING"}, f"{summary[WARNING]} of {n} boards have warnings; see the Printing panel")
        else:
            self.report({"INFO"}, f"{n} board{'s' if n > 1 else ''} ready to print")
        return {"FINISHED"}


class WBOARD_OT_export_stl(bpy.types.Operator, ExportHelper):
    """Export the selected boards as STL in millimetres"""

    bl_idname = "wboard.export_stl"
    bl_label = "Export STL"
    filename_ext = ".stl"
    filter_glob: StringProperty(default="*.stl", options={"HIDDEN"})
    one_file_per_board: BoolProperty(
        name="One File per Board",
        description="Write each board to its own file, named after the file "
                    "name chosen plus the board's name",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return any(o.weathered_board.is_board for o in context.selected_objects)

    def execute(self, context):
        mesh_io.set_scene_millimetres(context.scene)
        boards = [o for o in context.selected_objects if o.weathered_board.is_board]
        if not self.one_file_per_board:
            self._export(context, boards, self.filepath)
            self.report({"INFO"}, f"Exported {len(boards)} board(s) to {self.filepath}")
            return {"FINISHED"}
        stem, ext = os.path.splitext(self.filepath)
        written = []
        for obj in boards:
            safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in obj.name)
            path = f"{stem}_{safe}{ext}"
            self._export(context, [obj], path)
            written.append(path)
        self.report({"INFO"}, f"Exported {len(written)} files next to {self.filepath}")
        return {"FINISHED"}

    @staticmethod
    def _export(context, objects, path):
        """Export exactly ``objects``, restoring the selection afterwards."""
        before = list(context.selected_objects)
        active = context.view_layer.objects.active
        for o in before:
            o.select_set(False)
        for o in objects:
            o.select_set(True)
        try:
            bpy.ops.wm.stl_export(
                filepath=path,
                export_selected_objects=True,
                global_scale=1.0,
                apply_modifiers=True,
            )
        finally:
            for o in objects:
                o.select_set(False)
            for o in before:
                o.select_set(True)
            context.view_layer.objects.active = active


classes = (
    WBOARD_OT_add,
    WBOARD_OT_regenerate,
    WBOARD_OT_new_seed,
    WBOARD_OT_set_edges,
    WBOARD_OT_check,
    WBOARD_OT_export_stl,
)
