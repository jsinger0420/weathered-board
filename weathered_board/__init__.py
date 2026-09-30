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


def unregister():
    properties.unregister()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
