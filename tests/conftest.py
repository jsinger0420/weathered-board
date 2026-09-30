"""Make the add-on's ``core`` package importable without Blender.

``weathered_board/__init__.py`` imports bpy, so core tests import ``core``
directly from inside the add-on folder instead of through the package.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "weathered_board"))
