"""Operators: the buttons in the Weathered Board panel.

Add, Regenerate, New Seed, the edge-group buttons, Check Printability and
Export STL. Each operator's docstring is the tooltip Blender shows for its
button. ``rebuild`` is shared with live update in properties.py, and the
object-level printability checks (open edges, self-intersections, real
size) live here because they need Blender's mesh tools.
"""

import os

import bmesh
import bpy
import numpy as np
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ExportHelper
from mathutils.bvhtree import BVHTree

from . import mesh_io
from .core import ParamError, build, check
from .core import printcheck
from .core.printcheck import ERROR, INFO, OK, WARNING, Finding
from .core.params import EDGE_GROUPS

SEED_MAX = 2**31 - 1


def _random_seed() -> int:
    """A fresh seed for a new board: a random positive 31-bit integer.

    Blender integer properties are signed 32-bit, so seeds stay below 2**31.
    """
    return int(np.random.default_rng().integers(1, SEED_MAX))


def _active_board(context):
    """The active object if it is a weathered board, otherwise None.

    Operators that act on one board (Regenerate, New Seed) use this both in
    ``poll``, to grey out their button, and in ``execute``.
    """
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
    mesh_io.apply_simplify(obj)
    settings.last_error = ""
    settings.check_report = ""  # any earlier check no longer applies
    return ""


# --------------------------------------------------------------------------
# Printability
# --------------------------------------------------------------------------

SIZE_TOLERANCE = 0.005  # 0.5%


def object_findings(obj, params) -> list[Finding]:
    """Checks on the board as it actually is in the scene.

    It may have been edited, scaled or rotated since it was built.
    """
    out: list[Finding] = []
    bm = bmesh.new()
    try:
        # The mesh as it will export: with the Simplify modifier, if any.
        depsgraph = bpy.context.evaluated_depsgraph_get()
        bm.from_object(obj, depsgraph)
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

        n = len(bm.faces)
        simplified = obj.modifiers.get(mesh_io.SIMPLIFY_MODIFIER) is not None
        note = " (simplified)" if simplified else ""
        if n > printcheck.MAX_TRIANGLES:
            out.append(Finding(WARNING, "Heavy mesh",
                               f"{n:,} triangles; some slicers slow down. Turn on Simplify Mesh"))
        else:
            out.append(Finding(OK, "Mesh size", f"{n:,} triangles{note}"))
    finally:
        bm.free()
    return out


def run_checks(obj) -> list[Finding]:
    """All printability findings for one board."""
    params = obj.weathered_board.to_params()
    findings = object_findings(obj, params)
    # The core checks rebuild the board from its settings; the object
    # checks above already cover the mesh actually in the scene (shape,
    # watertightness and, after any simplifying, its size).
    skip = {"Watertight", "Mesh size", "Heavy mesh"}
    findings += [f for f in check(params) if f.title not in skip]
    return findings


def store_report(obj, findings: list[Finding]) -> None:
    """Save printability findings on the board so the panel can show them.

    Stored as one finding per line, ``LEVEL<tab>title<tab>detail``, in the
    board's hidden ``check_report`` property. A rebuild clears it.
    """
    obj.weathered_board.check_report = "\n".join(
        f"{f.level}\t{f.title}\t{f.detail}" for f in findings)


def worst(findings: list[Finding]) -> str:
    """The most serious level among ``findings``: ERROR, WARNING, INFO or OK.

    Used to summarise several boards' checks in one status-bar message.
    """
    for level in (ERROR, WARNING, INFO):
        if any(f.level == level for f in findings):
            return level
    return OK


class WBOARD_OT_add(bpy.types.Operator):
    """Add a new weathered board (or Count boards) at the 3D cursor, using the settings in this panel and a random seed unless Lock Seed is on"""

    bl_idname = "wboard.add"
    bl_label = "Add Weathered Board"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        """Build ``count`` boards from the scene's settings and add them.

        Each board gets its own seed (consecutive from a random start, or from
        the locked seed), its own copy of the settings, and a place beside the
        previous one along Y. Sets the scene to millimetres so exports come out
        the right size. Stops at the first board that fails to build and reports
        why.
        """
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
            mesh_io.apply_simplify(obj)
            # Lay boards out side by side along Y.
            width = float(np.ptp(verts[:, 1]))
            obj.location = context.scene.cursor.location.copy()
            obj.location.y += gap
            gap += width * 1.5
            obj.select_set(True)
            context.view_layer.objects.active = obj
        return {"FINISHED"}


