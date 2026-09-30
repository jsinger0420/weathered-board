"""Move numpy arrays from the core into Blender meshes."""

import bpy
import numpy as np


def set_scene_millimetres(scene: bpy.types.Scene) -> None:
    """1 Blender unit = 1 mm, so STL files come out in millimetres."""
    us = scene.unit_settings
    us.system = "METRIC"
    us.length_unit = "MILLIMETERS"
    us.scale_length = 0.001


def fill_mesh(mesh: bpy.types.Mesh, verts: np.ndarray, tris: np.ndarray) -> None:
    """Write triangles into an empty mesh with foreach_set (fast for dense meshes)."""
    n_verts, n_tris = len(verts), len(tris)
    mesh.vertices.add(n_verts)
    mesh.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    mesh.loops.add(n_tris * 3)
    mesh.loops.foreach_set("vertex_index", tris.astype(np.int32).ravel())
    mesh.polygons.add(n_tris)
    mesh.polygons.foreach_set("loop_start", np.arange(0, n_tris * 3, 3, dtype=np.int32))
    mesh.update()
    mesh.validate()


def new_board_object(context, name: str, verts: np.ndarray, tris: np.ndarray) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    fill_mesh(mesh, verts, tris)
    obj = bpy.data.objects.new(name, mesh)
    context.collection.objects.link(obj)
    return obj


def replace_mesh(obj: bpy.types.Object, verts: np.ndarray, tris: np.ndarray) -> None:
    """Give an existing board a freshly built mesh, dropping the old one."""
    old = obj.data
    mesh = bpy.data.meshes.new(old.name)
    fill_mesh(mesh, verts, tris)
    obj.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)
