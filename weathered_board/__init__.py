"""Weathered Board: generate weathered wooden boards for 3D printing.

Blender 4.2+ extension. The geometry lives in ``core/`` (pure numpy, no
bpy); this package adds the properties, operators and sidebar panel.
"""

import bpy

from . import operators, properties, ui_panel

_classes = (
    (properties.WBOARD_Settings,)
    + operators.classes
    + ui_panel.classes
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    properties.register()
    bpy.types.VIEW3D_MT_mesh_add.append(ui_panel.draw_add_menu)


def unregister():
    bpy.types.VIEW3D_MT_mesh_add.remove(ui_panel.draw_add_menu)
    if bpy.app.timers.is_registered(properties._flush_pending):
        bpy.app.timers.unregister(properties._flush_pending)
    properties.unregister()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
