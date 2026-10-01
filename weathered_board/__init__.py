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
    """Register the add-on with Blender.

    Registers the settings, operators and panels, attaches the settings to
    every Scene and Object, and adds Weathered Board to the Add > Mesh menu.
    Blender calls this when the extension is enabled.
    """
    for cls in _classes:
        bpy.utils.register_class(cls)
    properties.register()
    bpy.types.VIEW3D_MT_mesh_add.append(ui_panel.draw_add_menu)


def unregister():
    """Undo everything ``register`` did, in reverse order.

    Also cancels a pending live-update rebuild, so no timer fires into an
    add-on that is no longer loaded. Blender calls this when the extension
    is disabled or uninstalled.
    """
    bpy.types.VIEW3D_MT_mesh_add.remove(ui_panel.draw_add_menu)
    if bpy.app.timers.is_registered(properties._flush_pending):
        bpy.app.timers.unregister(properties._flush_pending)
    properties.unregister()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
