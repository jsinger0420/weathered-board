"""Move numpy arrays from the core into Blender meshes."""

import bpy
import numpy as np

PATTERN_ATTRIBUTE = "WB_Pattern"


def set_scene_millimetres(scene: bpy.types.Scene) -> None:
    """1 Blender unit = 1 mm, so STL files come out in millimetres."""
    us = scene.unit_settings
    us.system = "METRIC"
    us.length_unit = "MILLIMETERS"
    us.scale_length = 0.001


def fill_mesh(mesh: bpy.types.Mesh, verts: np.ndarray, tris: np.ndarray,
              colors: np.ndarray | None = None) -> None:
    """Write triangles, and optional per-vertex colours, into an empty mesh.

    Uses foreach_set, which is fast for dense meshes.
    """
    n_verts, n_tris = len(verts), len(tris)
    mesh.vertices.add(n_verts)
    mesh.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    mesh.loops.add(n_tris * 3)
    mesh.loops.foreach_set("vertex_index", tris.astype(np.int32).ravel())
    mesh.polygons.add(n_tris)
    mesh.polygons.foreach_set("loop_start", np.arange(0, n_tris * 3, 3, dtype=np.int32))
    # Smooth shading so the rounded edges look round in the viewport
    # (has no effect on the exported STL).
    mesh.polygons.foreach_set("use_smooth", np.ones(n_tris, dtype=bool))
    mesh.update()
    mesh.validate()
    if colors is not None:
        set_colors(mesh, colors)


def set_colors(mesh: bpy.types.Mesh, colors: np.ndarray) -> None:
    """Store the ring-pattern preview as the mesh's active colour attribute."""
    attr = mesh.color_attributes.get(PATTERN_ATTRIBUTE)
    if attr is None:
        attr = mesh.color_attributes.new(PATTERN_ATTRIBUTE, "FLOAT_COLOR", "POINT")
    rgba = np.ones((len(colors), 4), dtype=np.float32)
    rgba[:, :3] = colors
    attr.data.foreach_set("color", rgba.ravel())
    mesh.color_attributes.active_color = attr
    mesh.color_attributes.render_color_index = mesh.color_attributes.active_color_index


def new_board_object(context, name: str, verts: np.ndarray, tris: np.ndarray,
                     colors: np.ndarray | None = None) -> bpy.types.Object:
    """Create a new mesh object from board arrays and link it into the scene.

    ``verts`` are printed-millimetre positions, ``tris`` triangle indices and
    ``colors`` an optional per-vertex pattern preview. The object is linked
    into the active collection; the caller names, places and selects it.
    """
    mesh = bpy.data.meshes.new(name)
    fill_mesh(mesh, verts, tris, colors)
    obj = bpy.data.objects.new(name, mesh)
    context.collection.objects.link(obj)
    return obj


def replace_mesh(obj: bpy.types.Object, verts: np.ndarray, tris: np.ndarray,
                 colors: np.ndarray | None = None) -> None:
    """Give an existing board a freshly built mesh, dropping the old one.

    Materials on the board are carried over.
    """
    old = obj.data
    mesh = bpy.data.meshes.new(old.name)
    fill_mesh(mesh, verts, tris, colors)
    for mat in old.materials:
        mesh.materials.append(mat)
    obj.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)


SIMPLIFY_MODIFIER = "WB Simplify"


def apply_simplify(obj: bpy.types.Object) -> None:
    """Add, update or remove the board's Simplify modifier to match its settings.

    With Simplify Mesh on, a Decimate (collapse) modifier brings the board
    down to about Max Triangles. The full-detail mesh stays underneath, so
    turning Simplify off, or raising Max Triangles, needs no rebuild.
    Export STL and Check Printability use the simplified mesh. On an 8 ft
    1x6 at 1:48 (370,000 triangles in full), 20,000 triangles keeps every
    point within about 0.009 mm of the full mesh and 10,000 within 0.015 mm:
    the grain runs along the board, so long thin triangles can follow it.
    """
    settings = obj.weathered_board
    mod = obj.modifiers.get(SIMPLIFY_MODIFIER)
    full = len(obj.data.polygons)
    if not settings.simplify or full <= settings.max_triangles:
        if mod is not None:
            obj.modifiers.remove(mod)
        return
    if mod is None:
        mod = obj.modifiers.new(SIMPLIFY_MODIFIER, "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.use_collapse_triangulate = True
    mod.ratio = settings.max_triangles / full