class WBOARD_OT_regenerate(bpy.types.Operator):
    """Rebuild the selected board from its current settings. Keeps its seed, so only the settings you changed make a difference"""

    bl_idname = "wboard.regenerate"
    bl_label = "Regenerate"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        """Only available when the active object is a weathered board."""
        return _active_board(context) is not None

    def execute(self, context):
        """Rebuild the active board, reporting any build error."""
        error = rebuild(_active_board(context))
        if error:
            self.report({"ERROR"}, error)
            return {"CANCELLED"}
        return {"FINISHED"}


class WBOARD_OT_new_seed(bpy.types.Operator):
    """Give the selected board a new random seed and rebuild it: same settings, a different grain, knots and cracks"""

    bl_idname = "wboard.new_seed"
    bl_label = "New Seed"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        """Only available when the active object is a weathered board."""
        return _active_board(context) is not None

    def execute(self, context):
        """Give the active board a new random seed and rebuild it once.

        Live update is suspended while the seed changes, so the board is not
        rebuilt twice (once by the timer and once here).
        """
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
    """Set the rounding of a group of edges at once. Each edge can still be adjusted on its own afterwards"""

    bl_idname = "wboard.set_edges"
    bl_label = "Set Edge Rounding"
    bl_options = {"REGISTER", "UNDO"}

    group: EnumProperty(
        name="Edges",
        description="Which edges to set",
        items=[
            ("ALL", "All Edges", "All 12 edges"),
            ("LONG", "Long Edges", "The 4 edges that run the length of the board"),
            ("END_A", "End A Edges", "The 4 edges around end A (the left end)"),
            ("END_B", "End B Edges", "The 4 edges around end B (the right end)"),
        ],
    )
    value: FloatProperty(
        name="Rounding", default=0.15, min=0.0, max=1.0, subtype="FACTOR",
        description="0 = sharp corner, 1 = as round as the board allows",
    )
    target: StringProperty(default="SCENE", options={"HIDDEN"})

    GROUP_HELP = {
        "ALL": "Set the rounding of all 12 edges at once",
        "LONG": "Set the rounding of the 4 edges that run the length of the board",
        "END_A": "Set the rounding of the 4 edges around end A (the left end)",
        "END_B": "Set the rounding of the 4 edges around end B (the right end)",
    }

    @classmethod
    def description(cls, context, properties):
        """A tooltip for each of the All / Long / End A / End B buttons."""
        return cls.GROUP_HELP.get(properties.group, cls.__doc__) + \
            ". Each edge can still be adjusted on its own afterwards"

    def invoke(self, context, event):
        """Ask for the rounding value in a small pop-up before applying it."""
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        """Set every edge in the chosen group to the chosen rounding.

        Acts on the selected board's settings (``target`` = OBJECT) or on the
        settings for new boards (SCENE). Live update is suspended while the four
        or twelve values change, then the board is rebuilt once.
        """
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
    """Check the selected boards for printing problems: holes, crossing surfaces, size, ring detail, carving depth, wall thickness and mesh size. Results are listed below"""

    bl_idname = "wboard.check"
    bl_label = "Check Printability"

    @classmethod
    def poll(cls, context):
        """Only available when at least one selected object is a weathered board."""
        return any(o.weathered_board.is_board for o in context.selected_objects)

    def execute(self, context):
        """Check every selected board and store the findings on each.

        The findings appear in the Printing panel. One message in the status bar
        sums up the worst result across all the boards checked.
        """
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
    """Export the selected boards as STL files in millimetres, ready for a slicer or FreeCAD"""

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
        """Only available when at least one selected object is a weathered board."""
        return any(o.weathered_board.is_board for o in context.selected_objects)

    def execute(self, context):
        """Write the selected boards to STL, in millimetres.

        All boards go into the chosen file, or with ``one_file_per_board`` each
        goes into its own file: the chosen name plus ``_<board name>``, with any
        character a file name can't hold replaced by ``_``. Only boards are
        exported, even if other objects are selected too.
        """
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
